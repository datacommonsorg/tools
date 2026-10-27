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
"""Tests for `pair_cohorts` and `relate_cohorts` in `analytics.relations`.

Covers places covered by one side only, different reference dates and
precisions, ties at the group cut-offs, the group-size cap, coverage symmetry,
every pairing and parameter refusal, aligned-cohort inputs, fallbacks from
`target` to `by` for requested places and display names, non-finite summary
guards, helper preconditions, deterministic brute-force invariants, and prompt
rendering.
"""

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

import pytest

from narratives_agent.analytics import relations
from narratives_agent.analytics.alignment import AlignedCohort, align_cohort
from narratives_agent.analytics.digest import (
    AnalysisDigest,
    RefusedScriptResult,
    ScriptResult,
)
from narratives_agent.analytics.metrics import (
    GroupSummary,
    RankEntry,
    RelationEntry,
    RelationMetrics,
)
from narratives_agent.analytics.provenance import Provenance, Source
from narratives_agent.analytics.relations import (
    PairedCohort,
    PairedPlace,
    PairingRefusal,
    _align_cohort_side,
    _compute_finite_mean,
    _compute_finite_median,
    _compute_mean_difference,
    _describe_dropped_places,
    _rank_shared_places,
    _resolve_place_names,
    _resolve_table_requested_places,
    _select_group_entries,
    _summarize_group,
    _validate_pairing_parameters,
    pair_cohorts,
    relate_cohorts,
)
from narratives_agent.analytics.tables import (
    ObservationRow,
    ObservationTable,
)

_INCOME_SOURCE = Source(name="census.gov", url="https://census.gov")
_HEALTH_SOURCE = Source(name="cdc.gov", url="https://cdc.gov")


def _build_table(
    variable: tuple[str, str],
    observations: Sequence[tuple[str, str, float]],
    *,
    unit: str | None = None,
    scaling_factor: float | None = None,
    requested_places: Sequence[str] = (),
    place_names: Mapping[str, str] | None = None,
    source: Source = _HEALTH_SOURCE,
) -> ObservationTable:
    """Builds a table from `(place, date, value)` triples."""
    places = list(
        dict.fromkeys(
            [*requested_places, *(place for place, _, _ in observations)]
        )
    )
    resolved_names = (
        dict(place_names)
        if place_names is not None
        else {place: place.upper() for place in places}
    )
    variable_dcid, variable_name = variable
    return ObservationTable(
        variable_dcid=variable_dcid,
        variable_name=variable_name,
        unit=unit,
        scaling_factor=scaling_factor,
        provenance=Provenance(sources=(source,), facet_ids=(variable_dcid,)),
        rows=tuple(
            ObservationRow(
                place,
                resolved_names.get(place, place),
                date,
                value,
            )
            for place, date, value in sorted(observations)
        ),
        requested_places=tuple(requested_places),
        place_names=resolved_names,
    )


def _build_income_table(
    values: Mapping[str, float],
    date: str = "2022",
    *,
    scaling_factor: float | None = None,
    requested_places: Sequence[str] = (),
    place_names: Mapping[str, str] | None = None,
) -> ObservationTable:
    """Builds a median income table with one value per place on `date`."""
    return _build_table(
        ("Median_Income_Household", "Median income"),
        [(place, date, value) for place, value in values.items()],
        unit="USDollar",
        scaling_factor=scaling_factor,
        requested_places=requested_places,
        place_names=place_names,
        source=_INCOME_SOURCE,
    )


def _build_diabetes_table(
    values: Mapping[str, float],
    date: str = "2022",
    *,
    requested_places: Sequence[str] = (),
    place_names: Mapping[str, str] | None = None,
) -> ObservationTable:
    """Builds a diabetes prevalence table with one value per place."""
    return _build_table(
        ("Percent_Person_WithDiabetes", "Diabetes prevalence"),
        [(place, date, value) for place, value in values.items()],
        unit="Percent",
        requested_places=requested_places,
        place_names=place_names,
    )


def _extract_metrics(result: ScriptResult) -> RelationMetrics:
    """Returns the relation metrics of an ok result."""
    assert result.status == "ok", result.caveats
    assert isinstance(result.metrics, RelationMetrics)
    return result.metrics


def _collect_place_dcids(entries: Sequence[RelationEntry]) -> list[str]:
    """Returns the place DCIDs of a group, in order."""
    return [entry.place_dcid for entry in entries]


def test_places_covered_by_one_side_are_dropped_and_reported() -> None:
    # Test: Places that only one cohort covers.
    # Situation: Income covers p01 to p12, highest first; diabetes covers
    #   p01 to p09 and x99, so the three lowest-income places (the whole
    #   low tail of the `by` cohort) have no target value.
    # Expectation: The pair keeps the nine shared places; the lowest group
    #   is the three lowest-income places that do have diabetes data; the
    #   group summaries and their difference cover the listed entries; and
    #   one caveat counts and names the places dropped from each side.
    income = _build_income_table(
        {f"p{index:02d}": 13.0 - index for index in range(1, 13)}
    )
    diabetes = _build_diabetes_table(
        {
            **{f"p{index:02d}": float(index) for index in range(1, 10)},
            "x99": 50.0,
        }
    )

    paired = pair_cohorts(diabetes, income)
    assert isinstance(paired, PairedCohort)
    assert len(paired.places) == 9
    assert paired.target_only_places == ("x99",)
    assert paired.by_only_places == ("p10", "p11", "p12")

    result = relate_cohorts(diabetes, income, n=3, step_id="s2")
    metrics = _extract_metrics(result)
    assert result.step_id == "s2"
    assert result.variables == (
        "Percent_Person_WithDiabetes",
        "Median_Income_Household",
    )
    assert metrics.shared_place_count == 9
    assert metrics.target_only_place_count == 1
    assert metrics.by_only_place_count == 3
    assert metrics.group_size == 3
    assert _collect_place_dcids(metrics.highest_by) == ["p01", "p02", "p03"]
    assert _collect_place_dcids(metrics.lowest_by) == ["p09", "p08", "p07"]
    assert metrics.highest_by[0] == RelationEntry(
        rank=1,
        is_tied=False,
        place_dcid="p01",
        place_name="P01",
        by_value=12.0,
        target_value=1.0,
    )
    assert metrics.highest_by_summary == GroupSummary(
        count=3, target_mean=2.0, target_median=2.0
    )
    assert metrics.lowest_by_summary == GroupSummary(
        count=3, target_mean=8.0, target_median=8.0
    )
    assert metrics.target_mean_difference == -6.0
    assert (
        metrics.target_contributing_places,
        metrics.target_requested_places,
        metrics.by_contributing_places,
        metrics.by_requested_places,
    ) == (10, 10, 12, 12)
    assert (
        "Only places with a value for both variables are compared: 1 place "
        "with a value for Diabetes prevalence has no value for Median income "
        "on 2022 (X99); 3 places with a value for Median income have no value "
        "for Diabetes prevalence on 2022 (P10, P11, and P12)."
    ) in result.caveats
    assert result.provenance.sources == (_HEALTH_SOURCE, _INCOME_SOURCE)


