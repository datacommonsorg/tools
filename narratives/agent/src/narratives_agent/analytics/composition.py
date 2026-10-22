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
"""Computes shares of a total and transitions across ordered stages.

Evaluates component shares (with unallocated remainders) or stage-to-stage
retention transitions across a shared reference date and compatible units.
"""

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from narratives_agent.analytics.alignment import (
    DEFAULT_MIN_COVERAGE,
    AlignedCohort,
    find_unit_mismatch,
    has_adequate_coverage,
    select_reference_date,
    validate_alignment_parameters,
)
from narratives_agent.analytics.digest import (
    PERCENT_SCALE,
    CoverageReport,
    OkScriptResult,
    RefusedScriptResult,
    ScriptResult,
    conjugate_have,
    format_percent,
    format_place_names,
)
from narratives_agent.analytics.metrics import (
    CompositionComponent,
    CompositionMetrics,
    CompositionMode,
    CompositionPlace,
    StageShare,
    StagesPlace,
    StageTransition,
)
from narratives_agent.analytics.provenance import merge_provenance
from narratives_agent.analytics.script_inputs import (
    CohortInput,
    build_invalid_parameters_refusal,
    build_refusal,
    resolve_target_places,
    validate_place_dcids,
)

__all__ = ["compute_composition"]

_SCRIPT_NAME: Literal["compute_composition"] = "compute_composition"
# Relative tolerance by which a component sum may exceed the total. It absorbs
# binary floating-point error in the sum; parts and a whole published
# separately and rounded at a coarser precision can exceed it and are refused.
_SUM_TOLERANCE = 1e-6
# Floats represent every integer below this magnitude exactly.
_MAX_EXACT_INTEGER = 2.0**53
# Stage transitions need a stage to move from and a stage to move to.
_MIN_STAGES = 2

# Maps each observation date to a place-to-value lookup for one input.
type _ValuesByDate = dict[str, dict[str, float]]


@dataclass(frozen=True)
class _AlignedInputs:
    """The inputs aligned to one shared reference date across target places."""

    reference_date: str
    complete_places: tuple[str, ...]
    total_values: dict[str, float]
    component_indexes: tuple[_ValuesByDate, ...]
    place_names: dict[str, str]
    coverage: CoverageReport


def _index_values_by_date(
    item: CohortInput, target_places: frozenset[str]
) -> _ValuesByDate:
    """Indexes an input's values by date and place within `target_places`.

    A place with several rows on one date keeps the last row in table
    order, as `align_cohort` does. An aligned cohort with no row for the
    target places yields an empty index, as a table without such rows does.
    """
    if isinstance(item, AlignedCohort):
        rows_by_place = {
            row.place_dcid: row.value
            for row in item.rows
            if row.place_dcid in target_places
        }
        return {item.reference_date: rows_by_place} if rows_by_place else {}
    values_by_date: _ValuesByDate = {}
    for row in item.rows:
        if row.place_dcid in target_places:
            values_by_date.setdefault(row.date, {})[row.place_dcid] = row.value
    return values_by_date


def _list_complete_places(
    indexes: Sequence[_ValuesByDate], target_places: Sequence[str], date: str
) -> tuple[str, ...]:
    """Returns the target places with a value in every input on `date`."""
    return tuple(
        place
        for place in target_places
        if all(place in index.get(date, {}) for index in indexes)
    )


def _select_shared_reference_date(
    indexes: Sequence[_ValuesByDate],
    target_places: Sequence[str],
    min_coverage: float,
) -> str | None:
    """Picks the most recent date with adequate complete-case coverage.

    A place counts toward a date only when every input has a value for it
    on that date. When no date reaches `min_coverage`, the date with the
    most complete places is chosen (most recent on a tie) so the refusal
    can report the best figure the inputs offer. Returns None when no input
    has any value for the target places.
    """
    dates = {date for index in indexes for date in index}
    if not dates:
        return None
    complete_counts = {
        date: len(_list_complete_places(indexes, target_places, date))
        for date in dates
    }
    return select_reference_date(
        complete_counts, len(target_places), min_coverage
    )


