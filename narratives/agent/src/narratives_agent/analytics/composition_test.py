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
"""Tests for `compute_composition` in `analytics.composition`.

Covers explicit and implied totals, disjointness checks, shared reference-date
selection, stage-to-stage transitions, parameter or unit refusals, aligned
cohort inputs, and a brute-force sweep of the result invariants.
"""

import dataclasses
import functools
import itertools
from collections.abc import Sequence

import pytest

from narratives_agent.analytics.alignment import AlignedCohort, align_cohort
from narratives_agent.analytics.composition import compute_composition
from narratives_agent.analytics.digest import ScriptResult
from narratives_agent.analytics.metrics import (
    CompositionComponent,
    CompositionMetrics,
    CompositionMode,
    CompositionPlace,
    StagesPlace,
    StageTransition,
)
from narratives_agent.analytics.provenance import Provenance, Source
from narratives_agent.analytics.script_inputs import CohortInput
from narratives_agent.analytics.tables import ObservationRow, ObservationTable

_SOURCES = {
    1: Source(name="Census", url="https://census"),
    2: Source(name="ACS", url="https://acs"),
    3: Source(name="Survey", url="https://survey"),
}


def _build_table(
    variable_dcid: str,
    observations: Sequence[tuple[str, str, float]],
    *,
    source_id: int = 1,
    requested_places: Sequence[str] = (),
    unit: str | None = "Person",
    scaling_factor: float | None = None,
) -> ObservationTable:
    """Builds a table of `variable_dcid` from `(place, date, value)` rows."""
    places = list(
        dict.fromkeys(
            [*requested_places, *(place for place, _, _ in observations)]
        )
    )
    return ObservationTable(
        variable_dcid=variable_dcid,
        variable_name=variable_dcid.replace("_", " "),
        unit=unit,
        scaling_factor=scaling_factor,
        provenance=Provenance(
            sources=(_SOURCES[source_id],),
            facet_ids=(f"f{source_id}",),
        ),
        rows=tuple(
            ObservationRow(place, place.upper(), date, value)
            for place, date, value in observations
        ),
        requested_places=tuple(requested_places),
        place_names={place: place.upper() for place in places},
    )


def _build_total_table() -> ObservationTable:
    """Builds a total of 100 for `a` and 50 for `b` on 2022."""
    return _build_table(
        "Count_Person", [("a", "2022", 100.0), ("b", "2022", 50.0)]
    )


def _build_component_tables() -> list[ObservationTable]:
    """Builds two components summing to 90 for `a` and 50 for `b` on 2022."""
    return [
        _build_table(
            "Count_Person_Male",
            [("a", "2022", 60.0), ("b", "2022", 25.0)],
            source_id=2,
        ),
        _build_table(
            "Count_Person_Female",
            [("a", "2022", 30.0), ("b", "2022", 25.0)],
            source_id=3,
        ),
    ]


def test_shares_of_an_explicit_total_report_the_unallocated_remainder() -> None:
    # Test: Composition against an explicit total.
    # Situation: A total of 100 and 50 for two places, with components of
    #   60 and 30 for the first and 25 and 25 for the second, all on 2022.
    # Expectation: Shares of 60% and 30% with 10 (10%) unallocated for the
    #   first place and 50% and 50% with nothing unallocated for the
    #   second; the result lists the total first, carries every source and
    #   facet, reports full coverage on 2022, and carries no caveat.
    result = compute_composition(
        _build_component_tables(), total=_build_total_table()
    )
    assert result.status == "ok"
    assert result.variables == (
        "Count_Person",
        "Count_Person_Male",
        "Count_Person_Female",
    )
    assert result.unit == "Person"
    assert result.coverage is not None
    assert result.coverage.contributing_places == 2
    assert result.coverage.reference_date == "2022"
    assert result.provenance.sources == (
        _SOURCES[1],
        _SOURCES[2],
        _SOURCES[3],
    )
    assert result.provenance.facet_ids == ("f1", "f2", "f3")
    assert result.provenance.methodology == (
        "Shares of Count Person on 2022: each component's value divided by "
        "the total, with the remainder the components leave unallocated; "
        "computed for 2 places."
    )
    assert result.caveats == ()
    metrics = result.metrics
    assert isinstance(metrics, CompositionMetrics)
    assert metrics.reference_date == "2022"
    assert metrics.mode == "composition"
    assert metrics.has_explicit_total is True
    assert metrics.total_variable_dcid == "Count_Person"
    assert metrics.component_variable_dcids == (
        "Count_Person_Male",
        "Count_Person_Female",
    )
    assert metrics.place_count == 2
    assert metrics.missing_places == ()
    assert metrics.places[0] == CompositionPlace(
        place_dcid="a",
        place_name="A",
        total_value=100.0,
        component_sum=90.0,
        components=(
            CompositionComponent(
                variable_dcid="Count_Person_Male",
                variable_name="Count Person Male",
                value=60.0,
                share_pct=60.0,
            ),
            CompositionComponent(
                variable_dcid="Count_Person_Female",
                variable_name="Count Person Female",
                value=30.0,
                share_pct=30.0,
            ),
        ),
        unallocated_value=10.0,
        unallocated_share_pct=10.0,
    )
    second = metrics.places[1]
    assert isinstance(second, CompositionPlace)
    assert [item.share_pct for item in second.components] == [
        50.0,
        50.0,
    ]
    assert second.unallocated_value == 0.0
    assert second.unallocated_share_pct == 0.0


def test_shares_without_a_total_use_the_component_sum_with_a_caveat() -> None:
    # Test: Composition with an implied total.
    # Situation: Components of 3 and 1 for one place and no total.
    # Expectation: Shares of 75% and 25%, a zero unallocated remainder,
    #   `total_value` None, `has_explicit_total` False, a caveat stating
    #   that the shares are relative to the component sum, and a
    #   methodology naming the sum.
    result = compute_composition(
        [
            _build_table("Renewable", [("a", "2022", 3.0)], source_id=1),
            _build_table("Fossil", [("a", "2022", 1.0)], source_id=2),
        ]
    )
    assert result.status == "ok"
    metrics = result.metrics
    assert isinstance(metrics, CompositionMetrics)
    entry = metrics.places[0]
    assert isinstance(entry, CompositionPlace)
    assert entry.total_value is None
    assert entry.component_sum == 4.0
    assert [item.share_pct for item in entry.components] == [75.0, 25.0]
    assert entry.unallocated_value == 0.0
    assert entry.unallocated_share_pct == 0.0
    assert metrics.has_explicit_total is False
    assert metrics.total_variable_dcid is None
    assert result.caveats == (
        "No separate total variable was provided, so shares are computed "
        "relative to the sum of the supplied components and the unallocated "
        "remainder is zero by construction.",
    )
    assert result.provenance.methodology == (
        "Shares of the sum of Renewable, Fossil on 2022: each component's "
        "value divided by the sum of the supplied components; computed for "
        "1 place."
    )


