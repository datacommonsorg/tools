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
"""Summarizes the distribution of an aligned cohort and benchmarks places.

Computes central tendency, extrema, dispersion, quantiles, skewness, an
optional weighted mean, and focal-place benchmarks (`z_score`, `percentile`)
for a cohort at one date.
"""

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from narratives_agent.analytics.alignment import (
    DEFAULT_MIN_COVERAGE,
    AlignedCohort,
    AlignmentRefusal,
    align_cohort,
    has_adequate_coverage,
)
from narratives_agent.analytics.digest import (
    PERCENT_SCALE,
    OkScriptResult,
    RefusedScriptResult,
    ScriptResult,
    conjugate_have,
    format_place_names,
)
from narratives_agent.analytics.metrics import (
    DistributionFocalEntry,
    DistributionMetrics,
    PlaceValue,
)
from narratives_agent.analytics.provenance import Provenance, merge_provenance
from narratives_agent.analytics.ranking import compute_cohort_percentiles
from narratives_agent.analytics.script_inputs import (
    build_invalid_parameters_refusal,
    describe_missing_focal_places,
    resolve_aligned_cohort,
    validate_place_dcids,
)
from narratives_agent.analytics.tables import (
    ObservationRow,
    ObservationTable,
)

__all__ = ["summarize_distribution"]

_SCRIPT_NAME: Literal["summarize_distribution"] = "summarize_distribution"
# The smallest cohort for which the standard deviation and the quantiles are
# computed; a single value has no spread.
_MIN_PLACES_FOR_DISPERSION = 2
# Adjusted sample skewness is defined only for cohorts of at least three places.
_MIN_PLACES_FOR_SKEWNESS = 3
_QUARTILE_COUNT = 4
_DECILE_COUNT = 10
_PERCENT_PER_DECILE = int(PERCENT_SCALE) // _DECILE_COUNT
# The nine decile cut points use metric keys `p10` through `p90`, each key
# naming the percentage of the cohort at or below the cut.
_DECILE_KEYS = tuple(
    f"p{index * _PERCENT_PER_DECILE}" for index in range(1, _DECILE_COUNT)
)
# Inclusive interpolation includes the minimum and the maximum as the 0th and
# 100th percentiles, matching the spreadsheet function `PERCENTILE.INC`.
_QUANTILE_METHOD: Literal["inclusive"] = "inclusive"


@dataclass(frozen=True)
class _Weighting:
    """The outcome of weighting the cohort mean by a second variable."""

    weighted_mean: float | None
    weighted_place_count: int
    caveats: tuple[str, ...]


@dataclass(frozen=True)
class _Spread:
    """The dispersion, quantile, and skewness figures of a cohort.

    Each figure is None when the cohort is too small or too uniform for it,
    and `caveats` states why.
    """

    stdev: float | None
    q25: float | None
    q50: float | None
    q75: float | None
    iqr: float | None
    deciles: dict[str, float] | None
    skewness: float | None
    caveats: tuple[str, ...]


@dataclass(frozen=True)
class _FocalBenchmarks:
    """The benchmarks of the focal places against the cohort.

    `missing_places` lists the focal places with no value in the cohort,
    and `caveat` names them, or is None when none is missing.
    """

    entries: tuple[DistributionFocalEntry, ...]
    missing_places: tuple[str, ...]
    caveat: str | None


def _check_weights_date(
    aligned: AlignedCohort,
    weights: AlignedCohort | ObservationTable | None,
    step_id: str,
) -> RefusedScriptResult | None:
    """Refuses a weights cohort aligned to another date, or returns None.

    A weights table is aligned to the cohort's reference date later, so
    only a weights cohort can disagree with it.
    """
    if (
        isinstance(weights, AlignedCohort)
        and weights.reference_date != aligned.reference_date
    ):
        return build_invalid_parameters_refusal(
            aligned,
            script=_SCRIPT_NAME,
            step_id=step_id,
            caveat=(
                f"The weights cohort for {weights.variable_name} is aligned "
                f"to {weights.reference_date}, not to the cohort's reference "
                f"date {aligned.reference_date}."
            ),
        )
    return None


def _find_extremum(
    rows: Sequence[ObservationRow], *, is_largest: bool
) -> PlaceValue:
    """Returns the row with the smallest or largest value, ties by DCID."""
    row = min(
        rows,
        key=lambda item: (
            -item.value if is_largest else item.value,
            item.place_dcid,
        ),
    )
    return PlaceValue(
        place_dcid=row.place_dcid,
        place_name=row.place_name,
        value=row.value,
    )


