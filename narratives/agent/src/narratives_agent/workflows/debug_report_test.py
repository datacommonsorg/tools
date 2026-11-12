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
"""Tests for the turn debug report builder and gating in `debug_report`.

Verifies these behaviors in `debug_report`:
1. `should_emit_debug_report` gates emission across ("off", "on", "flag") modes
   and client request flags.
2. `build_debug_report` and `to_dict` handle terminal states (complete,
   clarification, refused, error).
3. Refused turns omit `pattern` even if `telemetry.pattern` was set.
4. `nested_phases` correctly attributes `processing` to `discovery`.
5. Aggregate and per-call token attribution are preserved.
6. Empty or populated `TurnCache` tables are profiled, covering chosen vs
   default vs derived sources, answer usage flags, date ranges, place caps,
   and place name resolution fallbacks.
7. `truncate_debug_text` preserves character count and truncates at boundaries.
8. `synthesis_prompt` and `synthesis_raw_output` are capped and serialized.
9. `role_configs` captures all 5 roles and clamps levels without secrets.
10. `prompt_hashes` hashes all prompt slots and packaged contracts.
11. `build_sha` is propagated and serialized.
"""

import hashlib
import json
import re
from dataclasses import replace
from types import MappingProxyType

import pytest

from narratives_agent.analytics.digest import AnalysisDigest, CoverageReport
from narratives_agent.analytics.provenance import Provenance, Source
from narratives_agent.analytics.summarize import SUMMARY_PLACE_LIST_CAP
from narratives_agent.analytics.tables import ObservationRow, ObservationTable
from narratives_agent.config_model import (
    PROMPT_SLOTS,
    AgentConfig,
    GeminiConfig,
    GeminiRole,
    Prompts,
)
from narratives_agent.gemini.schemas import QueryPattern
from narratives_agent.json_value import JsonObject
from narratives_agent.settings import DebugReportMode
from narratives_agent.telemetry import (
    TerminalState,
    TokenCounts,
    TurnTelemetry,
)
from narratives_agent.workflows.debug_report import (
    MAX_DEBUG_TEXT_CHARS,
    DebugCappedText,
    DebugRoleConfig,
    DebugStepRefusalDiagnostic,
    DebugThought,
    DebugTimeoutDiagnostic,
    build_debug_report,
    should_emit_debug_report,
    truncate_debug_text,
)
from narratives_agent.workflows.mcp_loop import RejectedSubmission
from narratives_agent.workflows.processing import (
    ProcessingDiagnostic,
    StepRefusalDiagnostic,
    TimeoutDiagnostic,
)
from narratives_agent.workflows.prompt_contracts import load_prompt_contract
from narratives_agent.workflows.specification import (
    AnalysisSpecification,
    AnalyzeTimeseriesStep,
    RankCohortStep,
    UnavailableReport,
)
from narratives_agent.workflows.turn_cache import CachedTable, TurnCache


def _make_telemetry(
    *,
    turn_id: str = "test-turn-123",
    pattern: QueryPattern | None = "single_point",
    mcp_iterations: int = 2,
    scripts: list[str] | None = None,
    processing_retries: int = 1,
    charts_emitted: int = 2,
    charts_rejected: int = 0,
    phase_durations: dict[str, float] | None = None,
) -> TurnTelemetry:
    """Factory helper returning a populated TurnTelemetry instance."""
    telemetry = TurnTelemetry(turn_id=turn_id)
    telemetry.pattern = pattern
    telemetry.mcp_iterations = mcp_iterations
    telemetry.scripts = scripts or ["analyze_timeseries"]
    telemetry.processing_retries = processing_retries
    telemetry.charts_emitted = charts_emitted
    telemetry.charts_rejected = charts_rejected
    if phase_durations is not None:
        telemetry.phase_durations_ms.update(phase_durations)
    return telemetry


def _make_table(
    *,
    variable_dcid: str = "Count_Person",
    variable_name: str = "Population",
    unit: str | None = "persons",
    scaling_factor: float | None = 1.0,
    measurement_method: str | None = "CensusMethod",
    observation_period: str | None = "P1Y",
    facet_id: str | None = "facet-123",
    source: Source | None = None,
    rows: tuple[ObservationRow, ...] = (),
    requested_places: tuple[str, ...] = ("country/USA",),
    place_names: dict[str, str] | None = None,
    parent_place_dcid: str | None = None,
    child_place_type: str | None = None,
) -> ObservationTable:
    """Factory helper returning an ObservationTable instance."""
    return ObservationTable(
        variable_dcid=variable_dcid,
        variable_name=variable_name,
        unit=unit,
        scaling_factor=scaling_factor,
        measurement_method=measurement_method,
        observation_period=observation_period,
        facet_id=facet_id,
        source=source,
        rows=rows,
        requested_places=requested_places,
        place_names=place_names or {"country/USA": "United States"},
        parent_place_dcid=parent_place_dcid,
        child_place_type=child_place_type,
        provenance=Provenance(),
    )


