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
"""Script name literals and typed metric records for analytical scripts.

Defines `ScriptName`, the per-script metric dataclasses (`TimeseriesMetrics`,
`RankingMetrics`, `DistributionMetrics`) and their shared value records
(`PeriodChange`, `LocalExtremum`, `PlaceSeriesSummary`, `PlaceValue`,
`LeaderDelta`, `CrossPlaceComparison`, `RankEntry`, `DistributionFocalEntry`),
and the `ScriptMetrics` union. Each metrics record names its script in a
`script` class variable so `OkScriptResult` can enforce at construction time
that it carries the metric record matching its `script`.
"""

from dataclasses import dataclass
from typing import ClassVar, Literal

__all__ = [
    "CrossPlaceComparison",
    "DistributionFocalEntry",
    "DistributionMetrics",
    "ExtremumKind",
    "LeaderDelta",
    "LocalExtremum",
    "PeriodChange",
    "PlaceSeriesSummary",
    "PlaceValue",
    "RankEntry",
    "RankingDirection",
    "RankingMetrics",
    "ScriptMetrics",
    "ScriptName",
    "TimeseriesMetrics",
]

type ScriptName = Literal[
    "align_cohort",
    "analyze_timeseries",
    "rank_cohort",
    "summarize_distribution",
    "compute_composition",
    "compute_derived_metric",
]

type ExtremumKind = Literal["peak", "trough"]
type RankingDirection = Literal["desc", "asc"]


@dataclass(frozen=True)
class PeriodChange:
    """The change between two consecutive observations.

    Attributes:
        from_date: Date of the earlier observation.
        to_date: Date of the later observation.
        from_value: Value of the earlier observation.
        to_value: Value of the later observation.
        absolute_change: `to_value - from_value`.
        percent_change: `absolute_change` as a percentage (0 to 100 scale) of
            `abs(from_value)`, or None when `from_value` is zero or the
            percentage is too large to represent as a float.
    """

    from_date: str
    to_date: str
    from_value: float
    to_value: float
    absolute_change: float
    percent_change: float | None


@dataclass(frozen=True)
class LocalExtremum:
    """An interior point where the series changes direction.

    A point is an extremum only when the steps on both sides of it are
    nonzero and of opposite sign, so a flat-topped peak or flat-bottomed
    trough is not reported.

    Attributes:
        date: Date of the point.
        value: Value of the point.
        kind: `peak` when the series rises into the point and falls out of
            it, `trough` in the opposite case.
    """

    date: str
    value: float
    kind: ExtremumKind


@dataclass(frozen=True)
class PlaceSeriesSummary:
    """The summary statistics of one place's series.

    Attributes:
        place_dcid: DCID of the place.
        place_name: Display name of the place.
        point_count: Number of dates in the series.
        start_date: Earliest date in the series.
        start_value: Value on `start_date`.
        end_date: Latest date in the series.
        end_value: Value on `end_date`.
        min_date: Date of the smallest value, the earliest on a tie.
        min_value: Smallest value.
        max_date: Date of the largest value, the earliest on a tie.
        max_value: Largest value.
        local_extrema: At most `LOCAL_EXTREMA_CAP` turning points, in date
            order.
        absolute_change: `end_value - start_value`; None for a single point.
        percent_change: `absolute_change` as a percentage (0 to 100 scale) of
            `abs(start_value)`; None for a single point, and None with a
            caveat on the result for a zero start or a percentage too large
            to represent as a float.
        cagr: Compound annual growth rate as a percentage (0 to 100 scale);
            None for a single point, and None with a growth-rate caveat on
            the result when an endpoint is not positive, the series spans
            less than a year, or the rate is too large to represent as a
            float.
        max_period_increase: Largest positive step, the earliest on a tie;
            None when the series never rises.
        max_period_decrease: Largest negative step, the earliest on a tie;
            None when the series never falls.
    """

    place_dcid: str
    place_name: str
    point_count: int
    start_date: str
    start_value: float
    end_date: str
    end_value: float
    min_date: str
    min_value: float
    max_date: str
    max_value: float
    local_extrema: tuple[LocalExtremum, ...]
    absolute_change: float | None
    percent_change: float | None
    cagr: float | None
    max_period_increase: PeriodChange | None
    max_period_decrease: PeriodChange | None


