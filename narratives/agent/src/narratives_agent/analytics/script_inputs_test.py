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
"""Tests for the shared script input checks in `analytics.script_inputs`."""

from collections.abc import Sequence

from narratives_agent.analytics.alignment import AlignedCohort, align_cohort
from narratives_agent.analytics.provenance import Provenance, Source
from narratives_agent.analytics.script_inputs import (
    build_invalid_parameters_refusal,
    build_refusal,
    describe_missing_focal_places,
    resolve_aligned_cohort,
    validate_place_dcids,
)
from narratives_agent.analytics.tables import ObservationRow, ObservationTable


def _build_table(
    observations: Sequence[tuple[str, str, float]],
    *,
    requested_places: Sequence[str] = (),
) -> ObservationTable:
    """Builds a population table from `(place, date, value)` triples."""
    places = list(
        dict.fromkeys(
            [*requested_places, *(place for place, _, _ in observations)]
        )
    )
    return ObservationTable(
        variable_dcid="Count_Person",
        variable_name="Total population",
        unit="Person",
        scaling_factor=None,
        provenance=Provenance(
            sources=(Source(name="Census", url="https://census"),),
            facet_ids=("f1",),
        ),
        rows=tuple(
            ObservationRow(place, place.upper(), date, value)
            for place, date, value in observations
        ),
        requested_places=tuple(requested_places),
        place_names={place: place.upper() for place in places},
    )


def _build_aligned_cohort_with_caveats() -> AlignedCohort:
    """Aligns three requested places, one of them stale, to 2022."""
    aligned = align_cohort(
        _build_table(
            [("a", "2022", 1.0), ("b", "2022", 2.0), ("c", "2021", 3.0)],
            requested_places=["a", "b", "c"],
        )
    )
    assert isinstance(aligned, AlignedCohort)
    assert aligned.caveats
    return aligned


def test_validate_place_dcids_rejects_strings_and_invalid_entries() -> None:
    # Test: The place-list check.
    # Situation: A bare string, a list whose second entry holds a space, a
    #   list of valid DCIDs, and an empty list.
    # Expectation: The string is named and quoted; the invalid entry is
    #   identified by position only; valid and empty lists pass.
    assert validate_place_dcids("geoId/06", parameter_name="places") == (
        "places must be a sequence of DCIDs, not the string 'geoId/06'."
    )
    assert validate_place_dcids(
        ["geoId/06", "not a dcid"], parameter_name="focal_places"
    ) == ("focal_places must hold DCIDs, but entry 2 of 2 is not a valid DCID.")
    assert (
        validate_place_dcids(
            ["geoId/06", "country/FRA"], parameter_name="places"
        )
        is None
    )
    assert validate_place_dcids([], parameter_name="places") is None


def test_refusals_keep_an_aligned_cohorts_caveats_and_coverage() -> None:
    # Test: The refused-result builders.
    # Situation: An `invalid_parameters` refusal of a table and of an
    #   aligned cohort with alignment caveats, and a `no_observations`
    #   refusal of a table.
    # Expectation: A table's refusal has no coverage and only its own
    #   caveat; an aligned cohort's carries its coverage and its caveats
    #   ahead of the refusal's; the variable and provenance come from the
    #   input.
    table = _build_table([("a", "2022", 1.0)])
    refused_table = build_invalid_parameters_refusal(
        table, script="rank_cohort", step_id="s2", caveat="Bad."
    )
    assert refused_table.refusal_reason == "invalid_parameters"
    assert refused_table.script == "rank_cohort"
    assert refused_table.step_id == "s2"
    assert refused_table.coverage is None
    assert refused_table.caveats == ("Bad.",)
    assert refused_table.variables == ("Count_Person",)
    assert refused_table.provenance == table.provenance
    aligned = _build_aligned_cohort_with_caveats()
    refused_cohort = build_invalid_parameters_refusal(
        aligned, script="summarize_distribution", step_id="s1", caveat="Bad."
    )
    assert refused_cohort.coverage == aligned.coverage
    assert refused_cohort.caveats == (*aligned.caveats, "Bad.")
    empty = build_refusal(
        table,
        script="analyze_timeseries",
        step_id="s1",
        reason="no_observations",
        coverage=None,
        caveat="None match.",
    )
    assert empty.refusal_reason == "no_observations"
    assert empty.caveats == ("None match.",)