@pytest.mark.parametrize(
    ("mode", "request_debug", "expected"),
    [
        pytest.param("off", False, False, id="off-no-request"),
        pytest.param("off", True, False, id="off-with-request"),
        pytest.param("on", False, True, id="on-no-request"),
        pytest.param("on", True, True, id="on-with-request"),
        pytest.param("flag", False, False, id="flag-no-request"),
        pytest.param("flag", True, True, id="flag-with-request"),
    ],
)
def test_should_emit_debug_report(
    mode: DebugReportMode, request_debug: bool, expected: bool
) -> None:
    # Test: Gating logic of `should_emit_debug_report`.
    # Situation: Every combination of server `mode` and client `request_debug`.
    # Expectation: "off" is always False; "on" is always True; "flag" reflects
    #   the client's request.
    assert (
        should_emit_debug_report(mode, request_debug=request_debug) is expected
    )


def test_build_debug_report_complete_turn_with_tokens_and_phases() -> None:
    # Test: Construction of DebugReport for a complete turn.
    # Situation: A turn completes successfully with discovery, processing,
    #   and synthesis phases, along with token call records.
    # Expectation: `pattern` is preserved, duration matches elapsed_ms(),
    #   `nested_phases` maps processing to discovery, and tokens and to_dict()
    #   serialize accurately.
    telemetry = _make_telemetry(
        turn_id="turn-complete-1",
        pattern="trend_delta",
        phase_durations={
            "discovery": 120.5,
            "processing": 45.2,
            "synthesis": 80.0,
        },
    )
    telemetry.tokens.add(
        TokenCounts(prompt=100, candidates=50, thoughts=20, total=170),
        phase="discovery",
        model="gemini-2.5-flash",
        round_number=1,
    )
    telemetry.tokens.add(
        TokenCounts(prompt=60, candidates=40, thoughts=0, total=100),
        phase="synthesis",
        model="gemini-2.5-flash",
    )
    telemetry.finish(TerminalState.COMPLETE)

    report = build_debug_report(
        telemetry=telemetry,
        terminal_state="complete",
        terminal_reason=None,
        is_clarification=False,
    )

    assert report.turn_id == "turn-complete-1"
    assert report.terminal_state == "complete"
    assert report.terminal_reason is None
    assert not report.is_clarification
    assert report.pattern == "trend_delta"
    assert report.duration_ms == telemetry.elapsed_ms()
    assert report.phase_durations_ms == {
        "discovery": 120.5,
        "processing": 45.2,
        "synthesis": 80.0,
    }
    assert report.nested_phases == {"processing": "discovery"}
    assert report.mcp_iterations == 2
    assert report.scripts == ("analyze_timeseries",)
    assert report.processing_retries == 1
    assert report.charts_emitted == 2
    assert report.charts_rejected == 0
    assert report.tokens.prompt_token_count == 160
    assert report.tokens.candidates_token_count == 90
    assert report.tokens.thoughts_token_count == 20
    assert report.tokens.total_token_count == 270
    assert len(report.tokens.calls) == 2
    assert report.tokens.calls[0].phase == "discovery"
    assert report.tokens.calls[0].round_number == 1
    assert report.tokens.calls[1].phase == "synthesis"
    assert report.tokens.calls[1].round_number is None

    payload = report.to_dict()
    assert payload["turn_id"] == "turn-complete-1"
    assert payload["nested_phases"] == {"processing": "discovery"}
    assert payload["tables"] == []
    # Verify round-trip JSON serialization.
    assert json.loads(json.dumps(payload)) == payload


def test_build_debug_report_clarification_turn() -> None:
    # Test: DebugReport for a clarification turn.
    # Situation: A turn ends in clarification without processing.
    # Expectation: `is_clarification` is True, `nested_phases` is empty,
    #   and `pattern` is retained.
    telemetry = _make_telemetry(
        pattern="single_point",
        phase_durations={"discovery": 50.0},
    )
    report = build_debug_report(
        telemetry=telemetry,
        terminal_state="complete",
        terminal_reason=None,
        is_clarification=True,
    )

    assert report.is_clarification is True
    assert report.pattern == "single_point"
    assert report.nested_phases == {}


