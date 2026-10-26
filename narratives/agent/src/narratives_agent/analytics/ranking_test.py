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
"""Tests for `rank_cohort` in `analytics.ranking`.

Covers competition ranks, deterministic tie-breaking, both ends of the
ranking and the caveats for ends that leave out tied places, percentiles,
focal place entries, and parameter and alignment refusals.
"""

import functools
import random
from collections.abc import Sequence
from dataclasses import dataclass

import pytest

from narratives_agent.analytics.alignment import AlignedCohort, align_cohort
from narratives_agent.analytics.digest import ScriptResult
from narratives_agent.analytics.metrics import (
    RankEntry,
    RankingDirection,
    RankingMetrics,
)
from narratives_agent.analytics.provenance import Provenance, Source
from narratives_agent.analytics.ranking import (
    compute_cohort_percentiles,
    rank_cohort,
)
from narratives_agent.analytics.tables import (
    ObservationRow,
    ObservationTable,
)

_SOURCE = Source(name="Wikidata", url="https://wikidata")


def _table(
    observations: Sequence[tuple[str, str, float]],
    *,
    requested_places: Sequence[str] = (),
) -> ObservationTable:
    """Builds a table from `(place, date, value)` triples in table order."""
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
        provenance=Provenance(sources=(_SOURCE,), facet_ids=("f1",)),
        rows=tuple(
            ObservationRow(place, place.upper(), date, value)
            for place, date, value in observations
        ),
        requested_places=tuple(requested_places),
        place_names={place: place.upper() for place in places},
    )


def _tied_cohort() -> ObservationTable:
    """Five places on one date with values 10, 8, 8, 5, 5 in mixed order."""
    return _table(
        [
            ("d", "2022", 5.0),
            ("b", "2022", 8.0),
            ("a", "2022", 10.0),
            ("e", "2022", 5.0),
            ("c", "2022", 8.0),
        ]
    )


def _build_rank_entry(
    rank: int, is_tied: bool, place: str, value: float, percentile: float
) -> RankEntry:
    """Builds the expected `RankEntry` for one ranked place."""
    return RankEntry(
        rank=rank,
        is_tied=is_tied,
        place_dcid=place,
        place_name=place.upper(),
        value=value,
        percentile=percentile,
    )


def test_tied_values_share_competition_ranks_in_dcid_order() -> None:
    # Test: Ranking with ties, descending.
    # Situation: Values 10, 8, 8, 5, 5 across places a to e, requested
    #   with `max_entries_per_end=3` and focal places `e` and an unknown `z`.
    # Expectation: Competition ranks 1, 2, 2, 4, 4 with `is_tied` on the
    #   shared values and ties ordered by DCID; percentiles are the share of
    #   values at or below each value; `top_n` is the first three, `bottom_n`
    #   is the lowest three from the far end inward with ties still in DCID
    #   order; the focal entry for `e` is reported and `z` is missing with
    #   a caveat; the bottom tail stops inside the tie at rank 2, so a
    #   caveat says so, while the top tail ends between distinct values; and
    #   the methodology names the date and the order.
    result = rank_cohort(
        _tied_cohort(), max_entries_per_end=3, focal_places=["e", "z", "e"]
    )
    assert result.status == "ok"
    assert result.coverage is not None
    assert result.coverage.contributing_places == 5
    metrics = result.metrics
    assert isinstance(metrics, RankingMetrics)
    assert metrics.reference_date == "2022"
    assert metrics.direction == "desc"
    assert metrics.max_entries_per_end == 3
    assert metrics.cohort_size == 5
    assert metrics.top_n == (
        _build_rank_entry(1, False, "a", 10.0, 100.0),
        _build_rank_entry(2, True, "b", 8.0, 80.0),
        _build_rank_entry(2, True, "c", 8.0, 80.0),
    )
    assert metrics.bottom_n == (
        _build_rank_entry(4, True, "d", 5.0, 40.0),
        _build_rank_entry(4, True, "e", 5.0, 40.0),
        _build_rank_entry(2, True, "b", 8.0, 80.0),
    )
    assert metrics.focal_entries == (
        _build_rank_entry(4, True, "e", 5.0, 40.0),
    )
    assert metrics.missing_focal_places == ("z",)
    assert result.caveats == (
        "z has no value for Total population in the ranked cohort on 2022, "
        "so no rank is available.",
        "2 places share rank 2, so the bottom 3 entries include only 1 of "
        "them, chosen in DCID order.",
    )
    assert result.provenance.methodology == (
        "Ranked 5 places by Total population on 2022 in descending order; "
        "places with the same value share a rank."
    )
    assert result.provenance.sources == (_SOURCE,)


