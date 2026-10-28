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
"""Derives one observation table from two by joining on place and date.

Joins two `ObservationTable` inputs on `(place, date)`, applies `per_capita`,
`ratio`, `difference`, `sum`, or `pct_change`, and merges composite provenance.
"""

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from narratives_agent.analytics.alignment import (
    find_unit_mismatch,
    has_adequate_coverage,
    validate_alignment_parameters,
)
from narratives_agent.analytics.digest import (
    PERCENT_SCALE,
    CoverageReport,
    OkScriptResult,
    RefusalReason,
    ScriptResult,
    conjugate_have,
    format_percent,
    format_place_names,
    format_scaling_factor,
)
from narratives_agent.analytics.metrics import (
    DerivedMetrics,
    DerivedOperation,
)
from narratives_agent.analytics.provenance import merge_provenance
from narratives_agent.analytics.script_inputs import (
    build_invalid_parameters_refusal,
    build_refusal,
    resolve_target_places,
    validate_place_dcids,
)
from narratives_agent.analytics.summarize import summarize_table
from narratives_agent.analytics.tables import (
    ObservationRow,
    ObservationTable,
    clean_display_name,
    is_inverted_date_range,
    is_valid_dcid,
    is_valid_observation_date,
    is_within_date_range,
)

__all__ = [
    "SCALED_OPERATIONS",
    "DerivedMetricOutcome",
    "compute_derived_metric",
    "derive_observation_table",
]

_SCRIPT_NAME: Literal["compute_derived_metric"] = "compute_derived_metric"
# Percentage changes always report `Percent` regardless of input units.
_PERCENT_UNIT = "Percent"
# A scaling factor that is absent means the values are not scaled.
_UNSCALED = 1.0
# Per-capita steps without an explicit scale try per-person (1), per-1,000, and
# per-100,000 in order, picking the smallest standard demographic multiplier
# that lifts the median non-zero magnitude to at least 1.0 so rates read as
# whole or near-whole numbers rather than tiny decimals.
_PER_CAPITA_SCALES = (_UNSCALED, 1_000.0, 100_000.0)
_MIN_READABLE_PER_CAPITA_MEDIAN = 1.0

# Quotient operations accept an optional caller-supplied scale multiplier.
SCALED_OPERATIONS: frozenset[DerivedOperation] = frozenset(
    {"per_capita", "ratio"}
)
# Additive operations require both inputs to share a unit and scaling factor.
_UNIT_MATCHED_OPERATIONS: frozenset[DerivedOperation] = frozenset(
    {"difference", "sum", "pct_change"}
)
type _SkipReason = Literal[
    "non_positive_denominator",
    "zero_denominator",
    "zero_baseline",
    "not_finite",
]
# Maps each join skip reason to a prose template parameterized by `{right}`.
_SKIP_DESCRIPTIONS: dict[_SkipReason, str] = {
    "non_positive_denominator": "the denominator {right} is zero or negative",
    "zero_denominator": "the denominator {right} is zero",
    "zero_baseline": "the baseline {right} is zero",
    "not_finite": "the result is not a finite number",
}

_YEAR_DATE_CHARS = 4
_MONTH_DATE_CHARS = 7
_DAY_DATE_CHARS = 10

# Maps each date string length to its human-readable granularity name.
_GRANULARITY_NAMES = {
    _YEAR_DATE_CHARS: "annual (YYYY)",
    _MONTH_DATE_CHARS: "monthly (YYYY-MM)",
    _DAY_DATE_CHARS: "daily (YYYY-MM-DD)",
}


@dataclass(frozen=True)
class DerivedMetricOutcome:
    """The derived table and the result that describes it.

    Attributes:
        table: The derived `ObservationTable` when `result.status == "ok"`;
            None when `result` is a `RefusedScriptResult`.
        result: The `OkScriptResult` with `DerivedMetrics`, or a
            `RefusedScriptResult` when no table could be derived.
    """

    table: ObservationTable | None
    result: ScriptResult


