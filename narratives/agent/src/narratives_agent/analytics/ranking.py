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
"""Ranks the places of an aligned cohort.

`rank_cohort` aligns a cohort to a single reference date, assigns standard
competition ranks, and reports top and bottom tails, focal place ranks and
percentiles, and cohort coverage.
"""

from collections import Counter
from collections.abc import Callable, Sequence
from typing import Literal

from narratives_agent.analytics.alignment import (
    DEFAULT_MIN_COVERAGE,
    AlignedCohort,
    AlignmentRefusal,
    align_cohort,
    validate_alignment_parameters,
)
from narratives_agent.analytics.digest import (
    PERCENT_SCALE,
    CoverageReport,
    OkScriptResult,
    RefusalReason,
    RefusedScriptResult,
    ScriptResult,
    conjugate_have,
    format_place_names,
)
from narratives_agent.analytics.metrics import (
    RankEntry,
    RankingDirection,
    RankingMetrics,
)
from narratives_agent.analytics.provenance import merge_provenance
from narratives_agent.analytics.tables import (
    ObservationRow,
    ObservationTable,
)

__all__ = [
    "DEFAULT_MAX_ENTRIES_PER_END",
    "compute_cohort_percentiles",
    "rank_cohort",
]

_SCRIPT_NAME: Literal["rank_cohort"] = "rank_cohort"
DEFAULT_MAX_ENTRIES_PER_END = 10


def _build_sort_key(
    direction: RankingDirection,
) -> Callable[[ObservationRow], tuple[float, str]]:
    """Returns the key that orders rows in `direction`, ties by DCID."""
    if direction == "desc":
        return lambda row: (-row.value, row.place_dcid)
    return lambda row: (row.value, row.place_dcid)


def _compute_competition_ranks(
    counts: Counter[float], direction: RankingDirection
) -> dict[float, int]:
    """Maps each distinct value to its standard competition rank.

    A value's rank is one more than the number of values ranked ahead of it,
    so two places sharing a value share a rank and the next value skips a
    position (1, 2, 2, 4). `counts` maps each value to its number of places.
    """
    ordered = sorted(counts, reverse=direction == "desc")
    ranks: dict[float, int] = {}
    position = 1
    for value in ordered:
        ranks[value] = position
        position += counts[value]
    return ranks


def compute_cohort_percentiles(values: Sequence[float]) -> dict[float, float]:
    """Maps each distinct value to its percentile within the cohort.

    The percentile of a value is the percentage of cohort places whose value
    is less than or equal to it, so the largest value is at 100.0, tied
    places share a percentile, and a cohort of one place is at 100.0. It is
    public so that any script reporting cohort percentiles can share this
    definition.

    Args:
        values: One value per cohort place; must not be empty.

    Returns:
        A map from each distinct value to its percentile (0 to 100 scale).
    """
    counts = Counter(values)
    total = len(values)
    percentiles: dict[float, float] = {}
    cumulative = 0
    for value in sorted(counts):
        cumulative += counts[value]
        percentiles[value] = cumulative / total * PERCENT_SCALE
    return percentiles


def _build_rank_entry(
    row: ObservationRow,
    ranks: dict[float, int],
    percentiles: dict[float, float],
    tie_counts: Counter[float],
) -> RankEntry:
    """Builds the `RankEntry` that describes one ranked place."""
    return RankEntry(
        rank=ranks[row.value],
        is_tied=tie_counts[row.value] > 1,
        place_dcid=row.place_dcid,
        place_name=row.place_name,
        value=row.value,
        percentile=percentiles[row.value],
    )


def _describe_tie_cut(
    listed: Sequence[ObservationRow],
    label: str,
    ranks: dict[float, int],
    tie_counts: Counter[float],
) -> str | None:
    """States that a tail leaves out places tied with its last entry.

    `listed` holds the rows of one tail, in tail order. Returns None when
    every cohort place that shares the last row's value is in the tail. The
    count covers the whole cohort, so a bottom tail that skips places
    already in the top tail still reports the places it does not list.
    """
    value = listed[-1].value
    shown = sum(1 for row in listed if row.value == value)
    if tie_counts[value] == shown:
        return None
    return (
        f"{tie_counts[value]} places share rank {ranks[value]}, so the "
        f"{label} {len(listed)} entries include only {shown} of them, chosen "
        "in DCID order."
    )


