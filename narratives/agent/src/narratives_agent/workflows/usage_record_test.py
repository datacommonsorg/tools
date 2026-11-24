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
"""Tests for the `chat_turn` record builder in `usage_record`.

Verifies that:
1. The written record has every key of the schema, in order, on a turn that
   ran every phase and on a turn that did not run any phase. On the second
   turn, a value that does not apply is `null`, `false`, zero, or an empty
   list.
2. The severity and the message follow the terminal state, and a caller
   cannot set them or the event name and schema version.
3. The record identifies the turn and the conversation, and reports the
   turn's index, whether it was signed, and whether signing compacted the
   conversation.
4. `outcome`, `outcome_reason`, `refusal_stage`, `has_data`, and `pattern`
   follow the terminal state, the reason, the digest, and the phases that
   ran.
5. The record lists the phase durations in a fixed order and marks
   `processing` as nested. It lists the token counts of each model call
   that reported its role and model, and it sorts the tool counts by tool
   name.
6. `build_usage_record` raises `ValueError` for a turn that has not ended.
   A record with every list at its bound stays under the size limit of one
   line.
7. `content` is `None` by default (`include_content=False`) even when the
   turn recorded user-visible outputs, and holds a `TurnContent` when
   `include_content=True`, shortening fields in priority order so the
   serialized line never exceeds `MAX_RECORD_LINE_BYTES`.
"""

import dataclasses
import json
import logging
import time

import pytest

from narratives_agent import telemetry as telemetry_module
from narratives_agent.analytics.digest import AnalysisDigest
from narratives_agent.analytics.metrics import ScriptName
from narratives_agent.analytics.provenance import Provenance
from narratives_agent.analytics.tables import ObservationRow, ObservationTable
from narratives_agent.analytics.timeseries import analyze_timeseries
from narratives_agent.json_value import JsonObject
from narratives_agent.telemetry import (
    MAX_RECORD_LINE_BYTES,
    TURN_PHASES,
    ErrorType,
    TerminalState,
    TitleOutcome,
    TokenCounts,
    TurnPhase,
    TurnTelemetry,
    write_structured_record,
)
from narratives_agent.workflows.charts import (
    MAX_CHARTS_PER_TURN,
    PlaceList,
    ResolvedLineChart,
)
from narratives_agent.workflows.classify import RefusedReason
from narratives_agent.workflows.mcp_loop import (
    DISCOVERY_TOOL_NAMES,
    MAX_ITERATIONS,
    SERVER_FUNCTION_NAMES,
)
from narratives_agent.workflows.title import MAX_TITLE_CHARS
from narratives_agent.workflows.transcript import (
    MAX_QUERY_CHARS,
    MAX_RESPONSE_CHARS,
    MAX_TURN_INDEX,
    ConversationStateSlots,
    Transcript,
    Turn,
)
from narratives_agent.workflows.turn_record import TurnRecord
from narratives_agent.workflows.usage_record import (
    RefusalStage,
    TokenCall,
    TokenTotals,
    TurnContent,
    TurnOutcome,
    UsageRecord,
    build_usage_record,
)

_TURN_ID = "fedcba9876543210fedcba9876543210"
_CONVERSATION_ID = "0123456789abcdef0123456789abcdef"
_BUILD_SHA = "0a1b2c3"
# `_KEYS` lists the keys of the `chat_turn` record, in the order of the
# schema.
_KEYS = [
    "severity",
    "message",
    "event",
    "schema_version",
    "build_sha",
    "turn_id",
    "conversation_id",
    "turn_index",
    "is_signed",
    "was_compacted",
    "terminal_state",
    "outcome",
    "outcome_reason",
    "refusal_stage",
    "has_data",
    "is_clarification",
    "is_truncated",
    "title_outcome",
    "pattern",
    "duration_ms",
    "phase_durations",
    "tokens",
    "token_calls",
    "mcp_iterations",
    "tool_call_count",
    "tool_call_counts",
    "tables_fetched",
    "total_rows_fetched",
    "scripts",
    "processing_retries",
    "charts_emitted",
    "charts_rejected",
    "content",
]
# `_TOOL_LABELS` holds the two labels that the discovery loop records in
# place of a tool name.
_TOOL_LABELS = ("unknown", "server_report_unavailable")


def _make_transcript(*turn_indexes: int) -> Transcript:
    """Builds a transcript whose earlier turns have `turn_indexes`."""
    return Transcript(
        turns=[
            Turn(
                turn_index=index,
                idempotency_key=f"key-{index}",
                user_query=f"Question {index}",
                model_response=f"Answer {index}",
                state_slots=ConversationStateSlots(),
                hmac="0" * 64,
            )
            for index in turn_indexes
        ],
        compacted_summary=None,
        conversation_id=_CONVERSATION_ID,
        current_query="Current question",
        current_idempotency_key="key-current",
    )


def _make_record(
    state: TerminalState = TerminalState.COMPLETE,
    reason: ErrorType | RefusedReason | None = None,
    *,
    phases: tuple[TurnPhase, ...] = (),
) -> TurnRecord:
    """Builds the record of a turn that ended after recording `phases`."""
    record = TurnRecord(telemetry=TurnTelemetry(turn_id=_TURN_ID))
    for phase in phases:
        record.telemetry.phase_durations_ms[phase] = 1.0
    record.terminal_state = state
    record.terminal_reason = reason
    record.telemetry.finish(state, reason)
    return record


