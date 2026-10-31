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
"""Tests for `run_turn` in the chat pipeline.

Verifies that:
1. A complete turn emits the answer as text and chart blocks, a `complete`
   terminal event carrying the idempotency key and the signed window, then
   the follow-ups, and is recorded as `complete`. The signed turn verifies
   on the next request, and an answer too long to sign is left unsigned.
2. The discovery phase runs the discovery loop, answers from its digest or
   from a default specification over the cache when the loop ends without
   one, streams the tool calls, the data status, and the digest's sources,
   passes the digest and the table inventory to synthesis, and records the
   scripts, fetch counts, and retries in telemetry.
3. A missing configuration, a failed discovery loop, an empty or slow tool
   list, and a failed, broken, stalled, or empty synthesis end the turn with
   one `error` terminal event carrying a fixed message and the
   machine-readable `reason`, and are recorded as `error` with that reason.
   Configuration and MCP failures end the turn before synthesis. When the MCP
   server is missing required tools, the discovery phase logs a warning and
   continues the turn.
4. An unexpected exception ends the turn as `internal_error`; a follow-up
   failure after the terminal event leaves the turn `complete`.
5. A chart block in the synthesis stream is resolved against the turn cache
   and emitted in place while its markdown fence is stripped from the signed
   text; a rejected chart block is dropped and, when no chart block is
   emitted for a turn with data, a default chart is appended.
6. Cancellation mid-turn is recorded as `canceled`; cancellation after the
   terminal event stays `complete`.
7. Synthesis receives the verified window before the current query, an
   `error` terminal event carries no signing fields, and a failure while
   signing leaves the delivered turn complete and unsigned.
8. The classify phase runs first behind a `classify` status frame: a
   refusal ends the turn in one `refused` terminal frame without an `error`
   key and without any model call, a clarification is emitted as the one
   text block and signed with empty state slots, a classification carries
   its pattern directive into the discovery loop and synthesis and its
   pattern into telemetry, and a classifier failure proceeds as
   `exploratory` without a directive. A model call that Gemini blocks in the
   classify phase, the discovery loop, or synthesis ends the turn as
   `refused` with reason `safety_blocked`.
9. The serialized frames of a complete turn match the recorded wire
   sequence, byte for byte.
"""

import asyncio
import json
import logging
import re
from collections.abc import AsyncGenerator, Callable, Iterator, Sequence
from dataclasses import dataclass, field, replace

import pytest

from narratives_agent.analytics.digest import (
    AnalysisDigest,
    RefusedScriptResult,
)
from narratives_agent.analytics.provenance import Provenance, Source
from narratives_agent.analytics.ranking import rank_cohort
from narratives_agent.analytics.tables import ObservationRow, ObservationTable
from narratives_agent.analytics.timeseries import analyze_timeseries
from narratives_agent.config_model import AgentConfig, Prompts
from narratives_agent.gemini.client import (
    GeminiBlockedError,
    GeminiError,
    GeminiStreamError,
)
from narratives_agent.gemini.response import StreamChunk
from narratives_agent.gemini.schemas import QueryClassification
from narratives_agent.json_value import JsonObject, JsonValue
from narratives_agent.mcp import capabilities
from narratives_agent.mcp import client as mcp_client
from narratives_agent.telemetry import (
    ErrorType,
    TerminalState,
    TokenUsage,
    TurnTelemetry,
)
from narratives_agent.workflows import chat_pipeline
from narratives_agent.workflows import transcript as transcript_module
from narratives_agent.workflows.charts import PlaceList, ResolvedLineChart
from narratives_agent.workflows.classify import (
    Admitted,
    Clarification,
    RefusedReason,
    TurnRefusedError,
)
from narratives_agent.workflows.mcp_loop import (
    DiscoveryResult,
    McpLoopError,
    StatusCallback,
)
from narratives_agent.workflows.messages import (
    CHAT_DISABLED,
    CLASSIFY_STATUS,
    INTERNAL_ERROR,
    MCP_UNAVAILABLE,
    NO_DATA_MESSAGE,
    REFUSED_MESSAGE,
    SYNTHESIS_FAILED,
    TRUNCATED_MESSAGE,
)
from narratives_agent.workflows.pattern_guidance import build_pattern_directive
from narratives_agent.workflows.processing import (
    StepRefusalDiagnostic,
    execute_specification,
)
from narratives_agent.workflows.prompt_contracts import load_prompt_contract
from narratives_agent.workflows.specification import (
    AnalysisSpecification,
    UnavailableReport,
)
from narratives_agent.workflows.sse_frames import (
    EventName,
    SseFrame,
    serialize_source,
)
from narratives_agent.workflows.transcript import (
    MAX_RESPONSE_CHARS,
    ConversationStateSlots,
    Transcript,
    Turn,
    load_transcript,
)
from narratives_agent.workflows.turn_cache import CachedTable, TurnCache

_QUESTION = "What is the population of France?"
_IDEMPOTENCY_KEY = "test-idempotency-key"
_ANSWER = "About 68 million."
# Default chart of the series summary over `t1`: a line chart over France.
_DEFAULT_CHART: JsonObject = {
    "viz_type": "line",
    "title": "Total Population",
    "variable_dcids": ["Count_Person"],
    "place_dcids": ["country/FRA"],
    "facet_ids": {"Count_Person": "f1"},
}
_FOLLOW_UPS = ["And Spain?"]
_TRANSCRIPT = Transcript(
    turns=[],
    compacted_summary=None,
    current_query=_QUESTION,
    current_idempotency_key=_IDEMPOTENCY_KEY,
)
_INSEE = Source(name="INSEE", url="https://insee.fr/")
_INSEE_WIRE: JsonObject = {"name": "INSEE", "url": "https://insee.fr/"}
_TOOL_CALL: JsonObject = {
    "name": "fetch_observations",
    "arguments": {
        "variable_dcid": "Count_Person",
        "place_dcids": ["country/FRA"],
    },
    "result": json.dumps({"table_id": "t1", "row_count": 2}),
    "status": "success",
}
# Scopes of a complete turn: one for the fetched table, with the span of its
# dates, and one for the default chart, which carries no date.
_SCOPES: JsonObject = {
    "scopes": [
        {
            "places": {"country/FRA": "France"},
            "parent_place": None,
            "child_place_type": None,
            "variables": {"Count_Person": "Total Population"},
            "date_range": ["2022", "2023"],
        },
        {
            "places": {"country/FRA": "France"},
            "parent_place": None,
            "child_place_type": None,
            "variables": {"Count_Person": "Total Population"},
            "date_range": None,
        },
    ]
}
_CLASSIFICATION = QueryClassification.model_validate(
    {
        "serviceable": True,
        "pattern": "single_point",
        "geographic_shape": "single_place",
        "requires_computation": False,
    }
)
_CLARIFICATION_QUESTION = (
    "Do you mean Georgia the country or the U.S. state of Georgia?"
)
_SERIES_SPECIFICATION = AnalysisSpecification.model_validate(
    {
        "steps": [
            {"step_id": "s1", "script": "analyze_timeseries", "table": "t1"}
        ],
        "findings": ["France publishes an annual census estimate."],
    }
)


def _make_table(
    table_id: str = "t1",
    *,
    source: Source | None = _INSEE,
    places: Sequence[str] = ("country/FRA",),
) -> CachedTable:
    """Builds a cached population table with two years per place."""
    names = {place: place.rsplit("/", 1)[-1].title() for place in places}
    names["country/FRA"] = "France"
    return CachedTable(
        table_id=table_id,
        table=ObservationTable(
            variable_dcid="Count_Person",
            variable_name="Total Population",
            unit="Person",
            scaling_factor=None,
            provenance=Provenance(
                sources=(source,) if source is not None else ()
            ),
            rows=tuple(
                ObservationRow(place, names[place], date, value)
                for place in places
                for date, value in (("2022", 67.8e6), ("2023", 68.2e6))
            ),
            requested_places=tuple(places),
            place_names=names,
            facet_id="f1",
            source=source,
        ),
    )