def _has_mixed_vintages(
    inputs: Sequence[CohortInput],
    indexes: Sequence[_ValuesByDate],
    target_places: frozenset[str],
) -> bool:
    """Returns whether the places' latest dates differ within or across inputs.

    An aligned cohort keeps only its reference date, so its own coverage
    report states whether its table had mixed vintages. That flag is
    carried only when every place of the cohort is a target place, because
    the cohort does not record which of its places had other vintages.
    """
    if any(
        isinstance(item, AlignedCohort)
        and item.coverage.mixed_vintages
        and target_places.issuperset(resolve_target_places(item))
        for item in inputs
    ):
        return True
    latest_dates: set[str] = set()
    for index in indexes:
        latest_by_place: dict[str, str] = {}
        for date, values in index.items():
            for place in values:
                latest_by_place[place] = max(
                    latest_by_place.get(place, ""), date
                )
        latest_dates.update(latest_by_place.values())
    return len(latest_dates) > 1


def _format_exact_value(value: float) -> str:
    """Formats a value with every significant digit.

    Integral values below 2**53 print as integers, so a population of
    10000005 is not rounded to `1e+07` as the `g` format would round it;
    other values print as `repr` does.
    """
    if value.is_integer() and abs(value) < _MAX_EXACT_INTEGER:
        return str(int(value))
    return repr(value)


def _compute_exact_sum(values: Sequence[float]) -> float | None:
    """Returns the sum of `values` rounded once, or None on float overflow.

    Summing in exact rational arithmetic and rounding once avoids the
    accumulated rounding drift of repeated floating-point addition and
    catches sums that exceed the largest finite float instead of returning
    `inf`.
    """
    try:
        total = float(sum(map(Fraction, values)))
    except OverflowError:
        return None
    return total if math.isfinite(total) else None


def _compute_share_percent(value: float, whole: float) -> float | None:
    """Returns `value` as a percentage of a positive `whole`, or None.

    The percentage is None when `whole` is zero or negative, or when the
    quotient is too large to represent as a float.
    """
    if whole <= 0.0:
        return None
    percent = value / whole * PERCENT_SCALE
    return percent if math.isfinite(percent) else None


def _compute_percent_change(from_value: float, to_value: float) -> float | None:
    """Returns the percentage change from `from_value` to `to_value`, or None.

    The percentage change is `(to_value - from_value) / abs(from_value) * 100`.
    It is None when `from_value` is zero or when the percentage is too large to
    represent as a float.
    """
    if from_value == 0.0:
        return None
    percent = (to_value - from_value) / abs(from_value) * PERCENT_SCALE
    return percent if math.isfinite(percent) else None


def _compute_retention_ratio(
    from_value: float, to_value: float
) -> float | None:
    """Returns `to_value / from_value` for a positive `from_value`, or None.

    The ratio is None when `from_value` is zero or negative, or when the
    quotient is too large to represent as a float.
    """
    if from_value <= 0.0:
        return None
    ratio = to_value / from_value
    return ratio if math.isfinite(ratio) else None


def _build_composition_place(
    place: str,
    place_name: str,
    components: Sequence[CohortInput],
    values: Sequence[float],
    component_sum: float,
    total_value: float | None,
) -> CompositionPlace:
    """Builds one place's shares of an explicit or implied total."""
    whole = total_value if total_value is not None else component_sum
    unallocated = (
        max(0.0, float(Fraction(total_value) - Fraction(component_sum)))
        if total_value is not None
        else 0.0
    )
    return CompositionPlace(
        place_dcid=place,
        place_name=place_name,
        total_value=total_value,
        component_sum=component_sum,
        components=tuple(
            CompositionComponent(
                variable_dcid=component.variable_dcid,
                variable_name=component.variable_name,
                value=value,
                share_pct=_compute_share_percent(value, whole),
            )
            for component, value in zip(components, values, strict=True)
        ),
        unallocated_value=unallocated,
        unallocated_share_pct=_compute_share_percent(unallocated, whole),
    )