def test_components_exceeding_the_total_are_refused_with_exact_figures() -> (
    None
):
    # Test: Refusal when components sum to more than the explicit total.
    # Situation: A total of 100 with components of 70 and 40 (sum 110), and
    #   a total of 10,000,000 with components of 6,000,000 and 4,000,100
    #   (sum 10,000,100).
    # Expectation: Both are refused with `components_exceed_total`, carrying
    #   the coverage and a caveat naming the place, the sum, and the total
    #   with every integer digit.
    total = _build_table("Total", [("a", "2022", 100.0)])
    exceeded = compute_composition(
        [
            _build_table("Part_A", [("a", "2022", 70.0)], source_id=2),
            _build_table("Part_B", [("a", "2022", 40.0)], source_id=3),
        ],
        total=total,
    )
    assert exceeded.status == "refused"
    assert exceeded.refusal_reason == "components_exceed_total"
    assert exceeded.metrics is None
    assert exceeded.coverage is not None
    assert exceeded.coverage.contributing_places == 1
    assert exceeded.caveats == (
        "The components of A sum to 110 on 2022, more than the total of "
        "100, so they are not disjoint parts of it.",
    )
    large = compute_composition(
        [
            _build_table("Part_A", [("a", "2022", 6000000.0)], source_id=2),
            _build_table("Part_B", [("a", "2022", 4000100.0)], source_id=3),
        ],
        total=_build_table("Total", [("a", "2022", 10000000.0)]),
    )
    assert large.refusal_reason == "components_exceed_total"
    assert large.caveats == (
        "The components of A sum to 10000100 on 2022, more than the total of "
        "10000000, so they are not disjoint parts of it.",
    )


def test_component_sum_within_tolerance_clamps_unallocated_to_zero() -> None:
    # Test: The relative tolerance on the disjointness check.
    # Situation: A total of 100 with components of 60 and 40.001 (one part
    #   in a hundred thousand above the total, beyond the 1e-6 tolerance),
    #   and a total of 100 with components of 60 and 40.00001 (one part in
    #   ten million above the total, within the tolerance).
    # Expectation: The first is refused with `components_exceed_total`; the
    #   second is accepted with `unallocated_value` clamped to zero.
    total = _build_table("Total", [("a", "2022", 100.0)])
    just_over = compute_composition(
        [
            _build_table("Part_A", [("a", "2022", 60.0)], source_id=2),
            _build_table("Part_B", [("a", "2022", 40.001)], source_id=3),
        ],
        total=total,
    )
    assert just_over.status == "refused"
    assert just_over.refusal_reason == "components_exceed_total"
    assert just_over.metrics is None
    within = compute_composition(
        [
            _build_table("Part_A", [("a", "2022", 60.0)], source_id=2),
            _build_table("Part_B", [("a", "2022", 40.00001)], source_id=3),
        ],
        total=total,
    )
    assert within.status == "ok"
    assert isinstance(within.metrics, CompositionMetrics)
    within_place = within.metrics.places[0]
    assert isinstance(within_place, CompositionPlace)
    assert within_place.unallocated_value == 0.0


def test_zero_total_with_zero_components_reports_none_shares() -> None:
    # Test: Zero total in composition mode.
    # Situation: A zero total with a zero component, and a zero total with a
    #   positive component.
    # Expectation: The first succeeds with None shares and a None
    #   unallocated share; the second is refused as `components_exceed_total`.
    zero_total = _build_table("Total", [("a", "2022", 0.0)])
    empty = compute_composition(
        [_build_table("Part", [("a", "2022", 0.0)], source_id=2)],
        total=zero_total,
    )
    assert empty.status == "ok"
    assert isinstance(empty.metrics, CompositionMetrics)
    entry = empty.metrics.places[0]
    assert isinstance(entry, CompositionPlace)
    assert entry.components[0].share_pct is None
    assert entry.unallocated_value == 0.0
    assert entry.unallocated_share_pct is None
    overflow = compute_composition(
        [_build_table("Part", [("a", "2022", 1.0)], source_id=2)],
        total=zero_total,
    )
    assert overflow.refusal_reason == "components_exceed_total"
    assert overflow.metrics is None


def test_negative_values_in_composition_mode_are_refused() -> None:
    # Test: Negative values in composition mode.
    # Situation: One negative component against a positive total, and two
    #   negative components against a positive total.
    # Expectation: Both are refused with `invalid_parameters` naming the
    #   negative variables with a verb that agrees in number.
    negative = compute_composition(
        [_build_table("Part", [("a", "2022", -1.0)], source_id=2)],
        total=_build_table("Total", [("a", "2022", 10.0)]),
    )
    assert negative.status == "refused"
    assert negative.refusal_reason == "invalid_parameters"
    assert negative.metrics is None
    assert negative.caveats == (
        "Part is negative for A on 2022; shares of a total require "
        "non-negative values.",
    )
    both_negative = compute_composition(
        [
            _build_table("Part_A", [("a", "2022", -1.0)], source_id=2),
            _build_table("Part_B", [("a", "2022", -2.0)], source_id=3),
        ],
        total=_build_table("Total", [("a", "2022", 10.0)]),
    )
    assert both_negative.refusal_reason == "invalid_parameters"
    assert both_negative.metrics is None
    assert both_negative.caveats == (
        "Part A, Part B are negative for A on 2022; shares of a total "
        "require non-negative values.",
    )


def test_exact_rational_summing_avoids_intermediate_rounding_loss() -> None:
    # Test: Exact rational summing across large and unit-ulp components.
    # Situation: Components of 1.0, 1e16, and 1.0 summed against a total of
    #   10000000000000002.0, where naive left-to-right float addition loses
    #   both 1.0 increments because the ulp at 1e16 is 2.0.
    # Expectation: Exact rational summing rounds once to 10000000000000002.0
    #   with an unallocated remainder of 0.0.
    exact_sum = compute_composition(
        [
            _build_table("Part_1", [("a", "2022", 1.0)], source_id=1),
            _build_table("Part_2", [("a", "2022", 1e16)], source_id=2),
            _build_table("Part_3", [("a", "2022", 1.0)], source_id=3),
        ],
        total=_build_table("Total", [("a", "2022", 10000000000000002.0)]),
    )
    assert isinstance(exact_sum.metrics, CompositionMetrics)
    place = exact_sum.metrics.places[0]
    assert isinstance(place, CompositionPlace)
    assert place.component_sum == 10000000000000002.0
    assert place.unallocated_value == 0.0