def _resolve_operation(
    operation: DerivedOperation | str,
) -> DerivedOperation | None:
    """Narrows a validated operation string to `DerivedOperation`."""
    match operation:
        case "per_capita":
            return "per_capita"
        case "ratio":
            return "ratio"
        case "difference":
            return "difference"
        case "sum":
            return "sum"
        case "pct_change":
            return "pct_change"
        case _:
            return None


def _format_scale(scale: float) -> str:
    """Formats a positive finite scale for prose (`100,000` or `g`).

    Raises:
        ValueError: If `scale` is a boolean, not finite, or not above zero.
    """
    if isinstance(scale, bool) or not math.isfinite(scale) or scale <= 0.0:
        raise ValueError(
            f"The scale must be a finite number above zero, not {scale!r}."
        )
    return f"{int(scale):,}" if scale == int(scale) else f"{scale:g}"


def _resolve_table_scaling(table: ObservationTable) -> float:
    """Returns the table's scaling factor with "absent" read as unscaled."""
    return _UNSCALED if table.scaling_factor is None else table.scaling_factor


def _select_fitting_scale(per_person: Sequence[float]) -> float:
    """Returns the smallest per-capita scale that reads well for the values.

    The scale is the first of `_PER_CAPITA_SCALES` that puts the median
    non-zero magnitude at or above `_MIN_READABLE_PER_CAPITA_MEDIAN`, so GDP
    per person stays per person while crimes per person become crimes per
    1,000 people. When `per_person` is empty or every value is zero the
    values stay per person, and when even the largest scale leaves the
    median below one, the largest scale is used.
    """
    magnitudes = [
        abs(value)
        for value in per_person
        if value != 0.0 and math.isfinite(value)
    ]
    if not magnitudes:
        return _UNSCALED
    typical = statistics.median(magnitudes)
    for scale in _PER_CAPITA_SCALES:
        if typical * scale >= _MIN_READABLE_PER_CAPITA_MEDIAN:
            return scale
    return _PER_CAPITA_SCALES[-1]


def _build_default_name(
    left: ObservationTable,
    right: ObservationTable,
    operation: DerivedOperation,
    scale: float,
) -> str:
    """Returns a readable display name for the derived variable."""
    if operation == "per_capita":
        if scale == _UNSCALED:
            return f"{left.variable_name} per capita"
        return f"{left.variable_name} per {_format_scale(scale)} people"
    if operation == "ratio":
        if scale == PERCENT_SCALE:
            return (
                f"{left.variable_name} as a percentage of {right.variable_name}"
            )
        name = f"{left.variable_name} / {right.variable_name}"
        if scale != _UNSCALED:
            name += f", times {_format_scale(scale)}"
        return name
    if operation == "difference":
        return f"{left.variable_name} minus {right.variable_name}"
    if operation == "sum":
        return f"{left.variable_name} plus {right.variable_name}"
    return (
        f"Percentage change from {right.variable_name} to {left.variable_name}"
    )


def _describe_methodology(
    left: ObservationTable,
    right: ObservationTable,
    operation: DerivedOperation,
    scale: float,
) -> str:
    """Returns the formula of the derived variable for the provenance."""
    left_label = f"{left.variable_name} ({left.variable_dcid})"
    right_label = f"{right.variable_name} ({right.variable_dcid})"
    multiplied = (
        f" and multiplied by {_format_scale(scale)}"
        if scale != _UNSCALED
        else ""
    )
    if operation == "per_capita":
        formula = (
            f"{left_label} divided by {right_label}{multiplied}; pairs with "
            "a zero or negative denominator are skipped"
        )
    elif operation == "ratio":
        formula = (
            f"{left_label} divided by {right_label}{multiplied}; pairs with "
            "a zero denominator are skipped"
        )
    elif operation == "difference":
        formula = f"{left_label} minus {right_label}"
    elif operation == "sum":
        formula = f"{left_label} plus {right_label}"
    else:
        formula = (
            f"{left_label} minus {right_label}, divided by the magnitude of "
            f"{right_label} and expressed in percent; pairs with a zero "
            "baseline are skipped"
        )
    return f"{formula}. Observations are joined on place and date."