def _build_refusal(
    cohort_or_table: AlignedCohort | ObservationTable,
    step_id: str,
    reason: RefusalReason,
    coverage: CoverageReport | None,
    caveat: str,
) -> ScriptResult:
    """Builds a refused result, carrying the cohort coverage when known."""
    return RefusedScriptResult(
        step_id=step_id,
        script=_SCRIPT_NAME,
        refusal_reason=reason,
        variables=(cohort_or_table.variable_dcid,),
        variable_names={
            cohort_or_table.variable_dcid: cohort_or_table.variable_name
        },
        unit=cohort_or_table.unit,
        scaling_factor=cohort_or_table.scaling_factor,
        coverage=coverage,
        provenance=cohort_or_table.provenance,
        caveats=(caveat,),
    )


def _resolve_aligned_cohort(
    cohort_or_table: AlignedCohort | ObservationTable,
    *,
    max_entries_per_end: int,
    focal_places: Sequence[str],
    target_date: str | None,
    min_coverage: float,
    step_id: str,
) -> AlignedCohort | ScriptResult:
    """Checks the parameters and returns the cohort to rank, or a refusal.

    A table is aligned with `target_date` and `min_coverage`. An aligned
    cohort is used as given: `min_coverage` is not checked, and a
    `target_date` other than its reference date is refused. A refusal of an
    aligned cohort carries the cohort's coverage.
    """
    known_coverage = (
        cohort_or_table.coverage
        if isinstance(cohort_or_table, AlignedCohort)
        else None
    )
    if max_entries_per_end < 1:
        return _build_refusal(
            cohort_or_table,
            step_id,
            "invalid_parameters",
            known_coverage,
            "max_entries_per_end must be at least 1, not "
            f"{max_entries_per_end}.",
        )
    # A `str` is a `Sequence[str]`, so the type does not exclude it.
    if isinstance(focal_places, str):
        return _build_refusal(
            cohort_or_table,
            step_id,
            "invalid_parameters",
            known_coverage,
            f"focal_places must be a sequence of DCIDs, not the string "
            f"{focal_places!r}.",
        )
    if isinstance(cohort_or_table, AlignedCohort):
        # `min_coverage` applies only to alignment, which already happened.
        error = validate_alignment_parameters(target_date=target_date)
        if error is None and target_date not in (
            None,
            cohort_or_table.reference_date,
        ):
            error = (
                f"The cohort is aligned to {cohort_or_table.reference_date}, "
                f"so it cannot be ranked on the target date {target_date}."
            )
        if error is not None:
            return _build_refusal(
                cohort_or_table,
                step_id,
                "invalid_parameters",
                known_coverage,
                error,
            )
        return cohort_or_table
    error = validate_alignment_parameters(
        target_date=target_date, min_coverage=min_coverage
    )
    if error is not None:
        return _build_refusal(
            cohort_or_table, step_id, "invalid_parameters", None, error
        )
    aligned = align_cohort(
        cohort_or_table, target_date=target_date, min_coverage=min_coverage
    )
    if isinstance(aligned, AlignmentRefusal):
        return _build_refusal(
            cohort_or_table,
            step_id,
            aligned.reason,
            aligned.coverage,
            aligned.message,
        )
    return aligned


def _select_ends(
    rows: Sequence[ObservationRow], direction: RankingDirection, size: int
) -> tuple[list[ObservationRow], list[ObservationRow]]:
    """Returns the `size` leading rows and the `size` trailing rows.

    Both lists order ties by DCID, and the trailing rows run from the far
    end inward. One tie group can reach both ends, so when the cohort holds
    both lists in full, the trailing rows skip the places the leading rows
    list, which keeps the two lists disjoint.
    """
    leading = sorted(rows, key=_build_sort_key(direction))[:size]
    trailing = sorted(
        rows, key=_build_sort_key("asc" if direction == "desc" else "desc")
    )
    if len(rows) >= 2 * size:
        taken = {row.place_dcid for row in leading}
        trailing = [row for row in trailing if row.place_dcid not in taken]
    return leading, trailing[:size]


def _describe_missing_focal_places(
    aligned: AlignedCohort, missing_focal: Sequence[str]
) -> str:
    """States which focal places have no value in the ranked cohort."""
    names = format_place_names(
        [aligned.place_names.get(place, place) for place in missing_focal]
    )
    return (
        f"{names} {conjugate_have(len(missing_focal))} no value for "
        f"{aligned.variable_name} in the ranked cohort on "
        f"{aligned.reference_date}, so no rank is available."
    )