@dataclass(frozen=True)
class PlaceValue:
    """One place's observation value on a reference date.

    Attributes:
        place_dcid: DCID of the place.
        place_name: Display name of the place.
        value: Observation value.
    """

    place_dcid: str
    place_name: str
    value: float


@dataclass(frozen=True)
class LeaderDelta:
    """How a place compares against the leading place on a reference date.

    Attributes:
        place_dcid: DCID of the place.
        place_name: Display name of the place.
        absolute_delta: `value - leader value`, so never positive.
        percent_delta: `absolute_delta` as a percentage (0 to 100 scale) of the
            leader's absolute value, or None when the leader's value is zero
            or the percentage is too large to represent as a float.
    """

    place_dcid: str
    place_name: str
    absolute_delta: float
    percent_delta: float | None


@dataclass(frozen=True)
class CrossPlaceComparison:
    """Comparison of multiple places on one shared observation date.

    Attributes:
        reference_date: The date the places are compared on, chosen as
            `analyze_timeseries` documents; places without a value on it
            are left out of `entries`.
        entries: Every participating place, by value from largest to
            smallest, ties by DCID.
        spread: Largest minus smallest value among `entries`.
        leader: The first entry.
        deltas_from_leader: One entry per participating place other than
            the leader, in `entries` order.
    """

    reference_date: str
    entries: tuple[PlaceValue, ...]
    spread: float
    leader: PlaceValue
    deltas_from_leader: tuple[LeaderDelta, ...]


@dataclass(frozen=True)
class TimeseriesMetrics:
    """Metrics produced by `analyze_timeseries`.

    Attributes:
        place_count: Number of places with a series, equal to `len(series)`.
        series: One summary per place, in request order and then DCID order.
        missing_places: DCIDs of requested places with no observation in the
            window.
        cross_place_comparison: The comparison across places; None for a
            single place or when no two places share a date.
    """

    script: ClassVar[ScriptName] = "analyze_timeseries"

    place_count: int
    series: tuple[PlaceSeriesSummary, ...]
    missing_places: tuple[str, ...]
    cross_place_comparison: CrossPlaceComparison | None


@dataclass(frozen=True)
class RankEntry:
    """One place's rank, tie status, value, and percentile within a cohort.

    Attributes:
        rank: Standard competition rank in the ranking direction (1, 2, 2,
            4), starting at 1.
        is_tied: Whether another place in the cohort has the same value.
        place_dcid: DCID of the place.
        place_name: Display name of the place.
        value: Value on the reference date.
        percentile: Percentage (0 to 100 scale) of cohort places whose value
            is less than or equal to `value`. It does not depend on the
            ranking direction, so the largest value is at 100.
    """

    rank: int
    is_tied: bool
    place_dcid: str
    place_name: str
    value: float
    percentile: float


@dataclass(frozen=True)
class RankingMetrics:
    """Metrics produced by `rank_cohort`.

    Attributes:
        reference_date: The date the cohort is aligned to.
        direction: `desc` ranks the largest value first, `asc` the smallest.
        max_entries_per_end: The most entries requested at each end of the
            ranking; `top_n` and `bottom_n` are shorter when the cohort has
            fewer places.
        cohort_size: Number of places ranked.
        top_n: The leading entries in `direction`. When an end leaves out
            places tied with its last entry, the result carries a caveat
            saying how many share the rank.
        bottom_n: The trailing entries, ordered from the far end inward;
            disjoint from `top_n` when `cohort_size` is at least
            `2 * max_entries_per_end`, and overlapping it otherwise.
        focal_entries: Entries of the requested focal places, in request
            order.
        missing_focal_places: DCIDs of focal places with no value on
            `reference_date`.
    """

    script: ClassVar[ScriptName] = "rank_cohort"

    reference_date: str
    direction: RankingDirection
    max_entries_per_end: int
    cohort_size: int
    top_n: tuple[RankEntry, ...]
    bottom_n: tuple[RankEntry, ...]
    focal_entries: tuple[RankEntry, ...]
    missing_focal_places: tuple[str, ...]