def _build_stages_place(
    place: str,
    place_name: str,
    stages: Sequence[CohortInput],
    values: Sequence[float],
    total_value: float | None,
) -> StagesPlace:
    """Builds one place's stage shares and stage-to-stage transitions.

    The caller guarantees at least `_MIN_STAGES` stages and finite
    stage-to-stage deltas.
    """
    first_stage_value = values[0]
    transitions: list[StageTransition] = []
    for index in range(1, len(stages)):
        from_value, to_value = values[index - 1], values[index]
        transitions.append(
            StageTransition(
                from_variable=stages[index - 1].variable_dcid,
                from_variable_name=stages[index - 1].variable_name,
                from_value=from_value,
                to_variable=stages[index].variable_dcid,
                to_variable_name=stages[index].variable_name,
                to_value=to_value,
                absolute_delta=to_value - from_value,
                percent_change=_compute_percent_change(from_value, to_value),
                retention_ratio=_compute_retention_ratio(from_value, to_value),
                retention_pct=_compute_share_percent(to_value, from_value),
            )
        )
    return StagesPlace(
        place_dcid=place,
        place_name=place_name,
        total_value=total_value,
        stages=tuple(
            StageShare(
                variable_dcid=stage.variable_dcid,
                variable_name=stage.variable_name,
                value=value,
                share_of_first_stage_pct=_compute_share_percent(
                    value, first_stage_value
                ),
                share_pct=(
                    _compute_share_percent(value, total_value)
                    if total_value is not None
                    else None
                ),
            )
            for stage, value in zip(stages, values, strict=True)
        ),
        transitions=tuple(transitions),
    )


def _validate_composition_parameters(
    all_inputs: tuple[CohortInput, ...],
    components: Sequence[CohortInput],
    *,
    mode: CompositionMode,
    places: Sequence[str] | None,
    target_date: str | None,
    min_coverage: float,
    step_id: str,
) -> RefusedScriptResult | None:
    """Checks parameters, unit compatibility, and aligned reference dates."""
    if not components:
        return build_invalid_parameters_refusal(
            all_inputs,
            script=_SCRIPT_NAME,
            step_id=step_id,
            caveat="At least one component variable is required.",
        )
    if mode == "stages" and len(components) < _MIN_STAGES:
        return build_invalid_parameters_refusal(
            all_inputs,
            script=_SCRIPT_NAME,
            step_id=step_id,
            caveat=(
                f"Stage transitions require at least {_MIN_STAGES} ordered "
                f"stages, not {len(components)}."
            ),
        )
    if places is not None:
        places_error = validate_place_dcids(places, parameter_name="places")
        if places_error is not None:
            return build_invalid_parameters_refusal(
                all_inputs,
                script=_SCRIPT_NAME,
                step_id=step_id,
                caveat=places_error,
            )
    alignment_error = validate_alignment_parameters(
        target_date=target_date, min_coverage=min_coverage
    )
    if alignment_error is not None:
        return build_invalid_parameters_refusal(
            all_inputs,
            script=_SCRIPT_NAME,
            step_id=step_id,
            caveat=alignment_error,
        )
    mismatch = find_unit_mismatch(*all_inputs)
    if mismatch is not None:
        return build_refusal(
            all_inputs,
            script=_SCRIPT_NAME,
            step_id=step_id,
            reason=mismatch.reason,
            coverage=None,
            caveat=mismatch.message,
        )
    repeated_dcids = [
        dcid
        for dcid, occurrence_count in Counter(
            item.variable_dcid for item in all_inputs
        ).items()
        if occurrence_count > 1
    ]
    if repeated_dcids:
        verb = "is" if len(repeated_dcids) == 1 else "are"
        return build_invalid_parameters_refusal(
            all_inputs,
            script=_SCRIPT_NAME,
            step_id=step_id,
            caveat=(
                "Each input must be a different variable, but "
                f"{', '.join(repeated_dcids)} {verb} given more than once."
            ),
        )
    fixed_dates = sorted(
        {
            item.reference_date
            for item in all_inputs
            if isinstance(item, AlignedCohort)
        }
    )
    if len(fixed_dates) > 1:
        return build_invalid_parameters_refusal(
            all_inputs,
            script=_SCRIPT_NAME,
            step_id=step_id,
            caveat=(
                "The aligned inputs are on different reference dates "
                f"({', '.join(fixed_dates)}), so they cannot be combined."
            ),
        )
    if (
        fixed_dates
        and target_date is not None
        and target_date != fixed_dates[0]
    ):
        return build_invalid_parameters_refusal(
            all_inputs,
            script=_SCRIPT_NAME,
            step_id=step_id,
            caveat=(
                f"The aligned inputs are on {fixed_dates[0]}, not on the "
                f"requested target date {target_date}."
            ),
        )
    return None