def test_more_than_five_dropped_places_are_truncated_with_count() -> None:
    # Test: Truncation of dropped-place lists via `format_place_names`.
    # Situation: Income covers 14 places (p01 to p14) and diabetes covers
    #   p01 to p08, leaving 6 places in `by_only_places`.
    # Expectation: The dropped-places caveat lists the first 5 places and
    #   states "and 1 other place".
    income = _build_income_table(
        {f"p{index:02d}": float(index) for index in range(1, 15)}
    )
    diabetes = _build_diabetes_table(
        {f"p{index:02d}": float(index) for index in range(1, 9)}
    )

    result = relate_cohorts(diabetes, income, n=2)
    assert (
        "Only places with a value for both variables are compared: 6 places "
        "with a value for Median income have no value for Diabetes prevalence "
        "on 2022 (P09, P10, P11, P12, P13, and 1 other place)."
    ) in result.caveats


def test_each_cohort_is_aligned_on_its_own_reference_date() -> None:
    # Test: Two cohorts whose latest dates and precisions differ.
    # Situation: Diabetes reports 2021 and income reports 2023-06, and
    #   income covers five places of which diabetes covers four.
    # Expectation: Each side keeps its own reference date in the metrics, a
    #   caveat states both dates, and the dropped-place clause names the
    #   date of the variable the place lacks.
    income = _build_income_table(
        {"a": 5.0, "b": 4.0, "c": 3.0, "d": 2.0, "e": 1.0}, date="2023-06"
    )
    diabetes = _build_diabetes_table(
        {"a": 1.0, "b": 2.0, "c": 3.0, "d": 4.0}, date="2021"
    )

    result = relate_cohorts(diabetes, income, n=2)
    metrics = _extract_metrics(result)
    assert metrics.target_reference_date == "2021"
    assert metrics.by_reference_date == "2023-06"
    assert (
        "Diabetes prevalence is compared on 2021 and Median income on "
        "2023-06, the reference date of each cohort."
    ) in result.caveats
    assert (
        "Only places with a value for both variables are compared: 1 place "
        "with a value for Median income has no value for Diabetes prevalence "
        "on 2021 (E)."
    ) in result.caveats


def test_a_tie_at_the_cut_off_is_resolved_by_dcid() -> None:
    # Test: Tied `by` values straddling the group cut-off.
    # Situation: Income is 10, 8, 8, 8, 2, 1 for places a to f, and the
    #   groups hold two places each.
    # Expectation: The highest group lists a and b, with b marked tied at
    #   rank 2 and c and d left out by DCID order; the lowest group lists f
    #   then e; and each group's mean and median cover the listed entries.
    income = _build_income_table(
        {"a": 10.0, "b": 8.0, "c": 8.0, "d": 8.0, "e": 2.0, "f": 1.0}
    )
    diabetes = _build_diabetes_table(
        {"a": 100.0, "b": 50.0, "c": 0.0, "d": 0.0, "e": 10.0, "f": 20.0}
    )

    metrics = _extract_metrics(relate_cohorts(diabetes, income, n=2))
    assert [
        (entry.place_dcid, entry.rank, entry.is_tied)
        for entry in metrics.highest_by
    ] == [
        ("a", 1, False),
        ("b", 2, True),
    ]
    assert [(entry.place_dcid, entry.rank) for entry in metrics.lowest_by] == [
        ("f", 6),
        ("e", 5),
    ]
    assert metrics.highest_by_summary == GroupSummary(
        count=2, target_mean=75.0, target_median=75.0
    )
    assert metrics.lowest_by_summary == GroupSummary(
        count=2, target_mean=15.0, target_median=15.0
    )
    assert metrics.target_mean_difference == 60.0


def test_a_tie_across_the_middle_never_puts_a_place_in_both_groups() -> None:
    # Test: Tied `by` values that span both group cut-offs.
    # Situation: Income is 10, 5, 5, 1 for places a to d, with `n=10`, so
    #   each group holds two places and the tie at 5 sits on both cuts.
    # Expectation: The highest group is a then b and the lowest group is d
    #   then c: the groups are disjoint and together list all four places.
    income = _build_income_table({"a": 10.0, "b": 5.0, "c": 5.0, "d": 1.0})
    diabetes = _build_diabetes_table({"a": 1.0, "b": 2.0, "c": 3.0, "d": 4.0})

    metrics = _extract_metrics(relate_cohorts(diabetes, income, n=10))

    assert _collect_place_dcids(metrics.highest_by) == ["a", "b"]
    assert _collect_place_dcids(metrics.lowest_by) == ["d", "c"]
    assert [entry.is_tied for entry in metrics.lowest_by] == [False, True]