def _compute_sample_skewness(
    values: Sequence[float], mean: float, stdev: float
) -> float:
    """Returns the adjusted Fisher-Pearson sample skewness.

    The statistic is `cohort_size / ((cohort_size - 1)(cohort_size - 2))`
    times the sum of the cubed standardized deviations, with the sample
    standard deviation as the scale, which is the estimator spreadsheets
    and statistics packages report as sample skewness. The caller
    guarantees at least three values and a positive standard deviation.
    """
    cohort_size = len(values)
    cubed_deviation_sum = sum(((value - mean) / stdev) ** 3 for value in values)
    return (
        cohort_size
        / ((cohort_size - 1) * (cohort_size - 2))
        * cubed_deviation_sum
    )


def _compute_exact_mean(
    values: Sequence[float], weights: Sequence[float] | None = None
) -> float:
    """Returns the (weighted) mean, summed exactly and rounded once.

    A floating-point sum can round the mean one ulp outside the values it
    averages (`statistics.fmean` of three copies of 0.1 is
    0.10000000000000002) and can overflow when the values or the
    value-weight products are large. Summing in exact rational arithmetic
    and rounding once keeps the mean within `[min, max]`, because rounding
    is monotonic and both bounds are floats, and the mean of finite values
    is always finite. `weights` must be positive.
    """
    if weights is None:
        return float(sum(map(Fraction, values)) / len(values))
    total = sum(
        Fraction(value) * Fraction(weight)
        for value, weight in zip(values, weights, strict=True)
    )
    return float(total / sum(map(Fraction, weights)))


def _compute_bracketed_quantiles(
    values: Sequence[float], parts: int
) -> list[float]:
    """Returns the inclusive cut points, each clamped to its bracket.

    `statistics.quantiles` interpolates between two adjacent order
    statistics and can round a cut point between two equal values one ulp
    away from them. Clamping each cut point to its pair of order statistics
    keeps every cut point within `[min, max]` and in ascending order.
    `values` must be sorted and hold at least two values.
    """
    last_index = len(values) - 1
    cuts = statistics.quantiles(values, n=parts, method=_QUANTILE_METHOD)
    clamped: list[float] = []
    for index, cut in enumerate(cuts, start=1):
        position, remainder = divmod(index * last_index, parts)
        upper = values[position + 1] if remainder else values[position]
        clamped.append(min(max(cut, values[position]), upper))
    return clamped


def _compute_spread(
    values: Sequence[float], mean: float, aligned: AlignedCohort
) -> _Spread:
    """Computes the dispersion, quantiles, and skewness of sorted `values`.

    The standard deviation and the quantiles need at least two places and
    the skewness at least three with a nonzero spread; each figure that
    cannot be computed is None, with a caveat naming the reason.
    """
    cohort_size = len(values)
    if cohort_size < _MIN_PLACES_FOR_DISPERSION:
        return _Spread(
            stdev=None,
            q25=None,
            q50=None,
            q75=None,
            iqr=None,
            deciles=None,
            skewness=None,
            caveats=(
                f"Only one place ({aligned.rows[0].place_name}) reported a "
                f"value for "
                f"{aligned.variable_name} on {aligned.reference_date}; "
                "dispersion, quantiles, and z-scores require at least "
                f"{_MIN_PLACES_FOR_DISPERSION} places and skewness at least "
                f"{_MIN_PLACES_FOR_SKEWNESS}, so they are not computed.",
            ),
        )
    stdev = statistics.stdev(values)
    q25, q50, q75 = _compute_bracketed_quantiles(values, _QUARTILE_COUNT)
    deciles = dict(
        zip(
            _DECILE_KEYS,
            _compute_bracketed_quantiles(values, _DECILE_COUNT),
            strict=True,
        )
    )
    skewness: float | None = None
    caveats: tuple[str, ...] = ()
    if stdev == 0.0:
        caveats = (
            f"Every place reports the same value for {aligned.variable_name} "
            f"on {aligned.reference_date}, so skewness and z-scores are "
            "undefined.",
        )
    elif cohort_size >= _MIN_PLACES_FOR_SKEWNESS:
        skewness = _compute_sample_skewness(values, mean, stdev)
    else:
        caveats = (
            f"Skewness requires at least {_MIN_PLACES_FOR_SKEWNESS} places, "
            "so it is not computed for this cohort of two.",
        )
    return _Spread(
        stdev=stdev,
        q25=q25,
        q50=q50,
        q75=q75,
        iqr=q75 - q25,
        deciles=deciles,
        skewness=skewness,
        caveats=caveats,
    )