def test_resolve_aligned_cohort_aligns_tables_and_checks_cohorts() -> None:
    # Test: Resolution of a cohort-or-table argument.
    # Situation: A table aligned with defaults; a table with `min_coverage`
    #   1.5; a table below the default coverage; and an aligned cohort with
    #   its own date, another date, and `min_coverage` 1.5 without and with
    #   the check.
    # Expectation: The table is aligned; the bad `min_coverage` is refused
    #   with `invalid_parameters` and no coverage; the sparse table is
    #   refused with the alignment's reason and coverage; the aligned cohort
    #   is returned as given for its own date and an unchecked
    #   `min_coverage`, and is refused, carrying its coverage, for another
    #   date (naming the operation) and a checked bad `min_coverage`.
    table = _build_table([("a", "2022", 1.0), ("b", "2022", 2.0)])
    resolved = resolve_aligned_cohort(
        table,
        script="rank_cohort",
        step_id="s1",
        target_date=None,
        min_coverage=0.5,
        operation="ranked",
    )
    assert isinstance(resolved, AlignedCohort)
    assert resolved.reference_date == "2022"
    bad_coverage = resolve_aligned_cohort(
        table,
        script="rank_cohort",
        step_id="s1",
        target_date=None,
        min_coverage=1.5,
        operation="ranked",
    )
    assert not isinstance(bad_coverage, AlignedCohort)
    assert bad_coverage.refusal_reason == "invalid_parameters"
    assert bad_coverage.coverage is None
    sparse = resolve_aligned_cohort(
        _build_table(
            [("a", "2022", 1.0)], requested_places=["a", "b", "c", "d"]
        ),
        script="rank_cohort",
        step_id="s1",
        target_date=None,
        min_coverage=0.5,
        operation="ranked",
    )
    assert not isinstance(sparse, AlignedCohort)
    assert sparse.refusal_reason == "insufficient_coverage"
    assert sparse.coverage is not None
    assert sparse.coverage.contributing_places == 1

    aligned = _build_aligned_cohort_with_caveats()
    for target_date, min_coverage in (("2022", 0.5), (None, 1.5)):
        assert (
            resolve_aligned_cohort(
                aligned,
                script="summarize_distribution",
                step_id="s1",
                target_date=target_date,
                min_coverage=min_coverage,
                operation="summarized",
            )
            is aligned
        )
    other_date = resolve_aligned_cohort(
        aligned,
        script="summarize_distribution",
        step_id="s1",
        target_date="2021",
        min_coverage=0.5,
        operation="summarized",
    )
    assert not isinstance(other_date, AlignedCohort)
    assert other_date.coverage == aligned.coverage
    assert other_date.caveats == (
        *aligned.caveats,
        "The cohort is aligned to 2022, so it cannot be summarized on the "
        "target date 2021.",
    )
    checked = resolve_aligned_cohort(
        aligned,
        script="summarize_distribution",
        step_id="s1",
        target_date=None,
        min_coverage=1.5,
        operation="summarized",
        should_check_min_coverage=True,
    )
    assert not isinstance(checked, AlignedCohort)
    assert checked.refusal_reason == "invalid_parameters"
    assert checked.caveats[-1] == (
        "The minimum coverage must be between 0 and 1, not 1.5."
    )


def test_describe_missing_focal_places_names_the_cohort_and_figure() -> None:
    # Test: The caveat for focal places missing from a cohort.
    # Situation: One missing place with a display name and two without.
    # Expectation: The display name is used where known and the DCID
    #   otherwise, the verb agrees with the count, and the cohort label and
    #   the unavailable figure are worded as given.
    aligned = _build_aligned_cohort_with_caveats()
    assert describe_missing_focal_places(
        aligned, ["c"], cohort_label="ranked cohort", unavailable_figure="rank"
    ) == (
        "C has no value for Total population in the ranked cohort on 2022, "
        "so no rank is available."
    )
    assert describe_missing_focal_places(
        aligned,
        ["x", "y"],
        cohort_label="cohort",
        unavailable_figure="benchmark",
    ) == (
        "x and y have no value for Total population in the cohort on 2022, "
        "so no benchmark is available."
    )
