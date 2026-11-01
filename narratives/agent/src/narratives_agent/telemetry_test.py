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
"""Tests for the content-free telemetry in `narratives_agent.telemetry`.

Verifies these behaviors in `telemetry`:
1. Content capture on the google-genai instrumentation is forced off, even
   when environment variables enable it.
2. A real instrumented Gemini call records neither the prompt nor the
   response in any span, before or after `format_span` serializes it.
3. `format_span` drops every attribute outside its allowlist.
4. A streamed request produces one request span, not one per ASGI message.
5. `TurnTelemetry` records phases, tool names, and token counts, and its
   summary carries no conversation content.
6. The stdout span exporter and the turn-summary log handler write to the
   current `sys.stdout`, and the handler does not raise when writing fails.
7. `flush_telemetry` writes spans still waiting in the batch processor, and
   does nothing before `configure_telemetry` has run.
8. `configure_telemetry` installs the provider, handler, and instrumentors
   once and is idempotent on subsequent calls.
"""

import io
import json
import logging
import os
import sys
import time
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from google import genai
from google.genai import types
from opentelemetry import trace
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExportResult,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import SpanKind
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
    OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK,
    OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT,
)
from opentelemetry.util.genai.types import ContentCapturingMode
from opentelemetry.util.genai.utils import get_content_capturing_mode

from narratives_agent import telemetry

_USER_QUERY = "What is the population of Secretville in 2021?"
_SYSTEM_PROMPT = "You are the confidential narratives system prompt."
_MODEL_RESPONSE = "Secretville had 12345 residents in 2021."