def test_a_tie_at_the_lowest_cut_off_follows_rank_cohort() -> None:
    # Test: Tie order in the lowest group.
    # Situation: Income is 4, 3, 1, 1 for places a to d, with `n=1`, so the
    #   lowest group holds one of the two places tied at 1.
    # Expectation: The lowest group is c, the place `rank_cohort` lists
    #   first among its lowest values, because ties are ordered by
    #   ascending DCID.
    income = _build_income_table({"a": 4.0, "b": 3.0, "c": 1.0, "d": 1.0})
    diabetes = _build_diabetes_table({"a": 1.0, "b": 2.0, "c": 3.0, "d": 4.0})

    metrics = _extract_metrics(relate_cohorts(diabetes, income, n=1))

    assert _collect_place_dcids(metrics.highest_by) == ["a"]
    assert _collect_place_dcids(metrics.lowest_by) == ["c"]
    assert metrics.lowest_by[0].is_tied


def test_groups_are_capped_at_half_the_shared_places() -> None:
    # Test: A group size larger than half the shared places.
    # Situation: Twelve shared places and `n=10`.
    # Expectation: Each group holds six places, the two groups share no
    #   place, and a caveat says why the groups are smaller than asked.
    values = {f"p{index:02d}": float(index) for index in range(12)}
    result = relate_cohorts(
        _build_diabetes_table(values), _build_income_table(values), n=10
    )
    metrics = _extract_metrics(result)
    assert metrics.n == 10
    assert metrics.group_size == 6
    assert len(metrics.highest_by) == len(metrics.lowest_by) == 6
    assert not set(_collect_place_dcids(metrics.highest_by)) & set(
        _collect_place_dcids(metrics.lowest_by)
    )
    assert (
        "Each group holds 6 places instead of 10, at most half of the 12 "
        "shared places, so that the two groups do not overlap."
    ) in result.caveats


def test_fewer_than_two_shared_places_refuses_and_keeps_caveats() -> None:
    # Test: A pair that shares a single place after partial alignment.
    # Situation: Diabetes requests a and b and reports only a; income
    #   requests a and c and reports only a.
    # Expectation: The result is refused with `invalid_parameters`, names
    #   both variables, preserves both sides' alignment caveats ahead of the
    #   refusal caveat, and carries no metrics.
    diabetes = _build_diabetes_table({"a": 1.0}, requested_places=["a", "b"])
    income = _build_income_table({"a": 2.0}, requested_places=["a", "c"])
    result = relate_cohorts(diabetes, income)
    assert result.status == "refused"
    assert result.refusal_reason == "invalid_parameters"
    assert result.metrics is None
    assert result.variables == (
        "Percent_Person_WithDiabetes",
        "Median_Income_Household",
    )
    assert result.caveats == (
        "1 of 2 places on 2022 reported a value for Diabetes prevalence.",
        "1 of 2 places on 2022 reported a value for Median income.",
        "Only 1 place has a value for both Diabetes prevalence on 2022 and "
        "Median income on 2022; two groups need at least 2.",
    )


@pytest.mark.parametrize(
    "invalid_n",
    [0, -3, True, False],
    ids=["zero", "negative", "bool_true", "bool_false"],
)
def test_an_invalid_group_size_refuses(invalid_n: int) -> None:
    # Test: Invalid group sizes (`0`, negative, and boolean).
    # Situation: `relate_cohorts` called with `n` set to `invalid_n`.
    # Expectation: Each call is refused with `invalid_parameters`.
    values = {"a": 1.0, "b": 2.0}
    result = relate_cohorts(
        _build_diabetes_table(values),
        _build_income_table(values),
        n=invalid_n,
    )
    assert result.status == "refused"
    assert result.refusal_reason == "invalid_parameters"
    assert "group size must be an integer of at least 1" in result.caveats[-1]


@pytest.mark.parametrize(
    "invalid_coverage",
    [-0.1, 1.5, True, float("nan")],
    ids=["negative", "above_one", "boolean", "nan"],
)
def test_an_invalid_min_coverage_refuses(invalid_coverage: float) -> None:
    # Test: Invalid `min_coverage` values in `pair_cohorts` and
    #   `relate_cohorts`.
    # Situation: `min_coverage` is negative, above 1, a boolean, or NaN.
    # Expectation: `pair_cohorts` returns a `PairingRefusal` with
    #   `invalid_parameters`, and `relate_cohorts` returns a matching refused
    #   `ScriptResult`.
    values = {"a": 1.0, "b": 2.0}
    diabetes = _build_diabetes_table(values)
    income = _build_income_table(values)
    paired = pair_cohorts(diabetes, income, min_coverage=invalid_coverage)
    assert isinstance(paired, PairingRefusal)
    assert paired.reason == "invalid_parameters"
    result = relate_cohorts(diabetes, income, min_coverage=invalid_coverage)
    assert result.refusal_reason == "invalid_parameters"
    assert result.caveats == paired.caveats


def test_identical_variables_refuse_and_deduplicate_variable_names() -> None:
    # Test: Passing the same variable DCID as both `target` and `by`.
    # Situation: Both inputs measure `Percent_Person_WithDiabetes`, with
    #   different display names on the two tables.
    # Expectation: Both `pair_cohorts` and `relate_cohorts` refuse with
    #   `invalid_parameters`, deduplicating `result.variables` and keeping
    #   the `target` input's display name.
    values = {"a": 1.0, "b": 2.0, "c": 3.0, "d": 4.0}
    first = _build_table(
        ("Percent_Person_WithDiabetes", "Diabetes prevalence (CDC)"),
        [(place, "2022", value) for place, value in values.items()],
    )
    second = _build_table(
        ("Percent_Person_WithDiabetes", "Diabetes rate (alternate)"),
        [(place, "2022", value) for place, value in values.items()],
    )
    paired = pair_cohorts(first, second)
    assert isinstance(paired, PairingRefusal)
    assert paired.reason == "invalid_parameters"
    assert "must be different variables" in paired.caveats[-1]

    result = relate_cohorts(first, second)
    assert result.status == "refused"
    assert result.refusal_reason == "invalid_parameters"
    assert result.variables == ("Percent_Person_WithDiabetes",)
    assert result.variable_names == {
        "Percent_Person_WithDiabetes": "Diabetes prevalence (CDC)"
    }