def test_ascending_direction_reverses_the_ranks_and_tails() -> None:
    # Test: Ranking with ties, ascending.
    # Situation: The same cohort with `direction="asc"` and
    #   `max_entries_per_end=2`.
    # Expectation: The lowest values rank first (1, 1, 3, 3, 5), `top_n`
    #   holds the two lowest in DCID order with no caveat, because the tie
    #   ends exactly at `n`, and `bottom_n` holds the highest value first
    #   and stops inside the tie at rank 3, with a caveat.
    result = rank_cohort(_tied_cohort(), max_entries_per_end=2, direction="asc")
    metrics = result.metrics
    assert isinstance(metrics, RankingMetrics)
    assert metrics.top_n == (
        _build_rank_entry(1, True, "d", 5.0, 40.0),
        _build_rank_entry(1, True, "e", 5.0, 40.0),
    )
    assert metrics.bottom_n == (
        _build_rank_entry(5, False, "a", 10.0, 100.0),
        _build_rank_entry(3, True, "b", 8.0, 80.0),
    )
    assert result.caveats == (
        "2 places share rank 3, so the bottom 2 entries include only 1 of "
        "them, chosen in DCID order.",
    )


def test_a_tie_split_between_the_ends_gets_a_caveat_on_each() -> None:
    # Test: The caveats for a tie group that both ends cut through.
    # Situation: Values 10, 8, 8, and 5 ranked descending with
    #   `max_entries_per_end=2`, so the top end lists `a` and `b`, and the
    #   bottom end, which skips the places in the top end, lists `d` and `c`.
    # Expectation: `top_n` holds `a` and the first of the tied places by
    #   DCID, `bottom_n` holds `d` and the other tied place, and each end
    #   carries a caveat that two places share rank 2 and it lists one.
    table = _table(
        [
            ("a", "2022", 10.0),
            ("b", "2022", 8.0),
            ("c", "2022", 8.0),
            ("d", "2022", 5.0),
        ]
    )
    result = rank_cohort(table, max_entries_per_end=2)
    assert isinstance(result.metrics, RankingMetrics)
    assert [entry.place_dcid for entry in result.metrics.top_n] == ["a", "b"]
    assert [entry.place_dcid for entry in result.metrics.bottom_n] == [
        "d",
        "c",
    ]
    assert result.caveats == (
        "2 places share rank 2, so the top 2 entries include only 1 of them, "
        "chosen in DCID order.",
        "2 places share rank 2, so the bottom 2 entries include only 1 of "
        "them, chosen in DCID order.",
    )


def test_a_cohort_tied_throughout_gets_a_caveat_on_each_end() -> None:
    # Test: The caveats when both ends together list every place.
    # Situation: Four places share one value and the cohort is ranked with
    #   `max_entries_per_end=2`, so each end lists two of the four.
    # Expectation: Both ends carry the caveat that four places share rank 1
    #   and the end lists two of them.
    table = _table([(f"p{index}", "2022", 5.0) for index in range(4)])
    result = rank_cohort(table, max_entries_per_end=2)
    assert result.caveats == (
        "4 places share rank 1, so the top 2 entries include only 2 of them, "
        "chosen in DCID order.",
        "4 places share rank 1, so the bottom 2 entries include only 2 of "
        "them, chosen in DCID order.",
    )


