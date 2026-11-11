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
"""

import json

import pytest

from narratives_agent.analytics.provenance import Provenance, Source
from narratives_agent.analytics.summarize import SUMMARY_PLACE_LIST_CAP
from narratives_agent.analytics.tables import ObservationRow, ObservationTable
from narratives_agent.gemini.schemas import QueryPattern
from narratives_agent.settings import DebugReportMode
from narratives_agent.telemetry import (
    TerminalState,
    TokenCounts,
    TurnTelemetry,
)
from narratives_agent.workflows.debug_report import (
    build_debug_report,
    should_emit_debug_report,
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