@pytest.mark.parametrize(
    ("shared_count", "has_sufficient_coverage"),
    [(1, False), (4, False), (6, True)],
    ids=["single_shared_place", "fails_on_larger_side", "passes_on_both"],
)
def test_the_coverage_check_is_symmetric(
    shared_count: int, has_sufficient_coverage: bool
) -> None:
    # Test: Coverage of the join in both argument orders.
    # Situation: One cohort covers ten places and the other covers
    #   `shared_count` of them, against the default 50% coverage.
    # Expectation: One or four shared places refuse with
    #   `insufficient_coverage` in both orders (using singular "has" for 1
    #   and plural "have" for 4), and six pass in both.
    large = _build_diabetes_table(
        {f"p{index}": float(index) for index in range(10)}
    )
    small = _build_income_table(
        {f"p{index}": float(index) for index in range(shared_count)}
    )
    for target, by in ((large, small), (small, large)):
        result = relate_cohorts(target, by, n=2)
        if has_sufficient_coverage:
            assert result.status == "ok"
        else:
            assert result.refusal_reason == "insufficient_coverage"
            paired = pair_cohorts(target, by)
            assert isinstance(paired, PairingRefusal)
            assert paired.side is None
            expected_verb = (
                "also has a value"
                if shared_count == 1
                else ("also have a value")
            )
            assert expected_verb in paired.caveats[-1]


@pytest.mark.parametrize(
    ("target", "by", "target_date", "reason", "side"),
    [
        (
            _build_diabetes_table({"a": 1.0, "b": 2.0}),
            _build_income_table({"a": 1.0, "b": 2.0}),
            "last year",
            "invalid_parameters",
            "target",
        ),
        (
            _build_diabetes_table({"a": 1.0, "b": 2.0}),
            _build_table(
                ("Median_Income_Household", "Median income"),
                [("a", "2022", 1.0)],
                requested_places=["a", "b", "c", "d"],
            ),
            None,
            "insufficient_coverage",
            "by",
        ),
        (
            _build_diabetes_table({"a": 1.0, "b": 2.0}),
            _build_table(
                ("Median_Income_Household", "Median income"),
                [],
                requested_places=["a"],
            ),
            None,
            "no_observations",
            "by",
        ),
        (
            _build_diabetes_table({"a": 1.0, "b": 2.0}),
            _build_income_table({"c": 1.0, "d": 2.0}),
            None,
            "no_observations",
            None,
        ),
    ],
    ids=[
        "invalid_date",
        "by_alignment_coverage",
        "by_alignment_empty",
        "no_shared_place",
    ],
)
def test_pair_cohorts_returns_a_pairing_refusal(
    target: ObservationTable,
    by: ObservationTable,
    target_date: str | None,
    reason: str,
    side: str | None,
) -> None:
    # Test: Every refusal path of `pair_cohorts`.
    # Situation: An invalid target date, a `by` table that cannot be
    #   aligned for coverage or for lack of rows, and two cohorts with no
    #   place in common.
    # Expectation: Each returns a `PairingRefusal`, never a `ScriptResult`,
    #   with the reason, the side that failed (none for the join), a caveat,
    #   and the alignment's coverage when an alignment refused;
    #   `relate_cohorts` turns it into its own refused result with the same
    #   reason, caveats, and coverage.
    paired = pair_cohorts(target, by, target_date=target_date)
    assert isinstance(paired, PairingRefusal)
    assert paired.reason == reason
    assert paired.side == side
    assert paired.caveats
    assert (paired.coverage is not None) == (side == "by")
    result = relate_cohorts(target, by, target_date=target_date)
    assert result.script == "relate_cohorts"
    assert result.refusal_reason == reason
    assert result.caveats == paired.caveats
    assert result.coverage == paired.coverage


def test_aligned_cohort_accepts_matching_date_and_refuses_mismatch() -> None:
    # Test: Passing an `AlignedCohort` with matching, mismatched, and
    #   malformed dates.
    # Situation: `target` is pre-aligned to 2022 with a partial-coverage
    #   caveat; it is paired with no `target_date`, with `target_date="2022"`,
    #   with `target_date="2020"`, and with `target_date="not-a-date"`.
    # Expectation: Omitting `target_date` or passing `"2022"` uses the
    #   aligned cohort as-is; passing `"2020"` or `"not-a-date"` refuses with
    #   `invalid_parameters`, preserving the aligned cohort's coverage and
    #   caveat.
    diabetes = _build_diabetes_table(
        {"a": 1.0, "b": 2.0, "c": 3.0},
        requested_places=["a", "b", "c", "d"],
    )
    aligned = align_cohort(diabetes)
    assert isinstance(aligned, AlignedCohort)
    income = _build_income_table(
        {"a": 10.0, "b": 20.0, "c": 30.0, "d": 40.0},
        requested_places=["a", "b", "c", "d"],
    )

    for matching_date in (None, "2022"):
        paired = pair_cohorts(aligned, income, target_date=matching_date)
        assert isinstance(paired, PairedCohort)
        assert paired.target is aligned

    for bad_date in ("2020", "not-a-date"):
        refused_pair = pair_cohorts(aligned, income, target_date=bad_date)
        assert isinstance(refused_pair, PairingRefusal)
        assert refused_pair.reason == "invalid_parameters"
        assert refused_pair.side == "target"
        assert refused_pair.coverage == aligned.coverage
        assert refused_pair.caveats[0] == aligned.caveats[0]

        refused_result = relate_cohorts(aligned, income, target_date=bad_date)
        assert refused_result.refusal_reason == "invalid_parameters"
        assert refused_result.coverage == aligned.coverage
        assert refused_result.caveats == refused_pair.caveats

    disjoint_income_table = _build_income_table(
        {"e": 10.0, "f": 20.0},
        requested_places=["e", "f", "g"],
    )
    mixed_refused_pair = pair_cohorts(disjoint_income_table, aligned)
    assert isinstance(mixed_refused_pair, PairingRefusal)
    mixed_refused_result = relate_cohorts(disjoint_income_table, aligned)
    assert mixed_refused_result.caveats == mixed_refused_pair.caveats
    assert "Median income" in mixed_refused_result.caveats[0]
    assert "Diabetes prevalence" in mixed_refused_result.caveats[1]


