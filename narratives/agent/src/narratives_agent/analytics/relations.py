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
"""Relates two cohort variables across the places both cover.

`pair_cohorts` aligns each variable on its own reference date and joins the
two aligned cohorts on place, producing the `PairedCohort` that every
reduction relating two variables starts from. `relate_cohorts` ranks the
shared places by one variable and summarizes the other over the places with
the highest and the lowest values.
"""

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal

from narratives_agent.analytics.alignment import (
    DEFAULT_MIN_COVERAGE,
    AlignedCohort,
    AlignmentRefusal,
    align_cohort,
    has_adequate_coverage,
    validate_alignment_parameters,
)
from narratives_agent.analytics.digest import (
    CoverageReport,
    OkScriptResult,
    RefusedScriptResult,
    ScriptResult,
    conjugate_have,
    format_percent,
    format_place_names,
)
from narratives_agent.analytics.metrics import (
    GroupSummary,
    RankEntry,
    RankingMetrics,
    RelationEntry,
    RelationMetrics,
)
from narratives_agent.analytics.provenance import Provenance, merge_provenance
from narratives_agent.analytics.ranking import (
    DEFAULT_MAX_ENTRIES_PER_END,
    rank_cohort,
)
from narratives_agent.analytics.script_inputs import (
    CohortInput,
    build_invalid_parameters_refusal,
    build_refusal,
    resolve_target_places,
)
from narratives_agent.analytics.tables import (
    ObservationTable,
    is_valid_observation_date,
)

__all__ = [
    "MIN_SHARED_PLACES",
    "PairedCohort",
    "PairedPlace",
    "PairingRefusal",
    "pair_cohorts",
    "relate_cohorts",
]

_SCRIPT_NAME: Literal["relate_cohorts"] = "relate_cohorts"
# Minimum requested group size for `relate_cohorts`.
_MIN_GROUP_SIZE = 1
# Number of groups compared by `relate_cohorts` (`highest_by` and `lowest_by`).
_GROUP_COUNT = 2
# Two disjoint groups require at least this many shared places.
MIN_SHARED_PLACES = _MIN_GROUP_SIZE * _GROUP_COUNT

type PairingRefusalReason = Literal[
    "insufficient_coverage", "no_observations", "invalid_parameters"
]
type PairingSide = Literal["target", "by"]


@dataclass(frozen=True)
class PairedPlace:
    """One place with a value for both variables.

    Attributes:
        place_dcid: DCID of the shared place.
        place_name: Display name of the place, resolved from `target` with
            fallback to `by`.
        target_value: Finite value of the `target` variable on
            `target.reference_date`.
        by_value: Finite value of the `by` variable on `by.reference_date`.

    Raises:
        ValueError: If `target_value` or `by_value` is a boolean or not
            finite.
    """

    place_dcid: str
    place_name: str
    target_value: float
    by_value: float

    def __post_init__(self) -> None:
        """Rejects boolean or non-finite observation values."""
        for label, value in (
            ("target_value", self.target_value),
            ("by_value", self.by_value),
        ):
            if isinstance(value, bool) or not math.isfinite(value):
                raise ValueError(
                    f"{label} must be a finite number, not {value!r}."
                )


@dataclass(frozen=True)
class PairedCohort:
    """Two aligned cohorts joined on the places both cover.

    Attributes:
        target: The aligned cohort of the variable being summarized, which
            carries its variable, name, unit, scaling factor, and reference
            date.
        by: The aligned cohort of the variable the places are ordered by.
        places: The shared places with both values, sorted by place DCID;
            never empty.
        target_only_places: The places of `target` with no `by` value,
            sorted by place DCID.
        by_only_places: The places of `by` with no `target` value, sorted by
            place DCID.
        provenance: The merged provenance of both cohorts.

    Raises:
        ValueError: If `places` is empty.
    """

    target: AlignedCohort
    by: AlignedCohort
    places: tuple[PairedPlace, ...]
    target_only_places: tuple[str, ...]
    by_only_places: tuple[str, ...]
    provenance: Provenance

    def __post_init__(self) -> None:
        """Rejects a paired cohort without shared places."""
        if not self.places:
            raise ValueError(
                "A paired cohort must have at least one shared place."
            )