def test_overflowing_shares_stage_ratios_and_sums_are_handled() -> None:
    # Test: Finiteness guards on shares, ratios, and sums.
    # Situation: A stage transition from 1e-300 to 1e300 with a total of
    #   1e-300; two components of 1e308 in composition mode; and a stage
    #   transition from -1e308 to 1e308 in stages mode.
    # Expectation: Overflowing stage shares and transition ratios are None
    #   rather than `inf` with a caveat naming the place, and the overflowing
    #   component sum and stage delta are refused with `invalid_parameters`.
    stages_overflow = compute_composition(
        [
            _build_table("Stage_1", [("a", "2022", 1e-300)], source_id=1),
            _build_table("Stage_2", [("a", "2022", 1e300)], source_id=2),
        ],
        total=_build_table("Total", [("a", "2022", 1e-300)], source_id=3),
        mode="stages",
    )
    assert isinstance(stages_overflow.metrics, CompositionMetrics)
    stages_place = stages_overflow.metrics.places[0]
    assert isinstance(stages_place, StagesPlace)
    assert stages_place.stages[1].share_of_first_stage_pct is None
    assert stages_place.stages[1].share_pct is None
    transition = stages_place.transitions[0]
    assert transition.percent_change is None
    assert transition.retention_ratio is None
    assert transition.retention_pct is None
    assert stages_overflow.caveats == (
        "One or more stage shares or transition ratios are undefined for A "
        "because they are too large to represent.",
    )

    sum_overflow = compute_composition(
        [
            _build_table("Part_A", [("a", "2022", 1e308)], source_id=1),
            _build_table("Part_B", [("a", "2022", 1e308)], source_id=2),
        ]
    )
    assert sum_overflow.refusal_reason == "invalid_parameters"
    assert sum_overflow.caveats == (
        "The components of A on 2022 sum to a value too large to represent "
        "as a float.",
    )

    delta_overflow = compute_composition(
        [
            _build_table("Stage_1", [("a", "2022", -1e308)], source_id=1),
            _build_table("Stage_2", [("a", "2022", 1e308)], source_id=2),
        ],
        mode="stages",
    )
    assert delta_overflow.refusal_reason == "invalid_parameters"
    assert delta_overflow.caveats == (
        "The change from Stage 1 to Stage 2 for A on 2022 is too large to "
        "represent as a float.",
    )


def test_the_shared_reference_date_needs_every_input_on_one_date() -> None:
    # Test: Reference-date selection across inputs.
    # Situation: Three requested places. The total reports 2022 and 2023
    #   for every place, one component reports 2022 for every place and
    #   2023 for one, and the other reports 2022 for two places and 2023
    #   for two; the third place lacks the second component entirely.
    # Expectation: 2023 covers only 1 of 3 places in every input, so 2022
    #   is selected with 2 of 3 complete places, the missing place is
    #   reported, mixed vintages are flagged, and both caveats are stated;
    #   with 2022 given as `target_date`, the caveat names the requested date.
    places = ["a", "b", "c"]
    components = [
        _build_table(
            "Part_A",
            [
                ("a", "2022", 1.0),
                ("b", "2022", 1.0),
                ("c", "2022", 1.0),
                ("a", "2023", 1.0),
            ],
            source_id=2,
        ),
        _build_table(
            "Part_B",
            [
                ("a", "2022", 1.0),
                ("b", "2022", 1.0),
                ("a", "2023", 1.0),
                ("b", "2023", 1.0),
            ],
            source_id=3,
        ),
    ]
    total = _build_table(
        "Total",
        [(place, date, 10.0) for place in places for date in ("2022", "2023")],
        requested_places=places,
    )
    result = compute_composition(components, total=total)
    assert result.status == "ok"
    assert isinstance(result.metrics, CompositionMetrics)
    assert result.metrics.reference_date == "2022"
    assert result.metrics.place_count == 2
    assert result.metrics.missing_places == ("c",)
    assert result.coverage is not None
    assert result.coverage.mixed_vintages is True
    assert result.coverage.missing_places == ("c",)
    assert result.caveats == (
        "The inputs report different latest observation dates, so every "
        "value is aligned to 2022.",
        "2 of 3 places on 2022 have a value in every input; the rest are "
        "left out.",
    )
    requested = compute_composition(components, total=total, target_date="2022")
    assert requested.caveats[0] == (
        "The inputs report different latest observation dates; every value "
        "is aligned to the requested date 2022."
    )


def test_sparse_overlap_across_inputs_is_refused() -> None:
    # Test: `insufficient_coverage` when inputs overlap on too few places.
    # Situation: Four requested places where two components overlap on only
    #   one place on 2022.
    # Expectation: Refused with `insufficient_coverage` naming 1 of 4 places
    #   on 2022 with a singular verb and the 50% threshold.
    places = ["a", "b", "c", "d"]
    sparse = compute_composition(
        [
            _build_table(
                "Part_A",
                [("a", "2022", 1.0), ("b", "2022", 1.0)],
                requested_places=places,
            ),
            _build_table(
                "Part_B",
                [("a", "2022", 1.0), ("c", "2022", 1.0)],
                source_id=2,
            ),
        ]
    )
    assert sparse.status == "refused"
    assert sparse.refusal_reason == "insufficient_coverage"
    assert sparse.metrics is None
    assert sparse.coverage is not None
    assert sparse.coverage.contributing_places == 1
    assert sparse.coverage.requested_places == 4
    assert sparse.caveats == (
        "Only 1 of 4 places on 2022 has a value in every input, below the "
        "required 50% coverage.",
    )


def test_inputs_without_observations_are_refused() -> None:
    # Test: `no_observations` when no input holds a row for requested places.
    # Situation: Four requested places and a component table with no rows.
    # Expectation: Refused with `no_observations`, carrying zero coverage
    #   over the four places.
    places = ["a", "b", "c", "d"]
    empty = compute_composition(
        [_build_table("Part_A", [], requested_places=places)]
    )
    assert empty.refusal_reason == "no_observations"
    assert empty.metrics is None
    assert empty.coverage is not None
    assert empty.coverage.requested_places == 4
    assert empty.coverage.missing_places == tuple(places)
    assert empty.caveats == (
        "None of the inputs has an observation for any of the requested "
        "places (0 of 4 places).",
    )


def test_unmatched_target_date_or_precision_mismatch_is_refused() -> None:
    # Test: `target_date` refusals for absent dates and precision mismatches.
    # Situation: An explicit `target_date` that no input carries; a monthly
    #   `target_date` against yearly rows; and a yearly `target_date`
    #   against a table with an older yearly row and an overlapping monthly
    #   row.
    # Expectation: Each is refused with `insufficient_coverage`; the absent
    #   date cites 0 of 4 places without a threshold, and both precision
    #   mismatches name the overlapping or available precision example.
    places = ["a", "b", "c", "d"]
    absent_date = compute_composition(
        [_build_table("Part_A", [("a", "2022", 1.0)], requested_places=places)],
        target_date="2019",
    )
    assert absent_date.refusal_reason == "insufficient_coverage"
    assert absent_date.metrics is None
    assert absent_date.coverage is not None
    assert absent_date.coverage.reference_date == "2019"
    assert absent_date.coverage.contributing_places == 0
    assert absent_date.caveats == (
        "No place has a value in every input (0 of 4 places on 2019).",
    )
    other_precision = compute_composition(
        [_build_table("Part_A", [("a", "2022", 1.0)], requested_places=places)],
        target_date="2022-01",
    )
    assert other_precision.refusal_reason == "insufficient_coverage"
    assert other_precision.caveats == (
        "The target date 2022-01 does not match the precision of the input "
        "dates, such as 2022, so no place can be aligned to it.",
    )
    overlapping_precision = compute_composition(
        [
            _build_table(
                "Part_A",
                [("a", "2021", 1.0), ("a", "2022-06", 2.0)],
                requested_places=["a"],
            )
        ],
        target_date="2022",
    )
    assert overlapping_precision.refusal_reason == "insufficient_coverage"
    assert overlapping_precision.caveats == (
        "The target date 2022 does not match the precision of the input "
        "dates, such as 2022-06, so no place can be aligned to it.",
    )


