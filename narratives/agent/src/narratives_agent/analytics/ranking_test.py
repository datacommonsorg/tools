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

Covers competition ranks, deterministic tie-breaking, top and bottom tails
and the caveats for tails that stop inside a tie, percentiles, focal place
entries, and parameter and alignment refusals.
"""

import random
from collections.abc import Sequence

import pytest

from narratives_agent.analytics.alignment import AlignedCohort, align_cohort
from narratives_agent.analytics.metrics import RankEntry, RankingMetrics
from narratives_agent.analytics.provenance import Provenance, Source
from narratives_agent.analytics.ranking import rank_cohort
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
    #   with `n=3` and focal places `e` and an unknown `z`.
    # Expectation: Competition ranks 1, 2, 2, 4, 4 with `is_tied` on the
    #   shared values and ties ordered by DCID; percentiles are the share of
    #   values at or below each value; `top_n` is the first three, `bottom_n`
    #   is the lowest three from the far end inward with ties still in DCID
    #   order; the focal entry for `e` is reported and `z` is missing with
    #   a caveat; the bottom tail stops inside the tie at rank 2, so a
    #   caveat says so, while the top tail ends between distinct values; and
    #   the methodology names the date and the order.
    result = rank_cohort(_tied_cohort(), n=3, focal_places=["e", "z", "e"])
    assert result.status == "ok"
    assert result.coverage is not None
    assert result.coverage.contributing_places == 5
    metrics = result.metrics
    assert isinstance(metrics, RankingMetrics)
    assert metrics.reference_date == "2022"
    assert metrics.direction == "desc"
    assert metrics.n == 3
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
    # Situation: The same cohort with `direction="asc"` and `n=2`.
    # Expectation: The lowest values rank first (1, 1, 3, 3, 5), `top_n`
    #   holds the two lowest in DCID order with no caveat, because the tie
    #   ends exactly at `n`, and `bottom_n` holds the highest value first
    #   and stops inside the tie at rank 3, with a caveat.
    result = rank_cohort(_tied_cohort(), n=2, direction="asc")
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


def test_a_top_tail_that_stops_inside_a_tie_gets_a_caveat() -> None:
    # Test: The caveat for a top tail cut through a tie group.
    # Situation: Values 10, 8, 8, and 5 ranked descending with `n=2`, so the
    #   top tail ends inside the tie at rank 2.
    # Expectation: `top_n` holds `a` and the first of the tied places by
    #   DCID, and a caveat says two places share rank 2 and the top tail
    #   lists one of them.
    table = _table(
        [
            ("a", "2022", 10.0),
            ("b", "2022", 8.0),
            ("c", "2022", 8.0),
            ("d", "2022", 5.0),
        ]
    )
    result = rank_cohort(table, n=2)
    assert isinstance(result.metrics, RankingMetrics)
    assert [entry.place_dcid for entry in result.metrics.top_n] == ["a", "b"]
    assert result.caveats == (
        "2 places share rank 2, so the top 2 entries include only 1 of them, "
        "chosen in DCID order.",
    )


def test_one_tie_group_never_fills_both_tails_with_the_same_places() -> None:
    # Test: Disjoint tails when one tie group reaches both of them.
    # Situation: Twenty places share one value and the cohort is ranked
    #   with `n=3`, so the cohort holds both tails in full.
    # Expectation: The top tail lists the first three places by DCID, the
    #   bottom tail the next three, and each tail carries the tie caveat.
    table = _table([(f"p{index:02d}", "2022", 5.0) for index in range(20)])
    result = rank_cohort(table, n=3)
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
    # Situation: One place, `n=10`.
    # Expectation: Rank 1, not tied, percentile 100.0, and both tails hold
    #   that one entry.
    metrics = rank_cohort(_table([("a", "2022", 3.0)])).metrics
    assert isinstance(metrics, RankingMetrics)
    assert metrics.cohort_size == 1
    assert metrics.top_n == (_build_rank_entry(1, False, "a", 3.0, 100.0),)
    assert metrics.bottom_n == metrics.top_n


def test_bad_parameters_are_refused_as_invalid_parameters() -> None:
    # Test: Parameter validation.
    # Situation: `n=0`; separately a `target_date` of `latest`, which is not
    #   a year, a year and month, or a full date; a bare string `e` as
    #   `focal_places`; and a `min_coverage` of 1.5.
    # Expectation: Each is a refusal with `invalid_parameters`, `metrics=None`,
    #   no coverage, and a caveat naming the bad value, rather than a
    #   coverage refusal for a date no row carries or a raised `ValueError`.
    by_size = rank_cohort(_tied_cohort(), n=0)
    assert by_size.status == "refused"
    assert by_size.refusal_reason == "invalid_parameters"
    assert by_size.metrics is None
    assert by_size.coverage is None
    assert by_size.caveats == ("The ranking size must be at least 1, not 0.",)
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
    #   refused with `invalid_parameters` rather than silently ignored; and
    #   the malformed date is refused.
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
        "The cohort is aligned to 2022, so it cannot be ranked on the target "
        "date 2021.",
    )
    malformed = rank_cohort(aligned, target_date="latest")
    assert malformed.refusal_reason == "invalid_parameters"


def test_an_aligned_cohort_keeps_its_coverage_and_ignores_min_coverage() -> (
    None
):
    # Test: Parameter handling for an `AlignedCohort`.
    # Situation: A cohort aligned to 2022 is ranked with `n=0`, and then with
    #   `min_coverage=1.5`, which only alignment would use.
    # Expectation: `n=0` is refused with `invalid_parameters` and carries the
    #   cohort's coverage; `min_coverage=1.5` is ignored, because the cohort
    #   is already aligned, and the ranking succeeds.
    table = _table(
        [("a", "2022", 1.0), ("b", "2022", 2.0), ("c", "2021", 3.0)],
        requested_places=["a", "b", "c"],
    )
    aligned = align_cohort(table)
    assert isinstance(aligned, AlignedCohort)
    by_size = rank_cohort(aligned, n=0)
    assert by_size.refusal_reason == "invalid_parameters"
    assert by_size.coverage == aligned.coverage
    assert by_size.caveats == ("The ranking size must be at least 1, not 0.",)
    by_coverage = rank_cohort(aligned, min_coverage=1.5)
    assert isinstance(by_coverage.metrics, RankingMetrics)
    assert by_coverage.metrics.cohort_size == 2


def _ordered(
    rows: Sequence[tuple[str, float]], direction: str
) -> list[tuple[str, float]]:
    """Orders `(place, value)` pairs in `direction`, ties by DCID."""
    sign = -1.0 if direction == "desc" else 1.0
    return sorted(rows, key=lambda row: (sign * row[1], row[0]))


def _leaves_out_a_tied_place(
    tail: Sequence[RankEntry],
    rows: Sequence[tuple[str, float]],
    listed: set[str],
) -> bool:
    """Whether a place outside `listed` shares the last entry's value."""
    last = tail[-1].value
    return any(value == last and place not in listed for place, value in rows)