@dataclass(frozen=True)
class PairingRefusal:
    """Why two cohorts could not be paired.

    Attributes:
        reason: The refusal reason, from the `ScriptResult` vocabulary.
        caveats: Plain-English statements of any prior alignment caveats
            followed by the refusal reason; never empty.
        side: The input (`"target"` or `"by"`) whose date or alignment
            failed; None when the refusal applies to both inputs or to the
            shared-place join.
        coverage: The refusing side's alignment coverage when an alignment
            refused, or the agreed coverage of pre-aligned inputs; None when
            no single coverage report applies.

    Raises:
        ValueError: If `caveats` is empty.
    """

    reason: PairingRefusalReason
    caveats: tuple[str, ...]
    side: PairingSide | None = None
    coverage: CoverageReport | None = None

    def __post_init__(self) -> None:
        """Rejects a pairing refusal without caveats."""
        if not self.caveats:
            raise ValueError("A pairing refusal must have at least one caveat.")


def _collect_aligned_caveats(*items: CohortInput) -> tuple[str, ...]:
    """Returns the deduplicated caveats of any aligned cohort in `items`."""
    return tuple(
        dict.fromkeys(
            caveat
            for item in items
            if isinstance(item, AlignedCohort)
            for caveat in item.caveats
        )
    )


def _resolve_agreed_coverage(*items: CohortInput) -> CoverageReport | None:
    """Returns the coverage when all aligned inputs agree on one report."""
    coverages = {
        item.coverage for item in items if isinstance(item, AlignedCohort)
    }
    return next(iter(coverages)) if len(coverages) == 1 else None


def _has_explicit_target_places(item: CohortInput) -> bool:
    """Returns whether `item` carries an explicit target-place list."""
    if isinstance(item, AlignedCohort):
        return True
    return bool(item.requested_places)


def _resolve_table_requested_places(
    table: ObservationTable, other: CohortInput
) -> ObservationTable:
    """Fills `table.requested_places` from `other` when `table` omits them."""
    if table.requested_places or not _has_explicit_target_places(other):
        return table
    return replace(table, requested_places=resolve_target_places(other))


def _collect_input_place_names(item: CohortInput) -> dict[str, str]:
    """Collects display names from an input's rows and `place_names` map."""
    names = {row.place_dcid: row.place_name for row in item.rows}
    for place, name in item.place_names.items():
        if name and (place not in names or name != place):
            names[place] = name
    return names


def _resolve_place_names(
    target: CohortInput, by: CohortInput
) -> dict[str, str]:
    """Resolves place display names from `target`, falling back to `by`."""
    target_names = _collect_input_place_names(target)
    by_names = _collect_input_place_names(by)
    resolved: dict[str, str] = {}
    for place in dict.fromkeys((*target_names, *by_names)):
        target_name = target_names.get(place)
        by_name = by_names.get(place)
        if target_name and target_name != place:
            resolved[place] = target_name
        elif by_name and by_name != place:
            resolved[place] = by_name
        else:
            resolved[place] = target_name or by_name or place
    return resolved


def _format_cohort_label(cohort: AlignedCohort) -> str:
    """Names a cohort's variable with its reference date."""
    return f"{cohort.variable_name} on {cohort.reference_date}"


