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
5. `TurnTelemetry` records phases, tool names, and token counts on the turn
   span. The span does not have the turn ID, and `finish` does not write a
   structured line.
6. The stdout span exporter and the line handler write to the current
   `sys.stdout`, and the handler does not raise when writing fails.
7. `flush_telemetry` writes spans still waiting in the batch processor, and
   does nothing before `configure_telemetry` has run.
8. `configure_telemetry` installs the provider, handler, and instrumentors
   once and is idempotent on subsequent calls.
9. `write_structured_record` writes a record as one line of compact JSON,
   with its keys in the order of the dataclass fields and a non-finite
   number as `null`.
10. `record_budget_event` emits content-free `daily_token_budget` JSON records
    at `WARNING` and `ERROR` severities.
"""

import io
import json
import logging
import os
import sys
import time
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass

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
from opentelemetry.trace import SpanKind, StatusCode
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
                "narratives.terminal_state": "complete",
            }
        )

    (span,) = exporter.get_finished_spans()
    record = json.loads(telemetry.format_span(span))

    assert record["attributes"] == {
        "http.route": "/agent/chat/stream",
        "narratives.terminal_state": "complete",
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


def test_finish_ends_the_turn_span_once_without_a_structured_line(
    monkeypatch: pytest.MonkeyPatch, structured_lines: list[str]
) -> None:
    # Test: What `TurnTelemetry.finish` does when a turn ends.
    # Situation: The module tracer records spans in memory. A turn runs a
    #   discovery phase with two tool calls over three iterations, adds
    #   token usage from two Gemini calls, and finishes `complete`. `finish`
    #   is then called again with `error`.
    # Expectation: The tracer exports one turn span. It has the first
    #   terminal state, the iteration count, the tool call count, the tool
    #   names, and the summed tokens, and its status is not an error.
    #   `finish` does not write a structured line.
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(telemetry, "_tracer", provider.get_tracer(__name__))
    turn = telemetry.TurnTelemetry()
    with turn.phase("discovery"):
        turn.mcp_iterations = 3
        turn.record_tool_call("search_indicators")
        turn.record_tool_call("fetch_observations")
    turn.tokens.add(
        telemetry.TokenCounts(prompt=10, candidates=0, thoughts=0, total=15)
    )
    turn.tokens.add(
        telemetry.TokenCounts(prompt=0, candidates=4, thoughts=2, total=0)
    )

    turn.finish(telemetry.TerminalState.COMPLETE)
    turn.finish(telemetry.TerminalState.ERROR, "late_error")

    (span,) = [
        span
        for span in exporter.get_finished_spans()
        if span.name == "narratives.turn"
    ]
    attributes = dict(span.attributes or {})
    assert attributes["narratives.terminal_state"] == "complete"
    assert attributes["narratives.mcp_iterations"] == 3
    assert attributes["narratives.tool_call_count"] == 2
    assert attributes["narratives.tool_names"] == (
        "fetch_observations",
        "search_indicators",
    )
    assert attributes["narratives.tokens.prompt_token_count"] == 10
    assert attributes["narratives.tokens.candidates_token_count"] == 4
    assert attributes["narratives.tokens.thoughts_token_count"] == 2
    assert attributes["narratives.tokens.total_token_count"] == 15
    assert "error.type" not in attributes
    assert span.status.status_code is not StatusCode.ERROR
    assert structured_lines == []


def test_the_turn_span_does_not_have_the_turn_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: The spans of a turn do not have the turn ID.
    # Situation: The module tracer records spans in memory, and a turn with
    #   a known turn ID finishes after one phase.
    # Expectation: The turn span and the phase span do not have a
    #   `narratives.turn_id` attribute, and the turn ID does not appear in
    #   the serialized form of either span.
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(telemetry, "_tracer", provider.get_tracer(__name__))
    turn = telemetry.TurnTelemetry(turn_id="turn-id-0123456789abcdef")
    with turn.phase("classify"):
        pass

    turn.finish(telemetry.TerminalState.COMPLETE)

    spans = exporter.get_finished_spans()
    assert {span.name for span in spans} == {
        "narratives.turn",
        "narratives.phase.classify",
    }
    for span in spans:
        assert "narratives.turn_id" not in (span.attributes or {})
        assert turn.turn_id not in telemetry.format_span(span)


def test_repeated_phases_accumulate_and_analysis_fields_reach_the_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Phase accumulation and the span attributes of the analysis.
    # Situation: The module tracer records spans in memory; a turn times
    #   the processing phase twice, as a retried specification does, with
    #   the clock advanced by 100 ms and then 50 ms, and records the
    #   analysis and chart counts before finishing.
    # Expectation: The processing duration is the sum of both runs, and
    #   the turn span carries the scripts, the five counts, and the title
    #   outcome.
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
    turn.title_outcome = telemetry.TitleOutcome.EMITTED

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
    assert attributes["narratives.title_outcome"] == "emitted"


def test_a_turn_that_never_reaches_synthesis_records_no_title_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Default title outcome.
    # Situation: The module tracer records spans in memory, and a turn
    #   finishes without any phase setting `title_outcome`, as a refused or
    #   clarification turn does.
    # Expectation: The turn span records `narratives.title_outcome` as
    #   `not_requested`, so it is not counted as a title the model omitted.
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(telemetry, "_tracer", provider.get_tracer(__name__))
    turn = telemetry.TurnTelemetry()

    turn.finish(telemetry.TerminalState.REFUSED, "off_domain")

    (span,) = exporter.get_finished_spans()
    attributes = dict(span.attributes or {})
    assert attributes["narratives.title_outcome"] == "not_requested"


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
    state: telemetry.TerminalState,
    error_type: str | None,
    severity: str,
) -> None:
    # Test: The severity of the exported turn span.
    # Situation: The module tracer is replaced with one that records spans
    #   in memory, and a turn finishes in the parametrized state.
    # Expectation: The serialized turn span reports the expected severity.
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(telemetry, "_tracer", provider.get_tracer(__name__))

    telemetry.TurnTelemetry().finish(state, error_type)

    (span,) = exporter.get_finished_spans()
    assert json.loads(telemetry.format_span(span))["severity"] == severity


def test_the_pattern_is_recorded_only_when_the_classifier_assigned_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: The `narratives.pattern` attribute of the turn span.
    # Situation: One turn is classified as `trend_delta` and completes; a
    #   second turn is refused as `off_domain` before any classification is
    #   assigned; a third turn is classified as `single_point` and later
    #   refused as `safety_blocked`.
    # Expectation: The first span carries `narratives.pattern`. Both
    #   refused spans omit it and carry their refusal reasons in
    #   `error.type`.
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

    turn_spans = [
        span
        for span in exporter.get_finished_spans()
        if span.name == "narratives.turn"
    ]
    attributes = [dict(span.attributes or {}) for span in turn_spans]
    assert attributes[0]["narratives.pattern"] == "trend_delta"
    assert "narratives.pattern" not in attributes[1]
    assert attributes[1]["error.type"] == "off_domain"
    assert "narratives.pattern" not in attributes[2]
    assert attributes[2]["error.type"] == "safety_blocked"


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


def test_token_usage_add_records_call_records_and_accumulates_totals() -> None:
    # Test: Token usage accumulation and per-call attribution.
    # Situation: Multiple Gemini calls report usage metadata: some with phase,
    #   model, and round, some without phase or model, and one with None counts.
    # Expectation: Totals accumulate all non-None counts, only calls with
    #   non-empty phase and model append TokenCallRecord instances to calls,
    #   and None counts are ignored without appending to calls.
    usage = telemetry.TokenUsage()
    counts1 = telemetry.TokenCounts(
        prompt=10, candidates=5, thoughts=2, total=17
    )
    counts2 = telemetry.TokenCounts(prompt=3, candidates=4, thoughts=0, total=7)
    counts3 = telemetry.TokenCounts(prompt=2, candidates=1, thoughts=1, total=4)

    usage.add(
        counts1,
        phase="discovery",
        model="gemini-3.8-flash",
        round_number=1,
    )
    usage.add(counts2)
    usage.add(None, phase="discovery", model="gemini-3.8-flash", round_number=2)
    usage.add(
        counts3,
        phase="synthesis",
        model="gemini-3.8-flash",
    )

    assert usage.prompt_token_count == 15
    assert usage.candidates_token_count == 10
    assert usage.thoughts_token_count == 3
    assert usage.total_token_count == 28
    assert usage.calls == [
        telemetry.TokenCallRecord(
            phase="discovery",
            model="gemini-3.8-flash",
            round_number=1,
            counts=counts1,
        ),
        telemetry.TokenCallRecord(
            phase="synthesis",
            model="gemini-3.8-flash",
            round_number=None,
            counts=counts3,
        ),
    ]


def test_elapsed_ms_stays_at_the_duration_that_finish_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: `elapsed_ms()` before and after `finish()`.
    # Situation: The test calls `elapsed_ms()` 0.25 s after the start of
    #   the turn, `finish()` 1 s after it, and `elapsed_ms()` again 5 s
    #   after it.
    # Expectation: `elapsed_ms()` returns 250 ms before `finish()` and
    #   1000 ms after it, even though the clock has advanced.
    turn = telemetry.TurnTelemetry()
    clock = [turn._start + 0.25]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    elapsed_before = turn.elapsed_ms()
    clock[0] = turn._start + 1.0

    turn.finish(telemetry.TerminalState.COMPLETE)

    clock[0] = turn._start + 5.0
    assert elapsed_before == 250.0
    assert turn.elapsed_ms() == 1000.0


@dataclass(frozen=True, kw_only=True)
class _SampleItem:
    """Holds one nested item of `_SampleRecord`."""

    name: str
    ratio: float | None


@dataclass(frozen=True, kw_only=True)
class _SampleRecord(telemetry.StructuredRecord):
    """Holds a structured record with each kind of value a record uses."""

    state: telemetry.TerminalState
    reason: str | None
    is_signed: bool
    items: tuple[_SampleItem, ...]


def _make_sample_record(*items: _SampleItem) -> _SampleRecord:
    """Builds a sample structured record that holds `items`."""
    return _SampleRecord(
        severity="INFO",
        message="sample event",
        event="sample",
        schema_version=1,
        state=telemetry.TerminalState.COMPLETE,
        reason=None,
        is_signed=True,
        items=items,
    )


_SAMPLE_LINE = (
    '{"severity":"INFO","message":"sample event","event":"sample",'
    '"schema_version":1,"state":"complete","reason":null,"is_signed":true,'
    '"items":[{"name":"two\\nlines \\"quoted\\"","ratio":0.5}]}'
)


def test_write_structured_record_writes_one_line_of_compact_json(
    structured_lines: list[str],
) -> None:
    # Test: The line that `write_structured_record` writes.
    # Situation: A record holds the four shared keys, an enum, a `None`, a
    #   boolean, and a tuple with one nested dataclass. The nested string
    #   holds a line break and a double quote.
    # Expectation: The function writes exactly one line. It does not have
    #   a line break, it is JSON without spaces between its tokens, and its
    #   keys follow the order of the dataclass fields, with the four shared
    #   keys first.
    record = _make_sample_record(
        _SampleItem(name='two\nlines "quoted"', ratio=0.5)
    )

    telemetry.write_structured_record(record)

    (line,) = structured_lines
    assert "\n" not in line
    assert line == _SAMPLE_LINE
    assert json.loads(line)["items"][0]["name"] == 'two\nlines "quoted"'


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_write_structured_record_writes_a_non_finite_number_as_null(
    structured_lines: list[str], value: float
) -> None:
    # Test: A non-finite number in a structured record.
    # Situation: A nested field of the record holds NaN, infinity, or
    #   negative infinity.
    # Expectation: The line does not hold the JavaScript names for those
    #   values, which JSON does not allow, and the field parses as `null`.
    record = _make_sample_record(_SampleItem(name="x", ratio=value))

    telemetry.write_structured_record(record)

    (line,) = structured_lines
    assert "NaN" not in line
    assert "Infinity" not in line
    assert json.loads(line)["items"] == [{"name": "x", "ratio": None}]


def test_write_structured_record_reaches_stdout_as_one_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: The path of a structured record to stdout.
    # Situation: The logger for structured lines has the line handler that
    #   `configure_telemetry` installs, at level `INFO`, and `sys.stdout` is
    #   replaced.
    # Expectation: stdout holds the record's JSON followed by one newline,
    #   without a timestamp or a level in front of it.
    logger = telemetry._turn_logger
    level_before = logger.level
    monkeypatch.setattr(logger, "handlers", [telemetry._StdoutLineHandler()])
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)
    record = _make_sample_record(
        _SampleItem(name='two\nlines "quoted"', ratio=0.5)
    )
    logger.setLevel(logging.INFO)
    try:
        telemetry.write_structured_record(record)
    finally:
        logger.setLevel(level_before)

    assert stdout.getvalue() == _SAMPLE_LINE + "\n"


@pytest.mark.parametrize(
    ("state", "expected_severity", "used_tokens"),
    [
        pytest.param(
            telemetry.BudgetEventState.WARNING, "WARNING", 800, id="warning"
        ),
        pytest.param(
            telemetry.BudgetEventState.EXHAUSTED,
            "ERROR",
            1000,
            id="exhausted",
        ),
    ],
)
def test_record_budget_event_emits_structured_content_free_json(
    structured_lines: list[str],
    state: telemetry.BudgetEventState,
    expected_severity: str,
    used_tokens: int,
) -> None:
    # Test: Structured `daily_token_budget` event schema and severity.
    # Situation: `record_budget_event` is invoked for the `warning` and
    #   `exhausted` states.
    # Expectation: One JSON line is written to the structured stdout logger
    #   with severity WARNING or ERROR and only the allowlisted operational
    #   budget fields.
    telemetry.record_budget_event(
        state,
        used_tokens=used_tokens,
        limit_tokens=1000,
        utc_day="2026-11-20",
    )

    (message,) = structured_lines
    assert json.loads(message) == {
        "severity": expected_severity,
        "message": f"daily token budget {state}",
        "event": "daily_token_budget",
        "state": state,
        "used_tokens": used_tokens,
        "limit_tokens": 1000,
        "utc_day": "2026-11-20",
    }