def _finish_turn(
    monkeypatch: pytest.MonkeyPatch,
    record: TurnRecord,
    state: TerminalState,
    reason: ErrorType | RefusedReason | None = None,
    *,
    seconds: float,
) -> None:
    """Ends the turn of `record` in `state`, `seconds` after it started."""
    telemetry = record.telemetry
    monkeypatch.setattr(time, "monotonic", lambda: telemetry._start + seconds)
    record.terminal_state = state
    record.terminal_reason = reason
    telemetry.finish(state, reason)


def _make_digest(*, has_data: bool) -> AnalysisDigest:
    """Builds a digest with one computed result, or without a result."""
    if not has_data:
        return AnalysisDigest(results=())
    table = ObservationTable(
        variable_dcid="Count_Person",
        variable_name="Total Population",
        unit="Person",
        scaling_factor=None,
        provenance=Provenance(),
        rows=(
            ObservationRow("country/FRA", "France", "2022", 67.8e6),
            ObservationRow("country/FRA", "France", "2023", 68.2e6),
        ),
        requested_places=("country/FRA",),
        place_names={"country/FRA": "France"},
    )
    return AnalysisDigest.from_results(
        (analyze_timeseries(table, step_id="s1"),)
    )


def _build_record(
    record: TurnRecord, transcript: Transcript | None = None
) -> UsageRecord:
    """Builds the usage record of `record`, on a first turn by default."""
    return build_usage_record(
        record, transcript or _make_transcript(), build_sha=_BUILD_SHA
    )


def _write_record(record: UsageRecord, lines: list[str]) -> JsonObject:
    """Writes `record` and returns the one line it produced, parsed."""
    write_structured_record(record)
    (line,) = lines
    parsed = json.loads(line)
    assert isinstance(parsed, dict)
    return parsed


def test_a_turn_that_ran_every_phase_writes_every_key_with_its_value(
    monkeypatch: pytest.MonkeyPatch, structured_lines: list[str]
) -> None:
    # Test: The written `chat_turn` record of a turn where every key applies.
    # Situation: A follow-up turn after the turn with index 4 completes with
    #   data after 604.75 ms. The telemetry holds a duration for all six
    #   phases, in the order in which the phases end. The turn called three
    #   tools, made two model calls, ran two scripts, was truncated, and was
    #   signed with compaction.
    # Expectation: The line holds the schema's keys in order, each with the
    #   value that the turn recorded. The phases are in the fixed order with
    #   only `processing` nested, and the tools are sorted by name.
    record = TurnRecord(telemetry=TurnTelemetry(turn_id=_TURN_ID))
    telemetry = record.telemetry
    telemetry.pattern = "top_n_ranking"
    telemetry.mcp_iterations = 3
    telemetry.scripts = ["align_cohort", "rank_cohort"]
    telemetry.tables_fetched = 2
    telemetry.total_rows_fetched = 1_200
    telemetry.processing_retries = 1
    telemetry.charts_emitted = 4
    telemetry.charts_rejected = 5
    telemetry.title_outcome = TitleOutcome.EMITTED
    telemetry.phase_durations_ms.update(
        {
            "classify": 10.5,
            "processing": 20.25,
            "discovery": 300.0,
            "synthesis": 200.0,
            "finalize": 4.0,
            "follow_ups": 70.0,
        }
    )
    for tool in (
        "search_indicators",
        "fetch_observations",
        "search_indicators",
        "submit_specification",
    ):
        telemetry.record_tool_call(tool)
    telemetry.tokens.add(
        TokenCounts(prompt=100, candidates=10, thoughts=1, total=111),
        phase="classify",
        model="model-lite",
    )
    telemetry.tokens.add(
        TokenCounts(prompt=200, candidates=20, thoughts=2, total=222),
        phase="discovery",
        model="model-flash",
        round_number=1,
    )
    record.digest = _make_digest(has_data=True)
    record.loop_result.truncated = True
    record.is_signed = True
    record.was_compacted = True
    _finish_turn(monkeypatch, record, TerminalState.COMPLETE, seconds=0.60475)

    written = _write_record(
        _build_record(record, _make_transcript(3, 4)), structured_lines
    )

    assert list(written) == _KEYS
    assert written == {
        "severity": "INFO",
        "message": "chat turn complete",
        "event": "chat_turn",
        "schema_version": 2,
        "build_sha": _BUILD_SHA,
        "turn_id": _TURN_ID,
        "conversation_id": _CONVERSATION_ID,
        "turn_index": 5,
        "is_signed": True,
        "was_compacted": True,
        "terminal_state": "complete",
        "outcome": "answered_with_data",
        "outcome_reason": None,
        "refusal_stage": None,
        "has_data": True,
        "is_clarification": False,
        "is_truncated": True,
        "title_outcome": "emitted",
        "pattern": "top_n_ranking",
        "duration_ms": 604.75,
        "phase_durations": [
            {"phase": "classify", "duration_ms": 10.5, "is_nested": False},
            {"phase": "discovery", "duration_ms": 300.0, "is_nested": False},
            {"phase": "processing", "duration_ms": 20.25, "is_nested": True},
            {"phase": "synthesis", "duration_ms": 200.0, "is_nested": False},
            {"phase": "finalize", "duration_ms": 4.0, "is_nested": False},
            {"phase": "follow_ups", "duration_ms": 70.0, "is_nested": False},
        ],
        "tokens": {
            "prompt_token_count": 300,
            "candidates_token_count": 30,
            "thoughts_token_count": 3,
            "total_token_count": 333,
            "call_count": 2,
        },
        "token_calls": [
            {
                "role": "classify",
                "model": "model-lite",
                "round_number": None,
                "prompt_token_count": 100,
                "candidates_token_count": 10,
                "thoughts_token_count": 1,
                "total_token_count": 111,
            },
            {
                "role": "discovery",
                "model": "model-flash",
                "round_number": 1,
                "prompt_token_count": 200,
                "candidates_token_count": 20,
                "thoughts_token_count": 2,
                "total_token_count": 222,
            },
        ],
        "mcp_iterations": 3,
        "tool_call_count": 4,
        "tool_call_counts": [
            {"tool": "fetch_observations", "count": 1},
            {"tool": "search_indicators", "count": 2},
            {"tool": "submit_specification", "count": 1},
        ],
        "tables_fetched": 2,
        "total_rows_fetched": 1_200,
        "scripts": ["align_cohort", "rank_cohort"],
        "processing_retries": 1,
        "charts_emitted": 4,
        "charts_rejected": 5,
        "content": None,
    }