def test_stages_report_transitions_and_shares_of_first_stage_and_total() -> (
    None
):
    # Test: Sequential stages with positive stage values and a total.
    # Situation: Three ordered stages of 100, 80, and 20 for one place with
    #   a total of 200 on 2022.
    # Expectation: Transitions of -20 (-20%, retention 0.8) and -60 (-75%,
    #   retention 0.25), stage shares of the first stage of 100%, 80%, and
    #   20%, and shares of the total of 50%, 40%, and 10%.
    stages = [
        _build_table("Stage_1", [("a", "2022", 100.0)], source_id=1),
        _build_table("Stage_2", [("a", "2022", 80.0)], source_id=2),
        _build_table("Stage_3", [("a", "2022", 20.0)], source_id=3),
    ]
    result = compute_composition(
        stages,
        mode="stages",
        total=_build_table("Total", [("a", "2022", 200.0)], unit="Person"),
    )
    assert result.status == "ok"
    metrics = result.metrics
    assert isinstance(metrics, CompositionMetrics)
    assert metrics.mode == "stages"
    assert result.provenance.methodology == (
        "Stage-to-stage transitions across Stage 1, Stage 2, Stage 3 on "
        "2022: absolute delta, percentage change, and retention ratio "
        "between consecutive stages, with each stage as a share of Stage 1; "
        "computed for 1 place."
    )
    (first,) = metrics.places
    assert isinstance(first, StagesPlace)
    assert first.total_value == 200.0
    assert [stage.share_of_first_stage_pct for stage in first.stages] == [
        100.0,
        80.0,
        20.0,
    ]
    assert [stage.share_pct for stage in first.stages] == [
        50.0,
        40.0,
        10.0,
    ]
    assert first.transitions == (
        StageTransition(
            from_variable="Stage_1",
            from_variable_name="Stage 1",
            from_value=100.0,
            to_variable="Stage_2",
            to_variable_name="Stage 2",
            to_value=80.0,
            absolute_delta=-20.0,
            percent_change=-20.0,
            retention_ratio=0.8,
            retention_pct=80.0,
        ),
        StageTransition(
            from_variable="Stage_2",
            from_variable_name="Stage 2",
            from_value=80.0,
            to_variable="Stage_3",
            to_variable_name="Stage 3",
            to_value=20.0,
            absolute_delta=-60.0,
            percent_change=-75.0,
            retention_ratio=0.25,
            retention_pct=25.0,
        ),
    )


def test_zero_and_negative_stages_omit_undefined_ratios_and_shares() -> None:
    # Test: Zero and negative stage values in stages mode.
    # Situation: Three stages of 100, 0, and -5 for one place, and a
    #   two-stage transition from -4 to 2.
    # Expectation: A zero stage leaves the next percentage change and
    #   retention undefined; a negative first stage leaves
    #   `share_of_first_stage_pct` and retention undefined while still
    #   measuring `percent_change` against `abs(from_value)`.
    zero_and_negative = compute_composition(
        [
            _build_table("Stage_1", [("b", "2022", 100.0)], source_id=1),
            _build_table("Stage_2", [("b", "2022", 0.0)], source_id=2),
            _build_table("Stage_3", [("b", "2022", -5.0)], source_id=3),
        ],
        mode="stages",
    )
    assert isinstance(zero_and_negative.metrics, CompositionMetrics)
    (place_entry,) = zero_and_negative.metrics.places
    assert isinstance(place_entry, StagesPlace)
    zero_step, negative_step = place_entry.transitions
    assert zero_step.absolute_delta == -100.0
    assert zero_step.percent_change == -100.0
    assert zero_step.retention_ratio == 0.0
    assert negative_step.percent_change is None
    assert negative_step.retention_ratio is None
    assert negative_step.retention_pct is None
    assert place_entry.stages[2].share_of_first_stage_pct == -5.0

    signed = compute_composition(
        [
            _build_table("Stage_1", [("a", "2022", -4.0)], source_id=1),
            _build_table("Stage_2", [("a", "2022", 2.0)], source_id=2),
        ],
        mode="stages",
    )
    assert isinstance(signed.metrics, CompositionMetrics)
    signed_entry = signed.metrics.places[0]
    assert isinstance(signed_entry, StagesPlace)
    (signed_step,) = signed_entry.transitions
    assert signed_step.absolute_delta == 6.0
    assert signed_step.percent_change == 150.0
    assert signed_step.retention_ratio is None
    assert signed_step.retention_pct is None
    assert [
        stage.share_of_first_stage_pct for stage in signed_entry.stages
    ] == [None, None]


def test_stages_without_a_total_have_no_share_of_total() -> None:
    # Test: Stages mode with no denominator.
    # Situation: Two stages for one place and no total.
    # Expectation: `total_value` and each stage's `share_pct` are None, the
    #   share of the first stage is reported, and no implied-total caveat
    #   is added because nothing is divided by a sum.
    result = compute_composition(
        [
            _build_table("Stage_1", [("a", "2022", 50.0)], source_id=1),
            _build_table("Stage_2", [("a", "2022", 10.0)], source_id=2),
        ],
        mode="stages",
    )
    assert isinstance(result.metrics, CompositionMetrics)
    entry = result.metrics.places[0]
    assert isinstance(entry, StagesPlace)
    assert entry.total_value is None
    assert [stage.share_pct for stage in entry.stages] == [None, None]
    assert entry.stages[1].share_of_first_stage_pct == 20.0
    assert result.caveats == ()


def test_missing_or_insufficient_components_are_refused() -> None:
    # Test: Component count validation.
    # Situation: No components in composition mode, and one component in
    #   stages mode.
    # Expectation: Both are refused with `invalid_parameters` and
    #   `metrics=None`; the empty case carries no variables.
    none = compute_composition([])
    assert none.status == "refused"
    assert none.refusal_reason == "invalid_parameters"
    assert none.metrics is None
    assert none.variables == ()
    assert none.caveats == ("At least one component variable is required.",)
    single = compute_composition(
        [_build_table("Stage_1", [("a", "2022", 1.0)])], mode="stages"
    )
    assert single.refusal_reason == "invalid_parameters"
    assert single.metrics is None
    assert single.caveats == (
        "Stage transitions require at least 2 ordered stages, not 1.",
    )


def test_invalid_target_date_and_min_coverage_are_refused() -> None:
    # Test: Alignment parameter validation in `compute_composition`.
    # Situation: A `target_date` of `latest`, and `min_coverage` values of
    #   -0.1 and 1.5.
    # Expectation: Each is refused with `invalid_parameters`, `metrics=None`,
    #   and `coverage=None`.
    bad_date = compute_composition(
        [_build_table("Part", [("a", "2022", 1.0)])], target_date="latest"
    )
    assert bad_date.refusal_reason == "invalid_parameters"
    assert bad_date.metrics is None
    assert bad_date.caveats == (
        "The target date 'latest' is not a year, a year and month, or a "
        "full date.",
    )
    for min_coverage in (-0.1, 1.5):
        bad_coverage = compute_composition(
            [_build_table("Part", [("a", "2022", 1.0)])],
            min_coverage=min_coverage,
        )
        assert bad_coverage.refusal_reason == "invalid_parameters"
        assert bad_coverage.metrics is None
        assert bad_coverage.coverage is None
        assert bad_coverage.caveats == (
            "The minimum coverage must be between 0 and 1, not "
            f"{min_coverage}.",
        )


