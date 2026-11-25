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
6. `tables` and `tables_truncated` record up to 20 non-empty fetched tables
   with validated identifiers, cohort or capped named-place scopes, and
   date spans. Empty fetches and derived tables are excluded, and trailing
   entries are dropped when a record would exceed `MAX_RECORD_LINE_BYTES`.
7. `highlighted_places` records up to 25 deduplicated places grounded in
   non-empty fetched tables across all 10 metric sources, with focal entries
   taking precedence on ranking and distribution steps.
8. `specification_origin` and `script_steps` describe the turn's
   specification. Every step that ran is listed with its outcome, the list
   ends at a refused step, and it is empty after a run that timed out. A
   failed earlier run of the default specification does not change the
   steps of the final run. A refused step that the specification does not
   hold fails the build.
9. `rejected_submissions` records up to three rejected specifications by
   their reason, scripts, refused step, and timeout, without their error
   text.
10. `charts` records up to four charts of each of the six kinds with their
    origin, per-capita flag, and grounded variables, facets, places, or
    cohort. An identifier that a fetched table does not hold is left out.
11. `build_usage_record` raises `ValueError` for a turn that has not ended.
    A record with every list at its bound stays under the size limit of one
    line.
"""

import dataclasses
import json
import logging
import time
from collections.abc import Sequence
from dataclasses import replace

import pytest

from narratives_agent import telemetry as telemetry_module
from narratives_agent.analytics.composition import compute_composition
from narratives_agent.analytics.derived import derive_observation_table
from narratives_agent.analytics.digest import (
    AnalysisDigest,
    RefusalReason,
    RefusedScriptResult,
)
from narratives_agent.analytics.distribution import summarize_distribution
from narratives_agent.analytics.metrics import CompositionMode, ScriptName
from narratives_agent.analytics.provenance import Provenance
from narratives_agent.analytics.ranking import rank_cohort
from narratives_agent.analytics.relations import relate_cohorts
from narratives_agent.analytics.tables import (
    MAX_DCID_CHARS,
    ObservationRow,
    ObservationTable,
)
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
    ChartKind,
    ChildCohort,
    PlaceList,
    ResolvedBarChart,
    ResolvedChart,
    ResolvedHighlightChart,
    ResolvedLineChart,
    ResolvedMapChart,
    ResolvedRankingChart,
    ResolvedScatterChart,
)
from narratives_agent.workflows.classify import RefusedReason
from narratives_agent.workflows.mcp_loop import (
    DISCOVERY_TOOL_NAMES,
    MAX_ITERATIONS,
    MAX_PROCESSING_RETRIES,
    SERVER_FUNCTION_NAMES,
    RejectedSubmission,
)
from narratives_agent.workflows.processing import (
    StepRefusalDiagnostic,
    TimeoutDiagnostic,
)
from narratives_agent.workflows.specification import (
    AnalysisSpecification,
    RankCohortStep,
)
from narratives_agent.workflows.transcript import (
    MAX_PLACE_TYPE_CHARS,
    MAX_TURN_INDEX,
    ConversationStateSlots,
    Transcript,
    Turn,
)
from narratives_agent.workflows.turn_cache import CachedTable
from narratives_agent.workflows.turn_record import (
    ChartOrigin,
    SpecificationOrigin,
    TurnChart,
    TurnRecord,
)
from narratives_agent.workflows.usage_record import (
    MAX_CHART_VARIABLES,
    MAX_HIGHLIGHTED_PLACES,
    MAX_LOGGED_CHARTS,
    MAX_LOGGED_REJECTED_SUBMISSIONS,
    MAX_LOGGED_TABLES,
    MAX_TABLE_PLACE_DCIDS,
    ChartVariable,
    HighlightedPlace,
    LoggedChart,
    LoggedRejectedSubmission,
    LoggedScriptStep,
    LoggedTable,
    PlaceHighlightSource,
    RefusalStage,
    TokenCall,
    TokenTotals,
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
    "tables_truncated",
    "tables",
    "highlighted_places",
    "specification_origin",
    "scripts",
    "script_steps",
    "processing_retries",
    "rejected_submissions",
    "charts_emitted",
    "charts_rejected",
    "charts",
]
# `_TOOL_LABELS` holds the two labels that the discovery loop records in
# place of a tool name.
_TOOL_LABELS = ("unknown", "server_report_unavailable")
# `_COHORT_SPECIFICATION` aligns one table, reduces another, and ranks both
# cohorts.
_COHORT_SPECIFICATION = AnalysisSpecification.model_validate(
    {
        "steps": [
            {"step_id": "s1", "script": "align_cohort", "table": "t1"},
            {
                "step_id": "s2",
                "script": "reduce_series",
                "table": "t2",
                "metric": "percent_change",
            },
            {"step_id": "s3", "script": "rank_cohort", "table": "s1"},
            {"step_id": "s4", "script": "rank_cohort", "table": "s2"},
        ],
        "findings": ["Free text that the model wrote about its choice."],
    }
)
# `_RANKING_SPECIFICATION` aligns one table and ranks the cohort.
_RANKING_SPECIFICATION = AnalysisSpecification.model_validate(
    {
        "steps": [
            {"step_id": "s1", "script": "align_cohort", "table": "t1"},
            {"step_id": "s2", "script": "rank_cohort", "table": "s1"},
        ]
    }
)
_TIMEOUT = TimeoutDiagnostic(
    timeout_seconds=5.0,
    message="The analysis did not finish within 5 seconds.",
)
_COUNTIES = ChildCohort("geoId/06", "County")
_CHART_TITLE = "Free text that the model wrote as a chart title"
_CHART_UNIT = "Free text that the model wrote as a chart unit"


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


def _make_cached_table(
    table_id: str = "t1",
    *,
    variable_dcid: str = "Count_Person",
    places: Sequence[str] = ("country/FRA",),
    dates: Sequence[str] = ("2022", "2023"),
    facet_id: str | None = "f1",
    parent_place_dcid: str | None = None,
    child_place_type: str | None = None,
) -> CachedTable:
    """Builds a cached observation table for `places` over `dates`."""
    rows = tuple(
        ObservationRow(
            place_dcid=place,
            place_name=place,
            date=date,
            value=float((place_index + 1) * 10 + date_index),
        )
        for place_index, place in enumerate(places)
        for date_index, date in enumerate(dates)
    )
    return CachedTable(
        table_id=table_id,
        table=ObservationTable(
            variable_dcid=variable_dcid,
            variable_name=variable_dcid,
            unit="Person",
            scaling_factor=None,
            provenance=Provenance(),
            rows=rows,
            requested_places=tuple(places),
            place_names={place: place for place in places},
            facet_id=facet_id,
            parent_place_dcid=parent_place_dcid,
            child_place_type=child_place_type,
        ),
    )


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


def _make_step_refusal(
    step_id: str = "s2",
    script: ScriptName = "rank_cohort",
    refusal_reason: RefusalReason = "insufficient_coverage",
) -> StepRefusalDiagnostic:
    """Builds the diagnostic of a refused step, with a free-text message."""
    return StepRefusalDiagnostic(
        refusal_reason=refusal_reason,
        message="Only 1 of 4 places have a value.",
        step_id=step_id,
        script=script,
        input_table_ids=("t1",),
        coverage=None,
        alternative_sources=(),
        completed_results=(),
    )


def _store_chart_tables(record: TurnRecord) -> None:
    """Stores a named-place table and two county cohort tables on `record`.

    `t1` holds `Count_Person` for France and Germany. `t2` and `t3` hold two
    other variables for two counties of the cohort `_COUNTIES`.
    """
    counties = ("geoId/06001", "geoId/06085")
    record.cache.store_fetched(
        _make_cached_table("t1", places=("country/FRA", "country/DEU"))
    )
    record.cache.store_fetched(
        _make_cached_table(
            "t2",
            variable_dcid="Median_Income_Household",
            places=counties,
            dates=("2023",),
            facet_id="f2",
            parent_place_dcid=_COUNTIES.parent_place,
            child_place_type=_COUNTIES.child_place_type,
        )
    )
    record.cache.store_fetched(
        _make_cached_table(
            "t3",
            variable_dcid="Percent_Person_WithDiabetes",
            places=counties,
            dates=("2023",),
            facet_id="f3",
            parent_place_dcid=_COUNTIES.parent_place,
            child_place_type=_COUNTIES.child_place_type,
        )
    )


def _make_line_chart(
    *place_dcids: str,
    variable_dcid: str = "Count_Person",
    facet_id: str = "f1",
) -> ResolvedLineChart:
    """Builds a line chart of one variable over `place_dcids`."""
    return ResolvedLineChart(
        title=_CHART_TITLE,
        unit=_CHART_UNIT,
        variable_dcids=(variable_dcid,),
        facet_ids=((variable_dcid, facet_id),),
        scope=PlaceList(place_dcids),
    )


def _make_turn_charts(
    *charts: ResolvedChart, origin: ChartOrigin = "model"
) -> tuple[TurnChart, ...]:
    """Pairs each chart with `origin`, as the synthesis phase records it."""
    return tuple(TurnChart(chart=chart, origin=origin) for chart in charts)


def _make_logged_chart(
    kind: ChartKind,
    *,
    index: int = 0,
    origin: ChartOrigin = "model",
    variable_dcid: str = "Count_Person",
    facet_id: str = "f1",
    cohort: ChildCohort | None = None,
    place_dcids: tuple[str, ...] = (),
    per_capita: bool = False,
) -> LoggedChart:
    """Builds the expected logged form of a chart of one variable."""
    return LoggedChart(
        index=index,
        kind=kind,
        origin=origin,
        variables=(
            ChartVariable(variable_dcid=variable_dcid, facet_id=facet_id),
        ),
        parent_place_dcid=cohort.parent_place if cohort is not None else None,
        child_place_type=(
            cohort.child_place_type if cohort is not None else None
        ),
        place_dcids=place_dcids,
        per_capita=per_capita,
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


def _list_first_item_keys(written: JsonObject, key: str) -> list[str]:
    """Returns the keys of the first item of the list that `key` holds."""
    items = written[key]
    assert isinstance(items, list)
    first = items[0]
    assert isinstance(first, dict)
    return list(first)


def test_a_turn_that_ran_every_phase_writes_every_key_with_its_value(
    monkeypatch: pytest.MonkeyPatch, structured_lines: list[str]
) -> None:
    # Test: The written `chat_turn` record of a turn where every key applies.
    # Situation: A follow-up turn after the turn with index 4 completes with
    #   data after 604.75 ms. The telemetry holds a duration for all six
    #   phases, in the order in which the phases end. The turn fetched two
    #   tables, used the first in the answer, called three tools, made two
    #   model calls, ran the two scripts of a specification from the model
    #   after the server rejected one specification, drew one chart, was
    #   truncated, and was signed with compaction.
    # Expectation: The line holds the schema's keys in order, each with the
    #   value that the turn recorded. The phases are in the fixed order with
    #   only `processing` nested, and the tools are sorted by name. Each
    #   script step, rejected submission, and chart holds its keys in the
    #   declared order.
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
    record.cache.store_fetched(_make_cached_table("t1"))
    record.cache.store_fetched(
        _make_cached_table(
            "t2",
            variable_dcid="Median_Income_Household",
            places=("geoId/06", "geoId/36"),
            dates=("2023",),
            facet_id=None,
            parent_place_dcid="country/USA",
            child_place_type="State",
        )
    )
    record.used_table_ids = frozenset({"t1"})
    record.digest = _make_digest(has_data=True)
    record.specification = _RANKING_SPECIFICATION
    record.specification_origin = "model"
    record.loop_result.rejected_submissions.append(
        RejectedSubmission(
            round_number=2,
            reason="processing_failed",
            errors=("Only 1 of 4 places have a value.",),
            specification=_RANKING_SPECIFICATION,
            diagnostic=_make_step_refusal(),
        )
    )
    record.charts = _make_turn_charts(_make_line_chart("country/FRA"))
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
        "tables_truncated": False,
        "tables": [
            {
                "table_id": "t1",
                "used_in_answer": True,
                "variable_dcid": "Count_Person",
                "facet_id": "f1",
                "row_count": 2,
                "parent_place_dcid": None,
                "child_place_type": None,
                "places_with_data_count": 1,
                "place_dcids": ["country/FRA"],
                "earliest_date": "2022",
                "latest_date": "2023",
            },
            {
                "table_id": "t2",
                "used_in_answer": False,
                "variable_dcid": "Median_Income_Household",
                "facet_id": None,
                "row_count": 2,
                "parent_place_dcid": "country/USA",
                "child_place_type": "State",
                "places_with_data_count": 2,
                "place_dcids": [],
                "earliest_date": "2023",
                "latest_date": "2023",
            },
        ],
        "highlighted_places": [
            {"place_dcid": "country/FRA", "source": "timeseries"}
        ],
        "specification_origin": "model",
        "scripts": ["align_cohort", "rank_cohort"],
        "script_steps": [
            {
                "step_index": 0,
                "step_id": "s1",
                "script": "align_cohort",
                "status": "ok",
                "refusal_reason": None,
            },
            {
                "step_index": 1,
                "step_id": "s2",
                "script": "rank_cohort",
                "status": "ok",
                "refusal_reason": None,
            },
        ],
        "processing_retries": 1,
        "rejected_submissions": [
            {
                "round_number": 2,
                "reason": "processing_failed",
                "scripts": ["align_cohort", "rank_cohort"],
                "failed_step_id": "s2",
                "failed_script": "rank_cohort",
                "refusal_reason": "insufficient_coverage",
                "timed_out": False,
            }
        ],
        "charts_emitted": 4,
        "charts_rejected": 5,
        "charts": [
            {
                "index": 0,
                "kind": "line",
                "origin": "model",
                "variables": [
                    {"variable_dcid": "Count_Person", "facet_id": "f1"}
                ],
                "parent_place_dcid": None,
                "child_place_type": None,
                "place_dcids": ["country/FRA"],
                "per_capita": False,
            }
        ],
    }
    nested_keys = {
        key: _list_first_item_keys(written, key)
        for key in ("script_steps", "rejected_submissions", "charts")
    }
    assert nested_keys == {
        "script_steps": [
            "step_index",
            "step_id",
            "script",
            "status",
            "refusal_reason",
        ],
        "rejected_submissions": [
            "round_number",
            "reason",
            "scripts",
            "failed_step_id",
            "failed_script",
            "refusal_reason",
            "timed_out",
        ],
        "charts": [
            "index",
            "kind",
            "origin",
            "variables",
            "parent_place_dcid",
            "child_place_type",
            "place_dcids",
            "per_capita",
        ],
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

    usage = build_usage_record(record, _make_transcript(), build_sha=None)
    written = _write_record(usage, structured_lines)

    assert usage.tables_truncated is False
    assert usage.tables == ()
    assert usage.highlighted_places == ()
    assert usage.specification_origin is None
    assert usage.script_steps == ()
    assert usage.rejected_submissions == ()
    assert usage.charts == ()
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
        "tables_truncated": False,
        "tables": [],
        "highlighted_places": [],
        "specification_origin": None,
        "scripts": [],
        "script_steps": [],
        "processing_retries": 0,
        "rejected_submissions": [],
        "charts_emitted": 0,
        "charts_rejected": 0,
        "charts": [],
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


def test_a_turn_without_a_digest_has_empty_highlighted_places() -> None:
    # Test: `highlighted_places` when `record.digest` is `None`.
    # Situation: A turn fetched one table and ended in an error before a
    #   digest was resolved.
    # Expectation: `tables` holds the fetched table as unused,
    #   `tables_truncated` is `False`, and `highlighted_places` is empty.
    record = _make_record(TerminalState.ERROR, ErrorType.MCP_TIMEOUT)
    record.cache.store_fetched(_make_cached_table("t1"))

    usage = _build_record(record)

    assert len(usage.tables) == 1
    assert usage.tables[0].used_in_answer is False
    assert usage.tables_truncated is False
    assert usage.highlighted_places == ()


def test_a_named_place_table_records_its_identifiers_places_and_date_span(
    structured_lines: list[str],
) -> None:
    # Test: `LoggedTable` fields and key order for named-place tables.
    # Situation: A turn fetched two named-place tables and used the first in
    #   its answer. The first table has a facet ID, three places given out of
    #   alphabetical order, and three dates given out of chronological order.
    #   The second table does not have a facet ID and has one observation.
    # Expectation: Both tables appear in fetch order with `used_in_answer`
    #   reflecting `used_table_ids`, `parent_place_dcid` and
    #   `child_place_type` set to `None`, sorted `place_dcids`, and the
    #   minimum and maximum dates. Each serialized table object keeps the
    #   declared field order.
    record = _make_record()
    first = CachedTable(
        table_id="t1",
        table=ObservationTable(
            variable_dcid="Count_Person",
            variable_name="Total Population",
            unit="Person",
            scaling_factor=None,
            provenance=Provenance(),
            rows=(
                ObservationRow("country/ITA", "Italy", "2023-05", 58.9e6),
                ObservationRow("country/DEU", "Germany", "2021-01", 83.2e6),
                ObservationRow("country/FRA", "France", "2022-11", 67.8e6),
            ),
            requested_places=("country/ITA", "country/DEU", "country/FRA"),
            place_names={
                "country/ITA": "Italy",
                "country/DEU": "Germany",
                "country/FRA": "France",
            },
            facet_id="2176550201",
        ),
    )
    second = _make_cached_table(
        "t2",
        variable_dcid="UnemploymentRate_Person",
        places=("country/ESP",),
        dates=("2020",),
        facet_id=None,
    )
    record.cache.store_fetched(first)
    record.cache.store_fetched(second)
    record.used_table_ids = frozenset({"t1"})

    usage = _build_record(record)
    written = _write_record(usage, structured_lines)

    assert usage.tables_truncated is False
    assert usage.tables == (
        LoggedTable(
            table_id="t1",
            used_in_answer=True,
            variable_dcid="Count_Person",
            facet_id="2176550201",
            row_count=3,
            parent_place_dcid=None,
            child_place_type=None,
            places_with_data_count=3,
            place_dcids=("country/DEU", "country/FRA", "country/ITA"),
            earliest_date="2021-01",
            latest_date="2023-05",
        ),
        LoggedTable(
            table_id="t2",
            used_in_answer=False,
            variable_dcid="UnemploymentRate_Person",
            facet_id=None,
            row_count=1,
            parent_place_dcid=None,
            child_place_type=None,
            places_with_data_count=1,
            place_dcids=("country/ESP",),
            earliest_date="2020",
            latest_date="2020",
        ),
    )
    written_tables = written["tables"]
    assert isinstance(written_tables, list)
    first_written = written_tables[0]
    assert isinstance(first_written, dict)
    assert list(first_written) == [
        "table_id",
        "used_in_answer",
        "variable_dcid",
        "facet_id",
        "row_count",
        "parent_place_dcid",
        "child_place_type",
        "places_with_data_count",
        "place_dcids",
        "earliest_date",
        "latest_date",
    ]


def test_a_named_place_table_caps_its_place_list_at_twenty_five() -> None:
    # Test: Per-table cap on `place_dcids`.
    # Situation: A non-cohort table has observations for 30 distinct places,
    #   passed in reverse order.
    # Expectation: `places_with_data_count` is 30, `place_dcids` holds the
    #   first 25 sorted DCIDs, and `tables_truncated` stays `False`.
    places = [f"geoId/{index:02d}" for index in range(30, 0, -1)]
    record = _make_record()
    record.cache.store_fetched(
        _make_cached_table("t1", places=places, dates=("2023",))
    )

    usage = _build_record(record)

    (logged,) = usage.tables
    assert logged.places_with_data_count == 30
    assert len(logged.place_dcids) == MAX_TABLE_PLACE_DCIDS
    assert logged.place_dcids == tuple(
        f"geoId/{index:02d}" for index in range(1, 26)
    )
    assert usage.tables_truncated is False


def test_a_complete_child_place_cohort_table_omits_individual_place_dcids(
    structured_lines: list[str],
) -> None:
    # Test: `LoggedTable` for a complete child-place cohort.
    # Situation: A fetched table has a valid `parent_place_dcid` and a
    #   `child_place_type` of `MAX_PLACE_TYPE_CHARS` characters, with rows
    #   for three child places.
    # Expectation: `parent_place_dcid` and `child_place_type` are preserved,
    #   `places_with_data_count` is 3, and `place_dcids` is empty (`[]` in
    #   JSON).
    max_length_type = "A" * MAX_PLACE_TYPE_CHARS
    record = _make_record()
    record.cache.store_fetched(
        _make_cached_table(
            "t1",
            places=("geoId/06001", "geoId/06075", "geoId/06085"),
            dates=("2023",),
            parent_place_dcid="geoId/06",
            child_place_type=max_length_type,
        )
    )

    usage = _build_record(record)
    written = _write_record(usage, structured_lines)

    (logged,) = usage.tables
    assert logged.parent_place_dcid == "geoId/06"
    assert logged.child_place_type == max_length_type
    assert logged.places_with_data_count == 3
    assert logged.place_dcids == ()
    written_tables = written["tables"]
    assert isinstance(written_tables, list)
    first_written = written_tables[0]
    assert isinstance(first_written, dict)
    assert first_written["place_dcids"] == []


@pytest.mark.parametrize(
    ("parent_place_dcid", "child_place_type"),
    [
        pytest.param("geoId/06", None, id="missing child_place_type"),
        pytest.param(None, "County", id="missing parent_place_dcid"),
        pytest.param("bad parent", "County", id="invalid parent_place_dcid"),
        pytest.param(
            "geoId/06", "County_Name", id="invalid child_place_type pattern"
        ),
        pytest.param(
            "geoId/06",
            "A" * (MAX_PLACE_TYPE_CHARS + 1),
            id="child_place_type over length cap",
        ),
    ],
)
def test_an_incomplete_or_invalid_cohort_falls_back_to_named_places(
    parent_place_dcid: str | None, child_place_type: str | None
) -> None:
    # Test: Incomplete or invalid cohort metadata on a fetched table.
    # Situation: Only one of `parent_place_dcid` and `child_place_type` is
    #   set, or one of the two fails its pattern or length check.
    # Expectation: Both `parent_place_dcid` and `child_place_type` are `None`
    #   on `LoggedTable`, and `place_dcids` lists the table's valid places.
    record = _make_record()
    record.cache.store_fetched(
        _make_cached_table(
            "t1",
            places=("geoId/06075", "geoId/06001"),
            dates=("2023",),
            parent_place_dcid=parent_place_dcid,
            child_place_type=child_place_type,
        )
    )

    usage = _build_record(record)

    (logged,) = usage.tables
    assert logged.parent_place_dcid is None
    assert logged.child_place_type is None
    assert logged.places_with_data_count == 2
    assert logged.place_dcids == ("geoId/06001", "geoId/06075")


def test_empty_fetches_and_derived_tables_are_excluded_from_tables() -> None:
    # Test: Exclusion of 0-row fetched tables and derived tables.
    # Situation: The turn cache holds an empty fetched table `t1`, a
    #   non-empty fetched table `t2`, and a derived table `s1`, while
    #   `TurnTelemetry` counts both fetched tables.
    # Expectation: `tables_fetched` stays 2, `tables` holds only `t2`, and
    #   `tables_truncated` is `False`.
    record = _make_record()
    empty = CachedTable(
        table_id="t1",
        table=ObservationTable(
            variable_dcid="Count_Person",
            variable_name="Total Population",
            unit="Person",
            scaling_factor=None,
            provenance=Provenance(),
            rows=(),
            requested_places=("country/FRA",),
            place_names={"country/FRA": "France"},
        ),
    )
    populated = _make_cached_table(
        "t2", places=("country/DEU",), dates=("2023",)
    )
    derived = _make_cached_table(
        "s1", variable_dcid="Derived_PerCapita", places=("country/ESP",)
    )
    record.cache.store_fetched(empty)
    record.cache.store_fetched(populated)
    record.cache.store_derived(derived)
    record.telemetry.tables_fetched = record.cache.tables_fetched
    record.telemetry.total_rows_fetched = record.cache.total_rows_fetched

    usage = _build_record(record)

    assert usage.tables_fetched == 2
    assert usage.total_rows_fetched == 1
    assert [table.table_id for table in usage.tables] == ["t2"]
    assert usage.tables_truncated is False


def test_invalid_identifiers_and_dates_are_filtered_out() -> None:
    # Test: Pattern validation on table IDs, DCIDs, facet IDs, and row dates.
    # Situation: `t1` has an invalid `variable_dcid`, `t2` has only invalid
    #   place DCIDs, `t3` has an invalid `facet_id` alongside one valid and
    #   one invalid place DCID and one valid and one invalid date, `t4` has
    #   only invalid dates, and an entry under a malformed `t0` ID sits in
    #   the cache.
    # Expectation: `t1`, `t2`, and `t0` are excluded. `t3` is kept with
    #   `facet_id=None`, only the valid place DCID, and the valid date. `t4`
    #   is kept with `earliest_date=None` and `latest_date=None`.
    record = _make_record()
    record.cache.store_fetched(
        _make_cached_table("t1", variable_dcid="bad variable")
    )
    record.cache.store_fetched(
        _make_cached_table("t2", places=("bad place",), dates=("2023",))
    )
    record.cache.store_fetched(
        CachedTable(
            table_id="t3",
            table=ObservationTable(
                variable_dcid="Count_Person",
                variable_name="Total Population",
                unit="Person",
                scaling_factor=None,
                provenance=Provenance(),
                rows=(
                    ObservationRow("country/FRA", "France", "2021-13", 1.0),
                    ObservationRow("country/FRA", "France", "2022-06", 2.0),
                    ObservationRow("bad place", "Bad", "2020-01", 3.0),
                ),
                requested_places=("country/FRA",),
                place_names={"country/FRA": "France"},
                facet_id="bad facet",
            ),
        )
    )
    record.cache.store_fetched(
        _make_cached_table(
            "t4",
            places=("country/DEU",),
            dates=("0000", "2021-02-29", "not-a-date"),
        )
    )
    record.cache._tables["t0"] = _make_cached_table(
        "t0", places=("country/ITA",), dates=("2023",)
    )

    usage = _build_record(record)

    assert usage.tables == (
        LoggedTable(
            table_id="t3",
            used_in_answer=False,
            variable_dcid="Count_Person",
            facet_id=None,
            row_count=3,
            parent_place_dcid=None,
            child_place_type=None,
            places_with_data_count=1,
            place_dcids=("country/FRA",),
            earliest_date="2020-01",
            latest_date="2022-06",
        ),
        LoggedTable(
            table_id="t4",
            used_in_answer=False,
            variable_dcid="Count_Person",
            facet_id="f1",
            row_count=3,
            parent_place_dcid=None,
            child_place_type=None,
            places_with_data_count=1,
            place_dcids=("country/DEU",),
            earliest_date=None,
            latest_date=None,
        ),
    )


def test_twenty_qualifying_tables_are_kept_without_truncation() -> None:
    # Test: Count boundary at `MAX_LOGGED_TABLES` (`20`).
    # Situation: A turn fetched 20 non-empty tables and 2 empty 0-row tables.
    # Expectation: `tables` holds all 20 non-empty tables in fetch order, and
    #   `tables_truncated` is `False`.
    record = _make_record()
    for index in range(1, MAX_LOGGED_TABLES + 1):
        record.cache.store_fetched(
            _make_cached_table(f"t{index}", dates=("2023",))
        )
    for index in range(MAX_LOGGED_TABLES + 1, MAX_LOGGED_TABLES + 3):
        record.cache.store_fetched(
            _make_cached_table(f"t{index}", places=(), dates=())
        )

    usage = _build_record(record)

    assert len(usage.tables) == MAX_LOGGED_TABLES
    assert [table.table_id for table in usage.tables] == [
        f"t{index}" for index in range(1, MAX_LOGGED_TABLES + 1)
    ]
    assert usage.tables_truncated is False


def test_more_than_twenty_qualifying_tables_truncate_at_twenty() -> None:
    # Test: Count truncation above `MAX_LOGGED_TABLES` (`20`).
    # Situation: A turn fetched 22 qualifying non-empty tables.
    # Expectation: `tables` holds `t1` through `t20`, and `tables_truncated`
    #   is `True`.
    record = _make_record()
    for index in range(1, 23):
        record.cache.store_fetched(
            _make_cached_table(f"t{index}", dates=("2023",))
        )

    usage = _build_record(record)

    assert len(usage.tables) == MAX_LOGGED_TABLES
    assert [table.table_id for table in usage.tables] == [
        f"t{index}" for index in range(1, MAX_LOGGED_TABLES + 1)
    ]
    assert usage.tables_truncated is True


def test_tables_are_trimmed_from_the_end_to_stay_within_the_line_byte_limit(
    caplog: pytest.LogCaptureFixture, structured_lines: list[str]
) -> None:
    # Test: Byte-budget truncation of `tables` at `MAX_RECORD_LINE_BYTES`.
    # Situation: A turn fetched 20 named-place tables, and each table holds
    #   25 valid 256-character place DCIDs so the full 20-table list would
    #   serialize well above `MAX_RECORD_LINE_BYTES` (14 KiB).
    # Expectation: Trailing tables are dropped until the serialized JSON line
    #   is at most `MAX_RECORD_LINE_BYTES` bytes, `tables_truncated` is
    #   `True`, and `write_structured_record` does not log an oversized-line
    #   warning.
    assert MAX_RECORD_LINE_BYTES == 14 * 1024
    record = _make_record()
    for table_index in range(1, MAX_LOGGED_TABLES + 1):
        places = [
            f"p{table_index:02d}_{place_index:02d}_"
            + ("x" * (MAX_DCID_CHARS - 7))
            for place_index in range(MAX_TABLE_PLACE_DCIDS)
        ]
        record.cache.store_fetched(
            _make_cached_table(
                f"t{table_index}", places=places, dates=("2023",)
            )
        )

    usage = _build_record(record)
    with caplog.at_level(logging.WARNING, logger=telemetry_module.__name__):
        write_structured_record(usage)

    (line,) = structured_lines
    assert 0 < len(usage.tables) < MAX_LOGGED_TABLES
    assert [table.table_id for table in usage.tables] == [
        f"t{index}" for index in range(1, len(usage.tables) + 1)
    ]
    assert usage.tables_truncated is True
    assert len(line.encode("utf-8")) <= MAX_RECORD_LINE_BYTES
    assert caplog.records == []


def test_ranking_metrics_highlight_focal_then_top_then_bottom() -> None:
    # Test: `ranked_focal`, `ranked_top`, and `ranked_bottom` ordering.
    # Situation: A six-place cohort is ranked with `max_entries_per_end=2`.
    #   On the first turn, `geoId/06` (which is also first in `top_n`) and
    #   `geoId/03` are focal places. On the second turn, focal places are
    #   not requested.
    # Expectation: When focal places are present, `geoId/06` keeps
    #   `ranked_focal` instead of `ranked_top`, followed by `geoId/03`, the
    #   remaining `top_n` place, and `bottom_n`. Without focal places,
    #   `top_n` comes first and `bottom_n` follows.
    places = tuple(f"geoId/{index:02d}" for index in range(1, 7))
    cached = _make_cached_table(
        "t1",
        places=places,
        dates=("2023",),
        parent_place_dcid="country/USA",
        child_place_type="State",
    )

    with_focal = _make_record()
    with_focal.cache.store_fetched(cached)
    with_focal.digest = AnalysisDigest.from_results(
        (
            rank_cohort(
                cached.table,
                max_entries_per_end=2,
                focal_places=["geoId/06", "geoId/03"],
                step_id="s1",
            ),
        )
    )

    without_focal = _make_record()
    without_focal.cache.store_fetched(cached)
    without_focal.digest = AnalysisDigest.from_results(
        (rank_cohort(cached.table, max_entries_per_end=2, step_id="s1"),)
    )

    assert _build_record(with_focal).highlighted_places == (
        HighlightedPlace(
            place_dcid="geoId/06", source=PlaceHighlightSource.RANKED_FOCAL
        ),
        HighlightedPlace(
            place_dcid="geoId/03", source=PlaceHighlightSource.RANKED_FOCAL
        ),
        HighlightedPlace(
            place_dcid="geoId/05", source=PlaceHighlightSource.RANKED_TOP
        ),
        HighlightedPlace(
            place_dcid="geoId/01", source=PlaceHighlightSource.RANKED_BOTTOM
        ),
        HighlightedPlace(
            place_dcid="geoId/02", source=PlaceHighlightSource.RANKED_BOTTOM
        ),
    )
    assert _build_record(without_focal).highlighted_places == (
        HighlightedPlace(
            place_dcid="geoId/06", source=PlaceHighlightSource.RANKED_TOP
        ),
        HighlightedPlace(
            place_dcid="geoId/05", source=PlaceHighlightSource.RANKED_TOP
        ),
        HighlightedPlace(
            place_dcid="geoId/01", source=PlaceHighlightSource.RANKED_BOTTOM
        ),
        HighlightedPlace(
            place_dcid="geoId/02", source=PlaceHighlightSource.RANKED_BOTTOM
        ),
    )


def test_distribution_metrics_highlight_focal_then_max_then_min() -> None:
    # Test: `distribution_focal`, `distribution_max`, and `distribution_min`.
    # Situation: First, a four-place cohort is summarized with focal places
    #   `geoId/04` (equal to `max`) and `geoId/02`. Second, the same cohort
    #   is summarized without focal places. Third, a single-place cohort is
    #   summarized so `max` and `min` name the same place.
    # Expectation: Focal places come before `max` and `min` so `geoId/04`
    #   keeps `distribution_focal`. Without focal places, `max` precedes
    #   `min`. On the single-place cohort, the place is emitted once as
    #   `distribution_max`.
    four_places = _make_cached_table(
        "t1",
        places=("geoId/01", "geoId/02", "geoId/03", "geoId/04"),
        dates=("2023",),
    )
    single_place = _make_cached_table(
        "t1", places=("geoId/01",), dates=("2023",)
    )

    with_focal = _make_record()
    with_focal.cache.store_fetched(four_places)
    with_focal.digest = AnalysisDigest.from_results(
        (
            summarize_distribution(
                four_places.table,
                focal_places=["geoId/04", "geoId/02"],
                step_id="s1",
            ),
        )
    )

    without_focal = _make_record()
    without_focal.cache.store_fetched(four_places)
    without_focal.digest = AnalysisDigest.from_results(
        (summarize_distribution(four_places.table, step_id="s1"),)
    )

    singleton = _make_record()
    singleton.cache.store_fetched(single_place)
    singleton.digest = AnalysisDigest.from_results(
        (summarize_distribution(single_place.table, step_id="s1"),)
    )

    assert _build_record(with_focal).highlighted_places == (
        HighlightedPlace(
            place_dcid="geoId/04",
            source=PlaceHighlightSource.DISTRIBUTION_FOCAL,
        ),
        HighlightedPlace(
            place_dcid="geoId/02",
            source=PlaceHighlightSource.DISTRIBUTION_FOCAL,
        ),
        HighlightedPlace(
            place_dcid="geoId/01",
            source=PlaceHighlightSource.DISTRIBUTION_MIN,
        ),
    )
    assert _build_record(without_focal).highlighted_places == (
        HighlightedPlace(
            place_dcid="geoId/04",
            source=PlaceHighlightSource.DISTRIBUTION_MAX,
        ),
        HighlightedPlace(
            place_dcid="geoId/01",
            source=PlaceHighlightSource.DISTRIBUTION_MIN,
        ),
    )
    assert _build_record(singleton).highlighted_places == (
        HighlightedPlace(
            place_dcid="geoId/01",
            source=PlaceHighlightSource.DISTRIBUTION_MAX,
        ),
    )


@pytest.mark.parametrize("mode", ["composition", "stages"])
def test_relation_timeseries_and_composition_metrics_highlight_their_places(
    mode: CompositionMode,
) -> None:
    # Test: `related_highest`, `related_lowest`, `timeseries`, and
    #   `composition` (in both `composition` and `stages` modes).
    # Situation: One turn relates two four-place tables with `n=2`, a second
    #   turn analyzes two series, and a third turn computes composition or
    #   stages over two component tables for two places.
    # Expectation: Relation emits `highest_by` as `related_highest` and
    #   `lowest_by` as `related_lowest`, timeseries emits `series` as
    #   `timeseries`, and composition emits `places` as `composition` in
    #   both modes.
    places = ("geoId/01", "geoId/02", "geoId/03", "geoId/04")
    by_table = _make_cached_table(
        "t1", variable_dcid="Median_Income", places=places, dates=("2023",)
    )
    target_table = _make_cached_table(
        "t2", variable_dcid="Percent_Diabetes", places=places, dates=("2023",)
    )
    relation_record = _make_record()
    relation_record.cache.store_fetched(by_table)
    relation_record.cache.store_fetched(target_table)
    relation_record.digest = AnalysisDigest.from_results(
        (relate_cohorts(target_table.table, by_table.table, n=2, step_id="s1"),)
    )

    series_table = _make_cached_table(
        "t1", places=("country/FRA", "country/DEU"), dates=("2022", "2023")
    )
    series_record = _make_record()
    series_record.cache.store_fetched(series_table)
    series_record.digest = AnalysisDigest.from_results(
        (analyze_timeseries(series_table.table, step_id="s1"),)
    )

    comp_a = _make_cached_table(
        "t1",
        variable_dcid="Stage_One",
        places=("country/FRA", "country/DEU"),
        dates=("2023",),
    )
    comp_b = CachedTable(
        table_id="t2",
        table=ObservationTable(
            variable_dcid="Stage_Two",
            variable_name="Stage_Two",
            unit="Person",
            scaling_factor=None,
            provenance=Provenance(),
            rows=(
                ObservationRow("country/FRA", "France", "2023", 5.0),
                ObservationRow("country/DEU", "Germany", "2023", 10.0),
            ),
            requested_places=("country/FRA", "country/DEU"),
            place_names={"country/FRA": "France", "country/DEU": "Germany"},
            facet_id="f1",
        ),
    )
    comp_record = _make_record()
    comp_record.cache.store_fetched(comp_a)
    comp_record.cache.store_fetched(comp_b)
    comp_record.digest = AnalysisDigest.from_results(
        (
            compute_composition(
                [comp_a.table, comp_b.table], mode=mode, step_id="s1"
            ),
        )
    )

    assert _build_record(relation_record).highlighted_places == (
        HighlightedPlace(
            place_dcid="geoId/04",
            source=PlaceHighlightSource.RELATED_HIGHEST,
        ),
        HighlightedPlace(
            place_dcid="geoId/03",
            source=PlaceHighlightSource.RELATED_HIGHEST,
        ),
        HighlightedPlace(
            place_dcid="geoId/01",
            source=PlaceHighlightSource.RELATED_LOWEST,
        ),
        HighlightedPlace(
            place_dcid="geoId/02",
            source=PlaceHighlightSource.RELATED_LOWEST,
        ),
    )
    assert _build_record(series_record).highlighted_places == (
        HighlightedPlace(
            place_dcid="country/FRA", source=PlaceHighlightSource.TIMESERIES
        ),
        HighlightedPlace(
            place_dcid="country/DEU", source=PlaceHighlightSource.TIMESERIES
        ),
    )
    assert _build_record(comp_record).highlighted_places == (
        HighlightedPlace(
            place_dcid="country/FRA", source=PlaceHighlightSource.COMPOSITION
        ),
        HighlightedPlace(
            place_dcid="country/DEU", source=PlaceHighlightSource.COMPOSITION
        ),
    )


def test_derived_metrics_and_refused_steps_do_not_highlight_places() -> None:
    # Test: `DerivedMetrics` and `RefusedScriptResult` in `highlighted_places`.
    # Situation: A turn's digest contains an `ok` `DerivedMetrics` step over
    #   two non-empty fetched tables and a `RefusedScriptResult`.
    # Expectation: `highlighted_places` is empty.
    left = _make_cached_table(
        "t1", variable_dcid="Count_Employed", places=("country/FRA",)
    )
    right = _make_cached_table(
        "t2", variable_dcid="Count_Person", places=("country/FRA",)
    )
    derived_outcome = derive_observation_table(
        left.table, right.table, operation="per_capita", step_id="s1"
    )
    refused = RefusedScriptResult(
        step_id="s2",
        script="rank_cohort",
        variables=("Count_Person",),
        variable_names={"Count_Person": "Total Population"},
        provenance=Provenance(),
        variable_provenance={"Count_Person": Provenance()},
        refusal_reason="insufficient_coverage",
    )
    record = _make_record()
    record.cache.store_fetched(left)
    record.cache.store_fetched(right)
    record.digest = AnalysisDigest.from_results(
        (derived_outcome.result, refused)
    )

    assert _build_record(record).highlighted_places == ()


def test_highlighted_places_deduplicate_and_cap_at_twenty_five() -> None:
    # Test: Cross-step deduplication and 25-place cap on `highlighted_places`.
    # Situation: Step 1 (`analyze_timeseries`) highlights `geoId/30` and
    #   `geoId/29`. Step 2 (`rank_cohort` with `max_entries_per_end=15` over
    #   30 places) highlights all 30 places, including `geoId/30` and
    #   `geoId/29`.
    # Expectation: `geoId/30` and `geoId/29` appear once at the front with
    #   step 1's `timeseries` source, and the list stops at 25 distinct
    #   places in step and field order.
    places = tuple(f"geoId/{index:02d}" for index in range(1, 31))
    cached = _make_cached_table("t1", places=places, dates=("2022", "2023"))
    record = _make_record()
    record.cache.store_fetched(cached)
    record.digest = AnalysisDigest.from_results(
        (
            analyze_timeseries(
                cached.table, places=["geoId/30", "geoId/29"], step_id="s1"
            ),
            rank_cohort(cached.table, max_entries_per_end=15, step_id="s2"),
        )
    )

    highlighted = _build_record(record).highlighted_places

    assert len(highlighted) == MAX_HIGHLIGHTED_PLACES
    assert len({entry.place_dcid for entry in highlighted}) == (
        MAX_HIGHLIGHTED_PLACES
    )
    assert highlighted[:3] == (
        HighlightedPlace(
            place_dcid="geoId/30", source=PlaceHighlightSource.TIMESERIES
        ),
        HighlightedPlace(
            place_dcid="geoId/29", source=PlaceHighlightSource.TIMESERIES
        ),
        HighlightedPlace(
            place_dcid="geoId/28", source=PlaceHighlightSource.RANKED_TOP
        ),
    )


def test_highlighted_places_require_grounding_in_a_fetched_table() -> None:
    # Test: Grounding check on `highlighted_places`, including places from
    #   fetched tables truncated out of `tables`.
    # Situation: The cache holds 21 non-empty fetched tables (`t1`..`t21`,
    #   covering `geoId/01` through `geoId/21` respectively), an empty 0-row
    #   fetched table `t22` requesting `geoId/empty`, and a derived table `s1`
    #   covering `geoId/derived`. The digest highlights `geoId/01`, `geoId/21`,
    #   `geoId/empty`, `geoId/derived`, and an ungrounded `geoId/synthetic`.
    # Expectation: `t21` is omitted from `tables` by the 20-table cap, yet
    #   `geoId/21` is still accepted as grounded alongside `geoId/01`, while
    #   `geoId/empty`, `geoId/derived`, and `geoId/synthetic` are dropped.
    record = _make_record()
    for index in range(1, 22):
        record.cache.store_fetched(
            _make_cached_table(
                f"t{index}",
                places=(f"geoId/{index:02d}",),
                dates=("2023",),
            )
        )
    record.cache.store_fetched(
        CachedTable(
            table_id="t22",
            table=ObservationTable(
                variable_dcid="Count_Person",
                variable_name="Total Population",
                unit="Person",
                scaling_factor=None,
                provenance=Provenance(),
                rows=(),
                requested_places=("geoId/empty",),
                place_names={"geoId/empty": "Empty"},
            ),
        )
    )
    record.cache.store_derived(
        _make_cached_table(
            "s1",
            variable_dcid="Derived_Var",
            places=("geoId/derived",),
            dates=("2023",),
        )
    )
    synthetic_table = _make_cached_table(
        "t99",
        places=(
            "geoId/01",
            "geoId/21",
            "geoId/empty",
            "geoId/derived",
            "geoId/synthetic",
        ),
        dates=("2023",),
    )
    record.digest = AnalysisDigest.from_results(
        (analyze_timeseries(synthetic_table.table, step_id="s2"),)
    )

    usage = _build_record(record)

    assert len(usage.tables) == MAX_LOGGED_TABLES
    assert usage.tables_truncated is True
    assert "t21" not in {table.table_id for table in usage.tables}
    assert usage.highlighted_places == (
        HighlightedPlace(
            place_dcid="geoId/01", source=PlaceHighlightSource.TIMESERIES
        ),
        HighlightedPlace(
            place_dcid="geoId/21", source=PlaceHighlightSource.TIMESERIES
        ),
    )


@pytest.mark.parametrize("origin", ["model", "default"])
def test_a_specification_whose_run_succeeded_logs_every_step_as_ok(
    origin: SpecificationOrigin,
) -> None:
    # Test: `specification_origin` and `script_steps` after a run that
    #   succeeded.
    # Situation: The turn's specification has four steps. Its first
    #   two steps are `align_cohort` and `reduce_series`, which produce a
    #   cohort and not a result. The model wrote the specification, or the
    #   server built it as the default. The record does not hold a
    #   diagnostic for its run.
    # Expectation: The record holds the origin. `script_steps` lists all
    #   four steps in order, each with its index, its ID, its script, the
    #   status `ok`, and without a refusal reason.
    record = _make_record()
    record.specification = _COHORT_SPECIFICATION
    record.specification_origin = origin

    usage = _build_record(record)

    assert usage.specification_origin == origin
    assert usage.script_steps == (
        LoggedScriptStep(
            step_index=0,
            step_id="s1",
            script="align_cohort",
            status="ok",
            refusal_reason=None,
        ),
        LoggedScriptStep(
            step_index=1,
            step_id="s2",
            script="reduce_series",
            status="ok",
            refusal_reason=None,
        ),
        LoggedScriptStep(
            step_index=2,
            step_id="s3",
            script="rank_cohort",
            status="ok",
            refusal_reason=None,
        ),
        LoggedScriptStep(
            step_index=3,
            step_id="s4",
            script="rank_cohort",
            status="ok",
            refusal_reason=None,
        ),
    )


def test_an_earlier_failed_default_run_does_not_change_the_steps() -> None:
    # Test: `script_steps` when a retry of the default specification
    #   succeeded.
    # Situation: The first run of the default specification refused at `s1`,
    #   a `relate_cohorts` step, and the server kept that diagnostic with
    #   the diagnostics of the default runs. The retry, whose `s1` is an
    #   `align_cohort` step, succeeded, so the record does not hold a
    #   diagnostic for the turn's specification.
    # Expectation: The origin is `default`, and both steps of the retry have
    #   the status `ok`. The refusal of the first run does not appear.
    record = _make_record()
    record.default_diagnostics.append(
        _make_step_refusal("s1", "relate_cohorts", "insufficient_coverage")
    )
    record.specification = _RANKING_SPECIFICATION
    record.specification_origin = "default"

    usage = _build_record(record)

    assert usage.specification_origin == "default"
    assert [
        (step.step_id, step.script, step.status, step.refusal_reason)
        for step in usage.script_steps
    ] == [
        ("s1", "align_cohort", "ok", None),
        ("s2", "rank_cohort", "ok", None),
    ]


def test_a_refused_step_ends_the_script_steps() -> None:
    # Test: `script_steps` when the run of the turn's specification
    #   stopped at a refused step.
    # Situation: The last run of a default specification of four steps
    #   refused at its second step, `s2`, with the reason
    #   `no_observations`. Its diagnostic holds a free-text message.
    # Expectation: The first step has the status `ok`. The second step has
    #   the status `refused` and the reason code. The third and fourth
    #   steps, which did not run, are left out, while `scripts` in the
    #   telemetry is not read for this list.
    record = _make_record()
    record.specification = _COHORT_SPECIFICATION
    record.specification_origin = "default"
    record.specification_diagnostic = _make_step_refusal(
        "s2", "reduce_series", "no_observations"
    )

    usage = _build_record(record)

    assert usage.specification_origin == "default"
    assert usage.script_steps == (
        LoggedScriptStep(
            step_index=0,
            step_id="s1",
            script="align_cohort",
            status="ok",
            refusal_reason=None,
        ),
        LoggedScriptStep(
            step_index=1,
            step_id="s2",
            script="reduce_series",
            status="refused",
            refusal_reason="no_observations",
        ),
    )


def test_a_run_that_timed_out_does_not_list_script_steps() -> None:
    # Test: `script_steps` when the run of the turn's specification
    #   exceeded its time limit.
    # Situation: The last run of a default specification ended in a
    #   `TimeoutDiagnostic`, which does not say which steps finished. The
    #   telemetry lists the two scripts of the specification.
    # Expectation: The origin is `default`, `script_steps` is empty, and
    #   `scripts` still lists both scripts.
    record = _make_record()
    record.telemetry.scripts = _RANKING_SPECIFICATION.list_script_names()
    record.specification = _RANKING_SPECIFICATION
    record.specification_origin = "default"
    record.specification_diagnostic = _TIMEOUT

    usage = _build_record(record)

    assert usage.specification_origin == "default"
    assert usage.script_steps == ()
    assert usage.scripts == ("align_cohort", "rank_cohort")


def test_a_turn_without_a_specification_does_not_have_an_origin() -> None:
    # Test: `specification_origin` and `script_steps` without a
    #   specification.
    # Situation: The record holds an origin and a diagnostic, but it does
    #   not hold a specification.
    # Expectation: The origin is `None` and `script_steps` is empty, as in
    #   the debug report.
    record = _make_record()
    record.specification_origin = "model"
    record.specification_diagnostic = _make_step_refusal()

    usage = _build_record(record)

    assert usage.specification_origin is None
    assert usage.script_steps == ()


def test_a_refused_step_outside_the_specification_fails_the_build() -> None:
    # Test: Building a record whose diagnostic and specification disagree.
    # Situation: The turn's specification has the steps `s1` and `s2`, and
    #   the record's diagnostic names a refused step `s5`.
    # Expectation: `build_usage_record` raises `ValueError`, so the record
    #   never reports every step as `ok` beside a refusal.
    record = _make_record()
    record.specification = _RANKING_SPECIFICATION
    record.specification_origin = "default"
    record.specification_diagnostic = _make_step_refusal("s5")

    with pytest.raises(ValueError, match="does not hold the refused step"):
        _build_record(record)


def test_a_step_with_a_malformed_id_is_left_out_of_script_steps() -> None:
    # Test: The pattern check on the step IDs of `script_steps`.
    # Situation: The turn's specification holds three steps that were
    #   built without validation. The ID of the second step is free text.
    # Expectation: `script_steps` lists the first and the third step with
    #   their own indexes, and the free text does not appear.
    steps = [
        RankCohortStep.model_construct(
            step_id=step_id, script="rank_cohort", table="t1"
        )
        for step_id in ("s1", "free text", "s3")
    ]
    record = _make_record()
    record.specification = AnalysisSpecification.model_construct(steps=steps)
    record.specification_origin = "model"

    usage = _build_record(record)

    assert [(step.step_index, step.step_id) for step in usage.script_steps] == [
        (0, "s1"),
        (2, "s3"),
    ]


@pytest.mark.parametrize(
    ("submission", "expected"),
    [
        pytest.param(
            RejectedSubmission(
                round_number=1,
                reason="schema_invalid",
                errors=("- steps.0: free text of a validation error",),
            ),
            LoggedRejectedSubmission(
                round_number=1,
                reason="schema_invalid",
                scripts=(),
                failed_step_id=None,
                failed_script=None,
                refusal_reason=None,
                timed_out=False,
            ),
            id="schema_invalid",
        ),
        pytest.param(
            RejectedSubmission(
                round_number=2,
                reason="reference_invalid",
                errors=("s1.table references t99, free text",),
                specification=_COHORT_SPECIFICATION,
            ),
            LoggedRejectedSubmission(
                round_number=2,
                reason="reference_invalid",
                scripts=(
                    "align_cohort",
                    "reduce_series",
                    "rank_cohort",
                    "rank_cohort",
                ),
                failed_step_id=None,
                failed_script=None,
                refusal_reason=None,
                timed_out=False,
            ),
            id="reference_invalid",
        ),
        pytest.param(
            RejectedSubmission(
                round_number=3,
                reason="processing_failed",
                errors=("Only 1 of 4 places have a value.",),
                specification=_RANKING_SPECIFICATION,
                diagnostic=_make_step_refusal(
                    "s2", "rank_cohort", "unit_mismatch"
                ),
            ),
            LoggedRejectedSubmission(
                round_number=3,
                reason="processing_failed",
                scripts=("align_cohort", "rank_cohort"),
                failed_step_id="s2",
                failed_script="rank_cohort",
                refusal_reason="unit_mismatch",
                timed_out=False,
            ),
            id="processing_failed at a refused step",
        ),
        pytest.param(
            RejectedSubmission(
                round_number=4,
                reason="processing_failed",
                errors=(_TIMEOUT.message,),
                specification=_RANKING_SPECIFICATION,
                diagnostic=_TIMEOUT,
            ),
            LoggedRejectedSubmission(
                round_number=4,
                reason="processing_failed",
                scripts=("align_cohort", "rank_cohort"),
                failed_step_id=None,
                failed_script=None,
                refusal_reason=None,
                timed_out=True,
            ),
            id="processing_failed at the time limit",
        ),
        pytest.param(
            RejectedSubmission(
                round_number=5,
                reason="processing_failed",
                errors=("Only 1 of 4 places have a value.",),
                specification=_RANKING_SPECIFICATION,
                diagnostic=_make_step_refusal("free text", "rank_cohort"),
            ),
            LoggedRejectedSubmission(
                round_number=5,
                reason="processing_failed",
                scripts=("align_cohort", "rank_cohort"),
                failed_step_id=None,
                failed_script="rank_cohort",
                refusal_reason="insufficient_coverage",
                timed_out=False,
            ),
            id="refused step with a malformed ID",
        ),
    ],
)
def test_a_rejected_submission_is_logged_by_its_codes(
    submission: RejectedSubmission, expected: LoggedRejectedSubmission
) -> None:
    # Test: The logged form of each kind of rejected specification.
    # Situation: The discovery loop rejected one specification. It did not
    #   parse, it did not match the fetched tables, it refused at a step, it
    #   exceeded its time limit, or it refused at a step whose ID is free
    #   text. Each submission holds free-text errors.
    # Expectation: The record holds the round, the reason, and the scripts
    #   of a specification that parsed. Only a refused step fills the three
    #   step fields, and a step ID that is not `s<n>` is `None`. Only a run
    #   that exceeded its time limit has `timed_out` set.
    record = _make_record()
    record.loop_result.rejected_submissions.append(submission)

    assert _build_record(record).rejected_submissions == (expected,)


def test_rejected_submissions_are_capped_at_the_bound_of_the_loop() -> None:
    # Test: The cap on `rejected_submissions`.
    # Situation: The loop result holds five rejected specifications, in
    #   rounds 1 through 5, which is more than the discovery loop records.
    # Expectation: The record holds the first
    #   `MAX_LOGGED_REJECTED_SUBMISSIONS`, in submission order. The cap is
    #   one more than `MAX_PROCESSING_RETRIES`, which is three.
    record = _make_record()
    record.loop_result.rejected_submissions.extend(
        RejectedSubmission(
            round_number=round_number,
            reason="schema_invalid",
            errors=("free text",),
        )
        for round_number in range(1, 6)
    )

    logged = _build_record(record).rejected_submissions

    assert MAX_LOGGED_REJECTED_SUBMISSIONS == MAX_PROCESSING_RETRIES + 1 == 3
    assert [item.round_number for item in logged] == [1, 2, 3]


@pytest.mark.parametrize(
    ("chart", "expected"),
    [
        pytest.param(
            replace(
                _make_line_chart("country/FRA", "country/DEU"), per_capita=True
            ),
            _make_logged_chart(
                "line",
                place_dcids=("country/FRA", "country/DEU"),
                per_capita=True,
            ),
            id="line of named places, per capita",
        ),
        pytest.param(
            ResolvedLineChart(
                title=_CHART_TITLE,
                variable_dcids=("Median_Income_Household",),
                facet_ids=(("Median_Income_Household", "f2"),),
                scope=_COUNTIES,
            ),
            _make_logged_chart(
                "line",
                variable_dcid="Median_Income_Household",
                facet_id="f2",
                cohort=_COUNTIES,
            ),
            id="line of a cohort",
        ),
        pytest.param(
            ResolvedBarChart(
                title=_CHART_TITLE,
                unit=_CHART_UNIT,
                variable_dcids=("Count_Person",),
                facet_ids=(("Count_Person", "f1"),),
                scope=PlaceList(("country/DEU", "country/FRA")),
            ),
            _make_logged_chart(
                "bar", place_dcids=("country/DEU", "country/FRA")
            ),
            id="bar of named places",
        ),
        pytest.param(
            ResolvedBarChart(
                title=_CHART_TITLE,
                variable_dcids=("Median_Income_Household",),
                facet_ids=(("Median_Income_Household", "f2"),),
                scope=_COUNTIES,
            ),
            _make_logged_chart(
                "bar",
                variable_dcid="Median_Income_Household",
                facet_id="f2",
                cohort=_COUNTIES,
            ),
            id="bar of a cohort",
        ),
        pytest.param(
            ResolvedRankingChart(
                title=_CHART_TITLE,
                variable_dcids=("Median_Income_Household",),
                facet_ids=(("Median_Income_Household", "f2"),),
                cohort=_COUNTIES,
            ),
            _make_logged_chart(
                "ranking",
                variable_dcid="Median_Income_Household",
                facet_id="f2",
                cohort=_COUNTIES,
            ),
            id="ranking",
        ),
        pytest.param(
            ResolvedMapChart(
                title=_CHART_TITLE,
                variable_dcids=("Median_Income_Household",),
                facet_ids=(("Median_Income_Household", "f2"),),
                cohort=_COUNTIES,
                per_capita=True,
            ),
            _make_logged_chart(
                "map",
                variable_dcid="Median_Income_Household",
                facet_id="f2",
                cohort=_COUNTIES,
                per_capita=True,
            ),
            id="map, per capita",
        ),
        pytest.param(
            ResolvedScatterChart(
                title=_CHART_TITLE,
                variable_dcids=(
                    "Percent_Person_WithDiabetes",
                    "Median_Income_Household",
                ),
                facet_ids=(
                    ("Percent_Person_WithDiabetes", "f3"),
                    ("Median_Income_Household", "f2"),
                ),
                cohort=_COUNTIES,
            ),
            LoggedChart(
                index=0,
                kind="scatter",
                origin="model",
                variables=(
                    ChartVariable(
                        variable_dcid="Percent_Person_WithDiabetes",
                        facet_id="f3",
                    ),
                    ChartVariable(
                        variable_dcid="Median_Income_Household", facet_id="f2"
                    ),
                ),
                parent_place_dcid="geoId/06",
                child_place_type="County",
                place_dcids=(),
                per_capita=False,
            ),
            id="scatter",
        ),
        pytest.param(
            ResolvedHighlightChart(
                title=_CHART_TITLE,
                unit=_CHART_UNIT,
                variable_dcids=("Count_Person",),
                facet_ids=(("Count_Person", "f1"),),
                place_dcid="country/DEU",
            ),
            _make_logged_chart("highlight", place_dcids=("country/DEU",)),
            id="highlight",
        ),
    ],
)
def test_a_chart_of_each_kind_is_logged_by_its_identifiers(
    chart: ResolvedChart, expected: LoggedChart
) -> None:
    # Test: The logged form of a chart of each of the six kinds.
    # Situation: The turn fetched a named-place table and two county cohort
    #   tables, and the model wrote one chart with a free-text title. The
    #   chart is a line or a bar of named places or of the cohort, a
    #   ranking, a map, a scatter of two variables, or a highlight of one
    #   place. Two of the charts are per capita.
    # Expectation: The record holds the kind, the origin `model`, the
    #   variables, the facet of each variable, and the per-capita
    #   flag. A chart of named places lists them in the chart's order and
    #   does not have a parent place. A chart of the cohort has the parent
    #   place and the child place type, and its `place_dcids` is empty.
    record = _make_record()
    _store_chart_tables(record)
    record.charts = _make_turn_charts(chart)

    assert _build_record(record).charts == (expected,)


def test_a_chart_lists_up_to_twenty_five_places_in_its_own_order() -> None:
    # Test: The order and the cap of `place_dcids` on a chart.
    # Situation: A fetched table has rows for 30 places, and a line chart
    #   lists all 30 from the last to the first.
    # Expectation: The chart's `place_dcids` holds the first
    #   `MAX_TABLE_PLACE_DCIDS` (25) places in the chart's order, which is
    #   not the sorted order that `tables` uses.
    places = [f"geoId/{index:02d}" for index in range(1, 31)]
    record = _make_record()
    record.cache.store_fetched(
        _make_cached_table("t1", places=places, dates=("2023",))
    )
    record.charts = _make_turn_charts(_make_line_chart(*reversed(places)))

    (logged,) = _build_record(record).charts

    assert len(logged.place_dcids) == MAX_TABLE_PLACE_DCIDS
    assert logged.place_dcids == tuple(
        f"geoId/{index:02d}" for index in range(30, 5, -1)
    )


def test_a_chart_lists_up_to_ten_variables_with_their_facets() -> None:
    # Test: The cap on `variables` of a chart.
    # Situation: The turn fetched 12 tables of 12 variables for France, each
    #   from its own facet. A bar chart draws all 12 variables and pins each
    #   to its facet.
    # Expectation: The chart's `variables` holds the first
    #   `MAX_CHART_VARIABLES` (10) variables in the chart's order, each with
    #   its facet.
    variables = [f"Count_Person_{index:02d}" for index in range(1, 13)]
    record = _make_record()
    for index, variable_dcid in enumerate(variables, start=1):
        record.cache.store_fetched(
            _make_cached_table(
                f"t{index}",
                variable_dcid=variable_dcid,
                facet_id=f"f{index}",
            )
        )
    record.charts = _make_turn_charts(
        ResolvedBarChart(
            title=_CHART_TITLE,
            variable_dcids=(variables[0], *variables[1:]),
            facet_ids=tuple(
                (variable_dcid, f"f{index}")
                for index, variable_dcid in enumerate(variables, start=1)
            ),
            scope=PlaceList(("country/FRA",)),
        ),
    )

    (logged,) = _build_record(record).charts

    assert MAX_CHART_VARIABLES == 10
    assert logged.variables == tuple(
        ChartVariable(variable_dcid=variable_dcid, facet_id=f"f{index}")
        for index, variable_dcid in enumerate(variables[:10], start=1)
    )


def test_a_chart_keeps_only_identifiers_that_a_fetched_table_holds() -> None:
    # Test: The grounding of the variables, facets, and places of a chart.
    # Situation: The turn fetched `t1` with rows for France, fetched an
    #   empty `t2` for another variable and place, and derived `s1`, whose
    #   variable ID the model wrote. A bar chart names the variable of each
    #   of the three tables, pins the first to a facet ID that is free text
    #   and the other two to valid facet IDs, and lists France, the place of
    #   the empty table, the place of the derived table, and a place that
    #   the turn did not fetch. A highlight chart shows that last place.
    # Expectation: The bar chart keeps the variable of `t1` without a facet
    #   and keeps France. The highlight chart does not keep a variable or a
    #   place. The record holds both charts.
    record = _make_record()
    record.cache.store_fetched(_make_cached_table("t1"))
    record.cache.store_fetched(
        _make_cached_table(
            "t2",
            variable_dcid="Count_Empty_Indicator",
            places=("country/EMPTY",),
            dates=(),
        )
    )
    record.cache.store_derived(
        _make_cached_table(
            "s1",
            variable_dcid="model_written_derived_variable",
            places=("country/DERIVED",),
        )
    )
    record.charts = _make_turn_charts(
        ResolvedBarChart(
            title=_CHART_TITLE,
            variable_dcids=(
                "Count_Person",
                "Count_Empty_Indicator",
                "model_written_derived_variable",
            ),
            facet_ids=(
                ("Count_Person", "free text"),
                ("Count_Empty_Indicator", "f1"),
                ("model_written_derived_variable", "f1"),
            ),
            scope=PlaceList(
                (
                    "country/FRA",
                    "country/EMPTY",
                    "country/DERIVED",
                    "country/UNFETCHED",
                )
            ),
        ),
        ResolvedHighlightChart(
            title=_CHART_TITLE,
            variable_dcids=("model_written_derived_variable",),
            place_dcid="country/UNFETCHED",
        ),
    )

    assert _build_record(record).charts == (
        LoggedChart(
            index=0,
            kind="bar",
            origin="model",
            variables=(
                ChartVariable(variable_dcid="Count_Person", facet_id=None),
            ),
            parent_place_dcid=None,
            child_place_type=None,
            place_dcids=("country/FRA",),
            per_capita=False,
        ),
        LoggedChart(
            index=1,
            kind="highlight",
            origin="model",
            variables=(),
            parent_place_dcid=None,
            child_place_type=None,
            place_dcids=(),
            per_capita=False,
        ),
    )


@pytest.mark.parametrize(
    ("cohort", "is_kept"),
    [
        pytest.param(_COUNTIES, True, id="cohort of a fetched table"),
        pytest.param(
            ChildCohort("country/FRA", "AdministrativeArea1"),
            False,
            id="parent that has rows in a table of named places",
        ),
        pytest.param(
            ChildCohort("geoId/48", "County"),
            False,
            id="parent that the turn did not fetch",
        ),
        pytest.param(
            ChildCohort("geoId/06", "City"),
            False,
            id="fetched parent with a child place type that was not fetched",
        ),
        pytest.param(
            ChildCohort("geoId/06", "County Name"),
            False,
            id="child place type that is free text",
        ),
    ],
)
def test_a_chart_keeps_a_cohort_that_a_fetched_table_covers(
    cohort: ChildCohort, is_kept: bool
) -> None:
    # Test: The grounding of the cohort of a chart.
    # Situation: The turn fetched a named-place table with rows for France
    #   and a county cohort table of `geoId/06`, whose rows hold only the
    #   counties. A map draws one of five cohorts: the fetched cohort, the
    #   children of France, the counties of a parent that the turn did not
    #   fetch, the cities of the fetched parent, or the fetched parent with
    #   a child place type that is free text.
    # Expectation: The record keeps the parent place and the child place
    #   type of the fetched cohort, although `geoId/06` does not have a row
    #   of its own. Both are `None` for the other four, because a fetched
    #   table does not cover that parent place with that child place type.
    #   `place_dcids` is always empty.
    record = _make_record()
    _store_chart_tables(record)
    record.charts = _make_turn_charts(
        ResolvedMapChart(
            title=_CHART_TITLE,
            variable_dcids=("Median_Income_Household",),
            cohort=cohort,
        ),
    )

    (logged,) = _build_record(record).charts

    assert logged.place_dcids == ()
    if is_kept:
        assert logged.parent_place_dcid == cohort.parent_place
        assert logged.child_place_type == cohort.child_place_type
    else:
        assert logged.parent_place_dcid is None
        assert logged.child_place_type is None


@pytest.mark.parametrize(
    ("facet_id", "logged_facet_id"),
    [
        pytest.param("f1", "f1", id="facet of a fetched table of the variable"),
        pytest.param(
            "f2", None, id="facet of a fetched table of another variable"
        ),
        pytest.param("f9", None, id="facet that the turn did not fetch"),
        pytest.param("free text", None, id="facet that is free text"),
        pytest.param(None, None, id="variable that the chart does not pin"),
    ],
)
def test_a_chart_variable_keeps_a_facet_that_a_fetched_table_reports_for_it(
    facet_id: str | None, logged_facet_id: str | None
) -> None:
    # Test: The grounding of the facet of a chart's variable.
    # Situation: The turn fetched `Count_Person` for France from the facet
    #   `f1`, and another variable from the facet `f2`. A line chart draws
    #   `Count_Person` for France. It pins the variable to `f1`, to `f2`, to
    #   a facet that the turn did not fetch, or to free text, or it does not
    #   pin the variable.
    # Expectation: The record keeps the variable in every case. Its
    #   `facet_id` is `f1` for the pin to `f1`. It is `None` for the other
    #   three pins, because a fetched table does not report that facet for
    #   `Count_Person`, and for the variable that the chart does not pin.
    record = _make_record()
    _store_chart_tables(record)
    record.charts = _make_turn_charts(
        ResolvedLineChart(
            title=_CHART_TITLE,
            variable_dcids=("Count_Person",),
            facet_ids=(
                () if facet_id is None else (("Count_Person", facet_id),)
            ),
            scope=PlaceList(("country/FRA",)),
        )
    )

    (logged,) = _build_record(record).charts

    assert logged.variables == (
        ChartVariable(variable_dcid="Count_Person", facet_id=logged_facet_id),
    )


def test_each_chart_is_logged_with_its_recorded_origin() -> None:
    # Test: `origin` and `index` on the charts of the record.
    # Situation: The turn's record holds two charts. The first has the
    #   origin `model` and the second has the origin `default`.
    # Expectation: Each logged chart has the origin that the record holds
    #   for it and its position as `index`.
    record = _make_record()
    _store_chart_tables(record)
    record.charts = (
        TurnChart(chart=_make_line_chart("country/FRA"), origin="model"),
        TurnChart(chart=_make_line_chart("country/DEU"), origin="default"),
    )

    assert [
        (chart.index, chart.origin, chart.place_dcids)
        for chart in _build_record(record).charts
    ] == [
        (0, "model", ("country/FRA",)),
        (1, "default", ("country/DEU",)),
    ]


def test_charts_are_capped_at_four() -> None:
    # Test: The cap on `charts`.
    # Situation: The turn's record holds five charts.
    # Expectation: The record holds the first `MAX_LOGGED_CHARTS` (4), with
    #   the indexes 0 through 3.
    record = _make_record()
    _store_chart_tables(record)
    record.charts = _make_turn_charts(_make_line_chart("country/FRA")) * 5

    logged = _build_record(record).charts

    assert MAX_LOGGED_CHARTS == 4
    assert [chart.index for chart in logged] == [0, 1, 2, 3]


def test_a_turn_that_has_not_ended_does_not_have_a_record() -> None:
    # Test: Building a record before the turn has a terminal state.
    # Situation: The turn's record does not have a terminal state yet.
    # Expectation: `build_usage_record` raises `ValueError`.
    record = TurnRecord(telemetry=TurnTelemetry(turn_id=_TURN_ID))

    with pytest.raises(ValueError, match="has not ended"):
        _build_record(record)


def test_the_largest_record_fits_in_one_line(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    structured_lines: list[str],
) -> None:
    # Test: The size of the largest `chat_turn` line.
    # Situation: A failed turn has every list of the record at its bound: a
    #   duration for every phase, a count for every tool name and label
    #   that the discovery loop can record, a token call for every
    #   discovery round and for each of the other four roles, 20 cohort
    #   tables, 25 highlighted places carrying the longest source literal,
    #   six scripts, six script steps that end in a refused step, three
    #   rejected specifications, and four charts that each list 25 places.
    #   Every count and the duration have nine digits. The script, the
    #   reasons, and the pattern are the longest of their literals. The code
    #   does not bound the model name or the build SHA, so the test assumes
    #   a model name of 64 characters and a SHA of 40 characters. The server
    #   trims only `tables`, and four charts with `MAX_CHART_VARIABLES`
    #   variables each do not fit in the line, so the test assumes five
    #   variables on each chart.
    # Expectation: The record holds all 25 highlighted places, all six
    #   script steps, the three rejected specifications, all four charts,
    #   one token call for each of the `MAX_ITERATIONS` discovery rounds and
    #   four more, one count for each tool name, and the duration of
    #   999,999,999.25 ms. The server drops tables from the end of `tables`
    #   to make the line fit, and keeps at least one. The written line is at
    #   most `MAX_RECORD_LINE_BYTES` and does not log an oversized-line
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
    places = tuple(
        f"geoId/06{index:03d}" for index in range(1, MAX_HIGHLIGHTED_PLACES + 1)
    )
    for table_index in range(1, MAX_LOGGED_TABLES + 1):
        record.cache.store_fetched(
            _make_cached_table(
                f"t{table_index}",
                variable_dcid=f"Median_Income_Household_{table_index:02d}",
                places=places,
                dates=("2022-01-01", "2023-12-31"),
                facet_id=f"facet_{table_index:04d}",
                parent_place_dcid="country/USA",
                child_place_type="AdministrativeArea2",
            )
        )
    record.used_table_ids = frozenset(f"t{index}" for index in range(1, 7))
    specification = AnalysisSpecification.model_validate(
        {
            "steps": [
                {
                    "step_id": f"s{index}",
                    "script": longest_script,
                    "left": "t1",
                    "right": "t2",
                }
                for index in range(1, 7)
            ]
        }
    )
    refusal = _make_step_refusal(
        "s6", longest_script, "components_exceed_total"
    )
    record.specification = specification
    record.specification_origin = "default"
    record.specification_diagnostic = refusal
    record.loop_result.rejected_submissions.extend(
        RejectedSubmission(
            round_number=large,
            reason="processing_failed",
            errors=(refusal.message,),
            specification=specification,
            diagnostic=refusal,
        )
        for _ in range(MAX_LOGGED_REJECTED_SUBMISSIONS)
    )
    chart_variables = [
        f"Median_Income_Household_{index:02d}" for index in range(1, 6)
    ]
    record.charts = (
        _make_turn_charts(
            ResolvedLineChart(
                title=_CHART_TITLE,
                variable_dcids=(chart_variables[0], *chart_variables[1:]),
                facet_ids=tuple(
                    (variable_dcid, f"facet_{index:04d}")
                    for index, variable_dcid in enumerate(
                        chart_variables, start=1
                    )
                ),
                scope=PlaceList(places),
                per_capita=True,
            ),
            origin="default",
        )
        * MAX_LOGGED_CHARTS
    )
    first_table = record.cache.get("t1")
    assert first_table is not None
    record.digest = AnalysisDigest.from_results(
        (
            summarize_distribution(
                first_table.table,
                focal_places=list(places),
                step_id="s1",
            ),
        )
    )
    record.loop_result.truncated = True
    record.is_signed = True
    record.was_compacted = True
    _finish_turn(
        monkeypatch,
        record,
        TerminalState.ERROR,
        ErrorType.DAILY_TOKEN_BUDGET_EXHAUSTED,
        seconds=999_999.99925,
    )
    usage = build_usage_record(
        record, _make_transcript(MAX_TURN_INDEX), build_sha="f" * 40
    )

    with caplog.at_level(logging.WARNING, logger=telemetry_module.__name__):
        write_structured_record(usage)

    (line,) = structured_lines
    assert 0 < len(usage.tables) < MAX_LOGGED_TABLES
    assert usage.tables_truncated is True
    assert len(usage.highlighted_places) == MAX_HIGHLIGHTED_PLACES
    assert [step.status for step in usage.script_steps] == [
        *["ok"] * 5,
        "refused",
    ]
    assert len(usage.rejected_submissions) == MAX_LOGGED_REJECTED_SUBMISSIONS
    assert [len(chart.place_dcids) for chart in usage.charts] == (
        [MAX_TABLE_PLACE_DCIDS] * MAX_LOGGED_CHARTS
    )
    assert len(usage.token_calls) == MAX_ITERATIONS + 4
    assert usage.duration_ms == 999_999_999.25
    assert len(usage.tool_call_counts) == len(tools)
    assert len(line.encode("utf-8")) <= MAX_RECORD_LINE_BYTES
    assert caplog.records == []