def test_one_tie_group_never_fills_both_tails_with_the_same_places() -> None:
    # Test: Disjoint tails when one tie group reaches both of them.
    # Situation: Twenty places share one value and the cohort is ranked
    #   with `max_entries_per_end=3`, so the cohort holds both tails in full.
    # Expectation: The top tail lists the first three places by DCID, the
    #   bottom tail the next three, and each tail carries the tie caveat.
    table = _table([(f"p{index:02d}", "2022", 5.0) for index in range(20)])
    result = rank_cohort(table, max_entries_per_end=3)
    metrics = result.metrics
    assert isinstance(metrics, RankingMetrics)
    assert [entry.place_dcid for entry in metrics.top_n] == [
        "p00",
        "p01",
        "p02",
    ]
    assert [entry.place_dcid for entry in metrics.bottom_n] == [
        "p03",
        "p04",
        "p05",
    ]
    assert result.caveats == (
        "20 places share rank 1, so the top 3 entries include only 3 of "
        "them, chosen in DCID order.",
        "20 places share rank 1, so the bottom 3 entries include only 3 of "
        "them, chosen in DCID order.",
    )


def test_a_cohort_of_one_place_is_at_the_hundredth_percentile() -> None:
    # Test: Percentile and tails for a single-place cohort.
    # Situation: One place, `max_entries_per_end=10`.
    # Expectation: Rank 1, not tied, percentile 100.0, and both tails hold
    #   that one entry.
    metrics = rank_cohort(_table([("a", "2022", 3.0)])).metrics
    assert isinstance(metrics, RankingMetrics)
    assert metrics.cohort_size == 1
    assert metrics.top_n == (_build_rank_entry(1, False, "a", 3.0, 100.0),)
    assert metrics.bottom_n == metrics.top_n


def test_bad_parameters_are_refused_as_invalid_parameters() -> None:
    # Test: Parameter validation.
    # Situation: `max_entries_per_end=0`; separately a `target_date` of
    #   `latest`, which is not a year, a year and month, or a full date; a
    #   bare string `e` as `focal_places`; a focal place with whitespace and
    #   a newline, which is not a DCID; and a `min_coverage` of 1.5.
    # Expectation: Each is a refusal with `invalid_parameters`, `metrics=None`,
    #   no coverage, and a caveat naming the bad value (or, for the invalid
    #   DCID, its position, so the string never reaches a caveat), rather
    #   than a coverage refusal for a date no row carries or a raised
    #   `ValueError`.
    by_size = rank_cohort(_tied_cohort(), max_entries_per_end=0)
    assert by_size.status == "refused"
    assert by_size.refusal_reason == "invalid_parameters"
    assert by_size.metrics is None
    assert by_size.coverage is None
    assert by_size.caveats == (
        "max_entries_per_end must be at least 1, not 0.",
    )
    by_date = rank_cohort(_tied_cohort(), target_date="latest")
    assert by_date.status == "refused"
    assert by_date.refusal_reason == "invalid_parameters"
    assert by_date.metrics is None
    assert by_date.coverage is None
    assert by_date.caveats == (
        "The target date 'latest' is not a year, a year and month, or a "
        "full date.",
    )
    by_string = rank_cohort(_tied_cohort(), focal_places="e")
    assert by_string.refusal_reason == "invalid_parameters"
    assert by_string.caveats == (
        "focal_places must be a sequence of DCIDs, not the string 'e'.",
    )
    by_dcid = rank_cohort(_tied_cohort(), focal_places=["e", "geoId 06\nnote"])
    assert by_dcid.refusal_reason == "invalid_parameters"
    assert by_dcid.caveats == (
        "focal_places must hold DCIDs, but entry 2 of 2 is not a valid DCID.",
    )
    by_coverage = rank_cohort(_tied_cohort(), min_coverage=1.5)
    assert by_coverage.status == "refused"
    assert by_coverage.refusal_reason == "invalid_parameters"
    assert by_coverage.metrics is None
    assert by_coverage.coverage is None
    assert by_coverage.caveats == (
        "The minimum coverage must be between 0 and 1, not 1.5.",
    )