def test_a_turn_that_ran_no_phase_writes_every_key_with_its_empty_value(
    monkeypatch: pytest.MonkeyPatch, structured_lines: list[str]
) -> None:
    # Test: The written `chat_turn` record of a turn where few keys apply.
    # Situation: The first turn of a conversation ends as refused with
    #   reason `chat_disabled` after 12.5 ms, before any phase ran, on a
    #   deployment that does not set a build SHA.
    # Expectation: The line still holds every key of the schema, in order.
    #   A key that does not apply is `null`, `false`, zero, or an empty
    #   list.
    record = TurnRecord(telemetry=TurnTelemetry(turn_id=_TURN_ID))
    _finish_turn(
        monkeypatch,
        record,
        TerminalState.REFUSED,
        ErrorType.CHAT_DISABLED,
        seconds=0.0125,
    )

    written = _write_record(
        build_usage_record(record, _make_transcript(), build_sha=None),
        structured_lines,
    )

    assert list(written) == _KEYS
    assert written == {
        "severity": "INFO",
        "message": "chat turn refused",
        "event": "chat_turn",
        "schema_version": 2,
        "build_sha": None,
        "turn_id": _TURN_ID,
        "conversation_id": _CONVERSATION_ID,
        "turn_index": 0,
        "is_signed": False,
        "was_compacted": False,
        "terminal_state": "refused",
        "outcome": "refused",
        "outcome_reason": "chat_disabled",
        "refusal_stage": "availability",
        "has_data": False,
        "is_clarification": False,
        "is_truncated": False,
        "title_outcome": "not_requested",
        "pattern": None,
        "duration_ms": 12.5,
        "phase_durations": [],
        "tokens": {
            "prompt_token_count": 0,
            "candidates_token_count": 0,
            "thoughts_token_count": 0,
            "total_token_count": 0,
            "call_count": 0,
        },
        "token_calls": [],
        "mcp_iterations": 0,
        "tool_call_count": 0,
        "tool_call_counts": [],
        "tables_fetched": 0,
        "total_rows_fetched": 0,
        "scripts": [],
        "processing_retries": 0,
        "charts_emitted": 0,
        "charts_rejected": 0,
        "content": None,
    }


def test_a_caller_cannot_set_the_first_four_keys() -> None:
    # Test: The fields of the record that a caller cannot pass in.
    # Situation: The test inspects the dataclass fields of `UsageRecord`.
    # Expectation: `severity`, `message`, `event`, and `schema_version` are
    #   the only fields that the constructor does not accept, so the message
    #   cannot hold text that a caller chose.
    fixed = [
        field.name
        for field in dataclasses.fields(UsageRecord)
        if not field.init
    ]

    assert fixed == ["severity", "message", "event", "schema_version"]


@pytest.mark.parametrize(
    ("state", "reason", "severity", "message"),
    [
        (TerminalState.COMPLETE, None, "INFO", "chat turn complete"),
        (
            TerminalState.REFUSED,
            RefusedReason.OFF_DOMAIN,
            "INFO",
            "chat turn refused",
        ),
        (
            TerminalState.ERROR,
            ErrorType.MCP_TIMEOUT,
            "ERROR",
            "chat turn error",
        ),
        (TerminalState.CANCELED, None, "INFO", "chat turn canceled"),
    ],
)
def test_the_severity_and_the_message_follow_the_terminal_state(
    state: TerminalState,
    reason: ErrorType | RefusedReason | None,
    severity: str,
    message: str,
) -> None:
    # Test: The severity and the message of the record.
    # Situation: A turn ends in each of the four terminal states.
    # Expectation: The record keeps the terminal state. Only a turn that
    #   ended in an error has severity `ERROR`, and the message is `chat
    #   turn` followed by the state.
    usage = _build_record(_make_record(state, reason))

    assert usage.terminal_state == state
    assert usage.severity == severity
    assert usage.message == message