def _validate_pairing_parameters(
    target: CohortInput,
    by: CohortInput,
    *,
    min_coverage: float,
) -> PairingRefusal | None:
    """Validates `min_coverage` and checks that `target` and `by` differ."""
    prior_caveats = _collect_aligned_caveats(target, by)
    agreed_coverage = _resolve_agreed_coverage(target, by)
    if (
        isinstance(min_coverage, bool)
        or not isinstance(min_coverage, (int, float))
        or not math.isfinite(min_coverage)
    ):
        return PairingRefusal(
            reason="invalid_parameters",
            caveats=(
                *prior_caveats,
                f"The minimum coverage must be between 0 and 1, not "
                f"{min_coverage!r}.",
            ),
            coverage=agreed_coverage,
        )
    coverage_error = validate_alignment_parameters(min_coverage=min_coverage)
    if coverage_error is not None:
        return PairingRefusal(
            reason="invalid_parameters",
            caveats=(*prior_caveats, coverage_error),
            coverage=agreed_coverage,
        )
    if target.variable_dcid == by.variable_dcid:
        return PairingRefusal(
            reason="invalid_parameters",
            caveats=(
                *prior_caveats,
                "target and by must be different variables, but "
                f"{target.variable_dcid} was given for both.",
            ),
            coverage=agreed_coverage,
        )
    return None


def _align_cohort_side(
    item: CohortInput,
    other: CohortInput,
    *,
    date: str | None,
    min_coverage: float,
    side: PairingSide,
    prior_caveats: Sequence[str] = (),
) -> AlignedCohort | PairingRefusal:
    """Aligns one input on its own date; an aligned cohort passes through."""
    if date is not None and not is_valid_observation_date(date):
        return PairingRefusal(
            reason="invalid_parameters",
            caveats=(
                *prior_caveats,
                f"The {side} date {date!r} is not a year, a year and month, "
                "or a full date.",
            ),
            side=side,
            coverage=(
                item.coverage if isinstance(item, AlignedCohort) else None
            ),
        )
    if isinstance(item, AlignedCohort):
        if date is not None and date != item.reference_date:
            return PairingRefusal(
                reason="invalid_parameters",
                caveats=(
                    *prior_caveats,
                    f"The {side} cohort ({item.variable_name}) is aligned to "
                    f"{item.reference_date}, so it cannot be paired on the "
                    f"{side} date {date}.",
                ),
                side=side,
                coverage=item.coverage,
            )
        return item
    table = _resolve_table_requested_places(item, other)
    aligned = align_cohort(table, target_date=date, min_coverage=min_coverage)
    if isinstance(aligned, AlignmentRefusal):
        return PairingRefusal(
            reason=aligned.reason,
            caveats=(
                *prior_caveats,
                f"The {side} cohort ({item.variable_name}) could not be "
                f"aligned: {aligned.message}",
            ),
            side=side,
            coverage=aligned.coverage,
        )
    return aligned


def _build_paired_cohort(
    aligned_target: AlignedCohort,
    aligned_by: AlignedCohort,
    *,
    min_coverage: float,
) -> PairedCohort | PairingRefusal:
    """Joins two aligned cohorts on shared places and checks coverage."""
    target_rows = {row.place_dcid: row for row in aligned_target.rows}
    by_rows = {row.place_dcid: row for row in aligned_by.rows}
    shared = sorted(target_rows.keys() & by_rows.keys())
    prior_caveats = _collect_aligned_caveats(aligned_target, aligned_by)
    if not shared:
        return PairingRefusal(
            reason="no_observations",
            caveats=(
                *prior_caveats,
                "No place has a value for both "
                f"{_format_cohort_label(aligned_target)} and "
                f"{_format_cohort_label(aligned_by)}.",
            ),
        )
    for cohort, other in (
        (aligned_target, aligned_by),
        (aligned_by, aligned_target),
    ):
        if not has_adequate_coverage(
            len(shared), len(cohort.rows), min_coverage
        ):
            verb = conjugate_have(len(shared))
            return PairingRefusal(
                reason="insufficient_coverage",
                caveats=(
                    *prior_caveats,
                    f"Only {len(shared)} of the {len(cohort.rows)} places "
                    f"with a value for {_format_cohort_label(cohort)} also "
                    f"{verb} a value for {_format_cohort_label(other)}, below "
                    f"the required {format_percent(min_coverage)} coverage.",
                ),
            )
    place_names = _resolve_place_names(aligned_target, aligned_by)
    return PairedCohort(
        target=aligned_target,
        by=aligned_by,
        places=tuple(
            PairedPlace(
                place_dcid=place,
                place_name=place_names.get(place, place),
                target_value=target_rows[place].value,
                by_value=by_rows[place].value,
            )
            for place in shared
        ),
        target_only_places=tuple(sorted(target_rows.keys() - by_rows.keys())),
        by_only_places=tuple(sorted(by_rows.keys() - target_rows.keys())),
        provenance=merge_provenance(
            aligned_target.provenance, aligned_by.provenance
        ),
    )


