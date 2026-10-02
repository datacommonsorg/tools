# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Content-free operational telemetry for the chat pipeline.

This module records what the Architecture document's telemetry contract
(section 4.5) allows and nothing else: per-phase spans and durations, token
counts, MCP tool-loop iteration counts, tool names, and the terminal state of
each turn. It never records prompts, responses, tool arguments, raw MCP
payloads, session or user identifiers, or client IP addresses.

This module writes two streams of output, each formatted as one JSON object
per line on stdout so Cloud Logging parses every line as a structured entry.
The first stream consists of OpenTelemetry spans from the FastAPI, httpx, and
google-genai instrumentations and from `TurnTelemetry`. Spans are serialized by
`format_span`, which keeps only allowlisted attribute keys so that an
instrumentation that records a URL, a client address, or message text cannot
leak it regardless of its own configuration. The second stream consists of one
summary record per chat turn, written by `TurnTelemetry.finish`.

Content capture on the google-genai instrumentation is also switched off at
its source by `configure_telemetry`, so message text is never collected in
the first place.
"""

import json
import logging
import os
import sys
import time
import uuid
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.google_genai import (
    GoogleGenAiSdkInstrumentor,
)
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.trace import StatusCode
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
    OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK,
    OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT,
)

SERVICE_NAME = "narratives-agent"

type TerminalState = Literal["complete", "error", "refused", "canceled"]

# `_ALLOWED_SPAN_ATTRIBUTES` lists the span attributes permitted to leave the
# process. `format_span` drops all other attributes, including URLs, query
# strings, client and peer addresses, user agents, and any message or tool
# content recorded by an instrumentation.
_ALLOWED_SPAN_ATTRIBUTES = frozenset(
    {
        "error.type",
        "gen_ai.operation.name",
        "gen_ai.provider.name",
        "gen_ai.request.model",
        "gen_ai.response.finish_reasons",
        "gen_ai.response.model",
        "gen_ai.system",
        "gen_ai.usage.input_tokens",
        "gen_ai.usage.output_tokens",
        "http.method",
        "http.request.method",
        "http.response.status_code",
        "http.route",
        "http.status_code",
    }
)
# Attributes set directly by this module use this prefix and are content-free
# by construction.
_OWN_ATTRIBUTE_PREFIX = "narratives."

# Span timestamps are in nanoseconds; durations are reported in milliseconds.
_NANOSECONDS_PER_MILLISECOND = 1_000_000
_MILLISECONDS_PER_SECOND = 1000

_tracer = trace.get_tracer(__name__)

# `_turn_logger` emits the per-turn summary as a bare JSON line. A formatter
# that prepends a timestamp or level would make Cloud Logging treat the line as
# plain text, so this logger has its own handler and does not propagate to the
# root logger's formatter.
_turn_logger = logging.getLogger(f"{__name__}.turns")
_turn_logger.propagate = False

# `GoogleGenAiSdkInstrumentor` is a singleton whose constructor discards the
# state `uninstrument` needs, so the process constructs it exactly once.
_genai_instrumentor = GoogleGenAiSdkInstrumentor()

# `configure_telemetry` installs a global tracer provider and global
# instrumentation, which must happen once per process.
_configured: dict[str, bool] = {}


def _span_attributes(span: ReadableSpan) -> dict[str, Any]:
    """Returns the allowlisted attributes of `span`."""
    return {
        key: value
        for key, value in (span.attributes or {}).items()
        if key in _ALLOWED_SPAN_ATTRIBUTES
        or key.startswith(_OWN_ATTRIBUTE_PREFIX)
    }


def format_span(span: ReadableSpan) -> str:
    """Serializes `span` as one content-free JSON line.

    Span events are omitted entirely, because the google-genai
    instrumentation can attach message content to them.
    """
    context = span.get_span_context()
    start = span.start_time or 0
    end = span.end_time or start
    record = {
        "severity": "ERROR"
        if span.status.status_code.name == "ERROR"
        else "INFO",
        "message": f"span {span.name}",
        "span_name": span.name,
        "trace_id": f"{context.trace_id:032x}" if context else "",
        "span_id": f"{context.span_id:016x}" if context else "",
        "parent_span_id": f"{span.parent.span_id:016x}" if span.parent else "",
        "duration_ms": round((end - start) / _NANOSECONDS_PER_MILLISECOND, 2),
        "status": span.status.status_code.name,
        "attributes": _span_attributes(span),
    }
    return json.dumps(record, default=str) + "\n"


def _write_stdout_line(line: str) -> None:
    """Writes `line` to the current `sys.stdout`.

    `sys.stdout` is looked up on every write rather than bound once, because
    the span exporter runs on a background thread for the life of the
    process and the stream it was handed may since have been replaced (as a
    test runner does) or closed.
    """
    sys.stdout.write(line)
    sys.stdout.flush()


class _StdoutSpanExporter(SpanExporter):
    """Exports spans to stdout as content-free JSON lines."""

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """Writes one `format_span` line per span."""
        for span in spans:
            _write_stdout_line(format_span(span))
        return SpanExportResult.SUCCESS


class _StdoutLineHandler(logging.Handler):
    """Writes each log record's bare message as one stdout line."""

    def emit(self, record: logging.LogRecord) -> None:
        """Writes the record's message followed by a newline."""
        try:
            _write_stdout_line(record.getMessage() + "\n")
        # A logging handler must not propagate exceptions to the caller; this
        # mirrors `logging.StreamHandler.emit`.
        except Exception:
            self.handleError(record)