@pytest.fixture
def content_capture_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sets the environment variables that enable GenAI content capture."""
    monkeypatch.setenv(
        OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, "SPAN_AND_EVENT"
    )
    monkeypatch.setenv(OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT, "true")
    monkeypatch.setenv(OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK, "upload")


@pytest.mark.usefixtures("content_capture_requested")
def test_genai_content_capture_is_forced_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: The google-genai instrumentation is configured to capture no
    #   message content.
    # Situation: Environment variables enable span-and-event content capture
    #   and configure a completion hook.
    # Expectation: After `_disable_genai_content_capture`, the capturing mode
    #   is NO_CONTENT, events are off, and no completion hook is configured.
    telemetry._disable_genai_content_capture()

    assert get_content_capturing_mode() is ContentCapturingMode.NO_CONTENT
    assert os.environ[OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT] == ("false")
    assert OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK not in (os.environ)


@pytest.fixture
def instrumented_genai(
    content_capture_requested: None,
) -> Iterator[InMemorySpanExporter]:
    """Instruments google-genai with content capture disabled.

    Yields the exporter that receives every finished span. Another test may
    have instrumented the SDK already through `configure_telemetry`; that
    instrumentation is set aside for the test and restored afterward. The
    environment variables that `_disable_genai_content_capture` overwrites
    are first set through `content_capture_requested` so that `monkeypatch`
    restores them when the test ends.
    """
    telemetry._disable_genai_content_capture()
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    instrumentor = telemetry._genai_instrumentor
    was_instrumented = instrumentor.is_instrumented_by_opentelemetry
    if was_instrumented:
        instrumentor.uninstrument()
    instrumentor.instrument(tracer_provider=provider)
    yield exporter
    instrumentor.uninstrument()
    if was_instrumented:
        instrumentor.instrument()


def _make_gemini_response(request: httpx.Request) -> httpx.Response:
    """Answers every Gemini request with a fixed model response."""
    return httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [{"text": _MODEL_RESPONSE}],
                    },
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 7,
                "candidatesTokenCount": 9,
                "totalTokenCount": 16,
            },
        },
    )


@pytest.mark.asyncio
async def test_an_instrumented_gemini_call_records_no_content(
    instrumented_genai: InMemorySpanExporter,
) -> None:
    # Test: No prompt or response text reaches an exported span.
    # Situation: An async `generate_content` call with a user query and a
    #   system prompt runs through the real google-genai instrumentation,
    #   against a mock transport that returns a model response.
    # Expectation: The call produces at least one span; no span attribute
    #   or event contains the query, the system prompt, or the response; and
    #   the `format_span` output contains none of them either.
    client = genai.Client(
        api_key="test-key",
        http_options=types.HttpOptions(
            async_client_args={
                "transport": httpx.MockTransport(_make_gemini_response)
            }
        ),
    )

    response = await client.aio.models.generate_content(
        model="gemini-test",
        contents=_USER_QUERY,
        config=types.GenerateContentConfig(system_instruction=_SYSTEM_PROMPT),
    )

    assert response.text == _MODEL_RESPONSE
    spans = instrumented_genai.get_finished_spans()
    assert spans
    for span in spans:
        raw = json.dumps(
            {
                "attributes": dict(span.attributes or {}),
                "events": [
                    dict(event.attributes or {}) for event in span.events
                ],
            },
            default=str,
        )
        formatted = telemetry.format_span(span)
        for content in (_USER_QUERY, _SYSTEM_PROMPT, _MODEL_RESPONSE):
            assert content not in raw
            assert content not in formatted


def test_format_span_keeps_only_allowlisted_attributes() -> None:
    # Test: `format_span` drops attributes outside its allowlist.
    # Situation: A span carries a URL with a query string, a client address,
    #   a user agent, an allowlisted route, and a `narratives.` attribute.
    # Expectation: The serialized span keeps only the route and the
    #   `narratives.` attribute.
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    with provider.get_tracer(__name__).start_as_current_span("request") as s:
        s.set_attributes(
            {
                "url.full": f"https://agent.test/?q={_USER_QUERY}",
                "client.address": "203.0.113.7",
                "user_agent.original": "Mozilla/5.0",
                "http.route": "/agent/chat/stream",
                "narratives.turn_id": "turn-1",
            }
        )

    (span,) = exporter.get_finished_spans()
    record = json.loads(telemetry.format_span(span))

    assert record["attributes"] == {
        "http.route": "/agent/chat/stream",
        "narratives.turn_id": "turn-1",
    }


# `_STREAMED_CHUNKS` sets the number of body chunks sent by the streamed test
# route. Each chunk corresponds to one ASGI `send` message.
_STREAMED_CHUNKS = 5


def test_a_streamed_request_produces_one_request_span() -> None:
    # Test: ASGI per-message spans are excluded from request tracing.
    # Situation: An app instrumented with `instrument_app` serves a route
    #   that streams several body chunks, just as the chat route streams SSE
    #   frames.
    # Expectation: The request produces only the single server span for the
    #   request rather than additional spans for each `send` and `receive`.
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    app = FastAPI()

    @app.get("/stream")
    async def serve_stream() -> StreamingResponse:
        async def iter_chunks() -> AsyncIterator[bytes]:
            for _ in range(_STREAMED_CHUNKS):
                yield b"data: {}\n\n"

        return StreamingResponse(iter_chunks(), media_type="text/event-stream")

    telemetry.instrument_app(app, tracer_provider=provider)

    with TestClient(app) as client:
        response = client.get("/stream")

    assert response.status_code == 200
    assert response.content.count(b"data:") == _STREAMED_CHUNKS
    (span,) = exporter.get_finished_spans()
    assert span.kind is SpanKind.SERVER


class _RecordCollector(logging.Handler):
    """Collects the messages emitted on the turn logger."""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@pytest.fixture
def turn_records() -> Iterator[list[str]]:
    """Captures the JSON summaries `TurnTelemetry.finish` emits."""
    collector = _RecordCollector()
    logger = telemetry._turn_logger
    previous_level = logger.level
    logger.addHandler(collector)
    logger.setLevel(logging.INFO)
    yield collector.messages
    logger.removeHandler(collector)
    logger.setLevel(previous_level)


def test_turn_summary_records_operations_without_content(
    turn_records: list[str],
) -> None:
    # Test: The turn summary carries operational fields only.
    # Situation: A turn runs a discovery phase with two tool calls over
    #   three iterations, records the scripts and fetch counts of its
    #   analysis, adds token usage from two Gemini calls, and finishes
    #   `complete`; `finish` is then called again with `error`.
    # Expectation: Exactly one summary is emitted, with state `complete`, the
    #   phase duration, tool names and counts, the analysis counts, and
    #   summed tokens, and it contains no tool arguments or other content.
    turn = telemetry.TurnTelemetry()
    with turn.phase("discovery"):
        turn.mcp_iterations = 3
        turn.record_tool_call("search_indicators")
        turn.record_tool_call("fetch_observations")
    turn.scripts = ["rank_cohort", "summarize_distribution"]
    turn.tables_fetched = 2
    turn.total_rows_fetched = 1_200
    turn.processing_retries = 1
    turn.charts_emitted = 2
    turn.charts_rejected = 1
    turn.tokens.add(
        telemetry.TokenCounts(prompt=10, candidates=0, thoughts=0, total=15)
    )
    turn.tokens.add(
        telemetry.TokenCounts(prompt=0, candidates=4, thoughts=2, total=0)
    )

    turn.finish(telemetry.TerminalState.COMPLETE)
    turn.finish(telemetry.TerminalState.ERROR, "late_error")

    (message,) = turn_records
    record = json.loads(message)
    assert record["terminal_state"] == telemetry.TerminalState.COMPLETE
    assert record["turn_id"] == turn.turn_id
    assert set(record["phase_durations_ms"]) == {"discovery"}
    assert record["mcp_iterations"] == 3
    assert record["tool_calls"] == {
        "search_indicators": 1,
        "fetch_observations": 1,
    }
    assert record["scripts"] == ["rank_cohort", "summarize_distribution"]
    assert record["tables_fetched"] == 2
    assert record["total_rows_fetched"] == 1_200
    assert record["processing_retries"] == 1
    assert record["charts_emitted"] == 2
    assert record["charts_rejected"] == 1
    assert record["tokens"] == {
        "prompt_token_count": 10,
        "candidates_token_count": 4,
        "thoughts_token_count": 2,
        "total_token_count": 15,
    }
    assert set(record) == {
        "severity",
        "message",
        "event",
        "turn_id",
        "terminal_state",
        "error_type",
        "duration_ms",
        "phase_durations_ms",
        "mcp_iterations",
        "tool_call_count",
        "tool_calls",
        "tokens",
        "scripts",
        "tables_fetched",
        "total_rows_fetched",
        "processing_retries",
        "charts_emitted",
        "charts_rejected",
    }


def test_repeated_phases_accumulate_and_analysis_fields_reach_the_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Phase accumulation and the span attributes of the analysis.
    # Situation: The module tracer records spans in memory; a turn times
    #   the processing phase twice, as a retried specification does, with
    #   the clock advanced by 100 ms and then 50 ms, and records the
    #   analysis and chart counts before finishing.
    # Expectation: The processing duration is the sum of both runs, and
    #   the turn span carries the scripts and the five counts.
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(telemetry, "_tracer", provider.get_tracer(__name__))
    turn = telemetry.TurnTelemetry()
    readings = [0.0, 0.1, 0.0, 0.05]

    def read_clock() -> float:
        # The phase readings are consumed in order; `finish` reads the
        # clock afterwards and gets the last reading again.
        return readings.pop(0) if len(readings) > 1 else readings[0]

    monkeypatch.setattr(time, "monotonic", read_clock)
    for _ in range(2):
        with turn.phase("processing"):
            pass
    turn.scripts = ["analyze_timeseries"]
    turn.tables_fetched = 1
    turn.total_rows_fetched = 30
    turn.processing_retries = 1
    turn.charts_emitted = 1
    turn.charts_rejected = 2

    turn.finish(telemetry.TerminalState.COMPLETE)

    assert turn.phase_durations_ms == {"processing": 150.0}
    (span,) = [
        span
        for span in exporter.get_finished_spans()
        if span.name == "narratives.turn"
    ]
    attributes = dict(span.attributes or {})
    assert attributes["narratives.scripts"] == ("analyze_timeseries",)
    assert attributes["narratives.tables_fetched"] == 1
    assert attributes["narratives.total_rows_fetched"] == 30
    assert attributes["narratives.processing_retries"] == 1
    assert attributes["narratives.charts_emitted"] == 1
    assert attributes["narratives.charts_rejected"] == 2


@pytest.mark.parametrize(
    ("state", "error_type", "severity"),
    [
        (
            telemetry.TerminalState.ERROR,
            telemetry.ErrorType.MCP_TIMEOUT,
            "ERROR",
        ),
        (telemetry.TerminalState.COMPLETE, None, "INFO"),
    ],
)
def test_turn_span_severity_matches_the_terminal_state(
    monkeypatch: pytest.MonkeyPatch,
    turn_records: list[str],
    state: telemetry.TerminalState,
    error_type: str | None,
    severity: str,
) -> None:
    # Test: The exported turn span has the same severity as the turn summary.
    # Situation: The module tracer is replaced with one that records spans
    #   in memory, and a turn finishes in the parametrized state.
    # Expectation: The serialized turn span and the `chat_turn` record both
    #   report the expected severity.
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(telemetry, "_tracer", provider.get_tracer(__name__))

    telemetry.TurnTelemetry().finish(state, error_type)

    (span,) = exporter.get_finished_spans()
    assert json.loads(telemetry.format_span(span))["severity"] == severity
    (message,) = turn_records
    assert json.loads(message)["severity"] == severity


def test_the_pattern_is_recorded_only_when_the_classifier_assigned_one(
    monkeypatch: pytest.MonkeyPatch, turn_records: list[str]
) -> None:
    # Test: The `pattern` field of the turn summary and span.
    # Situation: One turn is classified as `trend_delta` and completes; a
    #   second turn is refused as `off_domain` before any classification is
    #   assigned; a third turn is classified as `single_point` and later
    #   refused as `safety_blocked`.
    # Expectation: The first summary and span carry `pattern` and the classify
    #   phase duration; both refused turns omit `pattern` from the summary and
    #   `narratives.pattern` from the span while recording their refusal
    #   reasons in `error_type`.
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(telemetry, "_tracer", provider.get_tracer(__name__))

    classified = telemetry.TurnTelemetry()
    with classified.phase("classify"):
        classified.pattern = "trend_delta"
    classified.finish(telemetry.TerminalState.COMPLETE)
    telemetry.TurnTelemetry().finish(
        telemetry.TerminalState.REFUSED, "off_domain"
    )
    later_refused = telemetry.TurnTelemetry()
    later_refused.pattern = "single_point"
    later_refused.finish(telemetry.TerminalState.REFUSED, "safety_blocked")

    first, second, third = (json.loads(message) for message in turn_records)
    assert first["pattern"] == "trend_delta"
    assert "classify" in first["phase_durations_ms"]
    assert "pattern" not in second
    assert second["error_type"] == "off_domain"
    assert "pattern" not in third
    assert third["error_type"] == "safety_blocked"
    turn_spans = [
        span
        for span in exporter.get_finished_spans()
        if span.name == "narratives.turn"
    ]
    attributes = [dict(span.attributes or {}) for span in turn_spans]
    assert attributes[0]["narratives.pattern"] == "trend_delta"
    assert "narratives.pattern" not in attributes[1]
    assert "narratives.pattern" not in attributes[2]


def _make_finished_span() -> ReadableSpan:
    """Returns one finished span with an allowlisted attribute."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    with provider.get_tracer(__name__).start_as_current_span("request") as s:
        s.set_attribute("http.route", "/agent/chat/stream")
    (span,) = exporter.get_finished_spans()
    return span