def _resolve_unit(
    left: ObservationTable,
    operation: DerivedOperation,
    derived_unit: str | None,
) -> str | None:
    """Returns the sanitized unit of the derived table.

    A difference or sum keeps the shared unit of its inputs and a
    percentage change is in percent. A quotient has no unit unless the
    caller names one, because the unit of a count per person or a ratio of
    two measures is not a unit the data plane names.
    """
    if derived_unit is not None:
        cleaned = clean_display_name(derived_unit, "")
        if cleaned:
            return cleaned
    if operation in ("difference", "sum"):
        return left.unit
    if operation == "pct_change":
        return _PERCENT_UNIT
    return None


def _resolve_scaling_factor(
    left: ObservationTable, operation: DerivedOperation
) -> float | None:
    """Returns the derived table's scaling factor.

    A difference or sum keeps the shared scaling of its inputs; a quotient
    cancels it, and a percentage is unscaled.
    """
    return left.scaling_factor if operation in ("difference", "sum") else None


def _index_rows_in_window(
    table: ObservationTable,
    target_places: frozenset[str],
    start_date: str | None,
    end_date: str | None,
) -> dict[tuple[str, str], ObservationRow]:
    """Indexes the rows for `target_places` in the window by place and date.

    A place with several rows on one date keeps the last row in table
    order, as `align_cohort` does.
    """
    return {
        (row.place_dcid, row.date): row
        for row in table.rows
        if row.place_dcid in target_places
        and is_within_date_range(row.date, start_date, end_date)
    }


def _collect_date_granularities(
    rows: dict[tuple[str, str], ObservationRow],
) -> set[int]:
    """Returns the date string lengths observed among the indexed rows."""
    return {len(date) for _, date in rows}


def _format_date_granularities(granularities: set[int]) -> str:
    """Formats a set of date character lengths into readable labels."""
    return ", ".join(
        _GRANULARITY_NAMES.get(length, f"{length}-character")
        for length in sorted(granularities)
    )


def _describe_granularity_mismatch(
    left: ObservationTable,
    right: ObservationTable,
    left_rows: dict[tuple[str, str], ObservationRow],
    right_rows: dict[tuple[str, str], ObservationRow],
) -> str:
    """Explains an empty join caused by mismatched date granularities.

    When both inputs have rows for the target places in the window but no
    `(place, date)` pair matched, the usual cause is that one table reports
    annual dates and the other monthly or daily ones, so the date strings
    can never be equal. Returns a sentence naming each table's granularities
    in that case, and an empty string otherwise, because an empty join with
    rows missing on one side is explained by the missing rows themselves.
    """
    if not left_rows or not right_rows:
        return ""
    left_granularities = _collect_date_granularities(left_rows)
    right_granularities = _collect_date_granularities(right_rows)
    if left_granularities & right_granularities:
        return ""
    return (
        f" {left.variable_name} reports "
        f"{_format_date_granularities(left_granularities)} dates while "
        f"{right.variable_name} reports "
        f"{_format_date_granularities(right_granularities)} dates, so no "
        "exact place and date pair can match; refetch one table at the "
        "other's granularity or align both to a shared date first."
    )


def _apply_operation(
    operation: DerivedOperation,
    left_value: float,
    right_value: float,
    scale: float,
) -> float | _SkipReason:
    """Applies the operation to one pair, or returns the skip reason.

    A quotient multiplies by the scale before dividing: `300 * 100000 /
    1000000` is exactly 30.0, while `300 / 1000000 * 100000` rounds to
    29.999999999999996, and the figure reaches the synthesis prompt as it
    is computed here. The product can overflow only for values near the
    floating-point limit, which the finiteness check turns into a skipped
    pair.

    Raises:
        ValueError: If `scale` is a boolean, not finite, or not above zero.
    """
    if isinstance(scale, bool) or not math.isfinite(scale) or scale <= 0.0:
        raise ValueError(
            f"The scale must be a finite number above zero, not {scale!r}."
        )
    if operation == "per_capita":
        if right_value <= 0.0:
            return "non_positive_denominator"
        value = left_value * scale / right_value
    elif operation == "ratio":
        if right_value == 0.0:
            return "zero_denominator"
        value = left_value * scale / right_value
    elif operation == "difference":
        value = left_value - right_value
    elif operation == "sum":
        value = left_value + right_value
    else:
        if right_value == 0.0:
            return "zero_baseline"
        value = (left_value - right_value) / abs(right_value) * PERCENT_SCALE
    if not math.isfinite(value):
        return "not_finite"
    return value