def test_build_debug_report_refused_turn_omits_pattern() -> None:
    # Test: `pattern` omission on refused turns.
    # Situation: A turn is refused with reason 'off_domain' after a pattern
    #   was assigned.
    # Expectation: `pattern` on `DebugReport` is None even though
    #   `telemetry.pattern` was set.
    telemetry = _make_telemetry(pattern="outliers")
    telemetry.finish(TerminalState.REFUSED, "off_domain")

    report = build_debug_report(
        telemetry=telemetry,
        terminal_state="refused",
        terminal_reason="off_domain",
    )

    assert report.terminal_state == "refused"
    assert report.terminal_reason == "off_domain"
    assert report.pattern is None
    assert report.to_dict()["pattern"] is None


def test_build_debug_report_error_turn() -> None:
    # Test: DebugReport on an error turn.
    # Situation: Turn ends with terminal_state="error" and a reason code.
    # Expectation: The error state and terminal reason are preserved.
    telemetry = _make_telemetry()
    telemetry.finish(TerminalState.ERROR, "mcp_timeout")

    report = build_debug_report(
        telemetry=telemetry,
        terminal_state="error",
        terminal_reason="mcp_timeout",
    )

    assert report.terminal_state == "error"
    assert report.terminal_reason == "mcp_timeout"


def test_build_debug_report_with_cached_tables_profiles_all_variants() -> None:
    # Test: Observation table profiling across all metadata variants.
    # Situation: Cache contains:
    #   - t1: fetched with explicit source override (chosen), used in answer,
    #     has full Source fields and dates.
    #   - t2: fetched with default source (server_default), unused in answer,
    #     empty rows (date_range=None, row_count=0).
    #   - s1: derived table (derived), used in answer.
    # Expectation: Table records match expected source selection, usage flags,
    #   date ranges, and row counts in storage order.
    cache = TurnCache()
    source = Source(
        name="US Census Bureau",
        url="https://census.gov",
        license="Public Domain",
        dataset="Decennial Census",
        provider="U.S. Dept of Commerce",
        date_range="2010 - 2020",
    )
    t1_table = _make_table(
        variable_dcid="Count_Person",
        variable_name="Population",
        source=source,
        rows=(
            ObservationRow(
                place_dcid="country/USA",
                place_name="United States",
                date="2010",
                value=308745538.0,
            ),
            ObservationRow(
                place_dcid="country/USA",
                place_name="United States",
                date="2020",
                value=331449281.0,
            ),
        ),
    )
    cache.store_fetched(
        CachedTable(
            table_id="t1",
            table=t1_table,
            source_selected_explicitly=True,
        )
    )

    t2_table = _make_table(
        variable_dcid="Median_Income_Person",
        variable_name="Median Income",
        source=None,
        rows=(),
    )
    cache.store_fetched(
        CachedTable(
            table_id="t2",
            table=t2_table,
            source_selected_explicitly=False,
        )
    )

    s1_table = _make_table(
        variable_dcid="Derived_Ratio",
        variable_name="Derived Ratio",
        rows=(
            ObservationRow(
                place_dcid="country/USA",
                place_name="United States",
                date="2020",
                value=0.5,
            ),
        ),
    )
    cache.store_derived(
        CachedTable(
            table_id="s1",
            table=s1_table,
        )
    )

    telemetry = _make_telemetry()
    report = build_debug_report(
        telemetry=telemetry,
        terminal_state="complete",
        cache=cache,
        used_table_ids={"t1", "s1"},
    )

    assert len(report.tables) == 3

    # Check t1 (chosen source, used in answer).
    t1_rec = report.tables[0]
    assert t1_rec.table_id == "t1"
    assert t1_rec.used_in_answer is True
    assert t1_rec.source_selection == "chosen"
    assert t1_rec.row_count == 2
    assert t1_rec.date_range == ("2010", "2020")
    assert t1_rec.source is not None
    assert t1_rec.source.name == "US Census Bureau"
    assert t1_rec.source.url == "https://census.gov"
    assert t1_rec.source.license == "Public Domain"
    assert t1_rec.source.dataset == "Decennial Census"
    assert t1_rec.source.provider == "U.S. Dept of Commerce"
    assert t1_rec.source.date_range == "2010 - 2020"

    # Check t2 (server default source, unused, empty rows).
    t2_rec = report.tables[1]
    assert t2_rec.table_id == "t2"
    assert t2_rec.used_in_answer is False
    assert t2_rec.source_selection == "server_default"
    assert t2_rec.row_count == 0
    assert t2_rec.date_range is None
    assert t2_rec.source is None

    # Check s1 (derived source, used in answer).
    s1_rec = report.tables[2]
    assert s1_rec.table_id == "s1"
    assert s1_rec.used_in_answer is True
    assert s1_rec.source_selection == "derived"
    assert s1_rec.row_count == 1
    assert s1_rec.date_range == ("2020", "2020")

    # Check to_dict serialization for tables.
    payload = report.to_dict()
    tables_payload = payload["tables"]
    assert isinstance(tables_payload, list)
    assert len(tables_payload) == 3
    t1_json, t2_json, s1_json = tables_payload
    assert isinstance(t1_json, dict)
    assert isinstance(t2_json, dict)
    assert isinstance(s1_json, dict)
    assert t1_json["date_range"] == ["2010", "2020"]
    assert t2_json["date_range"] is None
    assert s1_json["date_range"] == ["2020", "2020"]