def _resolve_composition_places(
    all_inputs: Sequence[CohortInput],
    *,
    total: CohortInput | None,
    places: Sequence[str] | None,
) -> tuple[str, ...]:
    """Resolves the target places in report order."""
    if places:
        return tuple(dict.fromkeys(places))
    total_places = resolve_target_places(total) if total is not None else ()
    if total_places:
        return total_places
    return tuple(
        dict.fromkeys(
            place
            for item in all_inputs
            for place in resolve_target_places(item)
        )
    )


def _build_insufficient_coverage_message(
    coverage: CoverageReport,
    *,
    observed_dates: Sequence[str],
    target_date: str | None,
    min_coverage: float,
) -> str:
    """Returns the caveat sentence for an `insufficient_coverage` refusal."""
    if coverage.contributing_places == 0:
        if target_date is not None:
            # Dates match as exact strings, so a `target_date` of another
            # precision matches no row even when the period has values. A date
            # that overlaps the target period at another precision is the best
            # example; otherwise any date, when no row shares the precision.
            overlapping_dates = [
                date
                for date in observed_dates
                if len(date) != len(target_date)
                and (
                    date.startswith(target_date) or target_date.startswith(date)
                )
            ]
            precisions = {len(date) for date in observed_dates}
            if overlapping_dates or len(target_date) not in precisions:
                example = max(overlapping_dates or observed_dates)
                return (
                    f"The target date {target_date} does not match the "
                    f"precision of the input dates, such as {example}, so "
                    "no place can be aligned to it."
                )
        # No threshold is cited, because no place has a value to count.
        return f"No place has a value in every input ({coverage.describe()})."
    verb = conjugate_have(coverage.contributing_places)
    return (
        f"Only {coverage.describe()} {verb} a value in every input, below "
        f"the required {format_percent(min_coverage)} coverage."
    )


def _align_composition_inputs(
    all_inputs: tuple[CohortInput, ...],
    *,
    total: CohortInput | None,
    places: Sequence[str] | None,
    target_date: str | None,
    min_coverage: float,
    step_id: str,
) -> _AlignedInputs | RefusedScriptResult:
    """Aligns `all_inputs` to one shared reference date across target places."""
    fixed_dates = sorted(
        {
            item.reference_date
            for item in all_inputs
            if isinstance(item, AlignedCohort)
        }
    )
    target_places = _resolve_composition_places(
        all_inputs, total=total, places=places
    )
    if not target_places:
        return build_refusal(
            all_inputs,
            script=_SCRIPT_NAME,
            step_id=step_id,
            reason="no_observations",
            coverage=CoverageReport(
                contributing_places=0,
                requested_places=0,
                coverage_ratio=0.0,
                reference_date=(
                    target_date
                    if target_date is not None
                    else (fixed_dates[0] if fixed_dates else None)
                ),
            ),
            caveat=(
                "No places were requested and no input holds an observation."
            ),
        )
    target_place_set = frozenset(target_places)
    indexes = tuple(
        _index_values_by_date(item, target_place_set) for item in all_inputs
    )
    if target_date is not None:
        reference_date: str | None = target_date
    elif fixed_dates:
        reference_date = fixed_dates[0]
    else:
        reference_date = _select_shared_reference_date(
            indexes, target_places, min_coverage
        )
    if reference_date is None or not any(indexes):
        empty_coverage = CoverageReport(
            contributing_places=0,
            requested_places=len(target_places),
            coverage_ratio=0.0,
            reference_date=reference_date,
            missing_places=target_places,
        )
        return build_refusal(
            all_inputs,
            script=_SCRIPT_NAME,
            step_id=step_id,
            reason="no_observations",
            coverage=empty_coverage,
            caveat=(
                "None of the inputs has an observation for any of the "
                f"requested places ({empty_coverage.describe()})."
            ),
        )
    complete_places = _list_complete_places(
        indexes, target_places, reference_date
    )
    complete_place_set = frozenset(complete_places)
    coverage = CoverageReport(
        contributing_places=len(complete_places),
        requested_places=len(target_places),
        coverage_ratio=len(complete_places) / len(target_places),
        reference_date=reference_date,
        missing_places=tuple(
            place for place in target_places if place not in complete_place_set
        ),
        mixed_vintages=_has_mixed_vintages(
            all_inputs, indexes, target_place_set
        ),
    )
    if not complete_places or not has_adequate_coverage(
        len(complete_places), len(target_places), min_coverage
    ):
        observed_dates = sorted({date for index in indexes for date in index})
        return build_refusal(
            all_inputs,
            script=_SCRIPT_NAME,
            step_id=step_id,
            reason="insufficient_coverage",
            coverage=coverage,
            caveat=_build_insufficient_coverage_message(
                coverage,
                observed_dates=observed_dates,
                target_date=target_date,
                min_coverage=min_coverage,
            ),
        )
    place_names: dict[str, str] = {}
    for item in all_inputs:
        for place, name in item.place_names.items():
            place_names.setdefault(place, name)
    return _AlignedInputs(
        reference_date=reference_date,
        complete_places=complete_places,
        total_values=indexes[0][reference_date] if total is not None else {},
        component_indexes=indexes[1:] if total is not None else indexes,
        place_names=place_names,
        coverage=coverage,
    )