def _build_skip_caveats(
    skipped: dict[_SkipReason, list[str]], right: ObservationTable
) -> list[str]:
    """States how many pairs each skip reason removed, naming examples."""
    caveats: list[str] = []
    for reason, labels in skipped.items():
        description = _SKIP_DESCRIPTIONS[reason].format(
            right=right.variable_name
        )
        noun = "pair" if len(labels) == 1 else "pairs"
        verb = "was" if len(labels) == 1 else "were"
        formatted_pairs = format_place_names(
            labels, singular_noun="pair", plural_noun="pairs"
        )
        caveats.append(
            f"{len(labels)} place and date {noun} "
            f"({formatted_pairs}) {verb} skipped because {description}."
        )
    return caveats


def _validate_derived_parameters(
    *,
    operation: DerivedOperation,
    scale: float | None,
    derived_variable_dcid: str | None,
    places: Sequence[str] | None,
    start_date: str | None,
    end_date: str | None,
    min_coverage: float,
) -> str | None:
    """Returns an `invalid_parameters` message when any argument is invalid."""
    if scale is not None:
        if operation not in SCALED_OPERATIONS:
            return (
                "The scale parameter applies only to 'per_capita' and "
                f"'ratio', not {operation!r}."
            )
        if isinstance(scale, bool) or not math.isfinite(scale) or scale <= 0.0:
            return (
                f"The scale must be a finite number above zero, not {scale!r}."
            )
    if derived_variable_dcid is not None and not is_valid_dcid(
        derived_variable_dcid
    ):
        return "derived_variable_dcid must be a valid DCID."
    if places is not None:
        places_error = validate_place_dcids(places, parameter_name="places")
        if places_error is not None:
            return places_error
    for bound in (start_date, end_date):
        if bound is not None and not is_valid_observation_date(bound):
            return (
                f"The date bound {bound!r} is not a year, a year and month, "
                "or a full date."
            )
    if (
        start_date is not None
        and end_date is not None
        and is_inverted_date_range(start_date, end_date)
    ):
        return (
            f"The date window starts at {start_date} and ends at {end_date}, "
            "which is before it starts."
        )
    return validate_alignment_parameters(min_coverage=min_coverage)


def _validate_table_compatibility(
    left: ObservationTable,
    right: ObservationTable,
    *,
    operation: DerivedOperation,
) -> tuple[RefusalReason, str] | None:
    """Checks unit compatibility, scaling compatibility, and distinct inputs."""
    if operation in _UNIT_MATCHED_OPERATIONS:
        mismatch = find_unit_mismatch(left, right)
        if mismatch is not None:
            return mismatch.reason, mismatch.message
    elif _resolve_table_scaling(left) != _resolve_table_scaling(right):
        left_scaling = format_scaling_factor(_resolve_table_scaling(left))
        right_scaling = format_scaling_factor(_resolve_table_scaling(right))
        return (
            "scaling_mismatch",
            f"Scaling factors differ: {left.variable_name} "
            f"({left.variable_dcid}) reports a scaling factor of "
            f"{left_scaling}; {right.variable_name} ({right.variable_dcid}) "
            f"reports a scaling factor of {right_scaling}.",
        )
    if left.variable_dcid == right.variable_dcid:
        return (
            "invalid_parameters",
            "left and right must be different variables, but "
            f"{left.variable_dcid} was given for both.",
        )
    return None