def test_build_debug_report_cohort_place_cap_and_name_resolution() -> None:
    # Test: Cohort place list cap and place name resolution fallback.
    # Situation: A table has 30 places with data (exceeding
    #   SUMMARY_PLACE_LIST_CAP of 25), with requested places defined:
    #   - requested place "geoId/02" has name in table.place_names.
    #   - place "geoId/03" has no entry in table.place_names but has row
    #     place_name.
    #   - place "geoId/04" has neither and falls back to DCID.
    # Expectation: `places_with_data_count` reflects the true total (30);
    #   `places` is capped at 25; requested places precede other places; names
    #   resolve via the 3-step fallback.
    cache = TurnCache()
    place_dcids = [f"geoId/{i:02d}" for i in range(1, 31)]
    # Requested places: geoId/02 first, then missing geoId/99, then geoId/01.
    requested = ("geoId/02", "geoId/99", "geoId/01")
    place_names = {"geoId/01": "Place 01", "geoId/02": "Place 02"}

    rows: list[ObservationRow] = []
    for dcid in place_dcids:
        # geoId/03 has a row place_name; geoId/04 has empty row place_name.
        if dcid == "geoId/03":
            row_name = "Row Resolved Place 03"
        elif dcid == "geoId/04":
            row_name = ""
        else:
            row_name = f"Row {dcid}"
        rows.append(
            ObservationRow(
                place_dcid=dcid,
                place_name=row_name,
                date="2021",
                value=100.0,
            )
        )

    cohort_table = _make_table(
        rows=tuple(rows),
        requested_places=requested,
        place_names=place_names,
        parent_place_dcid="country/USA",
        child_place_type="State",
    )
    cache.store_fetched(CachedTable(table_id="t1", table=cohort_table))

    telemetry = _make_telemetry()
    report = build_debug_report(
        telemetry=telemetry,
        terminal_state="complete",
        cache=cache,
    )

    t1_rec = report.tables[0]
    assert t1_rec.parent_place_dcid == "country/USA"
    assert t1_rec.child_place_type == "State"
    assert t1_rec.places_with_data_count == 30
    assert len(t1_rec.places) == SUMMARY_PLACE_LIST_CAP  # 25

    # Requested places with data ("geoId/02", "geoId/01") come first.
    assert t1_rec.places[0].dcid == "geoId/02"
    assert t1_rec.places[0].name == "Place 02"

    assert t1_rec.places[1].dcid == "geoId/01"
    assert t1_rec.places[1].name == "Place 01"

    # Next comes remaining places in sorted order: geoId/03, geoId/04, ...
    assert t1_rec.places[2].dcid == "geoId/03"
    assert t1_rec.places[2].name == "Row Resolved Place 03"

    assert t1_rec.places[3].dcid == "geoId/04"
    assert t1_rec.places[3].name == "geoId/04"