def _cohort_values(
    generator: random.Random, cohort_size: int, tie_size: int, tie_start: int
) -> list[float]:
    """Distinct values with one tie group, shuffled across the DCIDs."""
    values = [float(cohort_size - index) for index in range(cohort_size)]
    for index in range(tie_start, tie_start + tie_size):
        values[index] = values[tie_start]
    generator.shuffle(values)
    return values


def test_rank_cohort_invariants_hold_across_sizes_ties_and_directions() -> None:
    # Test: The ranking invariants checked by brute force.
    # Situation: Every cohort size from 1 to 9, every tie group size and
    #   start position, sizes `n` from 1 to past the cohort size, both
    #   directions, and a stale place that alignment leaves out, with values
    #   shuffled across DCIDs by a seeded generator.
    # Expectation: `top_n` is the first `min(n, cohort_size)` places in
    #   `direction` (ties by DCID); `bottom_n` is as many places from the
    #   other end, ordered from the far end inward and skipping the places
    #   in `top_n` when the cohort holds both tails in full; ranks are
    #   standard competition ranks and percentiles are the share of places
    #   at or below each value; a tie caveat appears for a tail exactly when
    #   a place outside the listed entries has the value of the tail's last
    #   entry; and ranking the table equals ranking its aligned cohort.
    generator = random.Random(20261025)
    checked = 0
    for cohort_size in range(1, 10):
        for tie_size in range(1, cohort_size + 1):
            for tie_start in range(cohort_size - tie_size + 1):
                values = _cohort_values(
                    generator, cohort_size, tie_size, tie_start
                )
                places = [f"p{index:02d}" for index in range(cohort_size)]
                rows = list(zip(places, values, strict=True))
                table = _table(
                    [(place, "2022", value) for place, value in rows]
                    + [("stale", "2020", 0.5)]
                )
                aligned = align_cohort(table)
                assert isinstance(aligned, AlignedCohort)
                for n in range(1, cohort_size + 3):
                    for direction in ("desc", "asc"):
                        result = rank_cohort(table, n=n, direction=direction)
                        assert result == rank_cohort(
                            aligned, n=n, direction=direction
                        )
                        metrics = result.metrics
                        assert isinstance(metrics, RankingMetrics)
                        size = min(n, cohort_size)
                        leading = _ordered(rows, direction)
                        trailing = _ordered(
                            rows, "asc" if direction == "desc" else "desc"
                        )
                        expected_top = leading[:size]
                        disjoint = cohort_size >= 2 * size
                        top_places = {place for place, _ in expected_top}
                        expected_bottom = [
                            row
                            for row in trailing
                            if not (disjoint and row[0] in top_places)
                        ][:size]
                        assert [
                            (entry.place_dcid, entry.value)
                            for entry in metrics.top_n
                        ] == expected_top
                        assert [
                            (entry.place_dcid, entry.value)
                            for entry in metrics.bottom_n
                        ] == expected_bottom
                        for entry in (*metrics.top_n, *metrics.bottom_n):
                            ahead = sum(
                                1
                                for value in values
                                if (value > entry.value)
                                == (direction == "desc")
                                and value != entry.value
                            )
                            assert entry.rank == ahead + 1
                            at_or_below = sum(
                                1 for value in values if value <= entry.value
                            )
                            assert entry.percentile == pytest.approx(
                                at_or_below / cohort_size * 100.0
                            )
                            assert entry.is_tied == (
                                values.count(entry.value) > 1
                            )
                        bottom_listed = {
                            entry.place_dcid for entry in metrics.bottom_n
                        }
                        if disjoint:
                            bottom_listed |= top_places
                        for label, tail, listed in (
                            ("top", metrics.top_n, top_places),
                            ("bottom", metrics.bottom_n, bottom_listed),
                        ):
                            marker = f"the {label} {size} entries include"
                            found = [
                                caveat
                                for caveat in result.caveats
                                if marker in caveat
                            ]
                            if not _leaves_out_a_tied_place(tail, rows, listed):
                                assert found == []
                                continue
                            last = tail[-1]
                            shown = sum(
                                1 for entry in tail if entry.value == last.value
                            )
                            assert found == [
                                f"{values.count(last.value)} places share "
                                f"rank {last.rank}, so the {label} {size} "
                                f"entries include only {shown} of them, "
                                "chosen in DCID order."
                            ]
                        checked += 1
    assert checked > 1000


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
    direct = rank_cohort(table, n=2, target_date="2020")
    assert direct == rank_cohort(aligned, n=2, target_date="2020")
    assert isinstance(direct.metrics, RankingMetrics)
    assert direct.metrics.reference_date == "2020"