def test_missing_requested_places_and_names_fall_back_to_other_input() -> None:
    # Test: Fallbacks between `target` and `by` for `requested_places` and
    #   place display names.
    # Situation: `target` omits `requested_places` and has raw DCIDs as its
    #   place names for `a` and `b`, while `by` specifies
    #   `requested_places=["a", "b", "c", "d"]` and human-readable names (both
    #   as an `ObservationTable` and as a pre-aligned `AlignedCohort`); then
    #   the roles are reversed so `by` omits `requested_places`.
    # Expectation: When `target` omits `requested_places`, it inherits `by`'s
    #   four requested places (`target_requested_places == 4`) whether `by` is
    #   an `ObservationTable` or an `AlignedCohort`, and falls back to `by`'s
    #   display names; when `by` omits `requested_places`, it inherits
    #   `target`'s four requested places (`by_requested_places == 4`).
    diabetes_no_requested = _build_diabetes_table(
        {"a": 1.0, "b": 2.0, "c": 3.0},
        requested_places=(),
        place_names={"a": "a", "b": "b", "c": "County C"},
    )
    income_with_requested = _build_income_table(
        {"a": 40.0, "b": 30.0, "c": 20.0, "d": 10.0},
        requested_places=["a", "b", "c", "d"],
        place_names={
            "a": "County A",
            "b": "County B",
            "c": "Income C",
            "d": "County D",
        },
    )

    result = relate_cohorts(diabetes_no_requested, income_with_requested, n=1)
    metrics = _extract_metrics(result)
    assert metrics.target_contributing_places == 3
    assert metrics.target_requested_places == 4
    assert metrics.by_contributing_places == 4
    assert metrics.by_requested_places == 4
    assert metrics.highest_by[0].place_name == "County A"
    assert metrics.lowest_by[0].place_name == "County C"
    assert (
        "3 of 4 places on 2022 reported a value for Diabetes prevalence."
    ) in result.caveats

    aligned_income = align_cohort(income_with_requested)
    assert isinstance(aligned_income, AlignedCohort)
    aligned_fallback_result = relate_cohorts(
        diabetes_no_requested, aligned_income, n=1
    )
    aligned_fallback_metrics = _extract_metrics(aligned_fallback_result)
    assert aligned_fallback_metrics.target_contributing_places == 3
    assert aligned_fallback_metrics.target_requested_places == 4

    reversed_result = relate_cohorts(
        income_with_requested, diabetes_no_requested, n=1
    )
    reversed_metrics = _extract_metrics(reversed_result)
    assert reversed_metrics.by_contributing_places == 3
    assert reversed_metrics.by_requested_places == 4
    assert reversed_metrics.highest_by[0].place_name == "Income C"


def test_non_finite_summaries_and_differences_report_none_with_caveat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Non-finite summary and difference guards (`math.isfinite`).
    # Situation: First, `highest_by` has `[1e308, 1e308]` and `lowest_by`
    #   has `[-1e308, -1e308]`, so `statistics.fmean` and `statistics.median`
    #   overflow on both groups; second, with `n=1` on `[1e308]` vs
    #   `[-1e308]`, each single-place group mean is finite (`1e308` and
    #   `-1e308`), while `target_mean_difference` (`1e308 - (-1e308)`)
    #   overflows; third, `statistics.fmean` is monkeypatched to return
    #   `inf`.
    # Expectation: Overflowing medians, means, and mean differences are
    #   reported as `None` (never `inf`, `-inf`, or `OverflowError`), and a
    #   caveat explains that summary statistics exceeded the floating-point
    #   range.
    income = _build_income_table({"a": 40.0, "b": 30.0, "c": 20.0, "d": 10.0})
    extreme_diabetes = _build_diabetes_table(
        {"a": 1e308, "b": 1e308, "c": -1e308, "d": -1e308}
    )
    result = relate_cohorts(extreme_diabetes, income, n=2)
    metrics = _extract_metrics(result)
    assert metrics.highest_by_summary.target_mean is None
    assert metrics.highest_by_summary.target_median is None
    assert metrics.lowest_by_summary.target_mean is None
    assert metrics.lowest_by_summary.target_median is None
    assert metrics.target_mean_difference is None
    assert (
        "Some summary statistics for Diabetes prevalence exceeded the "
        "floating-point range and are reported as None."
    ) in result.caveats

    diff_overflow = relate_cohorts(extreme_diabetes, income, n=1)
    diff_metrics = _extract_metrics(diff_overflow)
    assert diff_metrics.highest_by_summary.target_mean == 1e308
    assert diff_metrics.lowest_by_summary.target_mean == -1e308
    assert diff_metrics.target_mean_difference is None

    monkeypatch.setattr(statistics, "fmean", lambda _: float("inf"))
    mean_overflow = relate_cohorts(
        _build_diabetes_table({"a": 1.0, "b": 2.0, "c": 3.0, "d": 4.0}),
        income,
        n=2,
    )
    mean_metrics = _extract_metrics(mean_overflow)
    assert mean_metrics.highest_by_summary.target_mean is None
    assert mean_metrics.lowest_by_summary.target_mean is None
    assert mean_metrics.target_mean_difference is None