def _evaluate_composition_places(
    aligned: _AlignedInputs,
    all_inputs: tuple[CohortInput, ...],
    components: Sequence[CohortInput],
    *,
    total: CohortInput | None,
    step_id: str,
) -> tuple[CompositionPlace, ...] | RefusedScriptResult:
    """Checks non-negativity and disjointness and builds `CompositionPlace`s."""
    entries: list[CompositionPlace] = []
    for place in aligned.complete_places:
        values = [
            index[aligned.reference_date][place]
            for index in aligned.component_indexes
        ]
        total_value = aligned.total_values[place] if total is not None else None
        place_name = aligned.place_names.get(place, place)
        named_values = list(zip(components, values, strict=True))
        if total is not None and total_value is not None:
            named_values.insert(0, (total, total_value))
        negative_names = [
            item.variable_name for item, value in named_values if value < 0.0
        ]
        if negative_names:
            verb = "is" if len(negative_names) == 1 else "are"
            return build_refusal(
                all_inputs,
                script=_SCRIPT_NAME,
                step_id=step_id,
                reason="invalid_parameters",
                coverage=aligned.coverage,
                caveat=(
                    f"{', '.join(negative_names)} {verb} negative for "
                    f"{place_name} on {aligned.reference_date}; shares of a "
                    "total require non-negative values."
                ),
            )
        component_sum = _compute_exact_sum(values)
        if component_sum is None:
            return build_refusal(
                all_inputs,
                script=_SCRIPT_NAME,
                step_id=step_id,
                reason="invalid_parameters",
                coverage=aligned.coverage,
                caveat=(
                    f"The components of {place_name} on "
                    f"{aligned.reference_date} sum to a value too large to "
                    "represent as a float."
                ),
            )
        if total_value is not None and Fraction(component_sum) > Fraction(
            total_value
        ) * (1 + Fraction(_SUM_TOLERANCE)):
            return build_refusal(
                all_inputs,
                script=_SCRIPT_NAME,
                step_id=step_id,
                reason="components_exceed_total",
                coverage=aligned.coverage,
                caveat=(
                    f"The components of {place_name} sum to "
                    f"{_format_exact_value(component_sum)} on "
                    f"{aligned.reference_date}, more than the total of "
                    f"{_format_exact_value(total_value)}, so they are not "
                    "disjoint parts of it."
                ),
            )
        entries.append(
            _build_composition_place(
                place,
                place_name,
                components,
                values,
                component_sum,
                total_value,
            )
        )
    return tuple(entries)


def _evaluate_stages_places(
    aligned: _AlignedInputs,
    all_inputs: tuple[CohortInput, ...],
    components: Sequence[CohortInput],
    *,
    total: CohortInput | None,
    step_id: str,
) -> tuple[StagesPlace, ...] | RefusedScriptResult:
    """Checks stage deltas for overflow and builds `StagesPlace` entries."""
    entries: list[StagesPlace] = []
    for place in aligned.complete_places:
        values = [
            index[aligned.reference_date][place]
            for index in aligned.component_indexes
        ]
        total_value = aligned.total_values[place] if total is not None else None
        place_name = aligned.place_names.get(place, place)
        for index in range(1, len(components)):
            if not math.isfinite(values[index] - values[index - 1]):
                from_name = components[index - 1].variable_name
                to_name = components[index].variable_name
                return build_refusal(
                    all_inputs,
                    script=_SCRIPT_NAME,
                    step_id=step_id,
                    reason="invalid_parameters",
                    coverage=aligned.coverage,
                    caveat=(
                        f"The change from {from_name} to {to_name} for "
                        f"{place_name} on {aligned.reference_date} is too "
                        "large to represent as a float."
                    ),
                )
        entries.append(
            _build_stages_place(
                place, place_name, components, values, total_value
            )
        )
    return tuple(entries)