def test_repeated_input_variables_are_refused() -> None:
    # Test: Duplicate variable DCID validation.
    # Situation: The same variable given twice as a component, and given as
    #   both a component and the total.
    # Expectation: Both are refused with `invalid_parameters` naming the
    #   repeated variable DCID.
    part = _build_table("Part", [("a", "2022", 1.0)])
    repeated = compute_composition([part, part])
    assert repeated.refusal_reason == "invalid_parameters"
    assert repeated.metrics is None
    assert repeated.caveats == (
        "Each input must be a different variable, but Part is given more "
        "than once.",
    )
    total_as_part = compute_composition(
        [part, _build_table("Total", [("a", "2022", 1.0)])],
        total=_build_table("Total", [("a", "2022", 2.0)]),
    )
    assert total_as_part.refusal_reason == "invalid_parameters"
    assert total_as_part.caveats == (
        "Each input must be a different variable, but Total is given more "
        "than once.",
    )


def test_invalid_places_parameter_is_refused_by_position_without_echoing() -> (
    None
):
    # Test: `places` parameter validation via `validate_place_dcids`.
    # Situation: `places` passed as a bare string, and `places` containing a
    #   malformed DCID with a newline and space at position 2.
    # Expectation: Both are refused with `invalid_parameters`; the invalid
    #   entry is identified by position only without echoing the malformed
    #   string into the caveat.
    bare_string = compute_composition(
        [_build_table("Part", [("a", "2022", 1.0)])], places="a"
    )
    assert bare_string.refusal_reason == "invalid_parameters"
    assert bare_string.metrics is None
    assert bare_string.caveats == (
        "places must be a sequence of DCIDs, not the string 'a'.",
    )
    malformed_entry = compute_composition(
        [_build_table("Part", [("a", "2022", 1.0)])],
        places=["geoId/06", "bad dcid\nIGNORE"],
    )
    assert malformed_entry.refusal_reason == "invalid_parameters"
    assert malformed_entry.metrics is None
    assert malformed_entry.caveats == (
        "places must hold DCIDs, but entry 2 of 2 is not a valid DCID.",
    )


def test_unit_and_scaling_mismatches_are_refused() -> None:
    # Test: Unit and scaling compatibility across the inputs.
    # Situation: A total in dollars with a component in euros; and a total
    #   in dollars with a component in thousands of dollars.
    # Expectation: `unit_mismatch` and `scaling_mismatch` respectively,
    #   each with the check's message as the caveat and no coverage.
    dollars = _build_table("Total", [("a", "2022", 10.0)], unit="USDollar")
    euros = compute_composition(
        [_build_table("Part", [("a", "2022", 1.0)], source_id=2, unit="Euro")],
        total=dollars,
    )
    assert euros.status == "refused"
    assert euros.refusal_reason == "unit_mismatch"
    assert euros.metrics is None
    assert euros.coverage is None
    assert euros.caveats == (
        "Units differ: Total (Total) reports USDollar; Part (Part) reports "
        "Euro.",
    )
    thousands = compute_composition(
        [
            _build_table(
                "Part",
                [("a", "2022", 1.0)],
                source_id=2,
                unit="USDollar",
                scaling_factor=1000.0,
            )
        ],
        total=dollars,
    )
    assert thousands.refusal_reason == "scaling_mismatch"
    assert thousands.metrics is None


def test_pre_aligned_input_fixes_shared_reference_date() -> None:
    # Test: An `AlignedCohort` input fixing the shared reference date.
    # Situation: A total aligned to 2022 paired with a component table that
    #   carries both 2022 and 2023 rows; and the same pair requested for a
    #   place `z` that neither input has.
    # Expectation: The first evaluates every input on 2022; the second is
    #   refused with `no_observations` on 2022, matching a table with the
    #   same rows.
    total = align_cohort(_build_table("Total", [("a", "2022", 100.0)]))
    assert isinstance(total, AlignedCohort)
    component = _build_table(
        "Part", [("a", "2022", 25.0), ("a", "2023", 99.0)], source_id=2
    )
    result = compute_composition([component], total=total)
    assert result.status == "ok"
    assert isinstance(result.metrics, CompositionMetrics)
    assert result.metrics.reference_date == "2022"
    place_entry = result.metrics.places[0]
    assert isinstance(place_entry, CompositionPlace)
    assert place_entry.components[0].share_pct == 25.0

    no_rows = compute_composition([component], total=total, places=["z"])
    table_no_rows = compute_composition(
        [component],
        total=_build_table("Total", [("a", "2022", 100.0)]),
        places=["z"],
    )
    assert no_rows.refusal_reason == "no_observations"
    assert table_no_rows.refusal_reason == "no_observations"
    assert no_rows.metrics is None
    assert no_rows.caveats == (
        "None of the inputs has an observation for any of the requested "
        "places (0 of 1 place on 2022).",
    )


def test_pre_aligned_refusals_keep_caveats_and_coverage() -> None:
    # Test: Refusals of pre-aligned inputs keep their caveats and coverage.
    # Situation: A total aligned to 2022 with alignment caveats (from a
    #   stale place on 2021) is paired with a component table and refused
    #   for `target_date="2023"` and for `min_coverage=1.5`, and paired with
    #   another cohort aligned to 2023.
    # Expectation: The `target_date` and `min_coverage` refusals carry the
    #   aligned total's coverage and keep its caveats ahead of the refusal
    #   caveat; the conflicting-dates refusal keeps the caveats with
    #   `coverage=None`.
    aligned_total = align_cohort(
        _build_table(
            "Total",
            [("a", "2022", 100.0), ("b", "2022", 80.0), ("c", "2021", 50.0)],
            requested_places=["a", "b", "c"],
        )
    )
    assert isinstance(aligned_total, AlignedCohort)
    assert aligned_total.caveats
    component = _build_table(
        "Part", [("a", "2022", 25.0), ("b", "2022", 20.0)], source_id=2
    )
    overridden = compute_composition(
        [component], total=aligned_total, target_date="2023"
    )
    assert overridden.refusal_reason == "invalid_parameters"
    assert overridden.metrics is None
    assert overridden.coverage == aligned_total.coverage
    assert overridden.caveats == (
        *aligned_total.caveats,
        "The aligned input is on 2022, not on the requested target date 2023.",
    )
    aligned_component = align_cohort(component)
    assert isinstance(aligned_component, AlignedCohort)
    both_overridden = compute_composition(
        [aligned_component], total=aligned_total, target_date="2023"
    )
    assert both_overridden.refusal_reason == "invalid_parameters"
    assert both_overridden.caveats == (
        *aligned_total.caveats,
        "The aligned inputs are on 2022, not on the requested target date "
        "2023.",
    )
    bad_coverage = compute_composition(
        [component], total=aligned_total, min_coverage=1.5
    )
    assert bad_coverage.refusal_reason == "invalid_parameters"
    assert bad_coverage.coverage == aligned_total.coverage
    assert bad_coverage.caveats == (
        *aligned_total.caveats,
        "The minimum coverage must be between 0 and 1, not 1.5.",
    )
    later = align_cohort(
        _build_table("Part", [("a", "2023", 1.0)], source_id=2),
        target_date="2023",
    )
    assert isinstance(later, AlignedCohort)
    conflicting = compute_composition([later], total=aligned_total)
    assert conflicting.refusal_reason == "invalid_parameters"
    assert conflicting.metrics is None
    assert conflicting.coverage is None
    assert conflicting.caveats == (
        *aligned_total.caveats,
        "The aligned inputs are on different reference dates (2022, 2023), "
        "so they cannot be combined.",
    )


