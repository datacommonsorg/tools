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
"""Tests for cohort alignment and unit checks in `analytics.alignment`.

Covers reference-date selection against the coverage threshold and at its
boundary, its input guards, mixed vintage detection, the two refusal reasons
with their coverage figures, explicit target dates and their date precision,
rows at mixed date precisions, duplicate requested places, message wording,
validation of the threshold and the target date, and unit and scaling
compatibility across tables and cohorts.
"""

import dataclasses
import re
from collections.abc import Sequence

import pytest

from narratives_agent.analytics.alignment import (
    AlignedCohort,
    AlignmentRefusal,
    UnitMismatch,
    align_cohort,
    find_unit_mismatch,
    has_adequate_coverage,
    select_reference_date,
    validate_alignment_parameters,
)
from narratives_agent.analytics.provenance import Provenance, Source
from narratives_agent.analytics.tables import ObservationRow, ObservationTable


def _table(
    observations: Sequence[tuple[str, str, float]],
    *,
    requested_places: Sequence[str] = (),
    variable_dcid: str = "Count_Person",
    variable_name: str = "Total population",
    unit: str | None = None,
    scaling_factor: float | None = None,
) -> ObservationTable:
    """Builds a table from `(place, date, value)` triples in table order."""
    places = list(
        dict.fromkeys(
            [*requested_places, *(place for place, _, _ in observations)]
        )
    )
    return ObservationTable(
        variable_dcid=variable_dcid,
        variable_name=variable_name,
        unit=unit,
        scaling_factor=scaling_factor,
        provenance=Provenance(sources=(Source(name="s", url="u"),)),
        rows=tuple(
            ObservationRow(place, place.upper(), date, value)
            for place, date, value in observations
        ),
        requested_places=tuple(requested_places),
        place_names={place: place.upper() for place in places},
    )


def _ten_place_cohort() -> ObservationTable:
    """Ten places: nine report 2022, two report 2023, one reports only 2021."""
    places = [f"p{index}" for index in range(10)]
    observations: list[tuple[str, str, float]] = []
    for index, place in enumerate(places):
        if place == "p9":
            observations.append((place, "2021", 9.0))
            continue
        observations.append((place, "2022", float(index)))
        if place in ("p0", "p1"):
            observations.append((place, "2023", float(index) + 0.5))
    return _table(observations, requested_places=places)


def test_most_recent_date_with_adequate_coverage_is_selected() -> None:
    # Test: Reference date selection.
    # Situation: Ten requested places; 2023 has 2 of 10, 2022 has 9 of 10,
    #   and one place reports only 2021, so latest dates differ.
    # Expectation: 2022 is selected over the sparser 2023, the coverage is
    #   9 of 10 with `p9` missing, `mixed_vintages` is True, the rows are
    #   sorted by place, and both caveats are stated.
    aligned = align_cohort(_ten_place_cohort())
    assert isinstance(aligned, AlignedCohort)
    assert aligned.reference_date == "2022"
    assert aligned.coverage.contributing_places == 9
    assert aligned.coverage.requested_places == 10
    assert aligned.coverage.coverage_ratio == 0.9
    assert aligned.coverage.missing_places == ("p9",)
    assert aligned.coverage.mixed_vintages is True
    assert [row.place_dcid for row in aligned.rows] == [
        f"p{index}" for index in range(9)
    ]
    assert all(row.date == "2022" for row in aligned.rows)
    assert aligned.caveats == (
        "The places report different latest observation dates, so every "
        "value is aligned to 2022.",
        "9 of 10 places on 2022 reported a value for Total population.",
    )


def test_select_reference_date_prefers_recent_coverage_then_counts() -> None:
    # Test: The reference date rule shared with the analytical scripts.
    # Situation: Place counts for a cohort of ten, first with two dates that
    #   reach 50% coverage, then with no date that does and two dates tied
    #   for the largest count, and last with an 80% threshold that only the
    #   older of two dates reaches.
    # Expectation: The most recent qualifying date is chosen when one
    #   exists; otherwise the date with the largest count is chosen, and the
    #   more recent of the tied dates wins.
    assert (
        select_reference_date({"2021": 9, "2022": 6, "2023": 2}, 10) == "2022"
    )
    assert (
        select_reference_date({"2020": 3, "2021": 4, "2022": 4, "2023": 1}, 10)
        == "2022"
    )
    assert (
        select_reference_date({"2021": 9, "2022": 6}, 10, min_coverage=0.8)
        == "2021"
    )