def test_debug_report_serializes_trajectory_and_analysis_context() -> None:
    # Test: Serialization of thoughts, tool calls, rejected specs, diagnostics,
    #   specification, unavailable report, and digest.
    # Situation: A turn produces discovery and synthesis thoughts, a tool call,
    #   three rejected submissions covering each rejection reason, three
    #   diagnostics covering StepRefusalDiagnostic with and without coverage
    #   plus TimeoutDiagnostic, a valid specification, an unavailable report,
    #   and an analytical digest.
    # Expectation: build_debug_report populates typed dataclass records on
    #   DebugReport, and to_dict serializes every field matching the wire
    #   specification without leaking untyped internals.
    telemetry = _make_telemetry()
    thoughts = [
        DebugThought(
            phase="discovery", text="Looking up France.", round_number=1
        ),
        DebugThought(
            phase="synthesis", text="Writing response.", round_number=None
        ),
    ]
    tool_calls: list[JsonObject] = [
        {
            "name": "fetch_observations",
            "arguments": {"variable_dcid": "Count_Person"},
            "result": '{"table_id": "t1"}',
            "status": "success",
            "round": 1,
            "duration_ms": 12.3,
        }
    ]

    spec1 = AnalysisSpecification(
        steps=[
            AnalyzeTimeseriesStep(
                script="analyze_timeseries", step_id="s1", table="t99"
            )
        ]
    )
    spec2 = AnalysisSpecification(
        steps=[RankCohortStep(script="rank_cohort", step_id="s1", table="t1")]
    )
    final_spec = AnalysisSpecification(
        steps=[
            AnalyzeTimeseriesStep(
                script="analyze_timeseries", step_id="s1", table="t1"
            )
        ]
    )

    rejected_submissions = [
        RejectedSubmission(
            round_number=1,
            reason="schema_invalid",
            errors=("- specification: Invalid 'script' tag",),
            specification=None,
        ),
        RejectedSubmission(
            round_number=2,
            reason="reference_invalid",
            errors=("Table t99 does not exist",),
            specification=spec1,
        ),
        RejectedSubmission(
            round_number=3,
            reason="processing_failed",
            errors=("Insufficient coverage",),
            specification=spec2,
        ),
    ]

    diag_with_cov = StepRefusalDiagnostic(
        refusal_reason="insufficient_coverage",
        message="Only 1 place has data",
        step_id="s1",
        script="rank_cohort",
        input_table_ids=("t1",),
        coverage=CoverageReport(
            contributing_places=1,
            requested_places=4,
            coverage_ratio=0.25,
            reference_date="2022",
            missing_places=("b", "c", "d"),
            mixed_vintages=False,
        ),
        alternative_sources=(),
        completed_results=(),
    )
    diag_no_cov = StepRefusalDiagnostic(
        refusal_reason="no_observations",
        message="No observations found",
        step_id="s2",
        script="analyze_timeseries",
        input_table_ids=("t2",),
        coverage=None,
        alternative_sources=(),
        completed_results=(),
    )
    diag_timeout = TimeoutDiagnostic(
        timeout_seconds=5.0,
        message="Specification exceeded timeout",
    )

    diagnostics: list[tuple[int | None, ProcessingDiagnostic]] = [
        (1, diag_with_cov),
        (2, diag_no_cov),
        (None, diag_timeout),
    ]

    unavailable = UnavailableReport(
        searched_indicators=["Count_Person"],
        searched_places=["country/FRA"],
        reason="No data published",
        related_available=[],
    )

    digest = AnalysisDigest(results=(), sources=())

    report = build_debug_report(
        telemetry=telemetry,
        terminal_state="complete",
        thoughts=thoughts,
        tool_calls=tool_calls,
        rejected_submissions=rejected_submissions,
        diagnostics=diagnostics,
        specification=final_spec,
        specification_origin="model",
        unavailable=unavailable,
        digest=digest,
    )

    assert len(report.thoughts) == 2
    assert report.thoughts[0].phase == "discovery"
    assert report.thoughts[0].round_number == 1
    assert report.thoughts[1].phase == "synthesis"
    assert report.thoughts[1].round_number is None

    assert len(report.tool_calls) == 1
    assert report.tool_calls[0]["name"] == "fetch_observations"

    assert len(report.rejected_specifications) == 3
    assert report.rejected_specifications[0].reason == "schema_invalid"
    assert report.rejected_specifications[0].specification is None
    assert report.rejected_specifications[1].reason == "reference_invalid"
    assert report.rejected_specifications[1].specification == spec1
    assert report.rejected_specifications[2].reason == "processing_failed"
    assert report.rejected_specifications[2].specification == spec2

    assert len(report.diagnostics) == 3
    assert isinstance(report.diagnostics[0], DebugStepRefusalDiagnostic)
    assert report.diagnostics[0].kind == "step_refusal"
    assert report.diagnostics[0].round_number == 1
    assert report.diagnostics[0].coverage is not None
    assert report.diagnostics[0].coverage.contributing_places == 1
    assert report.diagnostics[0].coverage.missing_places == ("b", "c", "d")

    assert isinstance(report.diagnostics[1], DebugStepRefusalDiagnostic)
    assert report.diagnostics[1].round_number == 2
    assert report.diagnostics[1].coverage is None

    assert isinstance(report.diagnostics[2], DebugTimeoutDiagnostic)
    assert report.diagnostics[2].kind == "timeout"
    assert report.diagnostics[2].round_number is None
    assert report.diagnostics[2].timeout_seconds == 5.0

    assert report.specification == final_spec
    assert report.specification_origin == "model"
    assert report.unavailable == unavailable
    assert report.digest == digest

    # Verify serialization via to_dict()
    data = report.to_dict()

    assert data["thoughts"] == [
        {"phase": "discovery", "text": "Looking up France.", "round": 1},
        {"phase": "synthesis", "text": "Writing response.", "round": None},
    ]

    assert data["tool_calls"] == [
        {
            "name": "fetch_observations",
            "arguments": {"variable_dcid": "Count_Person"},
            "result": '{"table_id": "t1"}',
            "status": "success",
            "round": 1,
            "duration_ms": 12.3,
        }
    ]

    assert data["rejected_specifications"] == [
        {
            "round": 1,
            "reason": "schema_invalid",
            "errors": ["- specification: Invalid 'script' tag"],
            "specification": None,
        },
        {
            "round": 2,
            "reason": "reference_invalid",
            "errors": ["Table t99 does not exist"],
            "specification": spec1.model_dump(mode="json"),
        },
        {
            "round": 3,
            "reason": "processing_failed",
            "errors": ["Insufficient coverage"],
            "specification": spec2.model_dump(mode="json"),
        },
    ]

    assert data["diagnostics"] == [
        {
            "kind": "step_refusal",
            "round": 1,
            "step_id": "s1",
            "script": "rank_cohort",
            "refusal_reason": "insufficient_coverage",
            "message": "Only 1 place has data",
            "input_table_ids": ["t1"],
            "coverage": {
                "contributing_places": 1,
                "requested_places": 4,
                "coverage_ratio": 0.25,
                "reference_date": "2022",
                "missing_places": ["b", "c", "d"],
                "mixed_vintages": False,
            },
            "alternative_source_count": 0,
        },
        {
            "kind": "step_refusal",
            "round": 2,
            "step_id": "s2",
            "script": "analyze_timeseries",
            "refusal_reason": "no_observations",
            "message": "No observations found",
            "input_table_ids": ["t2"],
            "coverage": None,
            "alternative_source_count": 0,
        },
        {
            "kind": "timeout",
            "round": None,
            "timeout_seconds": 5.0,
            "message": "Specification exceeded timeout",
        },
    ]

    assert data["specification"] == final_spec.model_dump(mode="json")
    assert data["specification_origin"] == "model"
    assert data["unavailable"] == unavailable.model_dump(mode="json")
    assert data["digest"] == digest.to_dict()