def _resolve_target_places_and_names(
    left: ObservationTable,
    right: ObservationTable,
    *,
    places: Sequence[str] | None,
) -> tuple[tuple[str, ...], dict[str, str]]:
    """Resolves the target places in report order and their display names."""
    if places:
        target_places = tuple(dict.fromkeys(places))
    elif left.requested_places:
        target_places = resolve_target_places(left)
    elif right.requested_places:
        target_places = resolve_target_places(right)
    else:
        target_places = tuple(
            dict.fromkeys([*left.places_with_data, *right.places_with_data])
        )
    place_names = {place: place for place in target_places}
    place_names.update(right.place_names)
    place_names.update(left.place_names)
    return target_places, place_names


def _resolve_cohort_metadata(
    left: ObservationTable, right: ObservationTable
) -> tuple[str | None, str | None]:
    """Resolves `(parent_place_dcid, child_place_type)` for the table."""
    if left.parent_place_dcid is not None or left.child_place_type is not None:
        return left.parent_place_dcid, left.child_place_type
    if not left.requested_places or set(left.requested_places) == set(
        right.requested_places
    ):
        return right.parent_place_dcid, right.child_place_type
    return None, None


def _join_paired_rows(
    left_rows: dict[tuple[str, str], ObservationRow],
    right_rows: dict[tuple[str, str], ObservationRow],
    right: ObservationTable,
    place_names: dict[str, str],
    *,
    operation: DerivedOperation,
    scale: float | None,
) -> tuple[tuple[ObservationRow, ...], float, list[str]]:
    """Applies `operation` across shared `(place, date)` keys."""
    joined = sorted(left_rows.keys() & right_rows.keys())
    if scale is None:
        if operation == "per_capita":
            # Unscaled per-person quotients determine the per-capita scale
            # before reapplying the operation at that scale.
            per_person = [
                value
                for key in joined
                if not isinstance(
                    value := _apply_operation(
                        operation,
                        left_rows[key].value,
                        right_rows[key].value,
                        _UNSCALED,
                    ),
                    str,
                )
            ]
            resolved_scale = _select_fitting_scale(per_person)
        else:
            resolved_scale = _UNSCALED
    else:
        resolved_scale = scale

    rows: list[ObservationRow] = []
    skipped: dict[_SkipReason, list[str]] = {}
    for place, date in joined:
        outcome = _apply_operation(
            operation,
            left_rows[place, date].value,
            right_rows[place, date].value,
            resolved_scale,
        )
        name = place_names[place]
        if isinstance(outcome, str):
            skipped.setdefault(outcome, []).append(f"{name} ({date})")
            continue
        rows.append(ObservationRow(place, name, date, outcome))
    return tuple(rows), resolved_scale, _build_skip_caveats(skipped, right)


def _build_refused_outcome(
    left: ObservationTable,
    right: ObservationTable,
    *,
    step_id: str,
    reason: RefusalReason,
    coverage: CoverageReport | None,
    caveat: str,
    extra_caveats: Sequence[str] = (),
    unit: str | None,
    scaling_factor: float | None,
) -> DerivedMetricOutcome:
    """Builds a refused `DerivedMetricOutcome` using `script_inputs`."""
    if (
        reason == "invalid_parameters"
        and coverage is None
        and not extra_caveats
    ):
        refused = build_invalid_parameters_refusal(
            (left, right),
            script=_SCRIPT_NAME,
            step_id=step_id,
            caveat=caveat,
            unit=unit,
            scaling_factor=scaling_factor,
        )
    else:
        refused = build_refusal(
            (left, right),
            script=_SCRIPT_NAME,
            step_id=step_id,
            reason=reason,
            coverage=coverage,
            caveat=caveat,
            extra_caveats=extra_caveats,
            unit=unit,
            scaling_factor=scaling_factor,
        )
    return DerivedMetricOutcome(table=None, result=refused)