def test_alignment_refusals_propagate_with_their_coverage() -> None:
    # Test: A table that cannot be aligned.
    # Situation: Ten requested places of which three report, below the
    #   default coverage; and an empty table.
    # Expectation: The result is refused with the alignment's reason, the
    #   coverage figure is carried, and the refusal message is the caveat.
    places = [f"p{index}" for index in range(10)]
    sparse = rank_cohort(
        _table(
            [("p0", "2022", 1.0), ("p1", "2022", 2.0), ("p2", "2022", 3.0)],
            requested_places=places,
        )
    )
    assert sparse.status == "refused"
    assert sparse.refusal_reason == "insufficient_coverage"
    assert sparse.coverage is not None
    assert sparse.coverage.contributing_places == 3
    assert sparse.coverage.requested_places == 10
    assert sparse.caveats == (
        "Only 3 of 10 places on 2022 have a value for Total population "
        "(Count_Person), below the required 50% coverage.",
    )
    empty = rank_cohort(_table([], requested_places=places))
    assert empty.refusal_reason == "no_observations"
    assert empty.coverage is not None
    assert empty.coverage.contributing_places == 0


def test_an_aligned_cohort_is_ranked_without_realignment() -> None:
    # Test: Passing an `AlignedCohort` directly.
    # Situation: A table aligned by `align_cohort` to a 2022 reference date
    #   with one place missing, then ranked with a `target_date` equal to
    #   that date, with a different `target_date`, and with a malformed one.
    # Expectation: The matching date ranks the aligned rows on 2022 and
    #   carries the alignment caveats and coverage; the different date is
    #   refused with `invalid_parameters` rather than silently ignored,
    #   keeping the alignment caveats ahead of the reason; and the malformed
    #   date is refused.
    table = _table(
        [("a", "2022", 1.0), ("b", "2022", 2.0), ("c", "2021", 3.0)],
        requested_places=["a", "b", "c"],
    )
    aligned = align_cohort(table)
    assert isinstance(aligned, AlignedCohort)
    result = rank_cohort(aligned, target_date="2022")
    assert isinstance(result.metrics, RankingMetrics)
    assert result.metrics.reference_date == "2022"
    assert result.metrics.cohort_size == 2
    assert result.coverage == aligned.coverage
    assert result.caveats == aligned.caveats
    conflicting = rank_cohort(aligned, target_date="2021")
    assert conflicting.refusal_reason == "invalid_parameters"
    assert conflicting.caveats == (
        *aligned.caveats,
        "The cohort is aligned to 2022, so it cannot be ranked on the target "
        "date 2021.",
    )
    malformed = rank_cohort(aligned, target_date="latest")
    assert malformed.refusal_reason == "invalid_parameters"


def test_an_aligned_cohort_keeps_its_coverage_and_ignores_min_coverage() -> (
    None
):
    # Test: Parameter handling for an `AlignedCohort`.
    # Situation: A cohort aligned to 2022 is ranked with
    #   `max_entries_per_end=0`, and then with `min_coverage=1.5`, which only
    #   alignment would use.
    # Expectation: `max_entries_per_end=0` is refused with `invalid_parameters`
    #   and carries the cohort's coverage and caveats; `min_coverage=1.5` is
    #   ignored, because the cohort is already aligned, and the ranking
    #   succeeds.
    table = _table(
        [("a", "2022", 1.0), ("b", "2022", 2.0), ("c", "2021", 3.0)],
        requested_places=["a", "b", "c"],
    )
    aligned = align_cohort(table)
    assert isinstance(aligned, AlignedCohort)
    by_size = rank_cohort(aligned, max_entries_per_end=0)
    assert by_size.refusal_reason == "invalid_parameters"
    assert by_size.coverage == aligned.coverage
    assert by_size.caveats == (
        *aligned.caveats,
        "max_entries_per_end must be at least 1, not 0.",
    )
    by_coverage = rank_cohort(aligned, min_coverage=1.5)
    assert isinstance(by_coverage.metrics, RankingMetrics)
    assert by_coverage.metrics.cohort_size == 2


def _ordered(
    rows: Sequence[tuple[str, float]], direction: str
) -> list[tuple[str, float]]:
    """Orders `(place, value)` pairs in `direction`, ties by DCID."""
    sign = -1.0 if direction == "desc" else 1.0
    return sorted(rows, key=lambda row: (sign * row[1], row[0]))