def _count_required_places(cohort_size: int, min_coverage: float) -> int:
    """Returns the fewest places, at least one, that meet `min_coverage`.

    The count comes from `has_adequate_coverage`, the threshold test that
    decides whether the weighted mean is reported, so a caveat that states
    the count agrees with the decision. `min_coverage` must lie in
    `[0.0, 1.0]`, so the whole cohort always qualifies.
    """
    return next(
        count
        for count in range(1, cohort_size + 1)
        if has_adequate_coverage(count, cohort_size, min_coverage)
    )


def _collect_weights_by_place(
    weights: AlignedCohort | ObservationTable, reference_date: str
) -> dict[str, float]:
    """Returns each place's weight on `reference_date`.

    A weights table is aligned to the cohort's own reference date through
    `align_cohort` with no coverage requirement, so that a place's weight is
    always observed on the same date as its value and a duplicate row keeps
    the last one, as the cohort itself does. A table with no weight on that
    date yields no pairs rather than an error.
    """
    if isinstance(weights, ObservationTable):
        aligned = align_cohort(
            weights, target_date=reference_date, min_coverage=0.0
        )
        if isinstance(aligned, AlignmentRefusal):
            return {}
        weights = aligned
    return {row.place_dcid: row.value for row in weights.rows}


def _compute_weighted_mean(
    aligned: AlignedCohort,
    weights: AlignedCohort | ObservationTable,
    min_coverage: float,
) -> _Weighting:
    """Weights the cohort mean by `weights`, or explains why it is omitted.

    Places are paired by DCID on the cohort's reference date and a pair
    contributes only when its weight is strictly positive. The mean is
    omitted when no cohort place has a weight on that date, when any paired
    weight is negative, which marks the weights as unusable, and when no
    place or fewer than `min_coverage` of the cohort's places (as
    `has_adequate_coverage` decides) carry a positive weight, because a mean
    weighted over a fraction of the cohort would misstate the cohort.
    """
    weights_by_place = _collect_weights_by_place(
        weights, aligned.reference_date
    )
    paired = [
        (row, weights_by_place[row.place_dcid])
        for row in aligned.rows
        if row.place_dcid in weights_by_place
    ]
    if not paired:
        return _Weighting(
            weighted_mean=None,
            weighted_place_count=0,
            caveats=(
                f"{weights.variable_name} has no value on "
                f"{aligned.reference_date} for any place in the cohort, so "
                "the weighted mean is omitted.",
            ),
        )
    negative_rows = [row for row, weight in paired if weight < 0.0]
    if negative_rows:
        names = format_place_names([row.place_name for row in negative_rows])
        return _Weighting(
            weighted_mean=None,
            weighted_place_count=0,
            caveats=(
                f"{names} reported a negative value for "
                f"{weights.variable_name} on {aligned.reference_date}, so "
                "the weighted mean is omitted.",
            ),
        )
    positive_pairs = [
        (row.value, weight) for row, weight in paired if weight > 0.0
    ]
    cohort_size = len(aligned.rows)
    if not positive_pairs or not has_adequate_coverage(
        len(positive_pairs), cohort_size, min_coverage
    ):
        required = _count_required_places(cohort_size, min_coverage)
        verb = conjugate_have(len(positive_pairs))
        return _Weighting(
            weighted_mean=None,
            weighted_place_count=len(positive_pairs),
            caveats=(
                f"Only {len(positive_pairs)} of {cohort_size} places in the "
                f"cohort {verb} a positive value for {weights.variable_name} "
                f"on {aligned.reference_date}, fewer than the {required} "
                "needed, so the weighted mean is omitted.",
            ),
        )
    values, place_weights = zip(*positive_pairs, strict=True)
    return _Weighting(
        weighted_mean=_compute_exact_mean(values, place_weights),
        weighted_place_count=len(positive_pairs),
        caveats=(),
    )


def _compute_percent_of_median(value: float, median: float) -> float | None:
    """Returns `value` as a percentage of a positive `median`, or None.

    The percentage is None when the median is zero or negative, because a
    negative median inverts the ratio's ordering, and when it is too large
    to represent as a float.
    """
    if median <= 0.0:
        return None
    percent = value / median * PERCENT_SCALE
    return percent if math.isfinite(percent) else None


def _build_focal_entry(
    row: ObservationRow,
    *,
    mean: float,
    median: float,
    stdev: float | None,
    percentiles: dict[float, float],
) -> DistributionFocalEntry:
    """Builds the record that benchmarks one focal place against the cohort."""
    return DistributionFocalEntry(
        place_dcid=row.place_dcid,
        place_name=row.place_name,
        value=row.value,
        diff_from_median=row.value - median,
        pct_of_median=_compute_percent_of_median(row.value, median),
        diff_from_mean=row.value - mean,
        z_score=(
            (row.value - mean) / stdev
            if stdev is not None and stdev > 0.0
            else None
        ),
        percentile=percentiles[row.value],
    )