def test_helper_preconditions_raise_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Documented preconditions on dataclasses and private helpers.
    # Situation: Invalid values passed to `PairedPlace`, `PairedCohort`,
    #   `_rank_shared_places`, `_select_group_entries`,
    #   `_compute_finite_mean`, `_compute_finite_median`, `_summarize_group`,
    #   and `_describe_dropped_places`, plus an unexpected `rank_cohort`
    #   refusal in `_rank_shared_places`.
    # Expectation: Each violated precondition raises `ValueError`, and an
    #   unexpected ranking refusal raises `RuntimeError`.
    with pytest.raises(ValueError, match="target_value must be a finite"):
        PairedPlace("a", "A", float("inf"), 1.0)
    with pytest.raises(ValueError, match="by_value must be a finite"):
        PairedPlace("a", "A", 1.0, True)
    with pytest.raises(ValueError, match="at least one caveat"):
        PairingRefusal(reason="no_observations", caveats=())

    values = {"a": 1.0, "b": 2.0}
    aligned_target = align_cohort(_build_diabetes_table(values))
    aligned_by = align_cohort(_build_income_table(values))
    assert isinstance(aligned_target, AlignedCohort)
    assert isinstance(aligned_by, AlignedCohort)

    with pytest.raises(ValueError, match="at least one shared place"):
        PairedCohort(
            target=aligned_target,
            by=aligned_by,
            places=(),
            target_only_places=(),
            by_only_places=(),
            provenance=aligned_target.provenance,
        )

    one_place_pair = PairedCohort(
        target=aligned_target,
        by=aligned_by,
        places=(PairedPlace("a", "A", 1.0, 2.0),),
        target_only_places=("b",),
        by_only_places=("b",),
        provenance=aligned_target.provenance,
    )
    with pytest.raises(ValueError, match="At least 2 shared places"):
        _rank_shared_places(one_place_pair, step_id="s1")

    paired = pair_cohorts(aligned_target, aligned_by)
    assert isinstance(paired, PairedCohort)
    ranking = _rank_shared_places(paired, step_id="s1")

    with pytest.raises(ValueError, match="group size must be at least 1"):
        _select_group_entries(ranking, group_size=0)
    with pytest.raises(ValueError, match="require at least 4 ranked places"):
        _select_group_entries(ranking, group_size=2)

    with pytest.raises(ValueError, match="empty sequence"):
        _compute_finite_mean([])
    with pytest.raises(ValueError, match="empty sequence"):
        _compute_finite_median([])

    with pytest.raises(ValueError, match="at least one entry"):
        _summarize_group((), {"a": PairedPlace("a", "A", 1.0, 2.0)})
    with pytest.raises(ValueError, match="missing from paired cohort"):
        _summarize_group(
            (
                RankEntry(
                    rank=1,
                    is_tied=False,
                    place_dcid="b",
                    place_name="B",
                    value=2.0,
                    percentile=100.0,
                ),
            ),
            {"a": PairedPlace("a", "A", 1.0, 2.0)},
        )

    with pytest.raises(ValueError, match="dropped must not be empty"):
        _describe_dropped_places(aligned_target, aligned_by, (), {})

    monkeypatch.setattr(
        relations,
        "rank_cohort",
        lambda *_, **__: RefusedScriptResult(
            step_id="s1",
            script="rank_cohort",
            refusal_reason="no_observations",
            variables=("Median_Income_Household",),
            variable_names={"Median_Income_Household": "Median income"},
            unit="USDollar",
            scaling_factor=None,
            coverage=None,
            provenance=aligned_by.provenance,
            caveats=("Forced refusal.",),
        ),
    )
    with pytest.raises(RuntimeError, match="refused unexpectedly"):
        _rank_shared_places(paired, step_id="s1")


def test_decomposed_helpers_validate_align_resolve_and_summarize() -> None:
    # Test: Direct unit tests for the decomposed helper functions.
    # Situation: Valid and invalid calls to `_validate_pairing_parameters`,
    #   `_align_cohort_side`, `_resolve_table_requested_places`,
    #   `_resolve_place_names`, and `_compute_mean_difference`.
    # Expectation: Each helper returns the expected typed value.
    diabetes = _build_diabetes_table(
        {"a": 1.0, "b": 2.0},
        place_names={"a": "a", "b": "Target Bravo"},
    )
    income = _build_income_table(
        {"a": 10.0, "b": 20.0},
        requested_places=["a", "b"],
        place_names={"a": "Alpha", "b": "Bravo"},
    )
    assert (
        _validate_pairing_parameters(diabetes, income, min_coverage=0.5) is None
    )
    resolved_table = _resolve_table_requested_places(diabetes, income)
    assert resolved_table.requested_places == ("a", "b")

    names = _resolve_place_names(diabetes, income)
    assert names == {"a": "Alpha", "b": "Target Bravo"}
    preserved = _resolve_place_names(
        replace(income, place_names={"a": "a", "b": "Bravo"}),
        diabetes,
    )
    assert preserved == {"a": "Alpha", "b": "Bravo"}

    aligned_side = _align_cohort_side(
        diabetes,
        income,
        date="2022",
        min_coverage=0.5,
        side="target",
    )
    assert isinstance(aligned_side, AlignedCohort)
    assert (
        _compute_mean_difference(
            GroupSummary(count=1, target_mean=15.0, target_median=15.0),
            GroupSummary(count=1, target_mean=5.0, target_median=5.0),
        )
        == 10.0
    )


def test_units_and_scaling_factors_are_carried_through() -> None:
    # Test: Units and scaling factors of both cohorts.
    # Situation: Diabetes is in Percent with no scaling factor and income
    #   is in USDollar with a scaling factor of 500.
    # Expectation: The metrics report each side's unit and scaling factor,
    #   and the result's unit and scaling factor are the target's, the unit
    #   of the group means and their difference.
    values = {"a": 1.0, "b": 2.0, "c": 3.0, "d": 4.0}
    result = relate_cohorts(
        _build_diabetes_table(values),
        _build_income_table(values, scaling_factor=500.0),
        n=2,
    )
    metrics = _extract_metrics(result)
    assert (metrics.target_unit, metrics.target_scaling_factor) == (
        "Percent",
        None,
    )
    assert (metrics.by_unit, metrics.by_scaling_factor) == (
        "USDollar",
        500.0,
    )
    assert (result.unit, result.scaling_factor) == ("Percent", None)