def _cohort_values(
    generator: random.Random, cohort_size: int, tie_size: int, tie_start: int
) -> list[float]:
    """Distinct values with one tie group, shuffled across the DCIDs."""
    values = [float(cohort_size - index) for index in range(cohort_size)]
    for index in range(tie_start, tie_start + tie_size):
        values[index] = values[tie_start]
    generator.shuffle(values)
    return values


@dataclass(frozen=True)
class _RankingCase:
    """One generated ranking: its inputs, its aligned cohort, and its result.

    `rows` holds the ranked `(place, value)` pairs; the table also holds a
    stale place that alignment leaves out.
    """

    rows: tuple[tuple[str, float], ...]
    table: ObservationTable
    aligned: AlignedCohort
    max_entries_per_end: int
    direction: RankingDirection
    result: ScriptResult
    metrics: RankingMetrics

    @property
    def size(self) -> int:
        """The number of entries each end holds."""
        return min(self.max_entries_per_end, len(self.rows))

    @property
    def values(self) -> list[float]:
        """The ranked values, one per place."""
        return [value for _, value in self.rows]


@functools.cache
def _generate_ranking_cases() -> tuple[_RankingCase, ...]:
    """Builds every generated ranking case once for the invariant tests.

    Covers every cohort size from 1 to 9, every tie group size and start
    position, `max_entries_per_end` from 1 to past the cohort size, and both
    directions, with values shuffled across DCIDs by a seeded generator.
    """
    generator = random.Random(17)
    directions: tuple[RankingDirection, ...] = ("desc", "asc")
    cases: list[_RankingCase] = []
    for cohort_size in range(1, 10):
        for tie_size in range(1, cohort_size + 1):
            for tie_start in range(cohort_size - tie_size + 1):
                values = _cohort_values(
                    generator, cohort_size, tie_size, tie_start
                )
                places = [f"p{index:02d}" for index in range(cohort_size)]
                rows = tuple(zip(places, values, strict=True))
                table = _table(
                    [(place, "2022", value) for place, value in rows]
                    + [("stale", "2020", 0.5)]
                )
                aligned = align_cohort(table)
                assert isinstance(aligned, AlignedCohort)
                for max_entries_per_end in range(1, cohort_size + 3):
                    for direction in directions:
                        result = rank_cohort(
                            table,
                            max_entries_per_end=max_entries_per_end,
                            direction=direction,
                        )
                        assert isinstance(result.metrics, RankingMetrics)
                        cases.append(
                            _RankingCase(
                                rows=rows,
                                table=table,
                                aligned=aligned,
                                max_entries_per_end=max_entries_per_end,
                                direction=direction,
                                result=result,
                                metrics=result.metrics,
                            )
                        )
    assert len(cases) > 1000
    return tuple(cases)


def _expected_ends(
    case: _RankingCase,
) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
    """Computes both ends directly: the leading and the trailing places.

    The trailing places run from the far end inward and skip the leading
    places when the cohort holds both ends in full.
    """
    opposite = "asc" if case.direction == "desc" else "desc"
    top = _ordered(case.rows, case.direction)[: case.size]
    top_places = {place for place, _ in top}
    disjoint = len(case.rows) >= 2 * case.size
    bottom = [
        row
        for row in _ordered(case.rows, opposite)
        if not (disjoint and row[0] in top_places)
    ][: case.size]
    return top, bottom


def _assert_entry_matches_cohort(
    entry: RankEntry, values: Sequence[float], direction: str
) -> None:
    """Checks an entry's rank, percentile, and tie flag against `values`."""
    ahead = sum(
        1
        for value in values
        if value != entry.value
        and (value > entry.value) == (direction == "desc")
    )
    at_or_below = sum(1 for value in values if value <= entry.value)
    assert entry.rank == ahead + 1
    assert entry.percentile == pytest.approx(at_or_below / len(values) * 100.0)
    assert entry.is_tied == (values.count(entry.value) > 1)


def _expected_tie_caveat(
    end: Sequence[RankEntry], label: str, values: Sequence[float]
) -> str | None:
    """Computes the caveat for one end directly, or None when none is due.

    A caveat is due when more cohort places share the value of the end's
    last entry than the end lists.
    """
    last = end[-1]
    shown = sum(1 for entry in end if entry.value == last.value)
    sharing = values.count(last.value)
    if sharing == shown:
        return None
    return (
        f"{sharing} places share rank {last.rank}, so the {label} "
        f"{len(end)} entries include only {shown} of them, chosen in DCID "
        "order."
    )