def _has_overflowed_stage_figure(entry: StagesPlace) -> bool:
    """Returns whether any share or transition figure in `entry` overflowed."""
    first_stage_value = entry.stages[0].value
    if first_stage_value > 0.0 and any(
        stage.share_of_first_stage_pct is None for stage in entry.stages
    ):
        return True
    if (
        entry.total_value is not None
        and entry.total_value > 0.0
        and any(stage.share_pct is None for stage in entry.stages)
    ):
        return True
    for transition in entry.transitions:
        if transition.from_value != 0.0 and transition.percent_change is None:
            return True
        if transition.from_value > 0.0 and (
            transition.retention_ratio is None
            or transition.retention_pct is None
        ):
            return True
    return False


def _build_composition_caveats(
    coverage: CoverageReport,
    entries: Sequence[CompositionPlace] | Sequence[StagesPlace],
    *,
    mode: CompositionMode,
    has_explicit_total: bool,
    has_explicit_date: bool,
) -> tuple[str, ...]:
    """Builds the alignment, missing-place, and mode-specific caveats."""
    caveats: list[str] = []
    if coverage.mixed_vintages:
        if has_explicit_date:
            caveats.append(
                "The inputs report different latest observation dates; "
                "every value is aligned to the requested date "
                f"{coverage.reference_date}."
            )
        else:
            caveats.append(
                "The inputs report different latest observation dates, so "
                f"every value is aligned to {coverage.reference_date}."
            )
    if coverage.missing_places:
        verb = conjugate_have(coverage.contributing_places)
        caveats.append(
            f"{coverage.describe()} {verb} a value in every input; the "
            "rest are left out."
        )
    if mode == "composition" and not has_explicit_total:
        caveats.append(
            "No separate total variable was provided, so shares are computed "
            "relative to the sum of the supplied components and the "
            "unallocated remainder is zero by construction."
        )
    overflow_places = [
        entry.place_name
        for entry in entries
        if isinstance(entry, StagesPlace)
        and _has_overflowed_stage_figure(entry)
    ]
    if overflow_places:
        caveats.append(
            "One or more stage shares or transition ratios are undefined "
            f"for {format_place_names(overflow_places)} because they are "
            "too large to represent."
        )
    return tuple(caveats)


def _describe_methodology(
    components: Sequence[CohortInput],
    *,
    total: CohortInput | None,
    mode: CompositionMode,
    reference_date: str,
    place_count: int,
) -> str:
    """Describes the composition or stages computation for the provenance."""
    component_names = ", ".join(item.variable_name for item in components)
    place_noun = "place" if place_count == 1 else "places"
    if mode == "stages":
        return (
            f"Stage-to-stage transitions across {component_names} on "
            f"{reference_date}: absolute delta, percentage change, and "
            "retention ratio between consecutive stages, with each stage as "
            f"a share of {components[0].variable_name}; computed for "
            f"{place_count} {place_noun}."
        )
    if total is None:
        return (
            f"Shares of the sum of {component_names} on {reference_date}: "
            "each component's value divided by the sum of the supplied "
            f"components; computed for {place_count} {place_noun}."
        )
    return (
        f"Shares of {total.variable_name} on {reference_date}: each "
        "component's value divided by the total, with the remainder the "
        f"components leave unallocated; computed for {place_count} "
        f"{place_noun}."
    )