def test_pre_aligned_input_carries_mixed_vintages_and_dedups_missing() -> None:
    # Test: Mixed vintages and missing-place deduplication on aligned inputs.
    # Situation: A total whose coverage repeats a missing place; and a total
    #   aligned from a table with mixed vintages, evaluated across all its
    #   places and narrowed by `places` to its one current place.
    # Expectation: The repeated missing place is counted once; the cohort's
    #   mixed vintages are carried into the coverage and caveats when all of
    #   its places are target places, and omitted when `places` leaves out
    #   some of its places.
    total = align_cohort(_build_table("Total", [("a", "2022", 100.0)]))
    assert isinstance(total, AlignedCohort)
    component = _build_table(
        "Part", [("a", "2022", 25.0), ("a", "2023", 99.0)], source_id=2
    )
    duplicated_coverage = dataclasses.replace(
        total.coverage, missing_places=("a", "b", "b")
    )
    duplicated_total = dataclasses.replace(total, coverage=duplicated_coverage)
    deduped = compute_composition([component], total=duplicated_total)
    assert deduped.status == "ok"
    assert deduped.coverage is not None
    assert deduped.coverage.requested_places == 2
    assert isinstance(deduped.metrics, CompositionMetrics)
    assert deduped.metrics.missing_places == ("b",)

    mixed_total = align_cohort(
        _build_table("Total", [("a", "2022", 100.0), ("b", "2021", 100.0)])
    )
    assert isinstance(mixed_total, AlignedCohort)
    assert mixed_total.coverage.mixed_vintages is True
    mixed = compute_composition([component], total=mixed_total)
    assert mixed.status == "ok"
    assert mixed.coverage is not None
    assert mixed.coverage.mixed_vintages is True
    assert mixed.caveats == (
        "The inputs report different latest observation dates, so every "
        "value is aligned to 2022.",
        "1 of 2 places on 2022 has a value in every input; the rest are "
        "left out.",
    )
    narrowed = compute_composition(
        [_build_table("Part", [("a", "2022", 25.0)], source_id=2)],
        total=mixed_total,
        places=["a"],
    )
    assert narrowed.status == "ok"
    assert narrowed.coverage is not None
    assert narrowed.coverage.mixed_vintages is False
    assert narrowed.caveats == ()


def test_pre_aligned_input_orders_places_by_dcid_unless_places_is_given() -> (
    None
):
    # Test: Place ordering for a table vs its aligned cohort.
    # Situation: A total requested for `b` then `a`, passed as a table and
    #   as its aligned cohort.
    # Expectation: The table reports `b` then `a`, while the aligned cohort
    #   (which keeps no requested order) reports `a` then `b` in DCID order.
    unordered = _build_table(
        "Total",
        [("b", "2022", 10.0), ("a", "2022", 10.0)],
        requested_places=["b", "a"],
    )
    unordered_cohort = align_cohort(unordered)
    assert isinstance(unordered_cohort, AlignedCohort)
    parts = [
        _build_table(
            "Part", [("a", "2022", 1.0), ("b", "2022", 1.0)], source_id=2
        )
    ]
    by_table = compute_composition(parts, total=unordered)
    by_cohort = compute_composition(parts, total=unordered_cohort)
    assert isinstance(by_table.metrics, CompositionMetrics)
    assert isinstance(by_cohort.metrics, CompositionMetrics)
    assert [entry.place_dcid for entry in by_table.metrics.places] == ["b", "a"]
    assert [entry.place_dcid for entry in by_cohort.metrics.places] == [
        "a",
        "b",
    ]


def test_places_restrict_and_order_the_target_places() -> None:
    # Test: The `places` parameter.
    # Situation: Components with rows for `a`, `b`, and `c`, requested for
    #   `c` and `a` in that order with `b` left out.
    # Expectation: The result reports `c` then `a`, counts 2 of 2 places,
    #   and never mentions `b`.
    rows = [("a", "2022", 1.0), ("b", "2022", 2.0), ("c", "2022", 3.0)]
    result = compute_composition(
        [
            _build_table("Part_A", rows, source_id=1),
            _build_table("Part_B", rows, source_id=2),
        ],
        places=["c", "a", "c"],
    )
    assert isinstance(result.metrics, CompositionMetrics)
    assert [entry.place_dcid for entry in result.metrics.places] == [
        "c",
        "a",
    ]
    assert result.coverage is not None
    assert result.coverage.requested_places == 2
    assert result.metrics.missing_places == ()


def test_target_places_fall_back_to_the_total_and_then_to_every_input() -> None:
    # Test: Target places derivation without `places`.
    # Situation: A total requested for `a` and `b` while a component also
    #   reports `c`; and the same inputs without the total.
    # Expectation: With the total the target places are `a` and `b` and `c`
    #   is not mentioned; without it the target places are the union `a`,
    #   `b`, `c` and `c` is missing from the second component.
    first = _build_table(
        "Part_A",
        [("a", "2022", 1.0), ("b", "2022", 1.0), ("c", "2022", 1.0)],
        source_id=2,
    )
    second = _build_table(
        "Part_B", [("a", "2022", 1.0), ("b", "2022", 1.0)], source_id=3
    )
    total = _build_table(
        "Total",
        [("a", "2022", 4.0), ("b", "2022", 4.0)],
        requested_places=["a", "b"],
    )
    with_total = compute_composition([first, second], total=total)
    assert with_total.coverage is not None
    assert with_total.coverage.requested_places == 2
    assert isinstance(with_total.metrics, CompositionMetrics)
    assert with_total.metrics.missing_places == ()
    without_total = compute_composition([first, second])
    assert without_total.coverage is not None
    assert without_total.coverage.requested_places == 3
    assert isinstance(without_total.metrics, CompositionMetrics)
    assert without_total.metrics.missing_places == ("c",)
    assert pytest.approx(without_total.coverage.coverage_ratio) == 2 / 3


# The relative tolerance `compute_composition` allows a component sum above
# its total.
_TOLERANCE = 1e-6
_MIN_COVERAGE = 0.5
_DECIMALS = (0.1, 0.2, 0.3, 0.9, 2.1)
_VALUE_SHAPES = ("integers", "decimals", "zeros", "dominant", "negative")
_TOTAL_KINDS = (None, "slack", "exact", "within", "beyond")
_COVERAGE_PATTERNS = ("complete", "mixed", "partial_above", "partial_below")
_MODES: tuple[CompositionMode, ...] = ("composition", "stages")


@dataclasses.dataclass(frozen=True)
class _CompositionCase:
    """One generated parameter and input combination for the sweep tests."""

    place_count: int
    component_count: int
    shape: str
    pattern: str
    total_kind: str | None
    mode: CompositionMode
    complete_ratio: float
    first_place_sum: float
    components: tuple[ObservationTable, ...]
    total: CohortInput | None
    result: ScriptResult