def test_select_reference_date_rejects_empty_counts_and_cohorts() -> None:
    # Test: The input guards of `select_reference_date`.
    # Situation: An empty count mapping, and cohort sizes of 0 and -1.
    # Expectation: Each raises `ValueError` with a message naming the
    #   problem, rather than failing inside `max` or dividing by zero.
    with pytest.raises(
        ValueError, match=re.escape("counts_by_date must not be empty.")
    ):
        select_reference_date({}, 10)
    for cohort_size in (0, -1):
        with pytest.raises(
            ValueError,
            match=re.escape(
                f"The cohort size must be at least 1, not {cohort_size}."
            ),
        ):
            select_reference_date({"2022": 1}, cohort_size)


def test_an_aligned_cohort_without_rows_is_rejected() -> None:
    # Test: The non-empty invariant of `AlignedCohort`.
    # Situation: An aligned cohort copied with no rows, which `align_cohort`
    #   never produces.
    # Expectation: Construction raises `ValueError`.
    aligned = align_cohort(_table([("a", "2022", 1.0)]))
    assert isinstance(aligned, AlignedCohort)
    with pytest.raises(
        ValueError,
        match=re.escape("An aligned cohort must have at least one row."),
    ):
        dataclasses.replace(aligned, rows=())


def test_has_adequate_coverage_includes_the_threshold() -> None:
    # Test: The coverage predicate shared by the date rule and its callers.
    # Situation: 5, 4, and 0 of 10 places at the default 50% threshold, and
    #   0 of 10 at a threshold of 0.
    # Expectation: 5 of 10 meets the threshold exactly, 4 of 10 does not,
    #   and a threshold of 0 accepts any count.
    assert has_adequate_coverage(5, 10)
    assert not has_adequate_coverage(4, 10)
    assert has_adequate_coverage(0, 10, min_coverage=0.0)


def test_target_date_is_used_as_given_and_duplicates_keep_the_last_row() -> (
    None
):
    # Test: Alignment to an explicit date.
    # Situation: `target_date` names 2023, on which two places report, one
    #   of them twice.
    # Expectation: The cohort is aligned to 2023 with the later duplicate
    #   kept when the threshold is lowered to admit 2 of 3 places, and the
    #   refusal reports 2 of 3 on 2023 at a 70% threshold.
    table = _table(
        [
            ("a", "2023", 1.0),
            ("a", "2023", 2.0),
            ("b", "2023", 3.0),
            ("c", "2022", 4.0),
        ],
        requested_places=["a", "b", "c"],
    )
    aligned = align_cohort(table, target_date="2023", min_coverage=0.6)
    assert isinstance(aligned, AlignedCohort)
    assert [(row.place_dcid, row.value) for row in aligned.rows] == [
        ("a", 2.0),
        ("b", 3.0),
    ]
    refused = align_cohort(table, target_date="2023", min_coverage=0.7)
    assert isinstance(refused, AlignmentRefusal)
    assert refused.reason == "insufficient_coverage"
    assert refused.coverage.reference_date == "2023"
    assert refused.coverage.contributing_places == 2


def test_empty_table_is_refused_with_no_observations() -> None:
    # Test: Alignment of a table without rows.
    # Situation: Three places were requested and none has a row.
    # Expectation: A `no_observations` refusal with 0 of 3 coverage, every
    #   place missing, and a message naming the variable.
    refused = align_cohort(_table([], requested_places=["a", "b", "c"]))
    assert isinstance(refused, AlignmentRefusal)
    assert refused.reason == "no_observations"
    assert refused.coverage.contributing_places == 0
    assert refused.coverage.requested_places == 3
    assert refused.coverage.coverage_ratio == 0.0
    assert refused.coverage.missing_places == ("a", "b", "c")
    assert refused.message == (
        "Total population (Count_Person) has no observations for any of "
        "the requested places (0 of 3 places)."
    )


def test_rows_outside_the_requested_places_do_not_count() -> None:
    # Test: Rows for places that were not requested.
    # Situation: The only rows belong to a place outside the requested
    #   places.
    # Expectation: A `no_observations` refusal, because the target places
    #   have no data at all.
    refused = align_cohort(
        _table([("z", "2022", 1.0)], requested_places=["a", "b"])
    )
    assert isinstance(refused, AlignmentRefusal)
    assert refused.reason == "no_observations"