def test_the_digest_renders_the_relation_for_the_prompt() -> None:
    # Test: Prompt rendering of a relation result.
    # Situation: A digest holding one `relate_cohorts` result.
    # Expectation: The block names the script and both variables, renders
    #   the groups and their summaries, and states the methodology.
    values = {"a": 1.0, "b": 2.0, "c": 3.0, "d": 4.0}
    result = relate_cohorts(
        _build_diabetes_table(values), _build_income_table(values), n=1
    )
    text = AnalysisDigest.from_results((result,)).format_for_prompt()
    assert text.startswith(
        "Step s1: relate_cohorts on Diabetes prevalence "
        "(Percent_Person_WithDiabetes), Median income (Median_Income_Household)"
    )
    assert '"highest_by":[{"rank":1,"is_tied":false,"place_dcid":"d"' in text
    assert '"lowest_by_summary":{"count":1,"target_mean":1' in text
    assert '"target_mean_difference":3' in text
    assert "method: Paired the 4 places with a value for both" in text


@dataclass(frozen=True)
class _GeneratedRelationCase:
    """One deterministic case for the brute-force relation invariant tests."""

    target_table: ObservationTable
    by_table: ObservationTable
    target_values: dict[str, float]
    by_values: dict[str, float]
    target_date: str
    by_date: str
    n: int
    min_coverage: float
    result: ScriptResult


def _generate_relation_cases() -> list[_GeneratedRelationCase]:
    """Generates deterministic cases across sizes, ties, drops, and dates."""
    by_patterns: dict[str, tuple[float, ...]] = {
        "distinct": (70.0, 60.0, 50.0, 40.0, 30.0, 20.0, 10.0),
        "tie_top": (70.0, 60.0, 60.0, 60.0, 30.0, 20.0, 10.0),
        "tie_bottom": (70.0, 60.0, 50.0, 20.0, 20.0, 20.0, 10.0),
        "tie_middle": (70.0, 40.0, 40.0, 40.0, 40.0, 20.0, 10.0),
        "all_equal": (50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0),
    }
    cases: list[_GeneratedRelationCase] = []
    for shared_count in (0, 1, 2, 3, 4, 5, 6, 7):
        for extra_target, extra_by in ((0, 0), (1, 0), (0, 2), (1, 2)):
            if shared_count == 0 and (extra_target == 0 or extra_by == 0):
                continue
            for pattern_name, pattern in by_patterns.items():
                if shared_count < 2 and pattern_name != "distinct":
                    continue
                shared_places = [
                    f"p{index:02d}" for index in range(shared_count)
                ]
                target_only = [f"t{index:02d}" for index in range(extra_target)]
                by_only = [f"b{index:02d}" for index in range(extra_by)]
                target_values = {
                    **{
                        place: float((index + 1) * 3)
                        for index, place in enumerate(shared_places)
                    },
                    **{
                        place: float((index + 1) * 11)
                        for index, place in enumerate(target_only)
                    },
                }
                by_values = {
                    **{
                        place: pattern[index]
                        for index, place in enumerate(shared_places)
                    },
                    **{
                        place: float((index + 1) * 7)
                        for index, place in enumerate(by_only)
                    },
                }
                for target_date, by_date in (
                    ("2022", "2022"),
                    ("2021", "2023"),
                ):
                    if target_date != by_date and pattern_name not in (
                        "distinct",
                        "tie_middle",
                    ):
                        continue
                    target_table = _build_diabetes_table(
                        target_values, date=target_date
                    )
                    by_table = _build_income_table(by_values, date=by_date)
                    for n in (1, 2, 3):
                        for min_coverage in (0.5, 0.85):
                            cases.append(
                                _GeneratedRelationCase(
                                    target_table=target_table,
                                    by_table=by_table,
                                    target_values=target_values,
                                    by_values=by_values,
                                    target_date=target_date,
                                    by_date=by_date,
                                    n=n,
                                    min_coverage=min_coverage,
                                    result=relate_cohorts(
                                        target_table,
                                        by_table,
                                        n=n,
                                        min_coverage=min_coverage,
                                    ),
                                )
                            )
    return cases