@pytest.mark.parametrize(
    ("turn_indexes", "is_signed", "was_compacted", "turn_index"),
    [
        pytest.param((), True, False, 0, id="first turn"),
        pytest.param((0, 1), True, False, 2, id="follow-up turn"),
        pytest.param(
            (2, 3, 4, 5, 6, 7), True, True, 8, id="turn that compacts"
        ),
        pytest.param((), False, False, 0, id="unsigned first turn"),
        pytest.param((4, 5), False, False, 6, id="unsigned follow-up turn"),
    ],
)
def test_the_record_reports_the_turn_index_and_the_signing(
    turn_indexes: tuple[int, ...],
    is_signed: bool,
    was_compacted: bool,
    turn_index: int,
) -> None:
    # Test: `turn_index`, `is_signed`, and `was_compacted`.
    # Situation: A turn runs with the earlier turns of the given indexes,
    #   and the signing step recorded whether the turn was signed and
    #   whether signing compacted the conversation.
    # Expectation: The index is one more than the last earlier turn, or 0
    #   for a first turn, whether or not the turn was signed. The two flags
    #   are the ones that the signing step recorded.
    record = _make_record()
    record.is_signed = is_signed
    record.was_compacted = was_compacted

    usage = _build_record(record, _make_transcript(*turn_indexes))

    assert usage.turn_index == turn_index
    assert usage.is_signed is is_signed
    assert usage.was_compacted is was_compacted


@pytest.mark.parametrize(
    ("state", "is_clarification", "has_data", "outcome"),
    [
        (
            TerminalState.COMPLETE,
            False,
            True,
            TurnOutcome.ANSWERED_WITH_DATA,
        ),
        (
            TerminalState.COMPLETE,
            False,
            False,
            TurnOutcome.ANSWERED_WITHOUT_DATA,
        ),
        (TerminalState.COMPLETE, True, False, TurnOutcome.CLARIFIED),
        (TerminalState.REFUSED, False, True, TurnOutcome.REFUSED),
        (TerminalState.ERROR, False, True, TurnOutcome.ERROR),
        (TerminalState.CANCELED, False, True, TurnOutcome.CANCELED),
    ],
)
def test_the_outcome_follows_the_terminal_state_and_the_answer(
    state: TerminalState,
    is_clarification: bool,
    has_data: bool,
    outcome: TurnOutcome,
) -> None:
    # Test: The six values of `outcome`.
    # Situation: A turn completes with data, completes without data,
    #   completes with a clarification question, or ends as refused, failed,
    #   or canceled after its analysis produced data.
    # Expectation: A completed turn is `answered_with_data`,
    #   `answered_without_data`, or `clarified`. Any other turn has the
    #   outcome of its terminal state, even when its analysis produced
    #   data.
    record = _make_record(state)
    record.is_clarification = is_clarification
    record.digest = _make_digest(has_data=has_data)

    usage = _build_record(record)

    assert usage.outcome is outcome
    assert usage.is_clarification is is_clarification
    assert usage.has_data is has_data


@pytest.mark.parametrize(
    ("state", "reason"),
    [
        (TerminalState.REFUSED, RefusedReason.ADVERSARIAL),
        (TerminalState.REFUSED, ErrorType.CHAT_DISABLED),
        (TerminalState.ERROR, ErrorType.SYNTHESIS_STREAM_ERROR),
        (TerminalState.COMPLETE, None),
        (TerminalState.CANCELED, None),
    ],
)
def test_the_outcome_reason_is_the_code_of_a_refused_or_failed_turn(
    state: TerminalState, reason: ErrorType | RefusedReason | None
) -> None:
    # Test: `outcome_reason`.
    # Situation: A turn is refused by the classifier, refused because chat
    #   is disabled, fails, completes, or is canceled.
    # Expectation: The reason is the code that the agent loop recorded for
    #   a refused or failed turn, and `None` for a completed or canceled
    #   turn.
    usage = _build_record(_make_record(state, reason))

    assert usage.outcome_reason is reason


@pytest.mark.parametrize(
    ("phases", "reason", "stage"),
    [
        pytest.param(
            (),
            ErrorType.CHAT_DISABLED,
            RefusalStage.AVAILABILITY,
            id="before any phase",
        ),
        pytest.param(
            ("classify",),
            RefusedReason.OFF_DOMAIN,
            RefusalStage.CLASSIFY,
            id="classify",
        ),
        pytest.param(
            ("classify", "discovery"),
            RefusedReason.SAFETY_BLOCKED,
            RefusalStage.DISCOVERY,
            id="discovery",
        ),
        pytest.param(
            ("classify", "processing", "discovery"),
            RefusedReason.SAFETY_BLOCKED,
            RefusalStage.DISCOVERY,
            id="discovery after a processing run",
        ),
        pytest.param(
            ("classify", "processing", "discovery", "synthesis"),
            RefusedReason.SAFETY_BLOCKED,
            RefusalStage.SYNTHESIS,
            id="synthesis",
        ),
        pytest.param(
            ("synthesis", "processing", "discovery", "classify"),
            RefusedReason.SAFETY_BLOCKED,
            RefusalStage.SYNTHESIS,
            id="synthesis recorded first",
        ),
    ],
)
def test_the_refusal_stage_is_the_last_phase_that_a_refused_turn_entered(
    phases: tuple[TurnPhase, ...],
    reason: ErrorType | RefusedReason,
    stage: RefusalStage,
) -> None:
    # Test: The four values of `refusal_stage`.
    # Situation: The telemetry of a refused turn holds durations for one of
    #   six sets of phases. The sets are: no phase, `classify`, `classify`
    #   and `discovery`, the same with `processing`, all four phases in the
    #   order in which they end, and all four in another order.
    # Expectation: The stage is `availability` when the telemetry does not
    #   hold a duration. Otherwise the stage is the last of `classify`,
    #   `discovery`, and `synthesis` that has a duration, whatever the order
    #   of the durations. `processing` is never the stage.
    record = _make_record(TerminalState.REFUSED, reason, phases=phases)

    assert _build_record(record).refusal_stage is stage