@pytest.fixture(autouse=True)
def signing_secret(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Signs transcripts with a fixed secret resolved afresh per test."""
    monkeypatch.setenv(
        "TRANSCRIPT_HMAC_SECRET", "pipeline-test-secret-0123456789abcdef"
    )
    transcript_module.reset_signing_key()
    yield
    transcript_module.reset_signing_key()


@dataclass(frozen=True)
class _Request:
    """Carries the transcript fields of a chat request."""

    message: str
    idempotency_key: str
    turns: Sequence[Turn] = ()
    compacted_summary: str | None = None


class _RecordingTelemetry(TurnTelemetry):
    """Subclasses `TurnTelemetry` to record the terminal state of the turn."""

    finished: list[tuple[TerminalState, str | None]]

    def finish(
        self, state: TerminalState, error_type: str | None = None
    ) -> None:
        self.finished.append((state, error_type))
        super().finish(state, error_type)


@dataclass
class _Turn:
    """Holds the stubbed collaborators of one turn and their recorded state."""

    events: list[tuple[EventName, JsonObject]] = field(default_factory=list)
    finished: list[tuple[TerminalState, str | None]] = field(
        default_factory=list
    )
    telemetry: TurnTelemetry | None = None
    synthesis_calls: int = 0
    synthesis_messages: list[list[JsonObject]] = field(default_factory=list)
    synthesis_instructions: list[str] = field(default_factory=list)
    answer: str = _ANSWER
    follow_up_topics: list[list[str]] = field(default_factory=list)
    loop_classifications: list[QueryClassification | None] = field(
        default_factory=list
    )
    synthesis_release: asyncio.Event = field(default_factory=asyncio.Event)
    follow_ups_release: asyncio.Event = field(default_factory=asyncio.Event)

    def emit(self, frame: SseFrame) -> None:
        """Records the frame as the event name and payload the route sends."""
        self.events.append((frame.event, frame.payload()))

    def list_event_names(self) -> list[EventName]:
        """Returns the names of the events emitted so far, in order."""
        return [event for event, _ in self.events]

    def list_content_payloads(self, key: str) -> list[JsonValue]:
        """Returns the payloads of the `content` events carrying `key`."""
        return [
            data[key]
            for event, data in self.events
            if event == "content" and key in data
        ]

    def list_blocks(self) -> list[JsonObject]:
        """Returns the `block` payloads streamed, in order."""
        return [
            dict(block)
            for block in self.list_content_payloads("block")
            if isinstance(block, dict)
        ]

    def list_texts(self) -> list[str]:
        """Returns the markdown of the text blocks streamed, in order."""
        return [
            str(block["markdown"])
            for block in self.list_blocks()
            if block["type"] == "text"
        ]

    def list_charts(self) -> list[JsonObject]:
        """Returns the charts of the chart blocks streamed, in order."""
        return [
            dict(chart)
            for block in self.list_blocks()
            if block["type"] == "chart"
            and isinstance(chart := block.get("chart"), dict)
        ]

    def get_synthesis_context(self) -> str:
        """Returns the text of the final user message synthesis received."""
        (messages,) = self.synthesis_messages
        parts = messages[-1]["parts"]
        assert isinstance(parts, list)
        part = parts[0]
        assert isinstance(part, dict)
        text = part["text"]
        assert isinstance(text, str)
        return text


async def _run_accepted_loop(cache: TurnCache, **_: object) -> DiscoveryResult:
    """Plays a loop that fetched a table and accepted a series specification."""
    cache.store_fetched(_make_table())
    digest = await execute_specification(_SERIES_SPECIFICATION, cache)
    assert isinstance(digest, AnalysisDigest)
    return DiscoveryResult(
        tool_calls=[dict(_TOOL_CALL)],
        specification=_SERIES_SPECIFICATION,
        digest=digest,
    )


@pytest.fixture
def turn(monkeypatch: pytest.MonkeyPatch) -> _Turn:
    """Stubs every external call of a turn so each stage succeeds at once."""
    stub = _Turn()
    stub.synthesis_release.set()
    stub.follow_ups_release.set()

    def create_telemetry() -> _RecordingTelemetry:
        recording = _RecordingTelemetry()
        recording.finished = stub.finished
        stub.telemetry = recording
        return recording

    async def get_tools() -> list[mcp_client.McpTool]:
        return [
            mcp_client.McpTool(
                name=name,
                description="",
                input_schema={"type": "object", "properties": {}},
            )
            for name in sorted(capabilities.REQUIRED_TOOLS)
        ]

    async def classify(*args: object, **_: object) -> Admitted:
        return Admitted(_CLASSIFICATION)

    async def run_discovery(
        transcript: Transcript,
        config: AgentConfig,
        tools: Sequence[mcp_client.McpTool],
        telemetry: TurnTelemetry,
        cache: TurnCache,
        *,
        classification: QueryClassification | None = None,
        **_: object,
    ) -> DiscoveryResult:
        stub.loop_classifications.append(classification)
        return await _run_accepted_loop(cache)

    async def stream_answer() -> AsyncGenerator[StreamChunk]:
        await stub.synthesis_release.wait()
        yield StreamChunk("text", stub.answer)

    async def start_synthesis(
        *,
        messages: Sequence[JsonObject],
        system_instruction: str,
        **_: object,
    ) -> AsyncGenerator[StreamChunk]:
        stub.synthesis_calls += 1
        stub.synthesis_messages.append(list(messages))
        stub.synthesis_instructions.append(system_instruction)
        return stream_answer()

    async def generate_follow_ups(
        question: str,
        topics: list[str],
        config: AgentConfig,
        usage: TokenUsage,
    ) -> list[str]:
        stub.follow_up_topics.append(list(topics))
        await stub.follow_ups_release.wait()
        return list(_FOLLOW_UPS) if topics else []

    monkeypatch.setattr(chat_pipeline, "TurnTelemetry", create_telemetry)
    monkeypatch.setattr(
        chat_pipeline,
        "load_config",
        lambda: AgentConfig(
            prompts=Prompts(discovery="Gather data.", synthesis="Write prose.")
        ),
    )
    monkeypatch.setattr(chat_pipeline, "classify_query", classify)
    monkeypatch.setattr(mcp_client, "ensure_session_scope", lambda: None)
    monkeypatch.setattr(mcp_client, "async_get_tools", get_tools)
    monkeypatch.setattr(chat_pipeline, "execute_discovery_loop", run_discovery)
    monkeypatch.setattr(chat_pipeline, "async_gemini_stream", start_synthesis)
    monkeypatch.setattr(
        chat_pipeline, "generate_follow_up_questions", generate_follow_ups
    )
    return stub


def _install_loop(
    monkeypatch: pytest.MonkeyPatch,
    outcome: DiscoveryResult | BaseException,
    *tables: CachedTable,
) -> None:
    """Replaces the discovery loop with one that caches `tables` and ends
    with `outcome`, returning it or raising it."""

    async def run_loop(
        transcript: Transcript,
        config: AgentConfig,
        tools: Sequence[mcp_client.McpTool],
        telemetry: TurnTelemetry,
        cache: TurnCache,
        **_: object,
    ) -> DiscoveryResult:
        for table in tables:
            cache.store_fetched(table)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(chat_pipeline, "execute_discovery_loop", run_loop)


async def _start_and_wait_for(
    turn: _Turn, name: EventName
) -> asyncio.Task[None]:
    """Starts the turn and waits until it emits an event with the given name."""
    task = asyncio.create_task(chat_pipeline.run_turn(_TRANSCRIPT, turn.emit))
    async with asyncio.timeout(1):
        while name not in turn.list_event_names():
            await asyncio.sleep(0)
    return task


@pytest.mark.asyncio
async def test_complete_turn_emits_the_answer_then_the_follow_ups(
    turn: _Turn,
) -> None:
    # Test: The event sequence of a turn in which every phase succeeds.
    # Situation: Discovery, synthesis, and follow-ups all succeed, and the
    #   answer carries no chart block of its own.
    # Expectation: The answer is emitted as one text block and then the
    #   default chart as a chart block, followed by one `complete` terminal
    #   event with the request's idempotency key, the signed turn, the
    #   state slots built from the fetched table and the chart, and a
    #   one-turn window, and last the follow-ups; telemetry counts the one
    #   chart, and the turn is recorded as `complete`.
    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    assert turn.list_blocks() == [
        {"index": 0, "type": "text", "markdown": _ANSWER},
        {"index": 1, "type": "chart", "chart": _DEFAULT_CHART},
    ]
    content = [data for event, data in turn.events if event == "content"]
    assert content[-1] == {"block": turn.list_blocks()[1]}
    event, terminal = turn.events[-2]
    assert event == "terminal"
    signature = terminal["hmac"]
    assert isinstance(signature, str)
    assert re.fullmatch(r"[0-9a-f]{64}", signature)
    assert terminal == {
        "state": TerminalState.COMPLETE,
        "idempotency_key": _IDEMPOTENCY_KEY,
        "turn_index": 0,
        "hmac": signature,
        "state_slots": _SCOPES,
        "compacted_summary": None,
        "window": [
            {
                "turn_index": 0,
                "idempotency_key": _IDEMPOTENCY_KEY,
                "hmac": signature,
            }
        ],
    }
    assert turn.events[-1] == (
        "follow_ups",
        {"follow_up_questions": _FOLLOW_UPS},
    )
    assert turn.list_event_names().count("terminal") == 1
    assert turn.telemetry is not None
    assert turn.telemetry.charts_emitted == 1
    assert turn.telemetry.charts_rejected == 0
    assert turn.finished == [(TerminalState.COMPLETE, None)]


@pytest.mark.asyncio
async def test_the_discovery_phase_streams_its_results(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: The events and telemetry of the discovery phase.
    # Situation: The loop streams one thought and a processing status while
    #   it runs, fetches one table, and has a series specification
    #   accepted.
    # Expectation: The phase opens with a `discovery` status, relays the
    #   thought with phase `discovery` and the processing status, streams
    #   the tool call, a data status with data and no truncation, and the
    #   table's source as the one numbered source; synthesis receives the
    #   digest and the table inventory, prefixed with the numbered source,
    #   and not the model's finding; and telemetry records the script, the
    #   fetch counts, no retries, and the discovery phase.
    async def run_loop(
        transcript: Transcript,
        config: AgentConfig,
        tools: Sequence[mcp_client.McpTool],
        telemetry: TurnTelemetry,
        cache: TurnCache,
        *,
        thought_callback: Callable[[str], None],
        status_callback: StatusCallback,
        **_: object,
    ) -> DiscoveryResult:
        thought_callback("Looking up France.")
        status_callback("processing", "Analyzing data...")
        return await _run_accepted_loop(cache)

    monkeypatch.setattr(chat_pipeline, "execute_discovery_loop", run_loop)

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    statuses = [data for event, data in turn.events if event == "status"]
    assert statuses[1] == {
        "phase": "discovery",
        "message": "Querying data tools...",
    }
    assert statuses[2] == {
        "phase": "processing",
        "message": "Analyzing data...",
    }
    assert (
        "thought",
        {"thought": "Looking up France.", "phase": "discovery"},
    ) in turn.events
    assert turn.list_content_payloads("tool_call") == [_TOOL_CALL]
    assert turn.list_content_payloads("data_status") == [
        {"has_data": True, "truncated": False, "message": None}
    ]
    assert turn.list_content_payloads("sources") == [[_INSEE_WIRE]]
    context = turn.get_synthesis_context()
    assert "[1] INSEE - https://insee.fr/" in context
    assert "Step s1: analyze_timeseries on Total Population" in context
    assert "France publishes an annual census estimate." not in context
    assert "- t1: Total Population (Count_Person); unit: Person" in context
    assert turn.telemetry is not None
    assert turn.telemetry.scripts == ["analyze_timeseries"]
    assert turn.telemetry.tables_fetched == 1
    assert turn.telemetry.total_rows_fetched == 2
    assert turn.telemetry.processing_retries == 0
    assert "discovery" in turn.telemetry.phase_durations_ms
    assert turn.finished == [(TerminalState.COMPLETE, None)]


@pytest.mark.asyncio
async def test_a_digest_without_sources_cites_data_commons(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: The fallback source.
    # Situation: The accepted specification's table reports no source.
    # Expectation: The one source streamed and numbered for synthesis is
    #   the Data Commons fallback.
    async def run_loop(
        transcript: Transcript,
        config: AgentConfig,
        tools: Sequence[mcp_client.McpTool],
        telemetry: TurnTelemetry,
        cache: TurnCache,
        **_: object,
    ) -> DiscoveryResult:
        cache.store_fetched(_make_table(source=None))
        digest = await execute_specification(_SERIES_SPECIFICATION, cache)
        assert isinstance(digest, AnalysisDigest)
        return DiscoveryResult(
            specification=_SERIES_SPECIFICATION, digest=digest
        )

    monkeypatch.setattr(chat_pipeline, "execute_discovery_loop", run_loop)

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    assert turn.list_content_payloads("sources") == [
        [serialize_source(chat_pipeline._FALLBACK_SOURCE)]
    ]
    assert "[1] Data Commons - https://datacommons.org/" in (
        turn.get_synthesis_context()
    )


@pytest.mark.asyncio
async def test_an_unavailable_report_answers_without_data(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: The no-data path through the pipeline.
    # Situation: The loop ends with a `report_unavailable` note and no
    #   table.
    # Expectation: The data status reports no data with the no-data
    #   message, no sources are streamed, synthesis receives the note as
    #   missing data, no chart block is emitted and no default chart is
    #   appended, the follow-ups are grounded in the note alone, the turn
    #   completes with empty state slots, and telemetry records no scripts.
    report = UnavailableReport(
        searched_indicators=["Count_Person_Martian"],
        searched_places=["country/FRA"],
        reason="Data Commons has no Martian population series.",
        related_available=["Count_Person"],
    )
    _install_loop(monkeypatch, DiscoveryResult(unavailable=report))

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    assert turn.list_content_payloads("data_status") == [
        {
            "has_data": False,
            "truncated": False,
            "message": NO_DATA_MESSAGE,
        }
    ]
    assert turn.list_content_payloads("sources") == []
    assert turn.list_charts() == []
    context = turn.get_synthesis_context()
    assert "MISSING DATA:" in context
    assert "- " + report.format_note() in context
    assert "NUMBERED SOURCES" not in context
    assert turn.follow_up_topics == [[report.format_note()]]
    _, terminal = turn.events[-2]
    assert terminal["state_slots"] == {"scopes": []}
    assert turn.telemetry is not None
    assert turn.telemetry.scripts == []
    assert turn.finished == [(TerminalState.COMPLETE, None)]


@pytest.mark.asyncio
async def test_a_truncated_loop_falls_back_to_the_default_specification(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: The fallback when the loop ends at a bound with a table cached.
    # Situation: The loop returns truncated, without a specification, after
    #   caching one table; the classification is a single-point lookup.
    # Expectation: A series summary over the table answers the turn: the
    #   browser is told the processing phase ran, the data status has data
    #   and is truncated, the table's source is streamed, the state slots
    #   cover the table, and telemetry records the script and the
    #   processing phase.
    _install_loop(monkeypatch, DiscoveryResult(truncated=True), _make_table())

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    assert [data["phase"] for event, data in turn.events if event == "status"][
        :3
    ] == ["classify", "discovery", "processing"]
    assert turn.list_content_payloads("data_status") == [
        {"has_data": True, "truncated": True, "message": None}
    ]
    assert turn.list_content_payloads("sources") == [[_INSEE_WIRE]]
    assert "Step s1: analyze_timeseries" in turn.get_synthesis_context()
    _, terminal = turn.events[-2]
    assert terminal["state_slots"] == _SCOPES
    assert turn.telemetry is not None
    assert turn.telemetry.scripts == ["analyze_timeseries"]
    assert "processing" in turn.telemetry.phase_durations_ms
    assert turn.finished == [(TerminalState.COMPLETE, None)]


@pytest.mark.asyncio
async def test_a_truncated_loop_without_tables_reports_no_data(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: The fallback when the loop ends at a bound with nothing cached.
    # Situation: The loop returns truncated with an empty cache.
    # Expectation: The data status reports no data with the truncation
    #   message, synthesis receives the no-observations note, no follow-up
    #   topics or `follow_ups` frame are emitted, and the turn completes
    #   without a chart block.
    _install_loop(monkeypatch, DiscoveryResult(truncated=True))

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    assert turn.list_content_payloads("data_status") == [
        {
            "has_data": False,
            "truncated": True,
            "message": TRUNCATED_MESSAGE,
        }
    ]
    assert chat_pipeline._NO_OBSERVATIONS_NOTE in turn.get_synthesis_context()
    assert turn.list_charts() == []
    assert turn.follow_up_topics == [[]]
    assert "follow_ups" not in turn.list_event_names()
    assert turn.finished == [(TerminalState.COMPLETE, None)]


@pytest.mark.asyncio
async def test_exhausted_retries_fall_back_and_note_the_failure(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: The fallback after the retry budget is spent.
    # Situation: The loop returns without a digest after two retries, with
    #   the last diagnostic and one table cached.
    # Expectation: The default specification answers the turn, the
    #   diagnostic's message is carried to synthesis as a missing-data
    #   note after the results, and telemetry records the two retries.
    diagnostic = StepRefusalDiagnostic(
        refusal_reason="insufficient_coverage",
        message="Only 1 of 4 places have a value.",
        step_id="s1",
        script="rank_cohort",
        input_table_ids=("t1",),
        coverage=None,
        alternative_sources=(),
        completed_results=(),
    )
    _install_loop(
        monkeypatch,
        DiscoveryResult(processing_retries=2, last_diagnostic=diagnostic),
        _make_table(),
    )

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    assert turn.list_content_payloads("data_status") == [
        {"has_data": True, "truncated": False, "message": None}
    ]
    context = turn.get_synthesis_context()
    assert "Step s1: analyze_timeseries" in context
    assert (
        "- An analysis step failed: Only 1 of 4 places have a value." in context
    )
    assert turn.telemetry is not None
    assert turn.telemetry.processing_retries == 2
    assert turn.finished == [(TerminalState.COMPLETE, None)]


def _make_state_cohort(
    table_id: str, variable_dcid: str, places: str
) -> CachedTable:
    """Builds a 2023 table across the named states of one cohort."""
    dcids = [f"geoId/{place}" for place in places.split()]
    return CachedTable(
        table_id=table_id,
        table=ObservationTable(
            variable_dcid=variable_dcid,
            variable_name=variable_dcid,
            unit=None,
            scaling_factor=None,
            provenance=Provenance(sources=(_INSEE,)),
            rows=tuple(
                ObservationRow(dcid, dcid, "2023", float(index + 1))
                for index, dcid in enumerate(dcids)
            ),
            requested_places=tuple(dcids),
            place_names={dcid: dcid for dcid in dcids},
            parent_place_dcid="country/USA",
            child_place_type="State",
        ),
    )


@pytest.mark.asyncio
async def test_a_refused_default_relation_keeps_the_per_table_results(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: The correlation fallback when its relation refuses.
    # Situation: A correlation turn ends at a bound with two state cohort
    #   tables of different variables that share two of their five states,
    #   enough to pair them but below the coverage `relate_cohorts` needs,
    #   so the default's relation step refuses.
    # Expectation: The default runs again without the relation, both
    #   per-table rankings reach synthesis, and the relation's refusal is
    #   carried as a missing-data note.
    correlation = QueryClassification.model_validate(
        {
            "serviceable": True,
            "pattern": "correlation",
            "geographic_shape": "child_places",
            "requires_computation": True,
        }
    )

    async def classify(*args: object, **_: object) -> Admitted:
        return Admitted(correlation)

    monkeypatch.setattr(chat_pipeline, "classify_query", classify)
    _install_loop(
        monkeypatch,
        DiscoveryResult(truncated=True),
        _make_state_cohort("t1", "Median_Income", "01 02 03 04 05"),
        _make_state_cohort("t2", "Percent_Diabetes", "04 05 06 07 08"),
    )

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    context = turn.get_synthesis_context()
    assert "Step s1: rank_cohort on Median_Income" in context
    assert "Step s2: rank_cohort on Percent_Diabetes" in context
    assert "- An analysis step failed: Only 2 of the 5 places" in context
    assert "relate_cohorts" not in context
    assert turn.finished == [(TerminalState.COMPLETE, None)]


@pytest.mark.asyncio
async def test_a_refused_default_step_keeps_the_other_tables_results(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: The ranking fallback when one table's step refuses.
    # Situation: A top-N turn ends at a bound with two state cohort tables;
    #   the first requests four states but has a value for one, so its
    #   `rank_cohort` step refuses, and the second covers its states.
    # Expectation: The default runs again without the first table, the
    #   second table's ranking reaches synthesis, and the first table's
    #   refusal is carried as a missing-data note.
    ranking = QueryClassification.model_validate(
        {
            "serviceable": True,
            "pattern": "top_n_ranking",
            "geographic_shape": "child_places",
            "requires_computation": True,
        }
    )

    async def classify(*args: object, **_: object) -> Admitted:
        return Admitted(ranking)

    sparse = _make_state_cohort("t1", "Median_Income", "01 02 03 04")
    sparse = replace(
        sparse, table=replace(sparse.table, rows=sparse.table.rows[:1])
    )
    monkeypatch.setattr(chat_pipeline, "classify_query", classify)
    _install_loop(
        monkeypatch,
        DiscoveryResult(truncated=True),
        sparse,
        _make_state_cohort("t2", "Percent_Diabetes", "04 05 06"),
    )

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    context = turn.get_synthesis_context()
    assert "Step s1: rank_cohort on Percent_Diabetes" in context
    assert "rank_cohort on Median_Income" not in context
    assert "- An analysis step failed: " in context
    assert turn.finished == [(TerminalState.COMPLETE, None)]


@pytest.mark.asyncio
async def test_a_default_whose_every_table_refuses_notes_each_failure(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: The ranking fallback when every table's step refuses.
    # Situation: A top-N turn ends at a bound with two state cohort tables,
    #   each requesting four states with a value for one, so both
    #   `rank_cohort` steps refuse.
    # Expectation: The default runs again without the first table, then no
    #   table remains; the turn completes without a ranking, carrying one
    #   step-failure note for the first table and one default-failure note
    #   for the second.
    ranking = QueryClassification.model_validate(
        {
            "serviceable": True,
            "pattern": "top_n_ranking",
            "geographic_shape": "child_places",
            "requires_computation": True,
        }
    )

    async def classify(*args: object, **_: object) -> Admitted:
        return Admitted(ranking)

    def make_sparse_cohort(table_id: str, variable_dcid: str) -> CachedTable:
        entry = _make_state_cohort(table_id, variable_dcid, "01 02 03 04")
        return replace(
            entry, table=replace(entry.table, rows=entry.table.rows[:1])
        )

    monkeypatch.setattr(chat_pipeline, "classify_query", classify)
    _install_loop(
        monkeypatch,
        DiscoveryResult(truncated=True),
        make_sparse_cohort("t1", "Median_Income"),
        make_sparse_cohort("t2", "Percent_Diabetes"),
    )

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    context = turn.get_synthesis_context()
    assert "Step s1: rank_cohort" not in context
    assert context.count("- An analysis step failed: ") == 1
    assert context.count("- The default analysis also failed: ") == 1
    assert turn.finished == [(TerminalState.COMPLETE, None)]


def test_tables_used_skips_a_stale_derived_table() -> None:
    # Test: The tables a specification used.
    # Situation: The cache holds `t1`, `t2`, and a derived `s1` left by an
    #   earlier run; the accepted specification's `s1` is a result-only
    #   step over `t2`.
    # Expectation: Only `t2` is reported, so the stale `s1` reaches neither
    #   the inventory nor the state slots.
    cache = TurnCache()
    cache.store_fetched(_make_table("t1"))
    cache.store_fetched(_make_table("t2"))
    cache.store_derived(_make_table("s1"))
    specification = AnalysisSpecification.model_validate(
        {"steps": [{"step_id": "s1", "script": "rank_cohort", "table": "t2"}]}
    )

    tables = chat_pipeline._collect_tables_used(specification, cache)

    assert [table.table_id for table in tables] == ["t2"]


@pytest.mark.asyncio
async def test_the_signed_turn_verifies_on_the_next_request(
    turn: _Turn,
) -> None:
    # Test: The terminal event carries everything the next request needs.
    # Situation: A completed turn is rebuilt as the browser stores it from the
    #   query, the streamed answer, and the terminal event.
    # Expectation: The next request carrying that turn verifies.
    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)
    _, terminal = turn.events[-2]
    stored = Turn.model_validate(
        {
            "turn_index": terminal["turn_index"],
            "idempotency_key": terminal["idempotency_key"],
            "user_query": _QUESTION,
            "model_response": _ANSWER,
            "state_slots": terminal["state_slots"],
            "hmac": terminal["hmac"],
        }
    )

    loaded = load_transcript(_Request("And Spain?", "key-2", [stored]))

    assert loaded.turns == [stored]


@pytest.mark.asyncio
async def test_synthesis_receives_the_window_before_the_query(
    turn: _Turn,
) -> None:
    # Test: Multi-turn context reaches synthesis.
    # Situation: A transcript holds one earlier turn.
    # Expectation: Synthesis receives the earlier query and full answer as
    #   alternating messages, then the current query with the data results.
    earlier = Turn(
        turn_index=0,
        idempotency_key="key-0",
        user_query="Population of Spain?",
        model_response="About 48 million.",
        state_slots=ConversationStateSlots(),
        hmac="0" * 64,
    )
    follow_up = Transcript(
        turns=[earlier],
        compacted_summary=None,
        current_query=_QUESTION,
        current_idempotency_key=_IDEMPOTENCY_KEY,
    )

    await chat_pipeline.run_turn(follow_up, turn.emit)

    (messages,) = turn.synthesis_messages
    assert [message["role"] for message in messages] == [
        "user",
        "model",
        "user",
    ]
    assert messages[1]["parts"] == [{"text": "About 48 million."}]
    assert f"User Query: {_QUESTION}" in turn.get_synthesis_context()
    _, terminal = turn.events[-2]
    window = terminal["window"]
    assert isinstance(window, list)
    assert [
        entry["turn_index"] for entry in window if isinstance(entry, dict)
    ] == [0, 1]


@pytest.mark.asyncio
async def test_a_signing_failure_completes_the_turn_unsigned(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: A signing failure after the answer is delivered leaves the turn
    #   complete and unsigned.
    # Situation: Signing raises once the answer's blocks have been emitted.
    # Expectation: The turn still ends `complete`, without signing fields,
    #   and is recorded as `complete`.
    async def fail_finalize(*args: object, **_: object) -> None:
        raise RuntimeError("signing failed")

    monkeypatch.setattr(chat_pipeline, "finalize_turn", fail_finalize)

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    _, terminal = turn.events[-2]
    assert terminal == {
        "state": TerminalState.COMPLETE,
        "idempotency_key": _IDEMPOTENCY_KEY,
    }
    assert turn.finished == [(TerminalState.COMPLETE, None)]


@pytest.mark.asyncio
async def test_an_answer_too_long_to_sign_completes_unsigned(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: An answer longer than `MAX_RESPONSE_CHARS` completes unsigned.
    # Situation: Synthesis streams more than `MAX_RESPONSE_CHARS` characters.
    # Expectation: The turn completes, and its terminal event carries no
    #   signing fields, so the browser leaves the turn out of later context.
    async def stream_long_answer() -> AsyncGenerator[StreamChunk]:
        yield StreamChunk("text", "x" * (MAX_RESPONSE_CHARS + 1))

    async def start_synthesis(**_: object) -> AsyncGenerator[StreamChunk]:
        return stream_long_answer()

    monkeypatch.setattr(chat_pipeline, "async_gemini_stream", start_synthesis)

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    _, terminal = turn.events[-2]
    assert terminal == {
        "state": TerminalState.COMPLETE,
        "idempotency_key": _IDEMPOTENCY_KEY,
    }


@pytest.mark.asyncio
async def test_failed_discovery_loop_ends_the_turn_before_synthesis(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: Fail-closed handling of a discovery loop failure.
    # Situation: The loop raises `McpLoopError` of type `mcp_timeout`.
    # Expectation: The turn ends in one `error` terminal event with the
    #   loop's message, never calls synthesis, and is recorded as `error`
    #   with `mcp_timeout`.
    _install_loop(
        monkeypatch,
        McpLoopError(ErrorType.MCP_TIMEOUT, "The data request took too long."),
    )

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    event, terminal = turn.events[-1]
    assert event == "terminal"
    assert terminal["state"] == TerminalState.ERROR
    assert terminal["error"] == "The data request took too long."
    assert terminal["reason"] == ErrorType.MCP_TIMEOUT
    assert terminal["idempotency_key"] == _IDEMPOTENCY_KEY
    assert "hmac" not in terminal
    assert "window" not in terminal
    assert turn.list_event_names().count("terminal") == 1
    assert turn.synthesis_calls == 0
    assert turn.finished == [(TerminalState.ERROR, ErrorType.MCP_TIMEOUT)]


@pytest.mark.asyncio
async def test_failed_synthesis_reports_a_fixed_message(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: The user-facing message of a failed synthesis request.
    # Situation: The synthesis request fails with upstream error text.
    # Expectation: The turn ends in an `error` terminal event whose message
    #   is the fixed synthesis failure rather than the upstream text, and is
    #   recorded as `error` with `synthesis_error`.
    upstream = "HTTP 500: upstream detail"

    async def fail_synthesis(**_: object) -> AsyncGenerator[StreamChunk]:
        raise GeminiError(upstream)

    monkeypatch.setattr(chat_pipeline, "async_gemini_stream", fail_synthesis)

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    event, terminal = turn.events[-1]
    assert event == "terminal"
    error_message = terminal["error"]
    assert isinstance(error_message, str)
    assert error_message == SYNTHESIS_FAILED
    assert terminal["reason"] == ErrorType.SYNTHESIS_ERROR
    assert upstream not in error_message
    assert turn.finished == [(TerminalState.ERROR, ErrorType.SYNTHESIS_ERROR)]


@pytest.mark.asyncio
async def test_a_chart_block_is_resolved_and_streamed_in_place(
    turn: _Turn,
) -> None:
    # Test: A chart block the model writes.
    # Situation: The answer holds a paragraph, a chart block over `t1`
    #   naming the one place the table has, and a closing paragraph.
    # Expectation: The blocks are streamed in order with the chart resolved
    #   to the wire shape, the signed answer is the two paragraphs joined by
    #   a blank line with the block stripped, no default chart is added,
    #   the chart contributes a state slot, the follow-ups are grounded in
    #   the variable and the chart's title, and telemetry counts one chart.
    turn.answer = (
        "France is growing.\n\n"
        '```chart\n{"kind": "line", "tables": ["t1"], '
        '"places": ["country/FRA"], "title": "Population of France"}\n```\n\n'
        "It reached 68 million in 2023."
    )

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    chart = {**_DEFAULT_CHART, "title": "Population of France"}
    assert turn.list_blocks() == [
        {"index": 0, "type": "text", "markdown": "France is growing."},
        {"index": 1, "type": "chart", "chart": chart},
        {
            "index": 2,
            "type": "text",
            "markdown": "It reached 68 million in 2023.",
        },
    ]
    _, terminal = turn.events[-2]
    assert terminal["state_slots"] == _SCOPES
    stored = Turn.model_validate(
        {
            "turn_index": 0,
            "idempotency_key": _IDEMPOTENCY_KEY,
            "user_query": _QUESTION,
            "model_response": (
                "France is growing.\n\nIt reached 68 million in 2023."
            ),
            "state_slots": terminal["state_slots"],
            "hmac": terminal["hmac"],
        }
    )
    assert load_transcript(_Request("And Spain?", "key-2", [stored])).turns == [
        stored
    ]
    assert turn.follow_up_topics == [
        ["Total Population in France", "Population of France"]
    ]
    assert turn.telemetry is not None
    assert turn.telemetry.charts_emitted == 1
    assert turn.telemetry.charts_rejected == 0


@pytest.mark.asyncio
async def test_a_rejected_chart_block_gives_way_to_the_default_chart(
    turn: _Turn,
) -> None:
    # Test: The default-chart floor after a rejected block.
    # Situation: The answer's one chart block names a table the turn never
    #   fetched.
    # Expectation: The block is dropped without a trace in the text, the
    #   default chart is appended after the prose, and telemetry counts one
    #   rejected and one emitted chart.
    turn.answer = (
        "France is growing.\n\n"
        '```chart\n{"kind": "line", "tables": ["t9"], "title": "Ghost"}\n```'
    )

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    assert turn.list_texts() == ["France is growing."]
    assert turn.list_charts() == [_DEFAULT_CHART]
    assert turn.telemetry is not None
    assert turn.telemetry.charts_emitted == 1
    assert turn.telemetry.charts_rejected == 1
    assert turn.finished == [(TerminalState.COMPLETE, None)]


@pytest.mark.asyncio
async def test_a_chart_block_naming_an_unused_cached_table_is_rejected(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: Rejecting a chart block that names a cached table outside the
    #   table inventory.
    # Situation: The loop caches an unused `t1` for Germany and `t2` for
    #   France, accepts a series specification over `t2` alone, and
    #   synthesis emits a chart block naming `t1`.
    # Expectation: The `t1` chart block is dropped, the default chart for
    #   `t2` is appended in its place, and telemetry counts one rejected
    #   and one emitted chart.
    unused = _make_table("t1", places=("country/DEU",))
    unused = replace(unused, table=replace(unused.table, facet_id="f_unused"))
    accepted = _make_table("t2", places=("country/FRA",))
    spec = AnalysisSpecification.model_validate(
        {
            "steps": [
                {"step_id": "s1", "script": "analyze_timeseries", "table": "t2"}
            ]
        }
    )

    async def run_loop(
        transcript: Transcript,
        config: AgentConfig,
        tools: Sequence[mcp_client.McpTool],
        telemetry: TurnTelemetry,
        cache: TurnCache,
        **_: object,
    ) -> DiscoveryResult:
        cache.store_fetched(unused)
        cache.store_fetched(accepted)
        digest = await execute_specification(spec, cache)
        assert isinstance(digest, AnalysisDigest)
        return DiscoveryResult(specification=spec, digest=digest)

    monkeypatch.setattr(chat_pipeline, "execute_discovery_loop", run_loop)
    turn.answer = (
        "France is growing.\n\n"
        '```chart\n{"kind": "line", "tables": ["t1"], '
        '"places": ["country/DEU"], "title": "Germany"}\n```'
    )

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    assert turn.list_texts() == ["France is growing."]
    assert turn.list_charts() == [_DEFAULT_CHART]
    assert turn.telemetry is not None
    assert turn.telemetry.charts_emitted == 1
    assert turn.telemetry.charts_rejected == 1
    assert turn.finished == [(TerminalState.COMPLETE, None)]


@pytest.mark.asyncio
async def test_a_chart_block_on_a_no_data_turn_is_rejected(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: Rejecting a chart block when the turn has no computed data.
    # Situation: A top-N turn ends at a bound with one state cohort table
    #   requesting four states with two dates for only one state, so its
    #   default `rank_cohort` step refuses (`has_data=False`) while `t1`
    #   stays cached, and synthesis emits a `line` chart block over `t1`.
    # Expectation: `data_status` reports `has_data=False`, no chart block is
    #   emitted, and telemetry counts zero emitted and one rejected chart.
    ranking = QueryClassification.model_validate(
        {
            "serviceable": True,
            "pattern": "top_n_ranking",
            "geographic_shape": "child_places",
            "requires_computation": True,
        }
    )

    async def classify(*args: object, **_: object) -> Admitted:
        return Admitted(ranking)

    sparse = _make_state_cohort("t1", "Median_Income", "01 02 03 04")
    sparse = replace(
        sparse,
        table=replace(
            sparse.table,
            rows=(
                ObservationRow("geoId/01", "geoId/01", "2022", 1.0),
                ObservationRow("geoId/01", "geoId/01", "2023", 2.0),
            ),
        ),
    )
    monkeypatch.setattr(chat_pipeline, "classify_query", classify)
    _install_loop(monkeypatch, DiscoveryResult(truncated=True), sparse)
    turn.answer = (
        "State income data is sparse.\n\n"
        '```chart\n{"kind": "line", "tables": ["t1"], '
        '"places": ["geoId/01"], "title": "Sparse state"}\n```'
    )

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    assert turn.list_content_payloads("data_status") == [
        {"has_data": False, "truncated": True, "message": TRUNCATED_MESSAGE}
    ]
    assert turn.list_texts() == ["State income data is sparse."]
    assert turn.list_charts() == []
    assert turn.telemetry is not None
    assert turn.telemetry.charts_emitted == 0
    assert turn.telemetry.charts_rejected == 1
    assert turn.finished == [(TerminalState.COMPLETE, None)]


@pytest.mark.asyncio
async def test_a_stalled_synthesis_stream_fails_the_turn(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: The per-chunk idle timeout of the synthesis stream.
    # Situation: The timeout is shortened to 10 ms, and the stream yields
    #   one paragraph and then never yields again.
    # Expectation: The first paragraph is emitted as a text block, and the
    #   turn ends in an `error` terminal event with reason
    #   `synthesis_stream_error` rather than waiting on the stream.
    async def stream_stalled() -> AsyncGenerator[StreamChunk]:
        yield StreamChunk("text", "First paragraph.\n\n")
        await asyncio.Event().wait()

    async def start_stalled_synthesis(
        **_: object,
    ) -> AsyncGenerator[StreamChunk]:
        return stream_stalled()

    monkeypatch.setattr(chat_pipeline, "SYNTHESIS_CHUNK_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(
        chat_pipeline, "async_gemini_stream", start_stalled_synthesis
    )

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    assert turn.list_texts() == ["First paragraph."]
    terminal = _get_only_terminal(turn)
    assert terminal["reason"] == ErrorType.SYNTHESIS_STREAM_ERROR
    assert terminal["error"] == SYNTHESIS_FAILED
    assert turn.finished == [
        (TerminalState.ERROR, ErrorType.SYNTHESIS_STREAM_ERROR)
    ]


@pytest.mark.asyncio
async def test_a_synthesis_stream_stalled_on_open_fails_the_turn(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: The first-chunk timeout when opening the synthesis stream.
    # Situation: `SYNTHESIS_CHUNK_TIMEOUT_SECONDS` is shortened to 10 ms,
    #   and `async_gemini_stream` stalls awaiting the first chunk.
    # Expectation: No block is emitted, and the turn ends in an `error`
    #   terminal event with reason `synthesis_stream_error` and
    #   `SYNTHESIS_FAILED` rather than waiting for the HTTP timeout.
    async def hang_on_first_chunk(
        **_: object,
    ) -> AsyncGenerator[StreamChunk]:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    monkeypatch.setattr(chat_pipeline, "SYNTHESIS_CHUNK_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(
        chat_pipeline, "async_gemini_stream", hang_on_first_chunk
    )

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    assert turn.list_blocks() == []
    terminal = _get_only_terminal(turn)
    assert terminal["reason"] == ErrorType.SYNTHESIS_STREAM_ERROR
    assert terminal["error"] == SYNTHESIS_FAILED
    assert turn.finished == [
        (TerminalState.ERROR, ErrorType.SYNTHESIS_STREAM_ERROR)
    ]


@pytest.mark.asyncio
async def test_cancel_mid_turn_is_recorded_as_canceled(turn: _Turn) -> None:
    # Test: Cancellation while synthesis is streaming.
    # Situation: Synthesis is held open, and the turn is canceled once it
    #   has started.
    # Expectation: `CancelledError` is raised to the caller without a
    #   terminal event, and the turn is recorded as `canceled`.
    turn.synthesis_release.clear()
    task = await _start_and_wait_for(turn, "status")
    async with asyncio.timeout(1):
        while turn.synthesis_calls == 0:
            await asyncio.sleep(0)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert "terminal" not in turn.list_event_names()
    assert turn.finished == [(TerminalState.CANCELED, None)]


@pytest.mark.asyncio
async def test_cancel_after_the_terminal_event_stays_complete(
    turn: _Turn,
) -> None:
    # Test: Cancellation while follow-ups are generated.
    # Situation: Follow-up generation is held open, and the turn is canceled
    #   after the terminal event has been emitted.
    # Expectation: The turn is recorded as `complete` because the answer was
    #   already delivered.
    turn.follow_ups_release.clear()
    task = await _start_and_wait_for(turn, "terminal")

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert turn.finished == [(TerminalState.COMPLETE, None)]


def _get_only_terminal(turn: _Turn) -> JsonObject:
    """Returns the turn's single terminal payload and asserts it came last."""
    assert turn.list_event_names().count("terminal") == 1
    event, terminal = turn.events[-1]
    assert event == "terminal"
    return terminal


@pytest.mark.asyncio
async def test_missing_config_ends_the_turn_before_classify(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: Fail-closed handling when the agent configuration is missing.
    # Situation: `load_config` returns `None`.
    # Expectation: The turn ends immediately in one `error` terminal event with
    #   reason `config_missing`, without calling classify, discovery, or
    #   synthesis.
    monkeypatch.setattr(chat_pipeline, "load_config", lambda: None)

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    terminal = _get_only_terminal(turn)
    assert turn.list_event_names() == ["terminal"]
    assert terminal["state"] == TerminalState.ERROR
    assert terminal["reason"] == ErrorType.CONFIG_MISSING
    assert turn.synthesis_calls == 0
    assert turn.finished == [(TerminalState.ERROR, ErrorType.CONFIG_MISSING)]


@pytest.mark.asyncio
async def test_no_mcp_tools_fails_the_turn_before_synthesis(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: Fail-closed handling when no MCP tools are available.
    # Situation: MCP is enabled, but `async_get_tools` returns an empty list.
    # Expectation: The turn ends in an `error` terminal event with reason
    #   `mcp_unavailable` and a fixed message, without calling synthesis.
    async def return_no_tools() -> list[mcp_client.McpTool]:
        return []

    monkeypatch.setattr(mcp_client, "async_get_tools", return_no_tools)

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    terminal = _get_only_terminal(turn)
    assert terminal["reason"] == ErrorType.MCP_UNAVAILABLE
    assert terminal["error"] == MCP_UNAVAILABLE
    assert turn.synthesis_calls == 0
    assert turn.finished == [(TerminalState.ERROR, ErrorType.MCP_UNAVAILABLE)]


@pytest.mark.asyncio
async def test_a_slow_tool_list_fails_the_turn(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: The timeout for fetching the MCP tool list.
    # Situation: `_MCP_TOOLS_TIMEOUT_SECONDS` is shortened to 10 ms and
    #   `async_get_tools` never returns.
    # Expectation: The turn ends in an `error` terminal event with reason
    #   `mcp_timeout`, without calling synthesis.
    async def hang_tools() -> list[mcp_client.McpTool]:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    monkeypatch.setattr(chat_pipeline, "_MCP_TOOLS_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(mcp_client, "async_get_tools", hang_tools)

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    assert _get_only_terminal(turn)["reason"] == ErrorType.MCP_TIMEOUT
    assert turn.synthesis_calls == 0
    assert turn.finished == [(TerminalState.ERROR, ErrorType.MCP_TIMEOUT)]


@pytest.mark.asyncio
async def test_a_tool_list_missing_required_tools_logs_one_warning(
    monkeypatch: pytest.MonkeyPatch,
    turn: _Turn,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Test: Missing required tools log a warning during discovery.
    # Situation: `async_get_tools` returns only `get_observations` and
    #   `search_indicators`, leaving four required tools missing.
    # Expectation: The discovery phase logs one warning naming the four
    #   missing tools, and the turn still completes.
    async def return_partial_tools() -> list[mcp_client.McpTool]:
        return [
            mcp_client.McpTool(
                name=name,
                description="",
                input_schema={"type": "object", "properties": {}},
            )
            for name in ("get_observations", "search_indicators")
        ]

    monkeypatch.setattr(mcp_client, "async_get_tools", return_partial_tools)

    with caplog.at_level(logging.WARNING, logger=capabilities.logger.name):
        await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    (warning,) = [
        record
        for record in caplog.records
        if record.name == capabilities.logger.name
    ]
    assert warning.levelno == logging.WARNING
    assert warning.getMessage().endswith(
        "missing required tools: get_child_observations, "
        "get_multi_entity_observations, get_variable_metadata, "
        "search_child_indicators"
    )
    assert turn.finished == [(TerminalState.COMPLETE, None)]


@pytest.mark.parametrize(
    ("raw_stream", "expected_charts_emitted"),
    [
        (" \n", 0),
        (
            '```chart\n{"kind": "line", "tables": ["t1"], '
            '"title": "Total Population"}\n```\n',
            1,
        ),
    ],
)
@pytest.mark.asyncio
async def test_an_empty_synthesis_fails_the_turn(
    monkeypatch: pytest.MonkeyPatch,
    turn: _Turn,
    raw_stream: str,
    expected_charts_emitted: int,
) -> None:
    # Test: Fail-closed handling of synthesis output without prose text.
    # Situation: The synthesis stream finishes after yielding either only
    #   whitespace or only a chart block with no accompanying prose.
    # Expectation: The turn ends in an `error` terminal event with reason
    #   `synthesis_empty` and the fixed synthesis message, no text block or
    #   default chart is appended, and telemetry records `charts_emitted`.
    async def stream_blank() -> AsyncGenerator[StreamChunk]:
        yield StreamChunk("text", raw_stream)

    async def start_blank_synthesis(
        **_: object,
    ) -> AsyncGenerator[StreamChunk]:
        return stream_blank()

    monkeypatch.setattr(
        chat_pipeline, "async_gemini_stream", start_blank_synthesis
    )

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    terminal = _get_only_terminal(turn)
    assert terminal["reason"] == ErrorType.SYNTHESIS_EMPTY
    assert terminal["error"] == SYNTHESIS_FAILED
    assert turn.list_texts() == []
    assert len(turn.list_charts()) == expected_charts_emitted
    assert turn.telemetry is not None
    assert turn.telemetry.charts_emitted == expected_charts_emitted
    assert turn.finished == [(TerminalState.ERROR, ErrorType.SYNTHESIS_EMPTY)]


@pytest.mark.asyncio
async def test_a_broken_synthesis_stream_fails_the_turn(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: Fail-closed handling of a synthesis stream that fails mid-stream.
    # Situation: The synthesis stream yields one paragraph and part of the
    #   next, then raises `GeminiStreamError` with upstream error text.
    # Expectation: The completed paragraph is emitted as a text block, the
    #   partial paragraph is not, and the turn ends in an `error` terminal
    #   event with reason `synthesis_stream_error` and the fixed message
    #   rather than the upstream text.
    upstream = "HTTP 503: upstream detail"

    async def stream_broken() -> AsyncGenerator[StreamChunk]:
        yield StreamChunk("text", "First paragraph.\n\nAbout ")
        raise GeminiStreamError(upstream)

    async def start_broken_synthesis(
        **_: object,
    ) -> AsyncGenerator[StreamChunk]:
        return stream_broken()

    monkeypatch.setattr(
        chat_pipeline, "async_gemini_stream", start_broken_synthesis
    )

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    assert turn.list_texts() == ["First paragraph."]
    terminal = _get_only_terminal(turn)
    assert terminal["reason"] == ErrorType.SYNTHESIS_STREAM_ERROR
    assert terminal["error"] == SYNTHESIS_FAILED
    assert turn.finished == [
        (TerminalState.ERROR, ErrorType.SYNTHESIS_STREAM_ERROR)
    ]


@pytest.mark.asyncio
async def test_an_unexpected_exception_ends_the_turn_as_internal_error(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: Catch-all handling for unexpected exceptions inside a phase.
    # Situation: Rendering the synthesis message raises an unexpected
    #   `RuntimeError` containing internal details.
    # Expectation: The turn ends in an `error` terminal event with reason
    #   `internal_error` and the fixed internal-error message.
    detail = "internal detail"

    def fail_render(*args: object) -> str:
        raise RuntimeError(detail)

    monkeypatch.setattr(chat_pipeline, "render_synthesis_message", fail_render)

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    terminal = _get_only_terminal(turn)
    assert terminal["reason"] == ErrorType.INTERNAL_ERROR
    assert terminal["error"] == INTERNAL_ERROR
    assert turn.finished == [(TerminalState.ERROR, ErrorType.INTERNAL_ERROR)]


@pytest.mark.asyncio
async def test_a_follow_up_failure_leaves_the_turn_complete(
    monkeypatch: pytest.MonkeyPatch,
    turn: _Turn,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Test: Best-effort handling of follow-up question generation.
    # Situation: `generate_follow_up_questions` raises a `RuntimeError`
    #   after the terminal event has been emitted.
    # Expectation: The single terminal event is `complete`, no follow-ups are
    #   emitted, the turn is recorded as `complete`, and the failure is
    #   logged as one warning naming the exception type, without a traceback
    #   or the exception text.
    async def fail_follow_ups(
        question: str,
        topics: list[str],
        config: AgentConfig,
        usage: TokenUsage,
    ) -> list[str]:
        raise RuntimeError("follow-up model failed")

    monkeypatch.setattr(
        chat_pipeline, "generate_follow_up_questions", fail_follow_ups
    )

    with caplog.at_level(logging.WARNING, logger=chat_pipeline.__name__):
        await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    assert _get_only_terminal(turn)["state"] == TerminalState.COMPLETE
    assert "follow_ups" not in turn.list_event_names()
    assert turn.finished == [(TerminalState.COMPLETE, None)]
    (record,) = [
        record
        for record in caplog.records
        if record.getMessage().startswith("Follow-up generation failed")
    ]
    assert record.levelno == logging.WARNING
    assert record.getMessage() == "Follow-up generation failed: RuntimeError"
    assert record.exc_info is None


def test_collect_follow_up_topics_leaves_processing_diagnostics_out() -> None:
    # Test: The missing-data notes that become follow-up topics.
    # Situation: A digest with no results carries a data-gap note, a
    #   step-failure diagnostic, a default-analysis diagnostic, and the
    #   generic no-observations fallback note, and no chart was shown.
    # Expectation: The data-gap note is the only topic.
    digest = AnalysisDigest(
        results=(),
        sources=(),
        missing_notes=(
            "No county breakdown of median income exists.",
            "An analysis step failed: the cohort has one place.",
            "The default analysis also failed: the table has no dates.",
            chat_pipeline._NO_OBSERVATIONS_NOTE,
        ),
    )
    discovery = chat_pipeline.DiscoveryPhaseResult(
        digest=digest,
        spec=None,
        has_data=False,
        tool_calls=[],
        sources=[],
        tables=(),
    )

    topics = chat_pipeline.collect_follow_up_topics(discovery, [])

    assert topics == ["No county breakdown of median income exists."]


def test_collect_follow_up_topics_formats_scopes_and_deduplicates() -> None:
    # Test: Scope formatting, refused-step filtering, and deduplication in
    #   `collect_follow_up_topics`.
    # Situation: A digest holds an `OkScriptResult` over a four-place table,
    #   an `OkScriptResult` over a state cohort table, and a
    #   `RefusedScriptResult`, alongside two resolved charts and two data-gap
    #   notes that repeat earlier topics.
    # Expectation: Named places are capped at three, cohort tables use
    #   `" by State"`, refused steps are skipped, and duplicate topics across
    #   results, chart titles, and missing notes are dropped in order.
    multi_place = _make_table(
        "t1",
        places=(
            "country/FRA",
            "country/ESP",
            "country/ITA",
            "country/DEU",
        ),
    )
    cohort = _make_state_cohort("t2", "Median_Income", "01 02 03 04")
    refused = RefusedScriptResult(
        step_id="s3",
        script="rank_cohort",
        variables=("Count_Unemployment",),
        variable_names={"Count_Unemployment": "Unemployment"},
        provenance=Provenance(),
        refusal_reason="no_observations",
    )
    digest = AnalysisDigest.from_results(
        (
            analyze_timeseries(multi_place.table, step_id="s1"),
            rank_cohort(cohort.table, step_id="s2"),
            refused,
        ),
        missing_notes=("Population Trend", "No county breakdown exists."),
    )
    discovery = chat_pipeline.DiscoveryPhaseResult(
        digest=digest,
        spec=None,
        has_data=True,
        tool_calls=[],
        sources=[],
        tables=(multi_place, cohort),
    )
    charts = [
        ResolvedLineChart(
            title="Median_Income by State",
            variable_dcids=("Median_Income",),
            scope=PlaceList(("geoId/01",)),
        ),
        ResolvedLineChart(
            title="Population Trend",
            variable_dcids=("Count_Person",),
            scope=PlaceList(("country/FRA",)),
        ),
    ]

    topics = chat_pipeline.collect_follow_up_topics(discovery, charts)

    assert topics == [
        "Total Population in Deu, Esp, France",
        "Median_Income by State",
        "Population Trend",
        "No county breakdown exists.",
    ]


@pytest.mark.asyncio
async def test_the_classify_phase_opens_the_stream_and_guides_the_turn(
    turn: _Turn,
) -> None:
    # Test: The classified outcome of the classify phase.
    # Situation: The classifier admits the query as a single-point lookup
    #   and every later phase succeeds.
    # Expectation: The stream opens with a `classify` status frame followed
    #   by the `discovery` one, the classification reaches the discovery
    #   loop, the synthesis system instruction opens with the prompt,
    #   carries the synthesis contract, and ends with the synthesis half of
    #   the pattern's directive, and telemetry records the pattern and the
    #   classify phase duration.
    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    assert turn.events[0] == (
        "status",
        {"phase": "classify", "message": CLASSIFY_STATUS},
    )
    statuses = [
        data["phase"] for event, data in turn.events if event == "status"
    ]
    assert statuses[:2] == ["classify", "discovery"]
    assert turn.loop_classifications == [_CLASSIFICATION]
    (instruction,) = turn.synthesis_instructions
    assert instruction.startswith(
        f"Write prose.\n\n{load_prompt_contract('synthesis')}"
    )
    assert instruction.endswith(
        build_pattern_directive(_CLASSIFICATION, "synthesis")
    )
    assert turn.telemetry is not None
    assert turn.telemetry.pattern == "single_point"
    assert "classify" in turn.telemetry.phase_durations_ms
    assert turn.finished == [(TerminalState.COMPLETE, None)]


@pytest.mark.parametrize(
    ("reason", "message"),
    [
        (RefusedReason.ADVERSARIAL, REFUSED_MESSAGE),
        (
            RefusedReason.OFF_DOMAIN,
            "That request is outside the public statistical data this "
            "service covers (brand-specific coffee prices). Ask about a "
            "demographic, economic, health, climate, or social indicator "
            "for a place.",
        ),
    ],
)
@pytest.mark.asyncio
async def test_a_refusal_ends_the_turn_in_one_refused_frame(
    monkeypatch: pytest.MonkeyPatch,
    turn: _Turn,
    reason: RefusedReason,
    message: str,
) -> None:
    # Test: The refused outcome of the classify phase.
    # Situation: The classify phase refuses the query as adversarial or as
    #   off-domain.
    # Expectation: The stream is the `classify` status frame and one
    #   `refused` terminal frame carrying the idempotency key, the reason,
    #   and the message, with no `error` key and no signing fields; no
    #   discovery loop or synthesis runs; the turn is recorded as `refused`
    #   with the reason and without a pattern.
    async def refuse_classify(*args: object, **_: object) -> Admitted:
        raise TurnRefusedError(reason, message)

    monkeypatch.setattr(chat_pipeline, "classify_query", refuse_classify)

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    assert turn.list_event_names() == ["status", "terminal"]
    assert turn.events[1][1] == {
        "state": TerminalState.REFUSED,
        "idempotency_key": _IDEMPOTENCY_KEY,
        "reason": reason,
        "message": message,
    }
    assert turn.loop_classifications == []
    assert turn.synthesis_calls == 0
    assert turn.finished == [(TerminalState.REFUSED, reason)]
    assert turn.telemetry is not None
    assert turn.telemetry.pattern is None


@pytest.mark.asyncio
async def test_a_clarification_is_streamed_and_signed_with_empty_slots(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: The clarification outcome of the classify phase.
    # Situation: The classifier asks which Georgia the user means.
    # Expectation: The question is emitted as the one text block, the turn
    #   ends in a signed `complete` frame with empty state slots and a
    #   one-turn window, no data, sources, charts, or follow-ups are
    #   emitted, no discovery loop or synthesis runs, the pattern is
    #   recorded, and the next request carrying the turn verifies.
    async def clarify_classify(*args: object, **_: object) -> Clarification:
        return Clarification(_CLARIFICATION_QUESTION, _CLASSIFICATION)

    monkeypatch.setattr(chat_pipeline, "classify_query", clarify_classify)
    question = "What is the population of Georgia?"
    transcript = Transcript(
        turns=[],
        compacted_summary=None,
        current_query=question,
        current_idempotency_key=_IDEMPOTENCY_KEY,
    )

    await chat_pipeline.run_turn(transcript, turn.emit)

    assert turn.list_event_names() == ["status", "content", "terminal"]
    assert turn.events[1][1] == {
        "block": {
            "index": 0,
            "type": "text",
            "markdown": _CLARIFICATION_QUESTION,
        }
    }
    terminal = turn.events[2][1]
    assert terminal["state"] == TerminalState.COMPLETE
    assert terminal["turn_index"] == 0
    assert terminal["state_slots"] == {"scopes": []}
    assert terminal["window"] == [
        {
            "turn_index": 0,
            "idempotency_key": _IDEMPOTENCY_KEY,
            "hmac": terminal["hmac"],
        }
    ]
    assert turn.loop_classifications == []
    assert turn.synthesis_calls == 0
    assert turn.finished == [(TerminalState.COMPLETE, None)]
    assert turn.telemetry is not None
    assert turn.telemetry.pattern == "single_point"
    stored = Turn.model_validate(
        {
            "turn_index": terminal["turn_index"],
            "idempotency_key": terminal["idempotency_key"],
            "user_query": question,
            "model_response": _CLARIFICATION_QUESTION,
            "state_slots": terminal["state_slots"],
            "hmac": terminal["hmac"],
        }
    )
    loaded = load_transcript(_Request("The country", "key-2", [stored]))
    assert loaded.turns == [stored]


@pytest.mark.asyncio
async def test_a_classifier_failure_proceeds_as_exploratory(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: Fall-through when the classifier failed.
    # Situation: The classify phase admits the query without a verdict.
    # Expectation: The turn completes as usual, the discovery loop receives
    #   no classification, the synthesis system instruction is the prompt
    #   and the synthesis contract with no directive, and telemetry records
    #   the pattern as `exploratory`.
    async def return_unclassified(*args: object, **_: object) -> Admitted:
        return Admitted(None)

    monkeypatch.setattr(chat_pipeline, "classify_query", return_unclassified)

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    assert turn.loop_classifications == [None]
    assert turn.synthesis_instructions == [
        f"Write prose.\n\n{load_prompt_contract('synthesis')}"
    ]
    assert turn.telemetry is not None
    assert turn.telemetry.pattern == "exploratory"
    assert turn.finished == [(TerminalState.COMPLETE, None)]


@pytest.mark.parametrize(
    "phase_call", ["classify_query", "execute_discovery_loop"]
)
@pytest.mark.asyncio
async def test_a_blocked_call_before_synthesis_refuses_the_turn(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn, phase_call: str
) -> None:
    # Test: Central handling of a blocked model call in `run_turn`.
    # Situation: `classify_query` or `execute_discovery_loop` raises
    #   `GeminiBlockedError("PROHIBITED_CONTENT")`.
    # Expectation: The turn ends in a `refused` terminal frame with reason
    #   `safety_blocked` and the fixed message, synthesis never runs, and
    #   the turn is recorded as `refused` with `safety_blocked`.
    async def raise_blocked(*args: object, **_: object) -> None:
        raise GeminiBlockedError("PROHIBITED_CONTENT")

    monkeypatch.setattr(chat_pipeline, phase_call, raise_blocked)

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    terminal = _get_only_terminal(turn)
    assert terminal["state"] == TerminalState.REFUSED
    assert terminal["reason"] == RefusedReason.SAFETY_BLOCKED
    assert terminal["message"] == REFUSED_MESSAGE
    assert "error" not in terminal
    assert turn.synthesis_calls == 0
    assert turn.finished == [
        (TerminalState.REFUSED, RefusedReason.SAFETY_BLOCKED)
    ]


@pytest.mark.asyncio
async def test_a_blocked_synthesis_prompt_refuses_the_turn(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: Mapping of a blocked prompt in synthesis.
    # Situation: The synthesis request is blocked before any text streams.
    # Expectation: No block is emitted, the turn ends in a `refused`
    #   terminal frame with reason `safety_blocked`, and it is recorded as
    #   `refused` with `safety_blocked`.
    async def raise_blocked_synthesis(
        **_: object,
    ) -> AsyncGenerator[StreamChunk]:
        raise GeminiBlockedError("SAFETY")

    monkeypatch.setattr(
        chat_pipeline, "async_gemini_stream", raise_blocked_synthesis
    )

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    assert turn.list_blocks() == []
    terminal = _get_only_terminal(turn)
    assert terminal["state"] == TerminalState.REFUSED
    assert terminal["reason"] == RefusedReason.SAFETY_BLOCKED
    assert turn.finished == [
        (TerminalState.REFUSED, RefusedReason.SAFETY_BLOCKED)
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "chunk",
    [
        pytest.param(
            StreamChunk("thought", "Reviewing data."),
            id="after_thought",
        ),
        pytest.param(
            StreamChunk("text", "Unfinished first paragraph"),
            id="after_buffered_text_before_block",
        ),
    ],
)
async def test_a_synthesis_stream_blocked_before_any_block_refuses_the_turn(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn, chunk: StreamChunk
) -> None:
    # Test: Mid-stream safety block in `run_synthesis_phase` before any answer
    #   block has been emitted.
    # Situation: The synthesis stream yields either a thought chunk or partial
    #   paragraph text that has not yet completed a block, and then raises
    #   `GeminiBlockedError("SAFETY")`.
    # Expectation: No `content {block}` frame is emitted, the turn ends in a
    #   `refused` terminal frame with `reason="safety_blocked"`, and telemetry
    #   records `("refused", "safety_blocked")`.
    async def stream_blocked() -> AsyncGenerator[StreamChunk]:
        yield chunk
        raise GeminiBlockedError("SAFETY")

    async def start_synthesis(**_: object) -> AsyncGenerator[StreamChunk]:
        return stream_blocked()

    monkeypatch.setattr(chat_pipeline, "async_gemini_stream", start_synthesis)

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    if chunk.kind == "thought":
        assert (
            "thought",
            {"thought": "Reviewing data.", "phase": "synthesis"},
        ) in turn.events
    assert turn.list_blocks() == []
    terminal = _get_only_terminal(turn)
    assert terminal["state"] == TerminalState.REFUSED
    assert terminal["reason"] == RefusedReason.SAFETY_BLOCKED
    assert terminal["message"] == REFUSED_MESSAGE
    assert turn.finished == [
        (TerminalState.REFUSED, RefusedReason.SAFETY_BLOCKED)
    ]


@pytest.mark.asyncio
async def test_a_synthesis_stream_blocked_after_text_fails_as_stream_error(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: Mid-stream safety block in `run_synthesis_phase` after answer text.
    # Situation: The synthesis stream yields one paragraph and part of the next,
    #   then raises `GeminiBlockedError("SAFETY")`.
    # Expectation: The completed paragraph is emitted as a text block, and the
    #   turn ends in an `error` terminal frame with
    #   `reason="synthesis_stream_error"` and `SYNTHESIS_FAILED` rather than
    #   `refused`.
    async def stream_blocked_after_text() -> AsyncGenerator[StreamChunk]:
        yield StreamChunk("text", "First paragraph.\n\nAbout ")
        raise GeminiBlockedError("SAFETY")

    async def start_synthesis(**_: object) -> AsyncGenerator[StreamChunk]:
        return stream_blocked_after_text()

    monkeypatch.setattr(chat_pipeline, "async_gemini_stream", start_synthesis)

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    assert turn.list_texts() == ["First paragraph."]
    terminal = _get_only_terminal(turn)
    assert terminal["state"] == TerminalState.ERROR
    assert terminal["reason"] == ErrorType.SYNTHESIS_STREAM_ERROR
    assert terminal["error"] == SYNTHESIS_FAILED
    assert turn.finished == [
        (TerminalState.ERROR, ErrorType.SYNTHESIS_STREAM_ERROR)
    ]


@pytest.mark.asyncio
async def test_run_turn_aborts_immediately_when_chat_is_disabled(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: `ENABLE_CHAT` off switch in `run_turn`.
    # Situation: `ENABLE_CHAT` is set to `"false"`.
    # Expectation: `run_turn` emits only a single `error` terminal frame with
    #   `reason="chat_disabled"` and `CHAT_DISABLED`, makes no classifier, MCP,
    #   or synthesis calls, and records `("refused", "chat_disabled")` in
    #   telemetry so disabled turns are logged at INFO rather than ERROR.
    monkeypatch.setenv("ENABLE_CHAT", "false")

    async def fail_classify(*args: object, **_: object) -> Admitted:
        pytest.fail("classify_query should not run when chat is disabled")

    async def fail_tools() -> list[mcp_client.McpTool]:
        pytest.fail("async_get_tools should not run when chat is disabled")

    monkeypatch.setattr(chat_pipeline, "classify_query", fail_classify)
    monkeypatch.setattr(mcp_client, "async_get_tools", fail_tools)

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    assert turn.events == [
        (
            "terminal",
            {
                "state": TerminalState.ERROR,
                "idempotency_key": _IDEMPOTENCY_KEY,
                "error": CHAT_DISABLED,
                "reason": ErrorType.CHAT_DISABLED,
            },
        )
    ]
    assert turn.synthesis_calls == 0
    assert turn.finished == [(TerminalState.REFUSED, ErrorType.CHAT_DISABLED)]


# The serialized frames of a complete turn whose stubs also report a thought
# from discovery and from synthesis. The HMAC is deterministic because the
# `signing_secret` fixture fixes the signing key.
_WIRE_HMAC = "bab7873e1b550debfd0193a70934a1781d7cae19c5be8eea5e6dfe069f2917dc"
_WIRE_FRAMES: list[tuple[EventName, str]] = [
    (
        "status",
        '{"phase": "classify", "message": "Understanding the question..."}',
    ),
    ("status", '{"phase": "discovery", "message": "Querying data tools..."}'),
    ("thought", '{"thought": "Looking up France.", "phase": "discovery"}'),
    (
        "content",
        '{"tool_call": {"name": "fetch_observations", "arguments": '
        '{"variable_dcid": "Count_Person", "place_dcids": ["country/FRA"]}, '
        '"result": "{\\"table_id\\": \\"t1\\", \\"row_count\\": 2}", '
        '"status": "success"}}',
    ),
    (
        "content",
        '{"data_status": {"has_data": true, "truncated": false, '
        '"message": null}}',
    ),
    ("content", '{"sources": [{"name": "INSEE", "url": "https://insee.fr/"}]}'),
    ("status", '{"phase": "synthesis", "message": "Generating response..."}'),
    ("thought", '{"thought": "Writing the answer.", "phase": "synthesis"}'),
    (
        "content",
        '{"block": {"index": 0, "type": "text", '
        '"markdown": "About 68 million."}}',
    ),
    (
        "content",
        '{"block": {"index": 1, "type": "chart", "chart": '
        '{"viz_type": "line", "title": "Total Population", '
        '"variable_dcids": ["Count_Person"], '
        '"place_dcids": ["country/FRA"], '
        '"facet_ids": {"Count_Person": "f1"}}}}',
    ),
    (
        "terminal",
        '{"state": "complete", "idempotency_key": "test-idempotency-key", '
        f'"turn_index": 0, "hmac": "{_WIRE_HMAC}", "state_slots": '
        '{"scopes": [{"places": {"country/FRA": "France"}, '
        '"parent_place": null, "child_place_type": null, "variables": '
        '{"Count_Person": "Total Population"}, "date_range": '
        '["2022", "2023"]}, {"places": {"country/FRA": "France"}, '
        '"parent_place": null, "child_place_type": null, "variables": '
        '{"Count_Person": "Total Population"}, "date_range": null}]}, '
        '"compacted_summary": null, "window": '
        '[{"turn_index": 0, "idempotency_key": "test-idempotency-key", '
        f'"hmac": "{_WIRE_HMAC}"}}]}}',
    ),
    ("follow_ups", '{"follow_up_questions": ["And Spain?"]}'),
]


@pytest.mark.asyncio
async def test_a_complete_turn_serializes_to_the_recorded_frames(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: Wire equivalence of a complete turn.
    # Situation: Every phase succeeds, and the discovery loop and synthesis
    #   each report one thought, so the turn emits every frame type of a
    #   complete turn.
    # Expectation: The event names and the JSON `data` strings, serialized
    #   as the chat route serializes them, equal the recorded sequence.
    async def run_discovery(
        transcript: Transcript,
        config: AgentConfig,
        tools: Sequence[mcp_client.McpTool],
        telemetry: TurnTelemetry,
        cache: TurnCache,
        *,
        thought_callback: Callable[[str], None],
        **_: object,
    ) -> DiscoveryResult:
        thought_callback("Looking up France.")
        return await _run_accepted_loop(cache)

    async def stream_answer() -> AsyncGenerator[StreamChunk]:
        yield StreamChunk("thought", "Writing the answer.")
        yield StreamChunk("text", _ANSWER)

    async def start_synthesis(**_: object) -> AsyncGenerator[StreamChunk]:
        return stream_answer()

    monkeypatch.setattr(chat_pipeline, "execute_discovery_loop", run_discovery)
    monkeypatch.setattr(chat_pipeline, "async_gemini_stream", start_synthesis)

    await chat_pipeline.run_turn(_TRANSCRIPT, turn.emit)

    serialized = [(event, json.dumps(data)) for event, data in turn.events]
    assert serialized == _WIRE_FRAMES