def test_specification_origin_resolution() -> None:
    # Test: Specification origin resolution.
    # Situation: build_debug_report is called with:
    #   1. specification=None (with or without origin provided).
    #   2. specification is set with origin=None (defaults to "model").
    #   3. specification is set with explicit origin="default".
    # Expectation: specification_origin resolves to None when specification is
    #   None, defaults to "model" when specification is present, and honors
    #   explicit origin settings.
    telemetry = _make_telemetry()
    spec = AnalysisSpecification(
        steps=[
            AnalyzeTimeseriesStep(
                script="analyze_timeseries", step_id="s1", table="t1"
            )
        ]
    )

    # 1. specification is None
    report_none = build_debug_report(
        telemetry=telemetry,
        terminal_state="complete",
        specification=None,
        specification_origin="model",
    )
    assert report_none.specification_origin is None
    assert report_none.to_dict()["specification_origin"] is None

    # 2. specification is set, origin is omitted/None
    report_default = build_debug_report(
        telemetry=telemetry,
        terminal_state="complete",
        specification=spec,
        specification_origin=None,
    )
    assert report_default.specification_origin == "model"
    assert report_default.to_dict()["specification_origin"] == "model"

    # 3. specification is set, origin is explicitly "default"
    report_fallback = build_debug_report(
        telemetry=telemetry,
        terminal_state="complete",
        specification=spec,
        specification_origin="default",
    )
    assert report_fallback.specification_origin == "default"
    assert report_fallback.to_dict()["specification_origin"] == "default"


def test_truncate_debug_text_boundary_and_serialization() -> None:
    # Test: Boundary truncation and serialization of `truncate_debug_text`.
    # Situation: Strings at boundary lengths: empty, within max_chars,
    #   exactly equal to max_chars, and exceeding max_chars by one or more.
    # Expectation: Lengths <= max_chars retain full text with truncated=False;
    #   lengths > max_chars are sliced to max_chars with truncated=True and
    #   total_chars preserving the original character count.
    exact = "x" * MAX_DEBUG_TEXT_CHARS
    res_exact = truncate_debug_text(exact)
    assert res_exact.text == exact
    assert res_exact.truncated is False
    assert res_exact.total_chars == MAX_DEBUG_TEXT_CHARS

    overflow = "x" * (MAX_DEBUG_TEXT_CHARS + 1)
    res_overflow = truncate_debug_text(overflow)
    assert res_overflow.text == exact
    assert res_overflow.truncated is True
    assert res_overflow.total_chars == MAX_DEBUG_TEXT_CHARS + 1

    custom_max = 5
    res_short = truncate_debug_text("abc", max_chars=custom_max)
    assert res_short == DebugCappedText(
        text="abc", truncated=False, total_chars=3
    )
    assert res_short.to_dict() == {
        "text": "abc",
        "truncated": False,
        "total_chars": 3,
    }

    res_long = truncate_debug_text("abcdefgh", max_chars=custom_max)
    assert res_long == DebugCappedText(
        text="abcde", truncated=True, total_chars=8
    )
    assert res_long.to_dict() == {
        "text": "abcde",
        "truncated": True,
        "total_chars": 8,
    }