def test_span_exporter_writes_to_the_current_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: `_StdoutSpanExporter` writes each span as one line on stdout.
    # Situation: The exporter is created, and `sys.stdout` is then replaced,
    #   as a test runner does after the exporter's thread has started.
    # Expectation: The span's `format_span` line is written to the new
    #   stream, and the export reports success.
    span = _make_finished_span()
    exporter = telemetry._StdoutSpanExporter()
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)

    result = exporter.export([span])

    assert result is SpanExportResult.SUCCESS
    assert stdout.getvalue() == telemetry.format_span(span)


def test_turn_summary_handler_writes_the_bare_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: `_StdoutLineHandler` writes only the log message.
    # Situation: The handler is created, `sys.stdout` is then replaced, and
    #   a record with a formatted message is emitted.
    # Expectation: The new stream holds the formatted message followed by a
    #   newline, with no timestamp or level prefix.
    handler = telemetry._StdoutLineHandler()
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)

    handler.emit(logging.makeLogRecord({"msg": '{"turn": %d}', "args": (1,)}))

    assert stdout.getvalue() == '{"turn": 1}\n'


def test_turn_summary_handler_does_not_raise_when_writing_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: A write failure in `_StdoutLineHandler` does not reach the
    #   caller.
    # Situation: Writing to stdout raises, as it does when the stream has
    #   been closed.
    # Expectation: `emit` returns normally and passes the record to
    #   `handleError`, as `logging.StreamHandler` does.
    def raise_on_write(line: str) -> None:
        raise ValueError("I/O operation on closed file.")

    handled: list[logging.LogRecord] = []
    handler = telemetry._StdoutLineHandler()
    monkeypatch.setattr(telemetry, "_write_stdout_line", raise_on_write)
    monkeypatch.setattr(handler, "handleError", handled.append)
    record = logging.makeLogRecord({"msg": "summary"})

    handler.emit(record)

    assert handled == [record]