def test_insufficient_coverage_reports_the_best_available_date() -> None:
    # Test: Refusal when no date meets the threshold.
    # Situation: Ten requested places, with 3 reporting in 2020, 3 in 2022,
    #   and 1 in 2023.
    # Expectation: An `insufficient_coverage` refusal whose coverage names
    #   2022 (the most recent of the dates tied at 3 of 10) and whose
    #   message states the figure and the threshold.
    places = [f"p{index}" for index in range(10)]
    observations = [
        ("p0", "2020", 1.0),
        ("p1", "2020", 1.0),
        ("p2", "2020", 1.0),
        ("p3", "2022", 1.0),
        ("p4", "2022", 1.0),
        ("p5", "2022", 1.0),
        ("p6", "2023", 1.0),
    ]
    refused = align_cohort(_table(observations, requested_places=places))
    assert isinstance(refused, AlignmentRefusal)
    assert refused.reason == "insufficient_coverage"
    assert refused.coverage.reference_date == "2022"
    assert refused.coverage.contributing_places == 3
    assert refused.coverage.requested_places == 10
    assert refused.coverage.mixed_vintages is True
    assert refused.message == (
        "Only 3 of 10 places on 2022 have a value for Total population "
        "(Count_Person), below the required 50% coverage."
    )


def test_target_places_default_to_the_places_with_rows() -> None:
    # Test: Alignment of a table without recorded requested places.
    # Situation: `requested_places` is empty and two places have rows on
    #   the same date.
    # Expectation: The target places are the two places, coverage is 2 of 2,
    #   and no caveat is needed.
    aligned = align_cohort(_table([("b", "2022", 1.0), ("a", "2022", 2.0)]))
    assert isinstance(aligned, AlignedCohort)
    assert aligned.coverage.requested_places == 2
    assert aligned.coverage.coverage_ratio == 1.0
    assert aligned.coverage.mixed_vintages is False
    assert aligned.caveats == ()
    assert [row.place_dcid for row in aligned.rows] == ["a", "b"]


def test_target_date_of_another_precision_names_the_mismatch() -> None:
    # Test: A `target_date` whose precision differs from the row dates.
    # Situation: Three places report `2022-06`, and `target_date` is `2022`.
    # Expectation: An `insufficient_coverage` refusal whose message names
    #   the precision mismatch instead of claiming that no place has a value.
    table = _table(
        [("a", "2022-06", 1.0), ("b", "2022-06", 2.0), ("c", "2022-06", 3.0)],
        requested_places=["a", "b", "c"],
    )
    refused = align_cohort(table, target_date="2022")
    assert isinstance(refused, AlignmentRefusal)
    assert refused.reason == "insufficient_coverage"
    assert refused.message == (
        "The target date 2022 does not match the precision of the Total "
        "population (Count_Person) dates, such as 2022-06, so no place can "
        "be aligned to it."
    )


def test_target_date_overlapping_rows_of_another_precision_is_named() -> None:
    # Test: A `target_date` that shares its precision with some rows but
    #   overlaps others at a finer precision.
    # Situation: Two places report `2022-06`, one place reports `2023`, and
    #   `target_date` is `2022`.
    # Expectation: The refusal names the precision mismatch and quotes the
    #   overlapping `2022-06` rather than `2023`, even though `2023` has the
    #   precision of the target date.
    table = _table(
        [("a", "2022-06", 1.0), ("b", "2022-06", 2.0), ("c", "2023", 3.0)],
        requested_places=["a", "b", "c"],
    )
    refused = align_cohort(table, target_date="2022")
    assert isinstance(refused, AlignmentRefusal)
    assert refused.reason == "insufficient_coverage"
    assert refused.message == (
        "The target date 2022 does not match the precision of the Total "
        "population (Count_Person) dates, such as 2022-06, so no place can "
        "be aligned to it."
    )


def test_a_place_requested_twice_counts_once() -> None:
    # Test: Duplicate entries in `requested_places`.
    # Situation: The request lists `c`, `a`, `b`, `d`, `c`, `a`, and only
    #   `a` and `b` report 2022.
    # Expectation: The cohort has 4 places, so 2 of 4 meets the default
    #   threshold, and the missing places keep request order without
    #   repeats.
    table = _table(
        [("a", "2022", 1.0), ("b", "2022", 2.0)],
        requested_places=["c", "a", "b", "d", "c", "a"],
    )
    aligned = align_cohort(table)
    assert isinstance(aligned, AlignedCohort)
    assert aligned.coverage.requested_places == 4
    assert aligned.coverage.contributing_places == 2
    assert aligned.coverage.missing_places == ("c", "d")


def test_a_table_without_rows_or_places_names_no_place_count() -> None:
    # Test: The refusal of a table with no rows and no requested places.
    # Situation: An empty table with no target places.
    # Expectation: A `no_observations` refusal that names the variable and
    #   no place count.
    refused = align_cohort(_table([]))
    assert isinstance(refused, AlignmentRefusal)
    assert refused.reason == "no_observations"
    assert (
        refused.message
        == "Total population (Count_Person) has no observations."
    )