def rank_cohort(
    cohort_or_table: AlignedCohort | ObservationTable,
    *,
    max_entries_per_end: int = DEFAULT_MAX_ENTRIES_PER_END,
    direction: RankingDirection = "desc",
    focal_places: Sequence[str] = (),
    target_date: str | None = None,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
    step_id: str = "s1",
) -> ScriptResult:
    """Ranks the places of a cohort at its reference date.

    Args:
        cohort_or_table: An aligned cohort, or a table to align first with
            `target_date` and `min_coverage`. An aligned cohort already has
            a reference date: `min_coverage` is then unused and not
            checked, and a `target_date` other than that date is refused.
        max_entries_per_end: The most entries listed at each end of the
            ranking, in `top_n` and in `bottom_n`; must be at least 1. Each
            end lists fewer when the cohort has fewer places.
        direction: `desc` ranks the largest value first, `asc` the smallest.
        focal_places: Places whose entries are reported wherever they rank.
        target_date: Passed to `align_cohort` when a table is given.
        min_coverage: Passed to `align_cohort` when a table is given.
        step_id: Identifier of the analysis step (for example, `"s1"`).

    Returns:
        A result whose `metrics` is a `RankingMetrics` holding
        `reference_date`, `direction`, `max_entries_per_end`, `cohort_size`,
        `top_n` (the leading entries in `direction`), `bottom_n` (the
        trailing entries, ordered from the far end inward), `focal_entries`
        (in `focal_places` order), and `missing_focal_places`. Each entry is
        a `RankEntry` carrying `rank`, `is_tied`, `place_dcid`,
        `place_name`, `value`, and `percentile`. A caveat notes an end that
        leaves out places tied with its last entry. The result is refused
        with `invalid_parameters` when `max_entries_per_end` is below 1,
        `target_date` is not a valid date or differs from an aligned
        cohort's reference date, `min_coverage` is outside `[0.0, 1.0]` for
        a table, or `focal_places` is a string, carrying the cohort's
        coverage when an aligned cohort was passed; and with the alignment's
        reason when the cohort cannot be aligned.
    """
    aligned = _resolve_aligned_cohort(
        cohort_or_table,
        max_entries_per_end=max_entries_per_end,
        focal_places=focal_places,
        target_date=target_date,
        min_coverage=min_coverage,
        step_id=step_id,
    )
    if not isinstance(aligned, AlignedCohort):
        return aligned

    values = [row.value for row in aligned.rows]
    tie_counts = Counter(values)
    ranks = _compute_competition_ranks(tie_counts, direction)
    percentiles = compute_cohort_percentiles(values)
    entries_by_place = {
        row.place_dcid: _build_rank_entry(row, ranks, percentiles, tie_counts)
        for row in aligned.rows
    }
    size = min(max_entries_per_end, len(aligned.rows))
    leading, trailing = _select_ends(aligned.rows, direction, size)
    requested_focal = list(dict.fromkeys(focal_places))
    missing_focal = tuple(
        place for place in requested_focal if place not in entries_by_place
    )

    caveats = list(aligned.caveats)
    if missing_focal:
        caveats.append(_describe_missing_focal_places(aligned, missing_focal))
    for listed, label in ((leading, "top"), (trailing, "bottom")):
        tie_cut = _describe_tie_cut(listed, label, ranks, tie_counts)
        if tie_cut is not None:
            caveats.append(tie_cut)

    order = "descending" if direction == "desc" else "ascending"
    provenance = merge_provenance(
        aligned.provenance,
        methodology=(
            f"Ranked {len(aligned.rows)} places by {aligned.variable_name} "
            f"on {aligned.reference_date} in {order} order; places with "
            "the same value share a rank."
        ),
    )
    return OkScriptResult(
        step_id=step_id,
        script=_SCRIPT_NAME,
        variables=(aligned.variable_dcid,),
        variable_names={aligned.variable_dcid: aligned.variable_name},
        unit=aligned.unit,
        scaling_factor=aligned.scaling_factor,
        coverage=aligned.coverage,
        provenance=provenance,
        metrics=RankingMetrics(
            reference_date=aligned.reference_date,
            direction=direction,
            max_entries_per_end=max_entries_per_end,
            cohort_size=len(aligned.rows),
            top_n=tuple(entries_by_place[row.place_dcid] for row in leading),
            bottom_n=tuple(
                entries_by_place[row.place_dcid] for row in trailing
            ),
            focal_entries=tuple(
                entries_by_place[place]
                for place in requested_focal
                if place in entries_by_place
            ),
            missing_focal_places=missing_focal,
        ),
        caveats=tuple(caveats),
    )