def pair_cohorts(
    target: CohortInput,
    by: CohortInput,
    *,
    target_date: str | None = None,
    by_date: str | None = None,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> PairedCohort | PairingRefusal:
    """Aligns two variables on their own dates and joins them on place.

    A table is aligned with `align_cohort` on its own date argument; when a
    table omits `requested_places` and the other input carries an explicit
    target-place list, that list is used as the fallback. An aligned cohort
    is used as it is when its date argument is None or matches its
    `reference_date`. The join keeps the places with a value in both cohorts.
    It must hold at least `min_coverage` of each cohort's places, so swapping
    `target` and `by` never changes whether a pair passes.

    Args:
        target: The variable to summarize, as a table or an aligned cohort.
        by: The variable to order the places by, in the same forms.
        target_date: Optional reference date for `target`.
        by_date: Optional reference date for `by`.
        min_coverage: The share of each side's places, at alignment and
            after the join, that must remain; must lie in `[0.0, 1.0]`.

    Returns:
        The paired cohort, or a `PairingRefusal`: with `invalid_parameters`
        when `min_coverage` is outside `[0.0, 1.0]`, `target` and `by`
        measure the same variable, a date is not a valid observation date, or
        a date differs from an aligned input's `reference_date`; with the
        alignment's reason when a side cannot be aligned; with
        `no_observations` when the two cohorts share no place; and with
        `insufficient_coverage` when the shared places are fewer than
        `min_coverage` of either cohort.

    Raises:
        ValueError: Never raised directly; invalid parameters are returned as
            a `PairingRefusal` with reason `"invalid_parameters"`.
    """
    parameter_refusal = _validate_pairing_parameters(
        target, by, min_coverage=min_coverage
    )
    if parameter_refusal is not None:
        return parameter_refusal
    initial_caveats = _collect_aligned_caveats(target, by)
    aligned_target = _align_cohort_side(
        target,
        by,
        date=target_date,
        min_coverage=min_coverage,
        side="target",
        prior_caveats=initial_caveats,
    )
    if isinstance(aligned_target, PairingRefusal):
        return aligned_target
    aligned_by = _align_cohort_side(
        by,
        target,
        date=by_date,
        min_coverage=min_coverage,
        side="by",
        prior_caveats=_collect_aligned_caveats(aligned_target, by),
    )
    if isinstance(aligned_by, PairingRefusal):
        return aligned_by
    return _build_paired_cohort(
        aligned_target, aligned_by, min_coverage=min_coverage
    )


def _validate_relation_parameters(
    target: CohortInput,
    by: CohortInput,
    *,
    n: int,
    step_id: str,
) -> RefusedScriptResult | None:
    """Validates `n` before pairing `target` and `by`."""
    if isinstance(n, bool) or not isinstance(n, int) or n < _MIN_GROUP_SIZE:
        return build_invalid_parameters_refusal(
            (target, by),
            script=_SCRIPT_NAME,
            step_id=step_id,
            caveat=(
                "The group size must be an integer of at least "
                f"{_MIN_GROUP_SIZE}, not {n!r}."
            ),
        )
    return None


def _build_pairing_refusal_result(
    target: CohortInput,
    by: CohortInput,
    refusal: PairingRefusal,
    *,
    step_id: str,
) -> RefusedScriptResult:
    """Converts a `PairingRefusal` into a `RefusedScriptResult`."""
    result = build_refusal(
        (target, by),
        script=_SCRIPT_NAME,
        step_id=step_id,
        reason=refusal.reason,
        coverage=refusal.coverage,
        caveat=refusal.caveats[-1],
    )
    # `build_refusal` only collects caveats from inputs that were already
    # `AlignedCohort` instances at the boundary, whereas `refusal.caveats`
    # also carries caveats from any `ObservationTable` aligned during pairing
    # in `(target, by)` order.
    return replace(result, caveats=refusal.caveats)


def _rank_shared_places(
    paired: PairedCohort, *, step_id: str
) -> RankingMetrics:
    """Ranks the shared places of `paired` by their `by` values.

    Raises:
        ValueError: If `paired` has fewer than `MIN_SHARED_PLACES` shared
            places.
        RuntimeError: If `rank_cohort` refuses the aligned shared places.
    """
    shared = len(paired.places)
    if shared < MIN_SHARED_PLACES:
        raise ValueError(
            f"At least {MIN_SHARED_PLACES} shared places are required, "
            f"not {shared}."
        )
    shared_places = frozenset(place.place_dcid for place in paired.places)
    # Both groups come from a ranking of every shared place. Each end of that
    # ranking lists every shared place, so the two ends hold the same places
    # in opposite orders; the lowest group leaves out the places of the
    # highest group, and because the group size is at most half the shared
    # places, enough places remain.
    ranking = rank_cohort(
        replace(
            paired.by,
            rows=tuple(
                row for row in paired.by.rows if row.place_dcid in shared_places
            ),
        ),
        max_entries_per_end=shared,
        step_id=step_id,
    )
    if not isinstance(ranking.metrics, RankingMetrics):
        raise RuntimeError(
            f"Ranking {shared} aligned places refused unexpectedly: "
            f"{ranking.refusal_reason}."
        )
    return ranking.metrics


def _select_group_entries(
    ranking: RankingMetrics, *, group_size: int
) -> tuple[tuple[RankEntry, ...], tuple[RankEntry, ...]]:
    """Selects disjoint highest and lowest `by` groups of `group_size`.

    Raises:
        ValueError: If `group_size` is below `_MIN_GROUP_SIZE` or more than
            half of the ranked places.
    """
    if group_size < _MIN_GROUP_SIZE:
        raise ValueError(
            f"The group size must be at least {_MIN_GROUP_SIZE}, "
            f"not {group_size}."
        )
    if group_size * _GROUP_COUNT > len(ranking.top_n):
        raise ValueError(
            f"Two disjoint groups of {group_size} require at least "
            f"{group_size * _GROUP_COUNT} ranked places, not "
            f"{len(ranking.top_n)}."
        )
    highest_entries = ranking.top_n[:group_size]
    highest_places = {entry.place_dcid for entry in highest_entries}
    # `ranking.bottom_n` is already ordered ascending from smallest `by` value.
    lowest_entries = tuple(
        entry
        for entry in ranking.bottom_n
        if entry.place_dcid not in highest_places
    )[:group_size]
    return highest_entries, lowest_entries


def _compute_finite_mean(values: Sequence[float]) -> float | None:
    """Returns the arithmetic mean of `values`, or None on float overflow.

    Raises:
        ValueError: If `values` is empty.
    """
    if not values:
        raise ValueError("Cannot compute the mean of an empty sequence.")
    try:
        mean = statistics.fmean(values)
    except OverflowError:
        return None
    return mean if math.isfinite(mean) else None


def _compute_finite_median(values: Sequence[float]) -> float | None:
    """Returns the median of `values`, or None on float overflow.

    Raises:
        ValueError: If `values` is empty.
    """
    if not values:
        raise ValueError("Cannot compute the median of an empty sequence.")
    median = statistics.median(values)
    return median if math.isfinite(median) else None


def _summarize_group(
    ranked: Sequence[RankEntry],
    paired_places: Mapping[str, PairedPlace],
) -> tuple[tuple[RelationEntry, ...], GroupSummary]:
    """Builds a group's entries and summarizes the target over them.

    Raises:
        ValueError: If `ranked` is empty or names a place absent from
            `paired_places`.
    """
    if not ranked:
        raise ValueError("A relation group must have at least one entry.")
    missing = [
        entry.place_dcid
        for entry in ranked
        if entry.place_dcid not in paired_places
    ]
    if missing:
        raise ValueError(
            f"Ranked places missing from paired cohort: {missing}."
        )
    entries = tuple(
        RelationEntry(
            rank=entry.rank,
            is_tied=entry.is_tied,
            place_dcid=entry.place_dcid,
            place_name=paired_places[entry.place_dcid].place_name,
            by_value=entry.value,
            target_value=paired_places[entry.place_dcid].target_value,
        )
        for entry in ranked
    )
    values = [entry.target_value for entry in entries]
    return entries, GroupSummary(
        count=len(values),
        target_mean=_compute_finite_mean(values),
        target_median=_compute_finite_median(values),
    )


def _compute_mean_difference(
    highest_summary: GroupSummary, lowest_summary: GroupSummary
) -> float | None:
    """Returns `highest_mean - lowest_mean`, or None when not finite."""
    if (
        highest_summary.target_mean is None
        or lowest_summary.target_mean is None
    ):
        return None
    difference = highest_summary.target_mean - lowest_summary.target_mean
    return difference if math.isfinite(difference) else None


def _describe_dropped_places(
    cohort: AlignedCohort,
    other: AlignedCohort,
    dropped: tuple[str, ...],
    place_names: Mapping[str, str],
) -> str:
    """Counts the places of `cohort` that `other` lacks, naming examples.

    The clause names `other`'s reference date, because a dropped place can
    hold values for that variable on other dates.

    Raises:
        ValueError: If `dropped` is empty.
    """
    if not dropped:
        raise ValueError("dropped must not be empty.")
    listed = format_place_names(
        [place_names.get(place, place) for place in dropped]
    )
    noun = "place" if len(dropped) == 1 else "places"
    verb = conjugate_have(len(dropped))
    return (
        f"{len(dropped)} {noun} with a value for {cohort.variable_name} "
        f"{verb} no value for {_format_cohort_label(other)} ({listed})"
    )


def _build_pairing_caveats(paired: PairedCohort) -> list[str]:
    """States the reference dates when they differ, and the dropped places."""
    target, by = paired.target, paired.by
    caveats: list[str] = []
    if target.reference_date != by.reference_date:
        caveats.append(
            f"{target.variable_name} is compared on {target.reference_date} "
            f"and {by.variable_name} on {by.reference_date}, the reference "
            "date of each cohort."
        )
    place_names = _resolve_place_names(target, by)
    clauses = [
        _describe_dropped_places(cohort, other, dropped, place_names)
        for cohort, other, dropped in (
            (target, by, paired.target_only_places),
            (by, target, paired.by_only_places),
        )
        if dropped
    ]
    if clauses:
        caveats.append(
            "Only places with a value for both variables are compared: "
            + "; ".join(clauses)
            + "."
        )
    return caveats


def _build_relation_caveats(
    paired: PairedCohort,
    *,
    n: int,
    group_size: int,
    highest_summary: GroupSummary,
    lowest_summary: GroupSummary,
    target_mean_difference: float | None,
) -> tuple[str, ...]:
    """Builds the ordered caveats for a `relate_cohorts` result."""
    caveats = list(_collect_aligned_caveats(paired.target, paired.by))
    caveats.extend(_build_pairing_caveats(paired))
    shared = len(paired.places)
    if group_size < n:
        caveats.append(
            f"Each group holds {group_size} places instead of {n}, at most "
            f"half of the {shared} shared places, so that the two groups do "
            "not overlap."
        )
    has_non_finite_summary = any(
        figure is None
        for figure in (
            highest_summary.target_mean,
            highest_summary.target_median,
            lowest_summary.target_mean,
            lowest_summary.target_median,
            target_mean_difference,
        )
    )
    if has_non_finite_summary:
        caveats.append(
            f"Some summary statistics for {paired.target.variable_name} "
            "exceeded the floating-point range and are reported as None."
        )
    return tuple(caveats)


def _describe_methodology(paired: PairedCohort, *, group_size: int) -> str:
    """Returns the methodology sentence for `relate_cohorts`."""
    shared = len(paired.places)
    target_name = paired.target.variable_name
    by_name = paired.by.variable_name
    return (
        f"Paired the {shared} places with a value for both "
        f"{_format_cohort_label(paired.target)} and "
        f"{_format_cohort_label(paired.by)}, ranked them by {by_name} in "
        "descending order with places of the same value sharing a rank, and "
        f"summarized {target_name} over the {group_size} places with the "
        f"highest and the {group_size} with the lowest {by_name}."
    )


def _build_relation_result(
    paired: PairedCohort,
    *,
    n: int,
    group_size: int,
    highest_by: tuple[RelationEntry, ...],
    lowest_by: tuple[RelationEntry, ...],
    highest_summary: GroupSummary,
    lowest_summary: GroupSummary,
    target_mean_difference: float | None,
    caveats: tuple[str, ...],
    step_id: str,
) -> OkScriptResult:
    """Builds the `OkScriptResult` for `relate_cohorts`."""
    provenance = merge_provenance(
        paired.provenance,
        methodology=_describe_methodology(paired, group_size=group_size),
    )
    variable_names: dict[str, str] = {
        paired.target.variable_dcid: paired.target.variable_name,
    }
    variable_names.setdefault(paired.by.variable_dcid, paired.by.variable_name)
    return OkScriptResult(
        step_id=step_id,
        script=_SCRIPT_NAME,
        variables=tuple(variable_names),
        variable_names=variable_names,
        unit=paired.target.unit,
        scaling_factor=paired.target.scaling_factor,
        provenance=provenance,
        metrics=RelationMetrics(
            target_variable_dcid=paired.target.variable_dcid,
            target_reference_date=paired.target.reference_date,
            target_unit=paired.target.unit,
            target_scaling_factor=paired.target.scaling_factor,
            target_contributing_places=(
                paired.target.coverage.contributing_places
            ),
            target_requested_places=paired.target.coverage.requested_places,
            by_variable_dcid=paired.by.variable_dcid,
            by_reference_date=paired.by.reference_date,
            by_unit=paired.by.unit,
            by_scaling_factor=paired.by.scaling_factor,
            by_contributing_places=paired.by.coverage.contributing_places,
            by_requested_places=paired.by.coverage.requested_places,
            shared_place_count=len(paired.places),
            target_only_place_count=len(paired.target_only_places),
            by_only_place_count=len(paired.by_only_places),
            n=n,
            group_size=group_size,
            highest_by=highest_by,
            lowest_by=lowest_by,
            highest_by_summary=highest_summary,
            lowest_by_summary=lowest_summary,
            target_mean_difference=target_mean_difference,
        ),
        caveats=caveats,
    )


def relate_cohorts(
    target: CohortInput,
    by: CohortInput,
    *,
    n: int = DEFAULT_MAX_ENTRIES_PER_END,
    target_date: str | None = None,
    by_date: str | None = None,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
    step_id: str = "s1",
) -> ScriptResult:
    """Summarizes `target` over the places with the highest and lowest `by`.

    The two inputs are paired with `pair_cohorts`. The shared places are
    ranked by their `by` value with the rules of `rank_cohort` (competition
    ranks in descending order, ties ordered by place DCID and marked
    `is_tied`). The highest group is the start of `rank_cohort`'s leading
    order and the lowest group the start of its trailing order, leaving out
    any place already in the highest group, and each lists the group size,
    `min(n, shared // 2)`, so the groups never overlap. The groups are named
    by the `by` value rather than by a direction, because the places a
    question calls the poorest can hold the highest values of a poverty
    rate.

    Args:
        target: The variable to summarize, as a table or an aligned cohort.
        by: The variable to order the places by, in the same forms.
        n: The requested size of each group; must be an integer of at least
            1.
        target_date: Passed to `pair_cohorts`.
        by_date: Passed to `pair_cohorts`.
        min_coverage: Passed to `pair_cohorts`.
        step_id: Identifier of the analysis step (for example, `"s1"`).

    Returns:
        A result whose `metrics` is a `RelationMetrics` with both cohorts'
        variables, reference dates, units, scaling factors, and alignment
        coverage, the shared and dropped place counts, the `highest_by` and
        `lowest_by` entries, each group's count, mean, and median of
        `target` over its entries, and the highest group's target mean minus
        the lowest group's. Caveats state the alignments' qualifications,
        the reference dates when they differ, the places dropped from each
        side, any cap on the group size, and any summary figure omitted on
        floating-point overflow. The result is refused with
        `invalid_parameters` when `n` is not an integer of at least 1, when
        `target` and `by` measure the same variable, or when fewer than two
        places are shared, and with the pairing's reason when the inputs
        cannot be paired.

    Raises:
        RuntimeError: If ranking the aligned shared places fails
            unexpectedly.
    """
    parameter_refusal = _validate_relation_parameters(
        target, by, n=n, step_id=step_id
    )
    if parameter_refusal is not None:
        return parameter_refusal
    paired = pair_cohorts(
        target,
        by,
        target_date=target_date,
        by_date=by_date,
        min_coverage=min_coverage,
    )
    if isinstance(paired, PairingRefusal):
        return _build_pairing_refusal_result(
            target, by, paired, step_id=step_id
        )
    shared = len(paired.places)
    if shared < MIN_SHARED_PLACES:
        noun = "place" if shared == 1 else "places"
        verb = conjugate_have(shared)
        too_few_caveat = (
            f"Only {shared} {noun} {verb} a value for both "
            f"{_format_cohort_label(paired.target)} and "
            f"{_format_cohort_label(paired.by)}; two groups need at "
            f"least {MIN_SHARED_PLACES}."
        )
        refusal_caveats = (*_build_pairing_caveats(paired), too_few_caveat)
        return build_refusal(
            (paired.target, paired.by),
            script=_SCRIPT_NAME,
            step_id=step_id,
            reason="invalid_parameters",
            coverage=_resolve_agreed_coverage(paired.target, paired.by),
            caveat=refusal_caveats[0],
            extra_caveats=refusal_caveats[1:],
        )

    group_size = min(n, shared // _GROUP_COUNT)
    ranking = _rank_shared_places(paired, step_id=step_id)
    highest_entries, lowest_entries = _select_group_entries(
        ranking, group_size=group_size
    )
    paired_places = {place.place_dcid: place for place in paired.places}
    highest_by, highest_summary = _summarize_group(
        highest_entries, paired_places
    )
    lowest_by, lowest_summary = _summarize_group(lowest_entries, paired_places)
    target_mean_difference = _compute_mean_difference(
        highest_summary, lowest_summary
    )
    caveats = _build_relation_caveats(
        paired,
        n=n,
        group_size=group_size,
        highest_summary=highest_summary,
        lowest_summary=lowest_summary,
        target_mean_difference=target_mean_difference,
    )
    return _build_relation_result(
        paired,
        n=n,
        group_size=group_size,
        highest_by=highest_by,
        lowest_by=lowest_by,
        highest_summary=highest_summary,
        lowest_summary=lowest_summary,
        target_mean_difference=target_mean_difference,
        caveats=caveats,
        step_id=step_id,
    )