def _benchmark_focal_places(
    aligned: AlignedCohort,
    focal_places: Sequence[str],
    *,
    values: Sequence[float],
    mean: float,
    median: float,
    stdev: float | None,
) -> _FocalBenchmarks:
    """Benchmarks each distinct focal place against the cohort.

    Focal places keep their request order with duplicates removed; places
    with no value in the cohort are listed as missing and named in the
    caveat.
    """
    percentiles = compute_cohort_percentiles(values)
    rows_by_place = {row.place_dcid: row for row in aligned.rows}
    requested = list(dict.fromkeys(focal_places))
    missing = tuple(place for place in requested if place not in rows_by_place)
    entries = tuple(
        _build_focal_entry(
            rows_by_place[place],
            mean=mean,
            median=median,
            stdev=stdev,
            percentiles=percentiles,
        )
        for place in requested
        if place in rows_by_place
    )
    caveat = (
        describe_missing_focal_places(
            aligned,
            missing,
            cohort_label="cohort",
            unavailable_figure="benchmark",
        )
        if missing
        else None
    )
    return _FocalBenchmarks(
        entries=entries, missing_places=missing, caveat=caveat
    )


def _list_reported_variables(
    aligned: AlignedCohort,
    reported_weights: AlignedCohort | ObservationTable | None,
) -> tuple[tuple[str, ...], dict[str, str], tuple[Provenance, ...]]:
    """Returns the variables, their names, and their provenance to report.

    The weights variable is reported only when the weighted mean is.
    """
    sources = (
        (aligned,) if reported_weights is None else (aligned, reported_weights)
    )
    return (
        tuple(source.variable_dcid for source in sources),
        {source.variable_dcid: source.variable_name for source in sources},
        tuple(source.provenance for source in sources),
    )


def _describe_methodology(
    aligned: AlignedCohort,
    spread: _Spread,
    *,
    weight_variable_name: str | None,
    has_focal_entries: bool,
) -> str:
    """Describes the figures computed for the cohort, ending with a period.

    `weight_variable_name` names the variable the reported weighted mean is
    weighted by, or is None when no weighted mean is reported.
    """
    cohort_size = len(aligned.rows)
    place_noun = "place" if cohort_size == 1 else "places"
    if spread.skewness is not None:
        summary_terms = (
            "mean, median, minimum, maximum, the gap from minimum to "
            "maximum (max_minus_min), sample standard deviation, quartiles "
            "and deciles by linear interpolation, and adjusted "
            "Fisher-Pearson sample skewness"
        )
    elif spread.stdev is not None:
        summary_terms = (
            "mean, median, minimum, maximum, the gap from minimum to "
            "maximum (max_minus_min), sample standard deviation, and "
            "quartiles and deciles by linear interpolation"
        )
    else:
        summary_terms = (
            "mean, median, minimum, maximum, and the gap from minimum to "
            "maximum (max_minus_min)"
        )
    methodology = (
        f"Distribution of {aligned.variable_name} across {cohort_size} "
        f"{place_noun} on {aligned.reference_date}: {summary_terms}"
    )
    if weight_variable_name is not None:
        methodology += (
            f", with the mean also weighted by {weight_variable_name}"
        )
    if has_focal_entries:
        methodology += (
            "; focal places are compared with the cohort mean, median, and "
            "percentile"
        )
    return methodology + "."