def _build_derived_outcome(
    left: ObservationTable,
    right: ObservationTable,
    *,
    rows: tuple[ObservationRow, ...],
    operation: DerivedOperation,
    scale: float,
    unit: str | None,
    scaling_factor: float | None,
    derived_variable_dcid: str | None,
    derived_variable_name: str | None,
    target_places: tuple[str, ...],
    place_names: dict[str, str],
    joined_places: frozenset[str],
    missing_places: tuple[str, ...],
    coverage: CoverageReport,
    caveats: Sequence[str],
    step_id: str,
) -> DerivedMetricOutcome:
    """Builds the derived `ObservationTable` and `OkScriptResult`."""
    variable_dcid = (
        derived_variable_dcid
        or f"derived_{left.variable_dcid}_{operation}_{right.variable_dcid}"
    )
    default_name = _build_default_name(left, right, operation, scale)
    variable_name = clean_display_name(derived_variable_name, default_name)
    provenance = merge_provenance(
        left.provenance,
        right.provenance,
        methodology=_describe_methodology(left, right, operation, scale),
    )
    parent_place_dcid, child_place_type = _resolve_cohort_metadata(left, right)
    table = ObservationTable(
        variable_dcid=variable_dcid,
        variable_name=variable_name,
        unit=unit,
        scaling_factor=scaling_factor,
        provenance=provenance,
        rows=rows,
        requested_places=target_places,
        place_names=place_names,
        parent_place_dcid=parent_place_dcid,
        child_place_type=child_place_type,
    )
    summary = summarize_table(table)
    result = OkScriptResult(
        step_id=step_id,
        script=_SCRIPT_NAME,
        variables=(left.variable_dcid, right.variable_dcid),
        variable_names={
            left.variable_dcid: left.variable_name,
            right.variable_dcid: right.variable_name,
        },
        unit=unit,
        scaling_factor=scaling_factor,
        coverage=coverage,
        provenance=provenance,
        metrics=DerivedMetrics(
            derived_variable_dcid=variable_dcid,
            derived_variable_name=variable_name,
            operation=operation,
            scale=scale,
            observation_count=len(rows),
            place_count=len(joined_places),
            date_range=summary.date_range,
            value_range=summary.value_range,
            sample_rows=summary.sample_rows,
            missing_places=missing_places,
        ),
        caveats=tuple(caveats),
    )
    return DerivedMetricOutcome(table=table, result=result)