@pytest.mark.parametrize(
    ("state", "reason"),
    [
        (TerminalState.COMPLETE, None),
        (TerminalState.ERROR, ErrorType.SYNTHESIS_ERROR),
        (TerminalState.CANCELED, None),
    ],
)
def test_a_turn_that_was_not_refused_does_not_have_a_refusal_stage(
    state: TerminalState, reason: ErrorType | None
) -> None:
    # Test: `refusal_stage` on a turn that was not refused.
    # Situation: A turn that ran the classify, discovery, and synthesis
    #   phases completes, fails, or is canceled.
    # Expectation: The stage is `None`.
    record = _make_record(
        state, reason, phases=("classify", "discovery", "synthesis")
    )

    assert _build_record(record).refusal_stage is None


@pytest.mark.parametrize(
    ("state", "reason", "pattern"),
    [
        (TerminalState.COMPLETE, None, "trend_delta"),
        (TerminalState.ERROR, ErrorType.MCP_TIMEOUT, "trend_delta"),
        (TerminalState.REFUSED, RefusedReason.SAFETY_BLOCKED, None),
    ],
)
def test_the_pattern_is_left_out_of_a_refused_turn(
    state: TerminalState,
    reason: ErrorType | RefusedReason | None,
    pattern: str | None,
) -> None:
    # Test: `pattern` on a turn that the classifier labeled `trend_delta`.
    # Situation: The turn completes, fails, or is refused later, in the
    #   discovery phase.
    # Expectation: The record holds the pattern unless the turn was
    #   refused, in which case the pattern is `None`.
    record = TurnRecord(telemetry=TurnTelemetry(turn_id=_TURN_ID))
    record.telemetry.pattern = "trend_delta"
    record.terminal_state = state
    record.terminal_reason = reason

    assert _build_record(record).pattern == pattern


def test_the_record_holds_the_title_outcome_and_the_truncation() -> None:
    # Test: `title_outcome` and `is_truncated`.
    # Situation: The synthesis model omitted the title of a turn with data,
    #   and the discovery loop of the turn stopped at a limit.
    # Expectation: The title outcome is `omitted`, and `is_truncated` is
    #   true.
    record = _make_record()
    record.telemetry.title_outcome = TitleOutcome.OMITTED
    record.loop_result.truncated = True

    usage = _build_record(record)

    assert usage.title_outcome is TitleOutcome.OMITTED
    assert usage.is_truncated is True


def test_the_token_calls_list_each_model_call_that_was_attributed() -> None:
    # Test: `tokens` and `token_calls`.
    # Situation: A turn made a discovery call in round 2, a synthesis call,
    #   and one call whose counts were added without a role or a model.
    # Expectation: The totals sum all three calls. `token_calls` lists the
    #   two attributed calls in call order, each with its role, model,
    #   round, and four counts, and `call_count` is the length of that list.
    record = _make_record()
    tokens = record.telemetry.tokens
    tokens.add(
        TokenCounts(prompt=100, candidates=10, thoughts=1, total=111),
        phase="discovery",
        model="model-flash",
        round_number=2,
    )
    tokens.add(
        TokenCounts(prompt=200, candidates=20, thoughts=2, total=222),
        phase="synthesis",
        model="model-pro",
    )
    tokens.add(TokenCounts(prompt=400, candidates=40, thoughts=4, total=444))

    usage = _build_record(record)

    assert usage.tokens == TokenTotals(
        prompt_token_count=700,
        candidates_token_count=70,
        thoughts_token_count=7,
        total_token_count=777,
        call_count=2,
    )
    assert usage.token_calls == (
        TokenCall(
            role="discovery",
            model="model-flash",
            round_number=2,
            prompt_token_count=100,
            candidates_token_count=10,
            thoughts_token_count=1,
            total_token_count=111,
        ),
        TokenCall(
            role="synthesis",
            model="model-pro",
            round_number=None,
            prompt_token_count=200,
            candidates_token_count=20,
            thoughts_token_count=2,
            total_token_count=222,
        ),
    )


def test_a_turn_that_has_not_ended_does_not_have_a_record() -> None:
    # Test: Building a record before the turn has a terminal state.
    # Situation: The turn's record does not have a terminal state yet.
    # Expectation: `build_usage_record` raises `ValueError`.
    record = TurnRecord(telemetry=TurnTelemetry(turn_id=_TURN_ID))

    with pytest.raises(ValueError, match="has not ended"):
        _build_record(record)