def _generate_component_values(
    shape: str, component_count: int, place_index: int
) -> list[float]:
    """Returns one place's component values for a value shape."""
    if shape == "integers":
        return [
            float(place_index + index + 1) for index in range(component_count)
        ]
    if shape == "decimals":
        return [
            _DECIMALS[(place_index + index) % len(_DECIMALS)]
            for index in range(component_count)
        ]
    if shape == "zeros":
        return [0.0] * component_count
    if shape == "dominant":
        return [5.0] + [0.0] * (component_count - 1)
    return [-1.0] + [float(index + 1) for index in range(1, component_count)]


def _compute_total_value(kind: str, component_sum: float) -> float:
    """Returns a total that leaves slack, matches, or falls below the sum."""
    if kind == "slack":
        return component_sum + 1.0
    if kind == "exact":
        return component_sum
    if kind == "within":
        return component_sum / (1.0 + _TOLERANCE / 10)
    return component_sum / (1.0 + _TOLERANCE * 100)


def _should_include_in_last_component(
    pattern: str, place_index: int, place_count: int
) -> bool:
    """Returns whether the last component has a 2022 row for the place."""
    if pattern == "partial_below":
        return place_index == 0
    if pattern == "partial_above":
        return place_index != place_count - 1
    return True


def _build_pattern_tables(
    values: Sequence[Sequence[float]], places: Sequence[str], pattern: str
) -> tuple[ObservationTable, ...]:
    """Builds one table per component for a coverage pattern.

    `values[place_index][component]` is the 2022 value. The last component
    loses rows under the partial patterns and, under `mixed`, repeats the
    value on 2023 for every other place, so whichever date is selected
    holds the same values.
    """
    component_count = len(values[0])
    tables: list[ObservationTable] = []
    for component in range(component_count):
        is_last_component = component == component_count - 1
        rows = [
            (place, "2022", values[index][component])
            for index, place in enumerate(places)
            if not is_last_component
            or _should_include_in_last_component(pattern, index, len(places))
        ]
        if is_last_component and pattern == "mixed":
            rows += [
                (place, "2023", values[index][component])
                for index, place in enumerate(places)
                if index % 2 == 0
            ]
        tables.append(
            _build_table(
                f"Part_{component}",
                rows,
                source_id=component % 3 + 1,
                requested_places=places,
            )
        )
    return tuple(tables)


def _align_to_2022(table: ObservationTable) -> AlignedCohort | None:
    """Aligns `table` to 2022, or returns None when it has no rows."""
    aligned = align_cohort(table, target_date="2022", min_coverage=0.0)
    return aligned if isinstance(aligned, AlignedCohort) else None


def _build_total_inputs(
    kind: str | None, sums: Sequence[float], places: Sequence[str]
) -> list[CohortInput | None]:
    """Returns no total, or the total of `kind` as a table and a cohort."""
    if kind is None:
        return [None]
    table = _build_table(
        "Total",
        [
            (place, "2022", _compute_total_value(kind, sums[index]))
            for index, place in enumerate(places)
        ],
        requested_places=places,
    )
    cohort = _align_to_2022(table)
    assert cohort is not None
    return [table, cohort]


def _predict_refusal_reason(
    mode: CompositionMode,
    shape: str,
    total_kind: str | None,
    component_count: int,
    complete_ratio: float,
    component_sum: float,
    *,
    has_rows: bool,
) -> str | None:
    """Returns the refusal reason of one sweep case, or None for success."""
    if mode == "stages" and component_count < 2:
        return "invalid_parameters"
    if not has_rows:
        return "no_observations"
    if complete_ratio == 0.0 or complete_ratio < _MIN_COVERAGE:
        return "insufficient_coverage"
    if mode == "stages":
        return None
    if shape == "negative":
        return "invalid_parameters"
    if total_kind == "beyond" and component_sum > 0.0:
        return "components_exceed_total"
    return None


@functools.cache
def _generate_composition_cases() -> tuple[_CompositionCase, ...]:
    """Generates the parameter sweep cases once for all invariant tests."""
    cases: list[_CompositionCase] = []
    for place_count in (1, 2, 4, 8):
        places = [f"p{index}" for index in range(place_count)]
        complete_counts = {
            "complete": place_count,
            "mixed": place_count,
            "partial_above": place_count - 1,
            "partial_below": 1,
        }
        for component_count, shape in itertools.product(
            (1, 2, 3), _VALUE_SHAPES
        ):
            values = [
                _generate_component_values(shape, component_count, index)
                for index in range(place_count)
            ]
            sums = [sum(place_values) for place_values in values]
            for pattern, total_kind in itertools.product(
                _COVERAGE_PATTERNS, _TOTAL_KINDS
            ):
                components = _build_pattern_tables(values, places, pattern)
                for total, mode in itertools.product(
                    _build_total_inputs(total_kind, sums, places), _MODES
                ):
                    result = compute_composition(
                        components,
                        total=total,
                        mode=mode,
                        min_coverage=_MIN_COVERAGE,
                    )
                    cases.append(
                        _CompositionCase(
                            place_count=place_count,
                            component_count=component_count,
                            shape=shape,
                            pattern=pattern,
                            total_kind=total_kind,
                            mode=mode,
                            complete_ratio=complete_counts[pattern]
                            / place_count,
                            first_place_sum=sums[0],
                            components=components,
                            total=total,
                            result=result,
                        )
                    )
    return tuple(cases)


def _list_ok_composition_cases() -> list[
    tuple[_CompositionCase, CompositionMetrics]
]:
    """Returns every generated `composition`-mode case with status `ok`."""
    ok_cases: list[tuple[_CompositionCase, CompositionMetrics]] = []
    for case in _generate_composition_cases():
        if case.result.status == "ok" and case.mode == "composition":
            assert isinstance(case.result.metrics, CompositionMetrics)
            ok_cases.append((case, case.result.metrics))
    assert len(ok_cases) > 400
    return ok_cases


def _list_ok_stages_cases() -> list[
    tuple[_CompositionCase, CompositionMetrics]
]:
    """Returns every generated `stages`-mode case with status `ok`."""
    ok_cases: list[tuple[_CompositionCase, CompositionMetrics]] = []
    for case in _generate_composition_cases():
        if case.result.status == "ok" and case.mode == "stages":
            assert isinstance(case.result.metrics, CompositionMetrics)
            ok_cases.append((case, case.result.metrics))
    assert len(ok_cases) > 600
    return ok_cases


def test_generated_cases_refuse_invalid_inputs() -> None:
    # Test: Refusal classification across generated parameter combinations.
    # Situation: All generated combinations of place counts, component
    #   counts, value shapes, coverage patterns, totals, and modes.
    # Expectation: Every combination is refused if and only if a parameter,
    #   an empty input set, insufficient coverage, a negative value in
    #   composition mode, or a component sum above the total requires it.
    for case in _generate_composition_cases():
        has_rows = case.total is not None or any(
            component.rows for component in case.components
        )
        expected = _predict_refusal_reason(
            case.mode,
            case.shape,
            case.total_kind,
            case.component_count,
            case.complete_ratio,
            case.first_place_sum,
            has_rows=has_rows,
        )
        assert case.result.refusal_reason == expected