def _compute_expected_groups(
    case: _GeneratedRelationCase,
) -> tuple[list[str], list[str]]:
    """Computes the expected highest and lowest place lists from scratch."""
    shared_places = sorted(case.target_values.keys() & case.by_values.keys())
    group_size = min(case.n, len(shared_places) // 2)
    descending = sorted(
        shared_places, key=lambda place: (-case.by_values[place], place)
    )
    ascending = sorted(
        shared_places, key=lambda place: (case.by_values[place], place)
    )
    highest = descending[:group_size]
    highest_set = set(highest)
    lowest = [place for place in ascending if place not in highest_set][
        :group_size
    ]
    return highest, lowest


def _compute_expected_summary(
    places: Sequence[str], target_values: Mapping[str, float]
) -> tuple[float, float]:
    """Computes the exact mean and median of `target_values` over `places`."""
    ordered = sorted(target_values[place] for place in places)
    count = len(ordered)
    mean = sum(ordered) / count
    middle = count // 2
    median = (
        ordered[middle]
        if count % 2 == 1
        else (ordered[middle - 1] + ordered[middle]) / 2.0
    )
    return mean, median


def _assert_entry_matches_shared_cohort(
    entry: RelationEntry,
    shared_by_values: Mapping[str, float],
    target_values: Mapping[str, float],
) -> None:
    """Checks one `RelationEntry` against the shared places' values."""
    expected_by = shared_by_values[entry.place_dcid]
    expected_target = target_values[entry.place_dcid]
    all_by = list(shared_by_values.values())
    strictly_greater = sum(1 for value in all_by if value > expected_by)
    equal_count = sum(1 for value in all_by if value == expected_by)
    assert entry.by_value == expected_by
    assert entry.target_value == expected_target
    assert entry.rank == strictly_greater + 1
    assert entry.is_tied == (equal_count > 1)


def test_generated_relations_refuse_or_succeed_by_coverage_and_size() -> None:
    # Test: Refusal vs success across every generated case.
    # Situation: Deterministic combinations of shared counts (0 to 7),
    #   dropped places on each side, `n` (1 to 3), and `min_coverage` (0.5
    #   and 0.85).
    # Expectation: 0 shared places refuse with `no_observations`; coverage
    #   below `min_coverage` on either side refuses with
    #   `insufficient_coverage`; 1 shared place that passes coverage refuses
    #   with `invalid_parameters`; and 2 or more shared places with adequate
    #   coverage succeed.
    cases = _generate_relation_cases()
    assert cases
    for case in cases:
        shared = len(case.target_values.keys() & case.by_values.keys())
        target_ratio = shared / len(case.target_values)
        by_ratio = shared / len(case.by_values)
        if shared == 0:
            assert case.result.status == "refused"
            assert case.result.refusal_reason == "no_observations"
        elif target_ratio < case.min_coverage or by_ratio < case.min_coverage:
            assert case.result.status == "refused"
            assert case.result.refusal_reason == "insufficient_coverage"
        elif shared < 2:
            assert case.result.status == "refused"
            assert case.result.refusal_reason == "invalid_parameters"
        else:
            assert case.result.status == "ok"


def test_generated_relations_match_rank_cohort_and_never_overlap() -> None:
    # Test: Group membership, ordering, ranks, ties, and disjointness.
    # Situation: Every `ok` case from `_generate_relation_cases`.
    # Expectation: `group_size == min(n, shared // 2)`, `highest_by` and
    #   `lowest_by` are disjoint, and every entry's place, rank, and tie flag
    #   match the independent oracle over the shared places.
    for case in _generate_relation_cases():
        if case.result.status != "ok":
            continue
        metrics = _extract_metrics(case.result)
        shared_places = case.target_values.keys() & case.by_values.keys()
        expected_highest, expected_lowest = _compute_expected_groups(case)
        assert metrics.group_size == min(case.n, len(shared_places) // 2)
        assert _collect_place_dcids(metrics.highest_by) == expected_highest
        assert _collect_place_dcids(metrics.lowest_by) == expected_lowest
        assert not (set(expected_highest) & set(expected_lowest))
        shared_by = {place: case.by_values[place] for place in shared_places}
        for entry in (*metrics.highest_by, *metrics.lowest_by):
            _assert_entry_matches_shared_cohort(
                entry, shared_by, case.target_values
            )


def test_generated_relations_report_group_summaries_and_differences() -> None:
    # Test: Group means, medians, and mean differences across generated cases.
    # Situation: Every `ok` case from `_generate_relation_cases`.
    # Expectation: Each group's count, mean, and median and
    #   `target_mean_difference` match the independent oracle.
    for case in _generate_relation_cases():
        if case.result.status != "ok":
            continue
        metrics = _extract_metrics(case.result)
        expected_highest, expected_lowest = _compute_expected_groups(case)
        high_mean, high_median = _compute_expected_summary(
            expected_highest, case.target_values
        )
        low_mean, low_median = _compute_expected_summary(
            expected_lowest, case.target_values
        )
        assert metrics.highest_by_summary.count == len(expected_highest)
        assert metrics.highest_by_summary.target_mean == pytest.approx(
            high_mean
        )
        assert metrics.highest_by_summary.target_median == pytest.approx(
            high_median
        )
        assert metrics.lowest_by_summary.count == len(expected_lowest)
        assert metrics.lowest_by_summary.target_mean == pytest.approx(low_mean)
        assert metrics.lowest_by_summary.target_median == pytest.approx(
            low_median
        )
        assert metrics.target_mean_difference == pytest.approx(
            high_mean - low_mean
        )


def test_generated_relations_report_date_drop_and_cap_caveats() -> None:
    # Test: Date-mismatch, dropped-place, and group-size-cap caveats.
    # Situation: Every `ok` case from `_generate_relation_cases`.
    # Expectation: Each caveat is present if and only if its condition holds.
    for case in _generate_relation_cases():
        if case.result.status != "ok":
            continue
        metrics = _extract_metrics(case.result)
        has_date_caveat = any(
            "the reference date of each cohort" in caveat
            for caveat in case.result.caveats
        )
        has_drop_caveat = any(
            "Only places with a value for both variables are compared" in caveat
            for caveat in case.result.caveats
        )
        has_cap_caveat = any(
            "so that the two groups do not overlap" in caveat
            for caveat in case.result.caveats
        )
        assert has_date_caveat == (case.target_date != case.by_date)
        assert has_drop_caveat == (
            metrics.target_only_place_count > 0
            or metrics.by_only_place_count > 0
        )
        assert has_cap_caveat == (metrics.group_size < case.n)


def test_generated_relations_match_for_tables_and_aligned_cohorts() -> None:
    # Test: Equivalence between `ObservationTable` and `AlignedCohort` inputs.
    # Situation: Every generated case run with pre-aligned cohorts.
    # Expectation: Relating the aligned cohorts produces the same result as
    #   relating the raw tables.
    for case in _generate_relation_cases():
        aligned_target = align_cohort(
            case.target_table, min_coverage=case.min_coverage
        )
        aligned_by = align_cohort(case.by_table, min_coverage=case.min_coverage)
        assert isinstance(aligned_target, AlignedCohort)
        assert isinstance(aligned_by, AlignedCohort)
        assert case.result == relate_cohorts(
            aligned_target,
            aligned_by,
            n=case.n,
            min_coverage=case.min_coverage,
        )