def derive_observation_table(
    left: ObservationTable,
    right: ObservationTable,
    *,
    operation: DerivedOperation | str = "ratio",
    scale: float | None = None,
    derived_variable_dcid: str | None = None,
    derived_variable_name: str | None = None,
    derived_unit: str | None = None,
    places: Sequence[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    min_coverage: float = 0.0,
    step_id: str = "s1",
) -> DerivedMetricOutcome:
    """Derives a table of `left` combined with `right` on place and date.

    Args:
        left: The table on the left of the operation: the numerator, the
            minuend, or the later value of a percentage change.
        right: The table on the right: the denominator, the subtrahend, or
            the baseline.
        operation: `per_capita` or `ratio` divides and multiplies by
            `scale`; `difference` subtracts; `sum` adds; `pct_change`
            expresses `left` as a percentage change from `right`.
        scale: The multiplier of a quotient: `1.0` per person, `100_000.0`
            per hundred thousand, or `100.0` for a percentage. Must be a
            finite number greater than zero, and is accepted only for
            `per_capita` and `ratio`. When None, a per-capita step takes
            the scale that fits its values (per person, per 1,000, or per
            100,000 people, whichever is the smallest that puts the median
            value at or above one) and any other operation takes `1.0`.
        derived_variable_dcid: The identifier of the derived variable;
            defaults to `derived_<left>_<operation>_<right>`.
        derived_variable_name: The display name of the derived variable;
            defaults to a label built from the input names.
        derived_unit: The unit of the derived values. When None, a
            difference or sum keeps the inputs' unit, a percentage change
            is in `Percent`, and a quotient has no unit.
        places: The target places, in the order to report them. When empty,
            `left.requested_places` is used, then `right.requested_places`,
            and failing that the union of the places with data in both
            tables.
        start_date: The inclusive start of the window, a `YYYY`, `YYYY-MM`,
            or `YYYY-MM-DD` date compared as `is_within_date_range` does.
        end_date: The inclusive end of the window, in the same form.
        min_coverage: When above zero, the share of the target places that
            must have at least one derived row.
        step_id: Identifier of the analysis step (for example, `"s1"`).

    Returns:
        The derived table and a result whose `metrics` is a `DerivedMetrics`
        instance holding `derived_variable_dcid`, `derived_variable_name`,
        `operation`, `scale`, `observation_count`, `place_count`, `date_range`,
        `value_range`, `sample_rows`, and `missing_places`, with the composite
        provenance and the formula as its methodology. The outcome is refused,
        with no table, with `invalid_parameters` for an unrecognized
        `operation`, a `scale` on a non-quotient operation, a non-positive or
        non-finite `scale`, an invalid `derived_variable_dcid` or `places`
        entry, an invalid or inverted date window, an out-of-range
        `min_coverage`, or identical `left` and `right` variables; with
        `unit_mismatch` or `scaling_mismatch` when the inputs cannot be
        combined; with `no_observations` when no pair survives the join; and
        with `insufficient_coverage` when fewer than `min_coverage` of the
        target places have a derived row.
    """
    resolved_operation = _resolve_operation(operation)
    if resolved_operation is None:
        fallback_unit = (
            clean_display_name(derived_unit, "") or None
            if derived_unit is not None
            else None
        )
        return _build_refused_outcome(
            left,
            right,
            step_id=step_id,
            reason="invalid_parameters",
            coverage=None,
            caveat=(
                "The operation must be 'per_capita', 'ratio', 'difference', "
                f"'sum', or 'pct_change', not {operation!r}."
            ),
            unit=fallback_unit,
            scaling_factor=None,
        )
    unit = _resolve_unit(left, resolved_operation, derived_unit)
    scaling_factor = _resolve_scaling_factor(left, resolved_operation)

    parameter_error = _validate_derived_parameters(
        operation=resolved_operation,
        scale=scale,
        derived_variable_dcid=derived_variable_dcid,
        places=places,
        start_date=start_date,
        end_date=end_date,
        min_coverage=min_coverage,
    )
    if parameter_error is not None:
        return _build_refused_outcome(
            left,
            right,
            step_id=step_id,
            reason="invalid_parameters",
            coverage=None,
            caveat=parameter_error,
            unit=unit,
            scaling_factor=scaling_factor,
        )

    compatibility_error = _validate_table_compatibility(
        left, right, operation=resolved_operation
    )
    if compatibility_error is not None:
        refusal_reason, message = compatibility_error
        return _build_refused_outcome(
            left,
            right,
            step_id=step_id,
            reason=refusal_reason,
            coverage=None,
            caveat=message,
            unit=unit,
            scaling_factor=scaling_factor,
        )

    target_places, place_names = _resolve_target_places_and_names(
        left, right, places=places
    )
    target_place_set = frozenset(target_places)
    left_rows = _index_rows_in_window(
        left, target_place_set, start_date, end_date
    )
    right_rows = _index_rows_in_window(
        right, target_place_set, start_date, end_date
    )
    rows, resolved_scale, caveats = _join_paired_rows(
        left_rows,
        right_rows,
        right,
        place_names,
        operation=resolved_operation,
        scale=scale,
    )

    if not rows:
        reason_hint = _describe_granularity_mismatch(
            left, right, left_rows, right_rows
        )
        return _build_refused_outcome(
            left,
            right,
            step_id=step_id,
            reason="no_observations",
            coverage=CoverageReport(
                contributing_places=0,
                requested_places=len(target_places),
                coverage_ratio=0.0,
                reference_date=None,
                missing_places=target_places,
            ),
            caveat=(
                f"No observation of {left.variable_name} and "
                f"{right.variable_name} shares a place and date within the "
                f"requested window, so nothing can be derived.{reason_hint}"
            ),
            extra_caveats=caveats,
            unit=unit,
            scaling_factor=scaling_factor,
        )

    joined_places = frozenset(row.place_dcid for row in rows)
    missing_places = tuple(
        place for place in target_places if place not in joined_places
    )
    coverage = CoverageReport(
        contributing_places=len(joined_places),
        requested_places=len(target_places),
        coverage_ratio=len(joined_places) / len(target_places),
        reference_date=None,
        missing_places=missing_places,
    )
    if not has_adequate_coverage(
        len(joined_places), len(target_places), min_coverage
    ):
        verb = conjugate_have(coverage.contributing_places)
        return _build_refused_outcome(
            left,
            right,
            step_id=step_id,
            reason="insufficient_coverage",
            coverage=coverage,
            caveat=(
                f"Only {coverage.describe()} {verb} a derived value, below "
                f"the required {format_percent(min_coverage)} coverage."
            ),
            extra_caveats=caveats,
            unit=unit,
            scaling_factor=scaling_factor,
        )
    if missing_places:
        missing_names = [
            place_names.get(place, place) for place in missing_places
        ]
        caveats.append(
            "No joined observations are available for "
            f"{format_place_names(missing_names)}, so they are left out of "
            "the derived table."
        )

    return _build_derived_outcome(
        left,
        right,
        rows=rows,
        operation=resolved_operation,
        scale=resolved_scale,
        unit=unit,
        scaling_factor=scaling_factor,
        derived_variable_dcid=derived_variable_dcid,
        derived_variable_name=derived_variable_name,
        target_places=target_places,
        place_names=place_names,
        joined_places=joined_places,
        missing_places=missing_places,
        coverage=coverage,
        caveats=caveats,
        step_id=step_id,
    )


def compute_derived_metric(
    left: ObservationTable,
    right: ObservationTable,
    *,
    operation: DerivedOperation | str = "ratio",
    scale: float | None = None,
    derived_variable_dcid: str | None = None,
    derived_variable_name: str | None = None,
    derived_unit: str | None = None,
    places: Sequence[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    min_coverage: float = 0.0,
    step_id: str = "s1",
) -> ScriptResult:
    """Computes a derived metric and returns the digest `ScriptResult`.

    Args:
        left: The table on the left of the operation: the numerator, the
            minuend, or the later value of a percentage change.
        right: The table on the right: the denominator, the subtrahend, or
            the baseline.
        operation: `per_capita` or `ratio` divides and multiplies by
            `scale`; `difference` subtracts; `sum` adds; `pct_change`
            expresses `left` as a percentage change from `right`.
        scale: The multiplier of a quotient (`per_capita` or `ratio`).
            Must be a finite number greater than zero when given.
        derived_variable_dcid: The identifier of the derived variable;
            defaults to `derived_<left>_<operation>_<right>`.
        derived_variable_name: The display name of the derived variable;
            defaults to a label built from the input names.
        derived_unit: The unit of the derived values.
        places: The target places, in the order to report them. When empty,
            `left.requested_places` is used, then `right.requested_places`,
            and failing that the union of the places with data in both
            tables.
        start_date: The inclusive start of the window (`YYYY`, `YYYY-MM`,
            or `YYYY-MM-DD`).
        end_date: The inclusive end of the window, in the same form.
        min_coverage: When above zero, the share of the target places that
            must have at least one derived row.
        step_id: Identifier of the analysis step (for example, `"s1"`).

    Returns:
        An `OkScriptResult` with `DerivedMetrics`, or a
        `RefusedScriptResult` when the derivation is refused.
    """
    return derive_observation_table(
        left,
        right,
        operation=operation,
        scale=scale,
        derived_variable_dcid=derived_variable_dcid,
        derived_variable_name=derived_variable_name,
        derived_unit=derived_unit,
        places=places,
        start_date=start_date,
        end_date=end_date,
        min_coverage=min_coverage,
        step_id=step_id,
    ).result