def test_build_debug_report_synthesis_fields_and_capping() -> None:
    # Test: Synthesis prompt and raw output capping and serialization.
    # Situation: build_debug_report is called with None, short text, and text
    #   exceeding MAX_DEBUG_TEXT_CHARS.
    # Expectation: None produces None in both report fields and serialized dict;
    #   strings are converted to DebugCappedText and serialized via to_dict().
    telemetry = _make_telemetry()

    # 1. Unset synthesis fields
    report_none = build_debug_report(
        telemetry=telemetry,
        terminal_state="complete",
        synthesis_prompt=None,
        synthesis_raw_output=None,
    )
    assert report_none.synthesis_prompt is None
    assert report_none.synthesis_raw_output is None
    dict_none = report_none.to_dict()
    assert dict_none["synthesis_prompt"] is None
    assert dict_none["synthesis_raw_output"] is None

    # 2. Populated synthesis fields within limit
    prompt_text = "What is the poverty rate in California?"
    raw_output_text = "The poverty rate is 12%.\n\n```chart\n{}\n```"
    report_set = build_debug_report(
        telemetry=telemetry,
        terminal_state="complete",
        synthesis_prompt=prompt_text,
        synthesis_raw_output=raw_output_text,
    )
    assert report_set.synthesis_prompt == DebugCappedText(
        text=prompt_text, truncated=False, total_chars=len(prompt_text)
    )
    assert report_set.synthesis_raw_output == DebugCappedText(
        text=raw_output_text, truncated=False, total_chars=len(raw_output_text)
    )
    dict_set = report_set.to_dict()
    assert dict_set["synthesis_prompt"] == {
        "text": prompt_text,
        "truncated": False,
        "total_chars": len(prompt_text),
    }
    assert dict_set["synthesis_raw_output"] == {
        "text": raw_output_text,
        "truncated": False,
        "total_chars": len(raw_output_text),
    }

    # 3. Oversized synthesis fields
    oversized = "y" * (MAX_DEBUG_TEXT_CHARS + 50)
    report_oversized = build_debug_report(
        telemetry=telemetry,
        terminal_state="complete",
        synthesis_prompt=oversized,
        synthesis_raw_output=oversized,
    )
    assert report_oversized.synthesis_prompt is not None
    assert report_oversized.synthesis_prompt.truncated is True
    assert report_oversized.synthesis_prompt.total_chars == len(oversized)
    assert report_oversized.synthesis_prompt.text == "y" * MAX_DEBUG_TEXT_CHARS


def test_build_debug_report_role_configs_and_secret_redaction() -> None:
    # Test: Role configs resolution, clamping, and API key redaction.
    # Situation: build_debug_report is called with config=None, and with an
    #   AgentConfig carrying custom models, clamped levels, and a secret key.
    # Expectation: config=None produces empty role_configs; populated config
    #   snapshots all 5 roles in GeminiRole order with clamped thinking levels
    #   and never exposes config.gemini.api_key.
    telemetry = _make_telemetry()

    # 1. config is None
    report_no_config = build_debug_report(
        telemetry=telemetry, terminal_state="complete", config=None
    )
    assert report_no_config.role_configs == ()
    assert report_no_config.to_dict()["role_configs"] == []

    # 2. config is set with custom models and local api_key
    secret_key = "AIza_super_secret_local_dev_key_never_leak"
    config = AgentConfig(
        gemini=GeminiConfig(
            classify_model="gemini-3.8-flash",
            discovery_model="gemini-3.8-flash",
            synthesis_model="gemini-3.8-pro",
            follow_up_model="gemini-3.8-flash",
            compaction_model="gemini-3.8-flash",
            api_key=secret_key,
        )
    )

    report = build_debug_report(
        telemetry=telemetry, terminal_state="complete", config=config
    )

    # Must cover all 5 roles in GeminiRole order
    roles_order = [role.value for role in GeminiRole]
    assert [r.role for r in report.role_configs] == roles_order
    assert len(report.role_configs) == 5

    # Check thinking level clamping: classify model gemini-3.8-flash does not
    # accept MINIMAL and is clamped to low
    classify_cfg = report.role_configs[0]
    assert isinstance(classify_cfg, DebugRoleConfig)
    assert classify_cfg.role == "classify"
    assert classify_cfg.model == "gemini-3.8-flash"
    assert classify_cfg.temperature == 0.0
    assert classify_cfg.thinking_level == "low"

    # Discovery role
    discovery_cfg = report.role_configs[1]
    assert discovery_cfg.role == "discovery"
    assert discovery_cfg.temperature == 0.2
    assert discovery_cfg.thinking_level == "medium"

    # Synthesis role
    synthesis_cfg = report.role_configs[2]
    assert synthesis_cfg.role == "synthesis"
    assert synthesis_cfg.model == "gemini-3.8-pro"
    assert synthesis_cfg.temperature == 0.3
    assert synthesis_cfg.thinking_level == "medium"

    # Serialized form matches
    data = report.to_dict()
    assert data["role_configs"] == [
        {
            "role": r.role,
            "model": r.model,
            "temperature": r.temperature,
            "thinking_level": r.thinking_level,
        }
        for r in report.role_configs
    ]

    # Verify secret is NEVER leaked in role_configs or anywhere in report
    serialized_json = json.dumps(data)
    assert secret_key not in serialized_json
    assert not hasattr(classify_cfg, "api_key")