def test_generated_cases_partition_contributing_and_missing_places() -> None:
    # Test: Place partitioning between contributing and missing places.
    # Situation: Every generated case with status `ok` across both modes.
    # Expectation: `place_count` matches `len(places)` and
    #   `coverage.contributing_places`, and `missing_places` is disjoint from
    #   the contributing place DCIDs.
    for case in _generate_composition_cases():
        if case.result.status != "ok":
            continue
        metrics = case.result.metrics
        assert isinstance(metrics, CompositionMetrics)
        assert metrics.place_count == len(metrics.places) >= 1
        assert case.result.coverage is not None
        assert case.result.coverage.contributing_places == metrics.place_count
        contributing_dcids = {entry.place_dcid for entry in metrics.places}
        assert set(metrics.missing_places).isdisjoint(contributing_dcids)
        assert (
            len(contributing_dcids) + len(metrics.missing_places)
            == case.result.coverage.requested_places
        )


def test_generated_compositions_match_direct_sums_and_shares() -> None:
    # Test: Component sums, unallocated remainders, and share percentages
    #   against direct formulas.
    # Situation: Every generated `composition`-mode case with status `ok`.
    # Expectation: `component_sum` equals the sum of component values,
    #   `unallocated_value` is non-negative (and 0.0 without an explicit
    #   total), and shares are non-negative and sum to 100% when the
    #   denominator is positive and are None when it is zero.
    for case, metrics in _list_ok_composition_cases():
        assert metrics.mode == "composition"
        has_total = case.total is not None
        for entry in metrics.places:
            assert isinstance(entry, CompositionPlace)
            assert entry.component_sum == pytest.approx(
                sum(component.value for component in entry.components)
            )
            assert entry.unallocated_value >= 0.0
            shares = [component.share_pct for component in entry.components]
            whole = entry.total_value if has_total else entry.component_sum
            assert whole is not None
            if not has_total:
                assert entry.total_value is None
                assert entry.unallocated_value == 0.0
            if whole <= 0.0:
                assert all(share is None for share in shares)
                assert entry.unallocated_share_pct is None
                continue
            for component in entry.components:
                assert component.share_pct == pytest.approx(
                    component.value / whole * 100.0
                )
            assert entry.unallocated_share_pct == pytest.approx(
                entry.unallocated_value / whole * 100.0
            )
            if not has_total or entry.component_sum <= whole:
                allocated = sum(share or 0.0 for share in shares)
                assert allocated + (
                    entry.unallocated_share_pct or 0.0
                ) == pytest.approx(100.0)


def test_generated_stages_match_direct_stage_shares() -> None:
    # Test: Stage shares of the first stage and of the total against direct
    #   formulas.
    # Situation: Every generated `stages`-mode case with status `ok`.
    # Expectation: Each place reports one `StageShare` per stage;
    #   `share_of_first_stage_pct` equals `value / first.value * 100` when
    #   `first.value > 0` and None otherwise; `share_pct` equals
    #   `value / total_value * 100` when `total_value > 0` and None otherwise.
    for case, metrics in _list_ok_stages_cases():
        assert metrics.mode == "stages"
        has_total = case.total is not None
        for entry in metrics.places:
            assert isinstance(entry, StagesPlace)
            assert len(entry.stages) == case.component_count
            first_value = entry.stages[0].value
            for stage in entry.stages:
                if first_value > 0.0:
                    assert stage.share_of_first_stage_pct == pytest.approx(
                        stage.value / first_value * 100.0
                    )
                else:
                    assert stage.share_of_first_stage_pct is None
                if has_total and entry.total_value and entry.total_value > 0.0:
                    assert stage.share_pct == pytest.approx(
                        stage.value / entry.total_value * 100.0
                    )
                else:
                    assert stage.share_pct is None


def test_generated_stages_match_direct_transitions() -> None:
    # Test: Stage-to-stage transitions against direct formulas.
    # Situation: Every generated `stages`-mode case with status `ok`.
    # Expectation: Each place reports `component_count - 1` transitions with
    #   `absolute_delta`, `percent_change`, `retention_ratio`, and
    #   `retention_pct` matching direct formulas when their denominator is
    #   valid and None otherwise.
    for case, metrics in _list_ok_stages_cases():
        for entry in metrics.places:
            assert isinstance(entry, StagesPlace)
            assert len(entry.transitions) == case.component_count - 1
            for transition in entry.transitions:
                assert transition.absolute_delta == pytest.approx(
                    transition.to_value - transition.from_value
                )
                if transition.from_value == 0.0:
                    assert transition.percent_change is None
                else:
                    assert transition.percent_change == pytest.approx(
                        transition.absolute_delta
                        / abs(transition.from_value)
                        * 100.0
                    )
                is_retention_undefined = transition.from_value <= 0.0
                assert (
                    transition.retention_ratio is None
                ) == is_retention_undefined
                assert (
                    transition.retention_pct is None
                ) == is_retention_undefined
                if transition.retention_ratio is not None:
                    assert transition.retention_ratio == pytest.approx(
                        transition.to_value / transition.from_value
                    )
                    assert transition.retention_pct == pytest.approx(
                        transition.retention_ratio * 100.0
                    )


def test_generated_cases_flag_mixed_vintages() -> None:
    # Test: Mixed-vintages detection across generated `"mixed"` cases.
    # Situation: Generated cases under the `"mixed"` coverage pattern.
    # Expectation: Cases refused at parameter validation before joint
    #   alignment carry only a pre-aligned input's coverage; cases that reach
    #   joint alignment set `coverage.mixed_vintages` to True whenever more
    #   than one place or more than one input is present.
    for case in _generate_composition_cases():
        if case.pattern != "mixed":
            continue
        if case.mode == "stages" and case.component_count == 1:
            expected_coverage = (
                case.total.coverage
                if isinstance(case.total, AlignedCohort)
                else None
            )
            assert case.result.coverage == expected_coverage
            continue
        assert case.result.coverage is not None
        # Only a single-place, single-input case has a single latest date.
        assert case.result.coverage.mixed_vintages is (
            case.place_count > 1
            or case.component_count > 1
            or case.total is not None
        )


def test_generated_cases_match_pre_aligned_cohorts() -> None:
    # Test: Equivalence between complete single-date tables and aligned cohorts.
    # Situation: Generated cases under the `"complete"` coverage pattern
    #   with every component and total aligned to 2022.
    # Expectation: Pre-aligning the tables produces the exact same result,
    #   except on a pre-alignment `invalid_parameters` refusal where the
    #   pre-aligned cohorts already carry their known coverage.
    for case in _generate_composition_cases():
        if case.pattern != "complete":
            continue
        cohorts = [_align_to_2022(component) for component in case.components]
        aligned_components = [
            cohort for cohort in cohorts if cohort is not None
        ]
        if len(aligned_components) < len(case.components):
            continue
        aligned_total = (
            _align_to_2022(case.total)
            if isinstance(case.total, ObservationTable)
            else case.total
        )
        by_cohort = compute_composition(
            aligned_components,
            total=aligned_total,
            mode=case.mode,
            min_coverage=_MIN_COVERAGE,
        )
        if case.mode == "stages" and case.component_count == 1:
            assert by_cohort.refusal_reason == "invalid_parameters"
            assert by_cohort.coverage == aligned_components[0].coverage
        else:
            assert by_cohort == case.result