def test_a_threshold_that_is_not_a_whole_percentage_keeps_a_decimal() -> None:
    # Test: The threshold and verb in a coverage refusal.
    # Situation: One of three places reports 2022, at thresholds of 0.334
    #   and 0.9995.
    # Expectation: The messages state 33.4% and 99.95%, not 33% or 100%,
    #   which would misstate the threshold, and use "has" for one place.
    table = _table([("a", "2022", 1.0)], requested_places=["a", "b", "c"])
    refused = align_cohort(table, min_coverage=0.334)
    assert isinstance(refused, AlignmentRefusal)
    assert refused.message == (
        "Only 1 of 3 places on 2022 has a value for Total population "
        "(Count_Person), below the required 33.4% coverage."
    )
    near_whole = align_cohort(table, min_coverage=0.9995)
    assert isinstance(near_whole, AlignmentRefusal)
    assert near_whole.message.endswith("below the required 99.95% coverage.")


def test_mixed_vintages_with_a_target_date_name_the_requested_date() -> None:
    # Test: The mixed-vintage caveat when the caller chose the date.
    # Situation: Two places report 2022 and one also reports 2023; the
    #   cohort is aligned to an explicit 2022.
    # Expectation: The caveat says every value is aligned to the requested
    #   date, without giving mixed vintages as the reason for the date.
    aligned = align_cohort(
        _table([("a", "2022", 1.0), ("b", "2022", 2.0), ("b", "2023", 3.0)]),
        target_date="2022",
    )
    assert isinstance(aligned, AlignedCohort)
    assert aligned.caveats == (
        "The places report different latest observation dates; every value "
        "is aligned to the requested date 2022.",
    )


def test_coverage_equal_to_the_threshold_is_adequate() -> None:
    # Test: The boundary of the coverage threshold.
    # Situation: Four requested places, two of which report 2022, at the
    #   default 50% threshold.
    # Expectation: 2 of 4 meets the threshold, so the cohort aligns to 2022.
    table = _table(
        [("a", "2022", 1.0), ("b", "2022", 2.0)],
        requested_places=["a", "b", "c", "d"],
    )
    aligned = align_cohort(table)
    assert isinstance(aligned, AlignedCohort)
    assert aligned.reference_date == "2022"
    assert aligned.coverage.coverage_ratio == 0.5


def test_target_date_without_rows_is_refused() -> None:
    # Test: Alignment to a date on which no place reports.
    # Situation: One place reports 2022 and `target_date` names 2019.
    # Expectation: An `insufficient_coverage` refusal on 2019 with 0 of 1
    #   coverage, at the default threshold and at a threshold of 0, with a
    #   message that cites no threshold.
    refused = align_cohort(
        _table([("a", "2022", 1.0)], requested_places=["a"]),
        target_date="2019",
    )
    assert isinstance(refused, AlignmentRefusal)
    assert refused.reason == "insufficient_coverage"
    assert refused.coverage.reference_date == "2019"
    assert refused.coverage.contributing_places == 0
    assert refused.coverage.missing_places == ("a",)
    assert refused.message == (
        "No place has a value for Total population (Count_Person) (0 of 1 "
        "place on 2019)."
    )
    at_zero = align_cohort(
        _table([("a", "2022", 1.0)], requested_places=["a"]),
        target_date="2019",
        min_coverage=0.0,
    )
    assert at_zero == refused


def test_min_coverage_bounds_are_accepted() -> None:
    # Test: The inclusive bounds of `min_coverage`.
    # Situation: One of two requested places reports 2022, aligned at
    #   thresholds of 0.0 and 1.0.
    # Expectation: 0.0 aligns the cohort with 1 of 2 places, and 1.0
    #   refuses it as `insufficient_coverage`; neither raises.
    table = _table([("a", "2022", 1.0)], requested_places=["a", "b"])
    assert isinstance(align_cohort(table, min_coverage=0.0), AlignedCohort)
    refused = align_cohort(table, min_coverage=1.0)
    assert isinstance(refused, AlignmentRefusal)
    assert refused.reason == "insufficient_coverage"