@dataclass(frozen=True)
class DistributionFocalEntry:
    """One focal place benchmarked against a cohort's distribution.

    Attributes:
        place_dcid: DCID of the place.
        place_name: Display name of the place.
        value: Value on the reference date.
        diff_from_median: `value - median`, positive above the median.
        pct_of_median: `value` as a percentage (0 to 100 scale) of the
            cohort median, so 100 is at the median; None when the median is
            zero or negative, where a ratio to the median does not order
            places by value, or when the percentage is too large to
            represent as a float.
        diff_from_mean: `value - mean`, positive above the mean.
        z_score: `diff_from_mean` divided by the sample standard deviation;
            None when the cohort has one place or every place reports the
            same value.
        percentile: Percentage (0 to 100 scale) of cohort places whose value
            is less than or equal to `value`, as `compute_cohort_percentiles`
            defines it, so the largest value is at 100.
    """

    place_dcid: str
    place_name: str
    value: float
    diff_from_median: float
    pct_of_median: float | None
    diff_from_mean: float
    z_score: float | None
    percentile: float


@dataclass(frozen=True)
class DistributionMetrics:
    """Metrics produced by `summarize_distribution`.

    Attributes:
        reference_date: The date the cohort is aligned to.
        cohort_size: Number of places in the cohort.
        mean: Arithmetic mean of the cohort's values.
        median: Median of the cohort's values.
        min: The place with the smallest value, ties by DCID.
        max: The place with the largest value, ties by DCID.
        max_minus_min: `max.value - min.value`, in the variable's unit.
        stdev: Sample standard deviation (divisor `cohort_size - 1`); None
            when `cohort_size` is below 2.
        q25: First quartile by inclusive linear interpolation; None when
            `cohort_size` is below 2.
        q50: Second quartile, equal to `median`; None when `cohort_size` is
            below 2.
        q75: Third quartile by inclusive linear interpolation; None when
            `cohort_size` is below 2.
        iqr: `q75 - q25`; None when `cohort_size` is below 2.
        deciles: The nine decile cut points keyed `p10` through `p90`, by
            inclusive linear interpolation; None when `cohort_size` is below
            2.
        skewness: Adjusted Fisher-Pearson sample skewness, positive for a
            long upper tail; None when `cohort_size` is below 3 or every
            place reports the same value.
        weighted_mean: Mean of the cohort's values weighted by the weights
            variable over the places with a positive weight; None when no
            weights are given or the weighted mean is omitted with a caveat.
        weight_variable_dcid: DCID of the weights variable; None when no
            weights are given. Set even when `weighted_mean` is omitted.
        weighted_place_count: Number of cohort places with a positive
            weight on `reference_date`, or 0 when a negative weight omits
            the weighted mean; None when no weights are given.
        focal_entries: Entries of the requested focal places with a value
            on `reference_date`, in request order with duplicates removed.
        missing_focal_places: DCIDs of focal places with no value on
            `reference_date`.
    """

    script: ClassVar[ScriptName] = "summarize_distribution"

    reference_date: str
    cohort_size: int
    mean: float
    median: float
    min: PlaceValue
    max: PlaceValue
    max_minus_min: float
    stdev: float | None
    q25: float | None
    q50: float | None
    q75: float | None
    iqr: float | None
    deciles: dict[str, float] | None
    skewness: float | None
    weighted_mean: float | None
    weight_variable_dcid: str | None
    weighted_place_count: int | None
    focal_entries: tuple[DistributionFocalEntry, ...]
    missing_focal_places: tuple[str, ...]


type ScriptMetrics = TimeseriesMetrics | RankingMetrics | DistributionMetrics