def _disable_genai_content_capture() -> None:
    """Forces the google-genai instrumentation to record no message content.

    The variables are overwritten rather than defaulted, so a deployment
    cannot opt into content capture through its environment. A completion
    hook also enables content capture, so any configured hook is removed.
    """
    os.environ[OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT] = (
        "NO_CONTENT"
    )
    os.environ[OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT] = "false"
    os.environ.pop(OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK, None)


def configure_telemetry() -> None:
    """Installs the tracer provider and the httpx and google-genai hooks.

    This function is idempotent; only the first call has an effect.
    """
    if _configured.get("done"):
        return
    _configured["done"] = True
    _disable_genai_content_capture()

    _turn_logger.addHandler(_StdoutLineHandler())
    _turn_logger.setLevel(logging.INFO)

    provider = TracerProvider(
        resource=Resource.create({"service.name": SERVICE_NAME})
    )
    provider.add_span_processor(BatchSpanProcessor(_StdoutSpanExporter()))
    trace.set_tracer_provider(provider)
    # The httpx instrumentation covers the google-genai SDK's transport. The
    # MCP client and the data-plane proxy use `httpx2`, which it does not
    # patch; their latency is captured by the phase spans instead.
    HTTPXClientInstrumentor().instrument()
    _genai_instrumentor.instrument()


def instrument_app(
    app: FastAPI, tracer_provider: trace.TracerProvider | None = None
) -> None:
    """Adds one request span per HTTP request to `app`.

    This function must run before the application starts because it installs
    middleware. Per-message ASGI `send` and `receive` spans are excluded
    because a streamed chat turn sends one message per SSE frame and
    heartbeat, which would generate hundreds of redundant spans per turn.

    Args:
        app: The application to instrument.
        tracer_provider: The provider that receives the spans, or the global
            provider when `None`.
    """
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=tracer_provider,
        exclude_spans=["send", "receive"],
    )


@dataclass
class TokenUsage:
    """Accumulates Gemini token counts across all model calls in a turn."""

    prompt_token_count: int = 0
    candidates_token_count: int = 0
    thoughts_token_count: int = 0
    total_token_count: int = 0

    def add(self, usage: Mapping[str, int] | None) -> None:
        """Adds one call's REST-shaped `usageMetadata` to the totals."""
        if not usage:
            return
        self.prompt_token_count += usage.get("promptTokenCount", 0)
        self.candidates_token_count += usage.get("candidatesTokenCount", 0)
        self.thoughts_token_count += usage.get("thoughtsTokenCount", 0)
        self.total_token_count += usage.get("totalTokenCount", 0)


def _elapsed_ms(start: float) -> float:
    """Returns the milliseconds elapsed since a `time.monotonic()` timestamp."""
    return round((time.monotonic() - start) * _MILLISECONDS_PER_SECOND, 2)


@dataclass
class TurnTelemetry:
    """Collects the operational record of one chat turn.

    `turn_id` is a server-minted correlation ID scoped to this turn. It is
    never accepted from the client and never reused across turns.

    Phase spans are parented to the turn span explicitly instead of being
    made current so that the span tree does not depend on which task or
    context executes a phase; attaching a context in one task and detaching
    it in another raises a ValueError.
    """

    turn_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    tokens: TokenUsage = field(default_factory=TokenUsage)
    tool_calls: Counter[str] = field(default_factory=Counter)
    mcp_iterations: int = 0
    phase_durations_ms: dict[str, float] = field(default_factory=dict)
    _start: float = field(default_factory=time.monotonic)
    _span: trace.Span = field(
        default_factory=lambda: _tracer.start_span("narratives.turn")
    )
    _finished: bool = False

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        """Records a span and a duration for one pipeline phase."""
        start = time.monotonic()
        span = _tracer.start_span(
            f"narratives.phase.{name}",
            context=trace.set_span_in_context(self._span),
        )
        try:
            yield
        finally:
            self.phase_durations_ms[name] = _elapsed_ms(start)
            span.end()

    def record_tool_call(self, name: str) -> None:
        """Counts one MCP tool call by tool name."""
        self.tool_calls[name] += 1

    def finish(
        self, state: TerminalState, error_type: str | None = None
    ) -> None:
        """Ends the turn span and emits the turn summary.

        Only the first call has an effect, so the terminal state recorded is
        the one reached first.

        Args:
            state: The terminal state the turn reached.
            error_type: A short machine-readable reason for `error` and
                `refused` states. It must not contain user content.
        """
        if self._finished:
            return
        self._finished = True
        duration_ms = _elapsed_ms(self._start)
        record: dict[str, Any] = {
            "severity": "ERROR" if state == "error" else "INFO",
            "message": f"chat turn {state}",
            "event": "chat_turn",
            "turn_id": self.turn_id,
            "terminal_state": state,
            "error_type": error_type,
            "duration_ms": duration_ms,
            "phase_durations_ms": self.phase_durations_ms,
            "mcp_iterations": self.mcp_iterations,
            "tool_call_count": sum(self.tool_calls.values()),
            "tool_calls": dict(self.tool_calls),
            "tokens": asdict(self.tokens),
        }
        self._span.set_attributes(
            {
                "narratives.turn_id": self.turn_id,
                "narratives.terminal_state": state,
                "narratives.mcp_iterations": self.mcp_iterations,
                "narratives.tool_call_count": record["tool_call_count"],
                "narratives.tool_names": sorted(self.tool_calls),
                **{
                    f"narratives.tokens.{key}": value
                    for key, value in asdict(self.tokens).items()
                },
            }
        )
        if error_type:
            self._span.set_attribute("error.type", error_type)
        # `format_span` derives severity from the span status, so an error
        # turn needs an ERROR status to be exported at the same severity as
        # its `chat_turn` record.
        if state == "error":
            self._span.set_status(StatusCode.ERROR)
        self._span.end()
        _turn_logger.info(json.dumps(record))