def test_min_coverage_outside_zero_to_one_is_rejected() -> None:
    # Test: Validation of `min_coverage`.
    # Situation: Thresholds of 1.5 and -0.1.
    # Expectation: `validate_alignment_parameters` returns a message naming
    #   the value, and `align_cohort` raises `ValueError` with it.
    table = _table([("a", "2022", 1.0)])
    for min_coverage in (1.5, -0.1):
        expected = (
            f"The minimum coverage must be between 0 and 1, not {min_coverage}."
        )
        assert (
            validate_alignment_parameters(min_coverage=min_coverage) == expected
        )
        with pytest.raises(ValueError, match=re.escape(expected)):
            align_cohort(table, min_coverage=min_coverage)


def test_a_malformed_target_date_is_rejected() -> None:
    # Test: Validation of `target_date`.
    # Situation: Target dates of `2022/06` and an empty string.
    # Expectation: `validate_alignment_parameters` returns a message naming
    #   the value, and `align_cohort` raises `ValueError` with it rather than
    #   producing a refusal that reads as a data gap. Default arguments are
    #   valid.
    assert validate_alignment_parameters() is None
    table = _table([("a", "2022-06", 1.0)])
    for target_date in ("2022/06", ""):
        expected = (
            f"The target date {target_date!r} is not a year, a year and "
            "month, or a full date."
        )
        assert (
            validate_alignment_parameters(target_date=target_date) == expected
        )
        with pytest.raises(ValueError, match=re.escape(expected)):
            align_cohort(table, target_date=target_date)


def test_dates_of_different_precision_are_different_reference_dates() -> None:
    # Test: A cohort whose rows mix date precisions.
    # Situation: Places `a` and `b` report `2023`, and place `c` reports
    #   only `2023-07-31`.
    # Expectation: Dates match as exact strings. `2023-07-31` sorts after
    #   `2023` but has 1 of 3 places, below the threshold, so the cohort
    #   aligns to `2023` with 2 of 3 places, `c` missing, and both caveats
    #   stated.
    table = _table(
        [("a", "2023", 1.0), ("b", "2023", 2.0), ("c", "2023-07-31", 3.0)],
        requested_places=["a", "b", "c"],
    )
    aligned = align_cohort(table)
    assert isinstance(aligned, AlignedCohort)
    assert aligned.reference_date == "2023"
    assert aligned.coverage.contributing_places == 2
    assert aligned.coverage.missing_places == ("c",)
    assert aligned.caveats == (
        "The places report different latest observation dates, so every "
        "value is aligned to 2023.",
        "2 of 3 places on 2023 reported a value for Total population.",
    )


def test_units_are_compared_after_folding_and_an_unset_unit_conflicts() -> None:
    # Test: Unit comparison in `find_unit_mismatch`.
    # Situation: Two tables whose units differ only in case and whitespace,
    #   and a third with no unit and a different scaling factor.
    # Expectation: No table, a single table, and the first two together are
    #   compatible; adding the third is a `unit_mismatch`, reported before
    #   its scaling conflict, whose message names each table's variable and
    #   unit.
    dollars = _table([], unit="USDollar")
    folded = _table([], unit=" usdollar ")
    unset = _table(
        [],
        unit="",
        scaling_factor=1000.0,
        variable_dcid="Count_Household",
        variable_name="Total households",
    )
    assert find_unit_mismatch() is None
    assert find_unit_mismatch(dollars) is None
    assert find_unit_mismatch(dollars, folded) is None
    assert find_unit_mismatch(dollars, unset) == UnitMismatch(
        "unit_mismatch",
        "Units differ: Total population (Count_Person) reports USDollar; "
        "Total households (Count_Household) reports no unit.",
    )


def test_scaling_factors_are_compared_with_absent_read_as_one() -> None:
    # Test: Scaling comparison in `find_unit_mismatch`.
    # Situation: Tables sharing a unit where one has no scaling factor, one
    #   has `1.0`, and one has `1_000_000.0`; one of them is aligned first.
    # Expectation: Absent and `1.0` are compatible; `1_000_000.0` is a
    #   `scaling_mismatch` rendered as `1000000` without scientific
    #   notation, and an aligned cohort takes part like a table.
    absent = _table([("a", "2022", 1.0)], unit="Person")
    one = _table([], unit="Person", scaling_factor=1.0)
    million = _table(
        [],
        unit="Person",
        scaling_factor=1_000_000.0,
        variable_dcid="Count_Person_Urban",
        variable_name="Urban population",
    )
    aligned = align_cohort(absent)
    assert isinstance(aligned, AlignedCohort)
    assert find_unit_mismatch(aligned, one) is None
    assert find_unit_mismatch(aligned, million) == UnitMismatch(
        "scaling_mismatch",
        "Scaling factors differ: Total population (Count_Person) reports a "
        "scaling factor of 1; Urban population (Count_Person_Urban) reports "
        "a scaling factor of 1000000.",
    )