def compute_composition(
    components: Sequence[CohortInput],
    *,
    total: CohortInput | None = None,
    mode: CompositionMode = "composition",
    places: Sequence[str] | None = None,
    target_date: str | None = None,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
    step_id: str = "s1",
) -> ScriptResult:
    """Computes component shares of a total, or transitions across stages.

    Args:
        components: The component variables of a whole, or the ordered
            stages, each a table or an aligned cohort.
        total: The denominator total. In `composition` mode the shares are
            of this total when given and of the components' sum otherwise;
            in `stages` mode each stage is also reported as a share of it.
        mode: `composition` for shares and the unallocated remainder, or
            `stages` for stage-to-stage transitions.
        places: The target places, in the order to report them. When empty,
            the target places are the total's when a total is given, and
            otherwise the union of every input's requested or observed
            places. An aligned cohort does not carry a requested order, so
            the places it contributes are in DCID order, followed by the
            places its coverage reports as missing.
        target_date: The date to evaluate every input on, matched as an
            exact date string. When None, the most recent date on which at
            least `min_coverage` of the target places have a value in every
            input is selected.
        min_coverage: The minimum share of the target places, in
            `[0.0, 1.0]`, that must have a value in every input on the
            reference date. It is checked even when `target_date` is given
            or the inputs are aligned cohorts.
        step_id: Identifier of the analysis step (for example, `"s1"`).

    Returns:
        A result whose `metrics` is a `CompositionMetrics` instance holding
        `reference_date`, `mode`, `has_explicit_total`, `total_variable_dcid`,
        `component_variable_dcids`, `place_count`, `places` (one
        `CompositionPlace` or `StagesPlace` per complete place: in
        `composition` mode its `total_value`, `component_sum`, `components`
        with `share_pct`, `unallocated_value`, and `unallocated_share_pct`;
        in `stages` mode its `stages` with `share_of_first_stage_pct` and
        `share_pct`, and its `transitions` with `absolute_delta`,
        `percent_change`, `retention_ratio`, and `retention_pct`), and
        `missing_places`. The result is refused with `invalid_parameters`
        when there are no components, fewer than two stages in `stages`
        mode, `places` passed as a string or holding an invalid DCID, a
        malformed `target_date`, a `min_coverage` outside `[0.0, 1.0]`, the
        same variable given as more than one input, pre-aligned inputs on
        different dates or on a date other than `target_date`, a negative
        value or a component sum that overflows a float in `composition`
        mode, or a stage delta that overflows a float in `stages` mode; with
        `unit_mismatch` or `scaling_mismatch` when the inputs disagree; with
        `components_exceed_total` when a place's components sum to more than
        its total; with `no_observations` when no input has a value for any
        target place; and with `insufficient_coverage` when the places with
        a value in every input on the reference date, whether selected,
        given as `target_date`, or fixed by aligned inputs, fall below
        `min_coverage`.
    """
    all_inputs: tuple[CohortInput, ...] = (
        (total, *components) if total is not None else tuple(components)
    )
    parameter_refusal = _validate_composition_parameters(
        all_inputs,
        components,
        mode=mode,
        places=places,
        target_date=target_date,
        min_coverage=min_coverage,
        step_id=step_id,
    )
    if parameter_refusal is not None:
        return parameter_refusal

    aligned = _align_composition_inputs(
        all_inputs,
        total=total,
        places=places,
        target_date=target_date,
        min_coverage=min_coverage,
        step_id=step_id,
    )
    if isinstance(aligned, RefusedScriptResult):
        return aligned

    entries = (
        _evaluate_composition_places(
            aligned, all_inputs, components, total=total, step_id=step_id
        )
        if mode == "composition"
        else _evaluate_stages_places(
            aligned, all_inputs, components, total=total, step_id=step_id
        )
    )
    if isinstance(entries, RefusedScriptResult):
        return entries

    caveats = _build_composition_caveats(
        aligned.coverage,
        entries,
        mode=mode,
        has_explicit_total=total is not None,
        has_explicit_date=target_date is not None,
    )
    methodology = _describe_methodology(
        components,
        total=total,
        mode=mode,
        reference_date=aligned.reference_date,
        place_count=len(aligned.complete_places),
    )
    return OkScriptResult(
        step_id=step_id,
        script=_SCRIPT_NAME,
        variables=tuple(item.variable_dcid for item in all_inputs),
        variable_names={
            item.variable_dcid: item.variable_name for item in all_inputs
        },
        unit=all_inputs[0].unit,
        scaling_factor=all_inputs[0].scaling_factor,
        coverage=aligned.coverage,
        provenance=merge_provenance(
            *(item.provenance for item in all_inputs), methodology=methodology
        ),
        metrics=CompositionMetrics(
            reference_date=aligned.reference_date,
            mode=mode,
            has_explicit_total=total is not None,
            total_variable_dcid=(
                total.variable_dcid if total is not None else None
            ),
            component_variable_dcids=tuple(
                item.variable_dcid for item in components
            ),
            place_count=len(aligned.complete_places),
            places=entries,
            missing_places=aligned.coverage.missing_places,
        ),
        caveats=caveats,
    )