@pytest.mark.parametrize("include_content", [False, True])
def test_the_largest_record_fits_in_one_line(
    monkeypatch: pytest.MonkeyPatch,
    structured_lines: list[str],
    caplog: pytest.LogCaptureFixture,
    include_content: bool,
) -> None:
    # Test: The size of the largest `chat_turn` line, with and without content.
    # Situation: A failed turn has every list of the record at its bound: a
    #   duration for every phase, a count for every tool name and label
    #   that the discovery loop can record, a token call for every
    #   discovery round and for each of the other four roles, and six
    #   scripts, alongside maximal query, answer, title, chart-title, and
    #   follow-up strings. Every count and the duration have nine digits. The
    #   script, the reason, and the pattern are the longest of their literals,
    #   and the test assumes a model name of 64 characters and a SHA of 40
    #   characters.
    # Expectation: When `include_content` is `False`, `content` is `None` and
    #   the written line is smaller than `MAX_RECORD_LINE_BYTES`. When
    #   `include_content` is `True`, `content` is truncated so the written line
    #   stays within `MAX_RECORD_LINE_BYTES` without logging an oversized-line
    #   warning.
    large = 999_999_999
    counts = TokenCounts(
        prompt=large, candidates=large, thoughts=large, total=large
    )
    model = "m" * 64
    record = TurnRecord(telemetry=TurnTelemetry(turn_id=_TURN_ID))
    telemetry = record.telemetry
    telemetry.pattern = "sequential_stages"
    telemetry.mcp_iterations = MAX_ITERATIONS
    longest_script: ScriptName = "compute_derived_metric"
    telemetry.scripts = [longest_script] * 6
    telemetry.tables_fetched = large
    telemetry.total_rows_fetched = large
    telemetry.processing_retries = large
    telemetry.charts_emitted = large
    telemetry.charts_rejected = large
    for phase in TURN_PHASES:
        telemetry.phase_durations_ms[phase] = float(large) + 0.25
    tools = (*DISCOVERY_TOOL_NAMES, *SERVER_FUNCTION_NAMES, *_TOOL_LABELS)
    for tool in tools:
        telemetry.tool_calls[tool] = large
    telemetry.tokens.add(counts, phase="classify", model=model)
    for round_number in range(1, MAX_ITERATIONS + 1):
        telemetry.tokens.add(
            counts, phase="discovery", model=model, round_number=round_number
        )
    for role in ("synthesis", "compaction", "follow_up"):
        telemetry.tokens.add(counts, phase=role, model=model)
    record.digest = _make_digest(has_data=True)
    record.loop_result.truncated = True
    record.is_signed = True
    record.was_compacted = True
    record.answer_text = "a" * MAX_RESPONSE_CHARS
    record.title = "t" * MAX_TITLE_CHARS
    record.charts = tuple(
        ResolvedLineChart(
            title=f"Chart {index} " + ("c" * 80),
            variable_dcids=("Count_Person",),
            scope=PlaceList(("country/FRA",)),
        )
        for index in range(MAX_CHARTS_PER_TURN)
    )
    record.follow_up_questions = tuple(
        f"Question {index}? " + ("q" * 120) for index in range(3)
    )
    _finish_turn(
        monkeypatch,
        record,
        TerminalState.ERROR,
        ErrorType.DAILY_TOKEN_BUDGET_EXHAUSTED,
        seconds=999_999.99925,
    )
    transcript = dataclasses.replace(
        _make_transcript(MAX_TURN_INDEX),
        current_query="u" * MAX_QUERY_CHARS,
    )
    usage = build_usage_record(
        record,
        transcript,
        build_sha="f" * 40,
        include_content=include_content,
    )

    with caplog.at_level(logging.WARNING, logger=telemetry_module.__name__):
        write_structured_record(usage)

    (line,) = structured_lines
    assert len(usage.token_calls) == MAX_ITERATIONS + 4
    assert usage.duration_ms == 999_999_999.25
    assert len(usage.tool_call_counts) == len(tools)
    assert caplog.records == []
    if include_content:
        assert usage.content is not None
        assert usage.content.is_truncated is True
        assert len(line.encode("utf-8")) <= MAX_RECORD_LINE_BYTES
    else:
        assert usage.content is None
        assert len(line.encode("utf-8")) < MAX_RECORD_LINE_BYTES


def _make_resolved_chart(title: str) -> ResolvedLineChart:
    """Builds a resolved line chart with `title`."""
    return ResolvedLineChart(
        title=title,
        variable_dcids=("Count_Person",),
        scope=PlaceList(("country/FRA",)),
    )


def test_excluded_content_is_null_even_when_turn_outputs_are_recorded(
    structured_lines: list[str],
) -> None:
    # Test: `build_usage_record` with the default `include_content=False`.
    # Situation: The turn's record holds an answer, a title, two resolved
    #   charts, and follow-up questions.
    # Expectation: `usage.content` is `None`, the written JSON sets `"content"`
    #   to `null`, and the serialized line omits all of those strings.
    record = _make_record()
    record.answer_text = "About 68 million."
    record.title = "Population of France"
    record.charts = (
        _make_resolved_chart("Population Trend"),
        _make_resolved_chart("Annual Growth"),
    )
    record.follow_up_questions = ("And Spain?", "And Germany?")

    usage = build_usage_record(record, _make_transcript(), build_sha=_BUILD_SHA)
    written = _write_record(usage, structured_lines)

    assert usage.content is None
    assert written["content"] is None
    (line,) = structured_lines
    for text in (
        "Current question",
        "About 68 million.",
        "Population of France",
        "Population Trend",
        "And Spain?",
    ):
        assert text not in line