def test_flush_telemetry_does_nothing_before_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: `flush_telemetry` before `configure_telemetry` has run.
    # Situation: No tracer provider has been installed.
    # Expectation: `flush_telemetry` returns without raising.
    monkeypatch.setattr(telemetry, "_configured", {})

    telemetry.flush_telemetry()


def test_flush_telemetry_writes_buffered_spans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: `flush_telemetry` writes the spans the batch processor is
    #   still holding.
    # Situation: The installed provider batches spans with a delay far
    #   longer than the test, and one span has ended.
    # Expectation: The span has not been exported before the flush and has
    #   been exported after it.
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(
        BatchSpanProcessor(exporter, schedule_delay_millis=60_000)
    )
    monkeypatch.setattr(telemetry, "_configured", {"provider": provider})
    try:
        provider.get_tracer(__name__).start_span("turn").end()
        assert not exporter.get_finished_spans()

        telemetry.flush_telemetry()

        assert len(exporter.get_finished_spans()) == 1
    finally:
        provider.shutdown()


@pytest.mark.usefixtures("content_capture_requested")
def test_configure_telemetry_installs_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: `configure_telemetry` sets up the provider, turn handler, and
    #   instrumentors on the first call and is a no-op on later calls.
    # Situation: Global instrumentation hooks are stubbed to record calls
    #   without mutating process-wide OpenTelemetry state, and
    #   `configure_telemetry` is called twice.
    # Expectation: GenAI content capture is disabled, one `TracerProvider`
    #   is created and stored in `_configured`, `_StdoutLineHandler` is
    #   attached once at `INFO`, and the `httpx` and `google-genai`
    #   instrumentors are each called once.
    providers: list[TracerProvider] = []
    httpx_calls: list[None] = []
    genai_calls: list[None] = []
    monkeypatch.setattr(telemetry, "_configured", {})
    monkeypatch.setattr(
        trace,
        "set_tracer_provider",
        lambda provider: providers.append(provider),
    )
    monkeypatch.setattr(
        HTTPXClientInstrumentor,
        "instrument",
        lambda self: httpx_calls.append(None),
    )
    monkeypatch.setattr(
        telemetry._genai_instrumentor,
        "instrument",
        lambda: genai_calls.append(None),
    )
    handlers_before = list(telemetry._turn_logger.handlers)
    level_before = telemetry._turn_logger.level
    try:
        telemetry.configure_telemetry()
        telemetry.configure_telemetry()

        assert get_content_capturing_mode() is ContentCapturingMode.NO_CONTENT
        assert len(providers) == 1
        assert telemetry._configured == {"provider": providers[0]}
        assert httpx_calls == [None]
        assert genai_calls == [None]
        assert len(telemetry._turn_logger.handlers) == len(handlers_before) + 1
        assert isinstance(
            telemetry._turn_logger.handlers[-1], telemetry._StdoutLineHandler
        )
        assert telemetry._turn_logger.level == logging.INFO
    finally:
        telemetry._turn_logger.handlers[:] = handlers_before
        telemetry._turn_logger.setLevel(level_before)
        for provider in providers:
            provider.shutdown()