def test_build_debug_report_prompt_hashes_and_contracts() -> None:
    # Test: Prompt hashes generation across slots and packaged contracts.
    # Situation: build_debug_report is called with config=None and with an
    #   AgentConfig with distinct prompt text per slot.
    # Expectation: config=None produces empty prompt_hashes; populated config
    #   hashes every slot in PROMPT_SLOTS and both packaged contracts using
    #   SHA-256 hex digests, updating deterministically on edits.
    telemetry = _make_telemetry()

    # 1. config is None
    report_none = build_debug_report(
        telemetry=telemetry, terminal_state="complete", config=None
    )
    assert report_none.prompt_hashes == MappingProxyType({})
    assert report_none.to_dict()["prompt_hashes"] == {}

    # 2. config is set
    prompts = Prompts(
        classify="Classify prompt body",
        discovery="Discovery prompt body",
        synthesis="Synthesis prompt body",
        follow_up="Follow up prompt body",
    )
    config = AgentConfig(prompts=prompts)

    report = build_debug_report(
        telemetry=telemetry, terminal_state="complete", config=config
    )
    hashes = report.prompt_hashes
    data_hashes = report.to_dict()["prompt_hashes"]
    assert data_hashes == dict(hashes)

    expected_keys = set(PROMPT_SLOTS) | {
        "discovery_contract",
        "synthesis_contract",
    }
    assert set(hashes.keys()) == expected_keys

    # All hashes must be valid 64-char lowercase hex SHA-256 strings
    hex_pattern = re.compile(r"^[0-9a-f]{64}$")
    for key, digest_hex in hashes.items():
        assert hex_pattern.match(digest_hex), (
            f"Invalid hash for {key}: {digest_hex}"
        )

    # Verify contracts match sha256 of packaged markdown files
    expected_discovery = hashlib.sha256(
        load_prompt_contract("discovery").encode("utf-8")
    ).hexdigest()
    expected_synthesis = hashlib.sha256(
        load_prompt_contract("synthesis").encode("utf-8")
    ).hexdigest()
    assert hashes["discovery_contract"] == expected_discovery
    assert hashes["synthesis_contract"] == expected_synthesis

    # Verify slot hashes match content sha256
    assert (
        hashes["synthesis"]
        == hashlib.sha256(b"Synthesis prompt body").hexdigest()
    )

    # Changing a slot updates only that slot's hash
    config_modified = replace(
        config,
        prompts=replace(config.prompts, synthesis="Updated synthesis prompt"),
    )
    report_mod = build_debug_report(
        telemetry=telemetry, terminal_state="complete", config=config_modified
    )
    mod_hashes = report_mod.prompt_hashes
    assert mod_hashes["synthesis"] != hashes["synthesis"]
    assert mod_hashes["discovery"] == hashes["discovery"]
    assert mod_hashes["synthesis_contract"] == hashes["synthesis_contract"]


def test_build_debug_report_build_sha() -> None:
    # Test: Propagation and serialization of `build_sha`.
    # Situation: build_debug_report is called with build_sha=None and with
    #   an explicit SHA string.
    # Expectation: build_sha is stored on DebugReport and serialized in
    #   to_dict().
    telemetry = _make_telemetry()

    report_none = build_debug_report(
        telemetry=telemetry, terminal_state="complete", build_sha=None
    )
    assert report_none.build_sha is None
    assert report_none.to_dict()["build_sha"] is None

    sha = "3b34f1cac2c2f51e9662d330ebc58014a2193944"
    report_sha = build_debug_report(
        telemetry=telemetry, terminal_state="complete", build_sha=sha
    )
    assert report_sha.build_sha == sha
    assert report_sha.to_dict()["build_sha"] == sha