def summarize_distribution(
    cohort_or_table: AlignedCohort | ObservationTable,
    *,
    weights: AlignedCohort | ObservationTable | None = None,
    focal_places: Sequence[str] = (),
    target_date: str | None = None,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
    step_id: str = "s1",
) -> ScriptResult:
    """Summarizes the spread of a cohort's values at its reference date.

    Args:
        cohort_or_table: An aligned cohort, or a table to align first with
            `target_date` and `min_coverage`. An aligned cohort already has
            a reference date: a `target_date` other than that date is
            refused, and `min_coverage` is unused and not checked unless
            `weights` is given.
        weights: A second variable, such as population, to weight the mean
            by. A table is aligned to the cohort's reference date; a cohort
            must already be aligned to that date.
        focal_places: Places to benchmark against the cohort, in the order
            to report them.
        target_date: Passed to `align_cohort` when a table is given.
        min_coverage: Passed to `align_cohort` when a table is given, and
            the share of the cohort that must carry a positive weight for
            the weighted mean to be reported.
        step_id: Identifier of the analysis step (for example, `"s1"`).

    Returns:
        A result whose `metrics` is a `DistributionMetrics` instance holding
        `reference_date`, `cohort_size`, `mean`, `median`, `min` and `max`
        (each a `PlaceValue`), `max_minus_min` (the gap between those two
        values, in the variable's unit), `stdev`, `q25`, `q50`, `q75`, `iqr`,
        `deciles` (`p10` through `p90`), `skewness`, `weighted_mean`,
        `weight_variable_dcid`, `weighted_place_count`, `focal_entries` (in
        `focal_places` order, each a `DistributionFocalEntry` with
        `diff_from_median`, `pct_of_median`, `diff_from_mean`, `z_score`, and
        `percentile`), and `missing_focal_places`. The dispersion figures are
        `None` for a cohort of one place, the skewness is `None` for fewer
        than three places or a constant cohort, and the weighted mean is
        `None` when no weights are given or when negative or insufficient
        weights cause it to be omitted; each omitted figure carries a caveat.
        The result is refused with `invalid_parameters` when `target_date` is
        not a valid date or differs from an aligned cohort's reference date,
        `min_coverage` is outside `[0.0, 1.0]` for a table or when `weights`
        is given, `focal_places` is a string or holds an invalid DCID, or a
        weights cohort is aligned to another date, carrying the cohort's
        coverage and caveats once it is aligned; and with the alignment's
        reason when the cohort cannot be aligned.
    """
    error = validate_place_dcids(focal_places, parameter_name="focal_places")
    if error is not None:
        return build_invalid_parameters_refusal(
            cohort_or_table, script=_SCRIPT_NAME, step_id=step_id, caveat=error
        )
    # Once the cohort is aligned, `min_coverage` is only the weight coverage
    # threshold, so it is checked for an aligned cohort only with weights.
    aligned = resolve_aligned_cohort(
        cohort_or_table,
        script=_SCRIPT_NAME,
        step_id=step_id,
        target_date=target_date,
        min_coverage=min_coverage,
        operation="summarized",
        should_check_min_coverage=weights is not None,
    )
    if not isinstance(aligned, AlignedCohort):
        return aligned
    weights_refusal = _check_weights_date(aligned, weights, step_id)
    if weights_refusal is not None:
        return weights_refusal

    values = sorted(row.value for row in aligned.rows)
    mean = _compute_exact_mean(values)
    median = statistics.median(values)
    lowest = _find_extremum(aligned.rows, is_largest=False)
    highest = _find_extremum(aligned.rows, is_largest=True)
    spread = _compute_spread(values, mean, aligned)
    weighting = (
        _compute_weighted_mean(aligned, weights, min_coverage)
        if weights is not None
        else None
    )
    reported_weights = (
        weights
        if weighting is not None and weighting.weighted_mean is not None
        else None
    )
    focal = _benchmark_focal_places(
        aligned,
        focal_places,
        values=values,
        mean=mean,
        median=median,
        stdev=spread.stdev,
    )
    caveats = [
        *aligned.caveats,
        *spread.caveats,
        *(weighting.caveats if weighting is not None else ()),
        *((focal.caveat,) if focal.caveat is not None else ()),
    ]
    variables, variable_names, provenance_items = _list_reported_variables(
        aligned, reported_weights
    )
    methodology = _describe_methodology(
        aligned,
        spread,
        weight_variable_name=(
            reported_weights.variable_name
            if reported_weights is not None
            else None
        ),
        has_focal_entries=bool(focal.entries),
    )
    return OkScriptResult(
        step_id=step_id,
        script=_SCRIPT_NAME,
        variables=variables,
        variable_names=variable_names,
        unit=aligned.unit,
        scaling_factor=aligned.scaling_factor,
        coverage=aligned.coverage,
        provenance=merge_provenance(*provenance_items, methodology=methodology),
        metrics=DistributionMetrics(
            reference_date=aligned.reference_date,
            cohort_size=len(values),
            mean=mean,
            median=median,
            min=lowest,
            max=highest,
            max_minus_min=highest.value - lowest.value,
            stdev=spread.stdev,
            q25=spread.q25,
            q50=spread.q50,
            q75=spread.q75,
            iqr=spread.iqr,
            deciles=spread.deciles,
            skewness=spread.skewness,
            weighted_mean=(
                weighting.weighted_mean if weighting is not None else None
            ),
            weight_variable_dcid=(
                weights.variable_dcid if weights is not None else None
            ),
            weighted_place_count=(
                weighting.weighted_place_count
                if weighting is not None
                else None
            ),
            focal_entries=focal.entries,
            missing_focal_places=focal.missing_places,
        ),
        caveats=tuple(caveats),
    )