def test_generated_rankings_list_the_expected_ends() -> None:
    # Test: The places and order of both ends, checked by brute force.
    # Situation: Every generated case (see `_generate_ranking_cases`).
    # Expectation: `top_n` is the first `min(max_entries_per_end, cohort_size)`
    #   places in `direction`, ties by DCID; `bottom_n` is as many places from
    #   the other end, from the far end inward, skipping the places in
    #   `top_n` when the cohort holds both ends in full.
    for case in _generate_ranking_cases():
        expected_top, expected_bottom = _expected_ends(case)
        top = [(entry.place_dcid, entry.value) for entry in case.metrics.top_n]
        bottom = [
            (entry.place_dcid, entry.value) for entry in case.metrics.bottom_n
        ]
        assert top == expected_top
        assert bottom == expected_bottom


def test_generated_rankings_report_ranks_percentiles_and_ties() -> None:
    # Test: Each listed entry's rank, percentile, and tie flag.
    # Situation: Every generated case (see `_generate_ranking_cases`).
    # Expectation: Ranks are standard competition ranks in `direction`,
    #   percentiles are the share of places at or below each value, and an
    #   entry is tied exactly when another place has its value.
    for case in _generate_ranking_cases():
        for entry in (*case.metrics.top_n, *case.metrics.bottom_n):
            _assert_entry_matches_cohort(entry, case.values, case.direction)


def test_generated_rankings_report_tie_caveats() -> None:
    # Test: The tie caveat of each end.
    # Situation: Every generated case (see `_generate_ranking_cases`).
    # Expectation: An end carries a caveat exactly when more cohort places
    #   share its last entry's value than the end lists, with those counts
    #   and that entry's rank, and carries no caveat otherwise.
    for case in _generate_ranking_cases():
        for label, end in (
            ("top", case.metrics.top_n),
            ("bottom", case.metrics.bottom_n),
        ):
            marker = f"the {label} {case.size} entries include"
            found = [
                caveat for caveat in case.result.caveats if marker in caveat
            ]
            expected = _expected_tie_caveat(end, label, case.values)
            assert found == ([] if expected is None else [expected])


def test_generated_rankings_match_for_a_table_and_its_aligned_cohort() -> None:
    # Test: Equivalence of the two inputs.
    # Situation: Every generated case ranked again from its aligned cohort.
    # Expectation: Both results are equal.
    for case in _generate_ranking_cases():
        assert case.result == rank_cohort(
            case.aligned,
            max_entries_per_end=case.max_entries_per_end,
            direction=case.direction,
        )


def test_rank_cohort_on_a_target_date_equals_ranking_the_aligned_cohort() -> (
    None
):
    # Test: Equivalence of the two inputs when a target date is passed.
    # Situation: A table with values on 2020 and 2022 for every place,
    #   ranked with `target_date="2020"` directly and after `align_cohort`
    #   with the same date, passing the same `target_date` again.
    # Expectation: Both rankings are equal and use 2020.
    table = _table(
        [(f"p{index}", "2020", float(index)) for index in range(6)]
        + [(f"p{index}", "2022", float(10 - index)) for index in range(6)]
    )
    aligned = align_cohort(table, target_date="2020")
    assert isinstance(aligned, AlignedCohort)
    direct = rank_cohort(table, max_entries_per_end=2, target_date="2020")
    assert direct == rank_cohort(
        aligned, max_entries_per_end=2, target_date="2020"
    )
    assert isinstance(direct.metrics, RankingMetrics)
    assert direct.metrics.reference_date == "2020"


def test_cohort_percentiles_of_no_values_are_rejected() -> None:
    # Test: The non-empty precondition of `compute_cohort_percentiles`.
    # Situation: An empty sequence of values.
    # Expectation: `ValueError` rather than an empty mapping.
    with pytest.raises(ValueError, match="at least one value"):
        compute_cohort_percentiles([])