def test_included_content_populates_every_field_of_a_completed_data_turn(
    structured_lines: list[str],
) -> None:
    # Test: `TurnContent` on a completed turn with data when opted in.
    # Situation: A turn completes with data, an answer, an emitted title, two
    #   resolved charts, and two follow-up questions, and `include_content` is
    #   `True`.
    # Expectation: `usage.content` holds all six fields in schema order with
    #   `is_truncated` set to `False`.
    record = _make_record()
    record.digest = _make_digest(has_data=True)
    record.answer_text = "France had 68.2 million people in 2023."
    record.title = "Population of France"
    record.charts = (
        _make_resolved_chart("Population Trend"),
        _make_resolved_chart("Recent Census"),
    )
    record.follow_up_questions = ("How about Spain?", "How about Italy?")

    usage = build_usage_record(
        record,
        _make_transcript(),
        build_sha=_BUILD_SHA,
        include_content=True,
    )
    written = _write_record(usage, structured_lines)

    assert usage.content == TurnContent(
        query="Current question",
        answer_text="France had 68.2 million people in 2023.",
        title="Population of France",
        chart_titles=("Population Trend", "Recent Census"),
        follow_up_questions=("How about Spain?", "How about Italy?"),
        is_truncated=False,
    )
    content = written["content"]
    assert isinstance(content, dict)
    assert list(content) == [
        "query",
        "answer_text",
        "title",
        "chart_titles",
        "follow_up_questions",
        "is_truncated",
    ]
    assert content == {
        "query": "Current question",
        "answer_text": "France had 68.2 million people in 2023.",
        "title": "Population of France",
        "chart_titles": ["Population Trend", "Recent Census"],
        "follow_up_questions": ["How about Spain?", "How about Italy?"],
        "is_truncated": False,
    }


@pytest.mark.parametrize(
    (
        "state",
        "reason",
        "is_clarification",
        "answer_text",
        "title",
    ),
    [
        pytest.param(
            TerminalState.COMPLETE,
            None,
            True,
            "Do you mean Georgia the country or the U.S. state?",
            None,
            id="clarification",
        ),
        pytest.param(
            TerminalState.REFUSED,
            RefusedReason.OFF_DOMAIN,
            False,
            None,
            None,
            id="refused",
        ),
        pytest.param(
            TerminalState.ERROR,
            ErrorType.MCP_TIMEOUT,
            False,
            None,
            None,
            id="pre-synthesis error",
        ),
        pytest.param(
            TerminalState.CANCELED,
            None,
            False,
            "First paragraph emitted before disconnect.",
            "Population of France",
            id="mid-synthesis canceled with partial block",
        ),
        pytest.param(
            TerminalState.ERROR,
            ErrorType.SYNTHESIS_STREAM_ERROR,
            False,
            "First paragraph emitted before stream error.",
            None,
            id="mid-synthesis stream error with partial block",
        ),
    ],
)
def test_included_content_reflects_partial_or_absent_outputs_across_turn_paths(
    state: TerminalState,
    reason: ErrorType | RefusedReason | None,
    is_clarification: bool,
    answer_text: str | None,
    title: str | None,
) -> None:
    # Test: `TurnContent` across clarification, refused, failed, and canceled
    #   turns when `include_content` is `True`.
    # Situation: A turn ends as a clarification, a refusal, a pre-synthesis
    #   error, or a mid-synthesis abort or cancellation that already emitted
    #   one text block.
    # Expectation: `query` is always populated, `answer_text` holds the
    #   clarification question or partial text when emitted and `None`
    #   otherwise, `title` matches the emitted title, and `chart_titles` and
    #   `follow_up_questions` are empty.
    record = _make_record(state, reason)
    record.is_clarification = is_clarification
    record.answer_text = answer_text
    record.title = title

    usage = build_usage_record(
        record,
        _make_transcript(),
        build_sha=_BUILD_SHA,
        include_content=True,
    )

    assert usage.content == TurnContent(
        query="Current question",
        answer_text=answer_text,
        title=title,
        chart_titles=(),
        follow_up_questions=(),
        is_truncated=False,
    )


def test_included_content_truncates_oversized_answer_within_the_line_budget(
    structured_lines: list[str], caplog: pytest.LogCaptureFixture
) -> None:
    # Test: Byte-budget truncation of a 30,000-character `answer_text`.
    # Situation: `answer_text` has 30,000 characters mixing multi-byte UTF-8
    #   characters (`é`, `🌍`) and characters that expand in JSON (`\n`, `"`,
    #   `\\`), alongside a title, chart title, follow-up question, and query.
    # Expectation: `answer_text` is shortened on a whole-character boundary so
    #   the serialized UTF-8 line stays within `MAX_RECORD_LINE_BYTES`, parses
    #   as valid JSON, sets `content.is_truncated` to `True`, keeps the other
    #   content fields intact, and does not trigger an oversized-line warning.
    unit = 'Café 🌍 "quote"\nline\\slash '
    answer = (unit * (30_000 // len(unit) + 1))[:30_000]
    assert len(answer) == 30_000
    record = _make_record()
    record.answer_text = answer
    record.title = "Population of France"
    record.charts = (_make_resolved_chart("Population Trend"),)
    record.follow_up_questions = ("How about Spain?",)

    usage = build_usage_record(
        record,
        _make_transcript(),
        build_sha=_BUILD_SHA,
        include_content=True,
    )
    with caplog.at_level(logging.WARNING, logger=telemetry_module.__name__):
        write_structured_record(usage)

    (line,) = structured_lines
    assert len(line.encode("utf-8")) <= MAX_RECORD_LINE_BYTES
    assert caplog.records == []
    parsed = json.loads(line)
    assert isinstance(parsed, dict)
    assert usage.content is not None
    assert usage.content.is_truncated is True
    assert usage.content.answer_text is not None
    assert 0 < len(usage.content.answer_text) < len(answer)
    assert answer.startswith(usage.content.answer_text)
    assert usage.content.title == "Population of France"
    assert usage.content.chart_titles == ("Population Trend",)
    assert usage.content.follow_up_questions == ("How about Spain?",)
    assert usage.content.query == "Current question"
    assert parsed["content"]["is_truncated"] is True


def test_included_content_truncates_secondary_fields_when_answer_is_absent(
    structured_lines: list[str], caplog: pytest.LogCaptureFixture
) -> None:
    # Test: Byte-budget truncation when `answer_text` is `None`.
    # Situation: `answer_text` is `None`, while `query`, `chart_titles`, and
    #   `follow_up_questions` together push the serialized line past
    #   `MAX_RECORD_LINE_BYTES`.
    # Expectation: `answer_text` stays `None`, `follow_up_questions` and
    #   `chart_titles` are shortened from the end until the line fits within
    #   `MAX_RECORD_LINE_BYTES`, `is_truncated` is `True`, and
    #   `write_structured_record` does not log a warning.
    record = _make_record(TerminalState.ERROR, ErrorType.SYNTHESIS_EMPTY)
    record.answer_text = None
    record.title = "Population of France"
    record.charts = tuple(
        _make_resolved_chart(f"Chart {index}: " + ("é" * 500))
        for index in range(4)
    )
    record.follow_up_questions = tuple(
        f"Follow-up {index}: " + ("🌍" * 200) for index in range(3)
    )
    transcript = dataclasses.replace(
        _make_transcript(), current_query="q" * MAX_QUERY_CHARS
    )

    usage = build_usage_record(
        record,
        transcript,
        build_sha=_BUILD_SHA,
        include_content=True,
    )
    with caplog.at_level(logging.WARNING, logger=telemetry_module.__name__):
        write_structured_record(usage)

    (line,) = structured_lines
    assert len(line.encode("utf-8")) <= MAX_RECORD_LINE_BYTES
    assert caplog.records == []
    parsed = json.loads(line)
    assert parsed["content"]["answer_text"] is None
    assert parsed["content"]["is_truncated"] is True
    assert usage.content is not None
    assert usage.content.answer_text is None
    assert usage.content.is_truncated is True
    assert usage.content.follow_up_questions == ()
    assert len(usage.content.chart_titles) < 4
    assert usage.content.query == "q" * MAX_QUERY_CHARS


def test_included_content_shortens_fields_in_priority_order(
    monkeypatch: pytest.MonkeyPatch, structured_lines: list[str]
) -> None:
    # Test: Deterministic truncation priority across all five text fields and
    #   at the exact 1-byte overflow boundary.
    # Situation:
    #   1. With `answer_text`, `follow_up_questions`, and `chart_titles` empty,
    #      `title` and `query` exceed `MAX_RECORD_LINE_BYTES`, then `query`
    #      alone (4,000 multi-byte characters) exceeds `MAX_RECORD_LINE_BYTES`.
    #   2. A record whose untruncated line is `MAX_RECORD_LINE_BYTES + 1` bytes
    #      runs through `build_usage_record(..., include_content=True)`.
    # Expectation:
    #   1. `title` is shortened before `query`, and `query` is shortened when
    #      shortening the earlier fields does not fit within
    #      `MAX_RECORD_LINE_BYTES`.
    #   2. At the `MAX_RECORD_LINE_BYTES + 1` boundary, `answer_text` is
    #      shortened by one character and `is_truncated` is `True`.
    record = _make_record()
    record.answer_text = None
    record.title = "T" * 100
    long_query = "🌍" * 1_000  # 12,000 JSON bytes via \ud83c\udf0d escapes
    transcript = dataclasses.replace(
        _make_transcript(), current_query=long_query
    )

    usage = build_usage_record(
        record, transcript, build_sha=_BUILD_SHA, include_content=True
    )
    write_structured_record(usage)

    (line,) = structured_lines
    assert len(line.encode("utf-8")) <= MAX_RECORD_LINE_BYTES
    assert usage.content is not None
    assert usage.content.is_truncated is True
    assert usage.content.title == ""
    assert 0 < len(usage.content.query) < len(long_query)

    # Exact +1 byte boundary: untruncated line is MAX_RECORD_LINE_BYTES + 1.
    structured_lines.clear()
    boundary_record = _make_record()
    boundary_record.answer_text = "x" * 200
    probe = build_usage_record(
        boundary_record,
        _make_transcript(),
        build_sha=_BUILD_SHA,
        include_content=True,
    )
    write_structured_record(probe)
    (probe_line,) = structured_lines
    probe_bytes = len(probe_line.encode("utf-8"))
    structured_lines.clear()
    monkeypatch.setattr(
        "narratives_agent.workflows.usage_record.MAX_RECORD_LINE_BYTES",
        probe_bytes - 1,
    )

    clipped = build_usage_record(
        boundary_record,
        _make_transcript(),
        build_sha=_BUILD_SHA,
        include_content=True,
    )
    write_structured_record(clipped)
    (clipped_line,) = structured_lines
    assert len(clipped_line.encode("utf-8")) <= probe_bytes - 1
    assert clipped.content is not None
    assert clipped.content.is_truncated is True
    assert clipped.content.answer_text == "x" * 199
