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
"""Summarizes the time series of one or more places.

`analyze_timeseries` computes start and end values, net change, global and
local extrema, largest period-over-period changes, and compound annual growth
rates per place, and compares multiple places on a date they share.
`reduce_series` reduces each place's series to one figure over a date window
the cohort shares, as a `WindowCohort` that the cohort scripts rank,
summarize, or relate.
"""

import calendar
import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise
from typing import Literal

from narratives_agent.analytics.alignment import (
    DEFAULT_MIN_COVERAGE,
    WindowCohort,
    WindowRow,
    has_adequate_coverage,
    select_reference_date,
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
    format_percent,
    format_place_names,
    format_scaling_factor,
)
from narratives_agent.analytics.metrics import (
    CrossPlaceComparison,
    ExtremumKind,
    LeaderDelta,
    LocalExtremum,
    PeriodChange,
    PlaceSeriesSummary,
    PlaceValue,
    SeriesMetric,
    TimeseriesMetrics,
    format_series_metric_label,
)
from narratives_agent.analytics.provenance import merge_provenance
from narratives_agent.analytics.script_inputs import (
    build_invalid_parameters_refusal,
    build_refusal,
    collect_variable_provenance,
    resolve_target_places,
    validate_place_dcids,
)
from narratives_agent.analytics.tables import (
    WINDOW_DATE_SEPARATOR,
    ObservationRow,
    ObservationTable,
    format_reference_date_phrase,
    is_inverted_date_range,
    is_valid_observation_date,
    is_within_date_range,
)

__all__ = [
    "LOCAL_EXTREMA_CAP",
    "analyze_timeseries",
    "reduce_series",
]

_SCRIPT_NAME: Literal["analyze_timeseries"] = "analyze_timeseries"
_REDUCE_SCRIPT_NAME: Literal["reduce_series"] = "reduce_series"
# At most this many interior turning points are kept per place.
LOCAL_EXTREMA_CAP = 10
# A growth rate over a shorter span would extrapolate a short-term change.
_MIN_GROWTH_SPAN_YEARS = 1.0
_MONTHS_PER_YEAR = 12
# Places are compared only on a date that at least this many share.
_MIN_PLACES_SHARING_DATE = 2

# Why a change or growth rate is not reported for a place.
type _PlaceIssue = Literal[
    "single_point",
    "zero_start",
    "cagr_start_not_positive",
    "cagr_end_not_positive",
    "cagr_short_span",
    "percent_not_finite",
    "cagr_not_finite",
    "change_not_finite",
]
# One caveat per issue names every place it affects.
_PLACE_ISSUE_CAVEATS: dict[_PlaceIssue, str] = {
    "single_point": (
        "Only one observation is available for {places}, so no change over "
        "time is computed."
    ),
    "zero_start": (
        "The percentage change is undefined for {places} because the "
        "starting value is zero."
    ),
    "cagr_start_not_positive": (
        "The compound annual growth rate is undefined for {places} because "
        "the starting value is not positive."
    ),
    "cagr_end_not_positive": (
        "The compound annual growth rate is undefined for {places} because "
        "the ending value is not positive."
    ),
    "cagr_short_span": (
        "The compound annual growth rate is undefined for {places} because "
        "the series spans less than a year."
    ),
    "percent_not_finite": (
        "The percentage change is undefined for {places} because it is too "
        "large to represent."
    ),
    "cagr_not_finite": (
        "The compound annual growth rate is undefined for {places} because "
        "it is too large to represent."
    ),
    "change_not_finite": (
        "The change is undefined for {places} because it is too large to "
        "represent."
    ),
}
# A date's precision, named by its length, as in a `YYYY-MM` monthly date.
_PRECISION_NAMES: dict[int, str] = {4: "yearly", 7: "monthly", 10: "daily"}
# The window metrics computed over two consecutive observations of a place.
_CONSECUTIVE_METRICS: frozenset[SeriesMetric] = frozenset(
    {"latest_period_change", "latest_period_percent_change"}
)
# The window metrics reported as a percentage rather than in the source unit.
_PERCENT_METRICS: frozenset[SeriesMetric] = frozenset(
    {"latest_period_percent_change", "percent_change"}
)
_PERCENT_UNIT = "Percent"
_GROWTH_RATE_UNIT = "Percent per year"
# How `reduce_series` computes each metric, completing its methodology.
_REDUCTION_METHODS: dict[SeriesMetric, str] = {
    "latest_period_change": (
        "the latest pair of consecutive observations the places share"
    ),
    "latest_period_percent_change": (
        "the latest pair of consecutive observations the places share"
    ),
    "absolute_change": "each place's observations at both ends of the window",
    "percent_change": "each place's observations at both ends of the window",
    "cagr": "each place's observations at both ends of the window",
    "period_mean": "every observation of each place within the window",
}


@dataclass(frozen=True)
class _OverallChange:
    """The start-to-end change of one series and why any part is missing."""

    absolute_change: float | None
    percent_change: float | None
    cagr: float | None
    issues: tuple[_PlaceIssue, ...]


def _compute_fractional_year(date: str) -> float:
    """Converts a `YYYY`, `YYYY-MM`, or `YYYY-MM-DD` date to a decimal year.

    A year counts from its start, and a month adds its offset as twelfths of
    a year. A day adds its offset as a fraction of its own month's length, so
    the first day of a month equals the month, the same calendar date in two
    years is a whole number of years apart, and consecutive days differ by
    one twelfth of a year divided by the month's length, including across
    month boundaries and February 29. Annual, monthly, and daily series thus
    all yield the elapsed years that a growth rate needs.

    Args:
        date: A date that `is_valid_observation_date` accepts, so its month
            is 1 to 12 and its day exists in that month.

    Returns:
        The date as a decimal year, for example 2020.5 for `2020-07`.

    Raises:
        ValueError: If a date component is not numeric or the month is not
            1 to 12.
    """
    parts = [int(part) for part in date.split("-")]
    year = float(parts[0])
    if len(parts) > 1:
        year += (parts[1] - 1) / _MONTHS_PER_YEAR
    if len(parts) > 2:
        month_days = calendar.monthrange(parts[0], parts[1])[1]
        year += (parts[2] - 1) / month_days / _MONTHS_PER_YEAR
    return year


def _compute_percent_change(start: float, end: float) -> float | None:
    """Returns the percentage change from `start` to `end`, or None.

    The change is None when `start` is zero, and when it overflows a float,
    which only values near the float limit or a tiny `start` can cause.
    """
    if start == 0.0:
        return None
    percent = (end - start) / abs(start) * PERCENT_SCALE
    return percent if math.isfinite(percent) else None


def _compute_period_changes(
    points: Sequence[ObservationRow],
) -> list[PeriodChange]:
    """Returns the change over each consecutive pair of observations."""
    return [
        PeriodChange(
            from_date=earlier.date,
            to_date=later.date,
            from_value=earlier.value,
            to_value=later.value,
            absolute_change=later.value - earlier.value,
            percent_change=_compute_percent_change(earlier.value, later.value),
        )
        for earlier, later in pairwise(points)
    ]


def _find_extreme_period_changes(
    changes: Sequence[PeriodChange],
) -> tuple[PeriodChange | None, PeriodChange | None]:
    """Returns the largest increase and the largest decrease among `changes`.

    Either is None when the series never rises or never falls. On a tie in
    size, the earliest step is returned.
    """
    increases = [change for change in changes if change.absolute_change > 0.0]
    decreases = [change for change in changes if change.absolute_change < 0.0]
    largest_increase = min(
        increases,
        key=lambda change: (-change.absolute_change, change.to_date),
        default=None,
    )
    largest_decrease = min(
        decreases,
        key=lambda change: (change.absolute_change, change.to_date),
        default=None,
    )
    return largest_increase, largest_decrease


def _find_local_extrema(
    points: Sequence[ObservationRow],
) -> tuple[LocalExtremum, ...]:
    """Finds the interior points where the first difference changes sign.

    A point is a peak when the series rises into it and falls out of it, and
    a trough in the opposite case; a flat step on either side is not a
    reversal. Prominence is the smaller of the two swings around the point,
    and the `LOCAL_EXTREMA_CAP` most prominent points are kept, in date
    order.
    """
    candidates: list[tuple[float, LocalExtremum]] = []
    for index in range(1, len(points) - 1):
        left = points[index].value - points[index - 1].value
        right = points[index + 1].value - points[index].value
        kind: ExtremumKind | None = None
        if left > 0.0 and right < 0.0:
            kind = "peak"
        elif left < 0.0 and right > 0.0:
            kind = "trough"
        if kind is not None:
            prominence = min(abs(left), abs(right))
            candidates.append(
                (
                    prominence,
                    LocalExtremum(
                        date=points[index].date,
                        value=points[index].value,
                        kind=kind,
                    ),
                )
            )
    candidates.sort(key=lambda item: (-item[0], item[1].date))
    kept = [
        extremum for _prominence, extremum in candidates[:LOCAL_EXTREMA_CAP]
    ]
    return tuple(sorted(kept, key=lambda extremum: extremum.date))


def _compute_compound_annual_growth_rate(
    start: ObservationRow, end: ObservationRow
) -> tuple[float | None, _PlaceIssue | None]:
    """Returns the compound annual growth rate in percent, or why it is not.

    The rate is defined only for positive endpoints at least
    `_MIN_GROWTH_SPAN_YEARS` apart, because annualizing a shorter change
    extrapolates it, and a growth rate that is not defined must not be
    estimated. A rate that overflows a float, which only a ratio near the
    float limit can cause, is not defined either.
    """
    if start.value <= 0.0:
        return None, "cagr_start_not_positive"
    if end.value <= 0.0:
        return None, "cagr_end_not_positive"
    start_year = _compute_fractional_year(start.date)
    years = _compute_fractional_year(end.date) - start_year
    if years < _MIN_GROWTH_SPAN_YEARS:
        return None, "cagr_short_span"
    ratio = end.value / start.value
    growth = (ratio ** (1.0 / years) - 1.0) * PERCENT_SCALE
    if not math.isfinite(growth):
        return None, "cagr_not_finite"
    return growth, None


def _compute_overall_change(points: Sequence[ObservationRow]) -> _OverallChange:
    """Returns the absolute, percentage, and annualized start-to-end change.

    A single observation has no change, a zero start or an overflowing
    percentage has no percentage change, and the growth rate follows the
    rules of `_compute_compound_annual_growth_rate`; each missing figure is
    recorded as an issue.
    """
    start, end = points[0], points[-1]
    if len(points) == 1:
        return _OverallChange(None, None, None, ("single_point",))
    issues: list[_PlaceIssue] = []
    percent_change = _compute_percent_change(start.value, end.value)
    if percent_change is None:
        issues.append(
            "zero_start" if start.value == 0.0 else "percent_not_finite"
        )
    cagr, cagr_issue = _compute_compound_annual_growth_rate(start, end)
    if cagr_issue is not None:
        issues.append(cagr_issue)
    return _OverallChange(
        absolute_change=end.value - start.value,
        percent_change=percent_change,
        cagr=cagr,
        issues=tuple(issues),
    )


def _summarize_place(
    points: Sequence[ObservationRow],
) -> tuple[PlaceSeriesSummary, tuple[_PlaceIssue, ...]]:
    """Summarizes one place's series, sorted by date, with its issues."""
    start, end = points[0], points[-1]
    lowest = min(points, key=lambda row: (row.value, row.date))
    highest = min(points, key=lambda row: (-row.value, row.date))
    overall = _compute_overall_change(points)
    largest_increase, largest_decrease = _find_extreme_period_changes(
        _compute_period_changes(points)
    )
    summary = PlaceSeriesSummary(
        place_dcid=start.place_dcid,
        place_name=start.place_name,
        point_count=len(points),
        start_date=start.date,
        start_value=start.value,
        end_date=end.date,
        end_value=end.value,
        min_date=lowest.date,
        min_value=lowest.value,
        max_date=highest.date,
        max_value=highest.value,
        local_extrema=_find_local_extrema(points),
        absolute_change=overall.absolute_change,
        percent_change=overall.percent_change,
        cagr=overall.cagr,
        max_period_increase=largest_increase,
        max_period_decrease=largest_decrease,
    )
    return summary, overall.issues


def _summarize_places(
    series: Mapping[str, Mapping[str, ObservationRow]],
    ordered_places: Sequence[str],
) -> tuple[list[PlaceSeriesSummary], list[str]]:
    """Summarizes each place in order, with one caveat per issue.

    Each caveat names every place the issue affects, up to the cap that
    `format_place_names` applies, so a large cohort yields a few caveats
    rather than one per place.
    """
    summaries: list[PlaceSeriesSummary] = []
    places_by_issue: dict[_PlaceIssue, list[str]] = {}
    for place in ordered_places:
        points = sorted(series[place].values(), key=lambda row: row.date)
        summary, issues = _summarize_place(points)
        summaries.append(summary)
        for issue in issues:
            places_by_issue.setdefault(issue, []).append(summary.place_name)
    caveats = [
        _PLACE_ISSUE_CAVEATS[issue].format(places=format_place_names(names))
        for issue, names in places_by_issue.items()
    ]
    return summaries, caveats


def _select_comparison_date(
    dates_by_place: Mapping[str, set[str]],
) -> tuple[str, bool] | None:
    """Picks the date to compare places on, or None when none is shared.

    Among the dates at least `_MIN_PLACES_SHARING_DATE` places share,
    `select_reference_date` (the rule `align_cohort` uses) picks the latest
    date that `DEFAULT_MIN_COVERAGE` of the places share, or else the date
    most places share, the latest on a tie. The places counted are those
    with observations in the window, whereas `align_cohort` counts the
    requested places.

    Returns:
        The date, and whether it met `DEFAULT_MIN_COVERAGE`.
    """
    counts = Counter(
        date for place_dates in dates_by_place.values() for date in place_dates
    )
    shared = {
        date: count
        for date, count in counts.items()
        if count >= _MIN_PLACES_SHARING_DATE
    }
    if not shared:
        return None
    place_count = len(dates_by_place)
    reference_date = select_reference_date(shared, place_count)
    covered = has_adequate_coverage(shared[reference_date], place_count)
    return reference_date, covered


def _describe_comparison_date(
    reference_date: str, *, covered: bool, left_out: Sequence[str]
) -> str:
    """States which date the comparison uses and the places it leaves out.

    `covered` is True when `DEFAULT_MIN_COVERAGE` of the places share the
    date, and `left_out` holds the names of the places with no value on it.
    """
    share = format_percent(DEFAULT_MIN_COVERAGE)
    names = format_place_names(left_out)
    if covered:
        return (
            f"The comparison uses {reference_date}, the latest date at least "
            f"{share} of the places share, which leaves out {names}."
        )
    return (
        f"No date is shared by at least {share} of the places; the "
        f"comparison uses {reference_date}, the date the most places share, "
        f"which leaves out {names}."
    )


def _build_comparison(
    rows: Sequence[ObservationRow], reference_date: str
) -> CrossPlaceComparison:
    """Compares the places of `rows`, one row per place on `reference_date`.

    Entries are ordered by value, largest first and then by DCID, and each
    entry after the leader carries its difference from the leader.
    """
    entries = sorted(rows, key=lambda row: (-row.value, row.place_dcid))
    leader = entries[0]
    return CrossPlaceComparison(
        reference_date=reference_date,
        entries=tuple(
            PlaceValue(
                place_dcid=row.place_dcid,
                place_name=row.place_name,
                value=row.value,
            )
            for row in entries
        ),
        spread=entries[0].value - entries[-1].value,
        leader=PlaceValue(
            place_dcid=leader.place_dcid,
            place_name=leader.place_name,
            value=leader.value,
        ),
        deltas_from_leader=tuple(
            LeaderDelta(
                place_dcid=row.place_dcid,
                place_name=row.place_name,
                absolute_delta=row.value - leader.value,
                percent_delta=_compute_percent_change(leader.value, row.value),
            )
            for row in entries[1:]
        ),
    )


def _compare_places(
    series: Mapping[str, Mapping[str, ObservationRow]],
    ordered_places: Sequence[str],
    place_names: Mapping[str, str],
) -> tuple[CrossPlaceComparison | None, list[str]]:
    """Compares the places on one date most of them share, with caveats.

    A caveat names the places with no value on the chosen date. When no two
    places share a date, there is no comparison.
    """
    dates_by_place = {place: set(series[place]) for place in ordered_places}
    selection = _select_comparison_date(dates_by_place)
    if selection is None:
        return None, [
            "The places share no observation date, so they are not "
            "compared against each other."
        ]
    reference_date, covered = selection
    left_out = [
        place_names.get(place, place)
        for place in ordered_places
        if reference_date not in dates_by_place[place]
    ]
    caveats = (
        [
            _describe_comparison_date(
                reference_date, covered=covered, left_out=left_out
            )
        ]
        if left_out
        else []
    )
    rows = [
        series[place][reference_date]
        for place in ordered_places
        if reference_date in dates_by_place[place]
    ]
    return _build_comparison(rows, reference_date), caveats


def _describe_missing_places(
    table: ObservationTable, missing_places: Sequence[str], *, windowed: bool
) -> str:
    """States which places have no observation in the analyzed rows.

    The caveat names a few places, while `TimeseriesMetrics.missing_places`
    still lists every place. `windowed` is True when the call set a date
    window, which the caveat then mentions.
    """
    listed = format_place_names(
        [table.place_names.get(place, place) for place in missing_places]
    )
    window = " within the requested window" if windowed else ""
    subject = "it is" if len(missing_places) == 1 else "they are"
    return (
        f"No observations are available for {listed}{window}, so {subject} "
        "left out of the analysis."
    )


def _validate_parameters(
    places: Sequence[str] | None,
    start_date: str | None,
    end_date: str | None,
) -> str | None:
    """Returns why the parameters are invalid, or None when they are valid."""
    if places is not None:
        error = validate_place_dcids(places, parameter_name="places")
        if error is not None:
            return error
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
            f"The date window starts at {start_date} and ends at "
            f"{end_date}, which is before it starts."
        )
    return None


def _group_series_by_place(
    table: ObservationTable,
    places: Sequence[str],
    start_date: str | None,
    end_date: str | None,
) -> dict[str, dict[str, ObservationRow]]:
    """Groups the rows in the window by place and then by date.

    Only `places` are kept when it is not empty. When a place has two rows
    on the same date, the last row in table order is kept.
    """
    place_filter = set(places) if places else None
    series: dict[str, dict[str, ObservationRow]] = {}
    for row in table.rows:
        if place_filter is not None and row.place_dcid not in place_filter:
            continue
        if not is_within_date_range(row.date, start_date, end_date):
            continue
        series.setdefault(row.place_dcid, {})[row.date] = row
    return series


def _keep_one_precision(
    series: Mapping[str, Mapping[str, ObservationRow]],
) -> tuple[dict[str, dict[str, ObservationRow]], list[str]]:
    """Keeps one date precision per place, and lists the places filtered.

    A place whose dates mix precisions (`2020` and `2020-01`) keeps only
    its most common precision, the finer one on a tie, because changes and
    turning points across precisions compare values for different periods.
    """
    kept: dict[str, dict[str, ObservationRow]] = {}
    mixed: list[str] = []
    for place, rows_by_date in series.items():
        counts = Counter(len(date) for date in rows_by_date)
        precision = max(counts, key=lambda width: (counts[width], width))
        kept[place] = {
            date: row
            for date, row in rows_by_date.items()
            if len(date) == precision
        }
        if len(counts) > 1:
            mixed.append(place)
    return kept, mixed


def _describe_mixed_precision(
    table: ObservationTable, mixed: Sequence[str]
) -> str:
    """States which places report dates at more than one precision."""
    names = format_place_names(
        [table.place_names.get(place, place) for place in mixed]
    )
    return (
        f"{names} {conjugate_have(len(mixed))} dates at more than one "
        "precision, such as years and months, so only the most common "
        "precision is analyzed for each."
    )


def _order_places(
    observed: Iterable[str], preferred: Sequence[str]
) -> list[str]:
    """Orders the observed places: `preferred` order first, then sorted."""
    observed_set = set(observed)
    ordered = [place for place in preferred if place in observed_set]
    listed = set(ordered)
    ordered.extend(
        place for place in sorted(observed_set) if place not in listed
    )
    return ordered


def _describe_window(start_date: str | None, end_date: str | None) -> str:
    """Returns the date window as a phrase, or `""` when none was set."""
    if start_date is None and end_date is None:
        return ""
    return (
        f" from {start_date or 'the earliest date'} to "
        f"{end_date or 'the latest date'}"
    )


def analyze_timeseries(
    table: ObservationTable,
    *,
    places: Sequence[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    step_id: str = "s1",
) -> ScriptResult:
    """Summarizes each place's series in `table` and compares the places.

    When a place has two rows on the same date, the last row in table order
    is used. When a place's dates mix precisions, only its most common
    precision is analyzed, and a caveat names the place.

    Args:
        table: The table to analyze.
        places: The places to include, in the order to report them. When
            None or empty, every place in the table is included, in request
            order and then sorted order.
        start_date: The inclusive start of the window, a `YYYY`, `YYYY-MM`,
            or `YYYY-MM-DD` date compared as `is_within_date_range` does.
        end_date: The inclusive end of the window, in the same form.
        step_id: Identifier of the analysis step (for example, `"s1"`).

    Returns:
        A result whose `metrics` is a `TimeseriesMetrics` holding
        `place_count`, `series` (one `PlaceSeriesSummary` per place),
        `missing_places` (the places asked for, through `places` or the
        table's `requested_places`, that have no row in the window), and
        `cross_place_comparison` (on the latest date that
        `DEFAULT_MIN_COVERAGE` of the places with observations share, or
        else the date most places share; None for a single place or when no
        two places share a date). The result is refused with
        `invalid_parameters` when a bound is not a valid date, the start
        falls after the end, or `places` is a string or holds an invalid
        DCID, and with
        `no_observations` when no row matches the places and the window.
    """
    error = _validate_parameters(places, start_date, end_date)
    if error is not None:
        return build_invalid_parameters_refusal(
            table, script=_SCRIPT_NAME, step_id=step_id, caveat=error
        )
    requested = tuple(dict.fromkeys(places)) if places else ()
    grouped = _group_series_by_place(table, requested, start_date, end_date)
    if not grouped:
        return build_refusal(
            table,
            script=_SCRIPT_NAME,
            step_id=step_id,
            reason="no_observations",
            coverage=None,
            caveat="No observations match the requested places and date "
            f"window for {table.variable_name}.",
        )

    series, mixed = _keep_one_precision(grouped)
    preferred = tuple(dict.fromkeys(requested or table.requested_places))
    ordered_places = _order_places(series, preferred)
    windowed = start_date is not None or end_date is not None
    caveats: list[str] = []
    missing_places = tuple(place for place in preferred if place not in series)
    if missing_places:
        caveats.append(
            _describe_missing_places(table, missing_places, windowed=windowed)
        )
    if mixed:
        caveats.append(
            _describe_mixed_precision(table, _order_places(mixed, preferred))
        )
    summaries, summary_caveats = _summarize_places(series, ordered_places)
    caveats.extend(summary_caveats)
    comparison: CrossPlaceComparison | None = None
    if len(ordered_places) > 1:
        comparison, comparison_caveats = _compare_places(
            series, ordered_places, table.place_names
        )
        caveats.extend(comparison_caveats)

    provenance = merge_provenance(
        table.provenance,
        methodology=(
            "Start-to-end change, extrema, largest period-over-period "
            "changes, and compound annual growth rate computed per place "
            "over the observed series"
            f"{_describe_window(start_date, end_date)}."
        ),
    )
    return OkScriptResult(
        step_id=step_id,
        script=_SCRIPT_NAME,
        variables=(table.variable_dcid,),
        variable_names={table.variable_dcid: table.variable_name},
        unit=table.unit,
        scaling_factor=table.scaling_factor,
        provenance=provenance,
        variable_provenance=collect_variable_provenance(table),
        metrics=TimeseriesMetrics(
            place_count=len(summaries),
            series=tuple(summaries),
            missing_places=missing_places,
            cross_place_comparison=comparison,
        ),
        caveats=tuple(caveats),
    )


@dataclass(frozen=True)
class _WindowRefusal:
    """Why no shared date window could be selected for a reduction."""

    reason: RefusalReason
    caveat: str


def _keep_dominant_precision(
    series: Mapping[str, Mapping[str, ObservationRow]],
) -> tuple[dict[str, dict[str, ObservationRow]], list[str], int]:
    """Keeps one date precision across the whole cohort.

    The precision is the most common one across every observation, the
    finer one on a tie (`10 > 7 > 4`), because a window shared by the
    places must compare values for the same kind of period. A place left
    with no observation at that precision is dropped.

    Returns:
        The series at the chosen precision, the places that lost rows of
        another precision, and the chosen date length.
    """
    counts = Counter(len(date) for rows in series.values() for date in rows)
    precision = max(counts, key=lambda width: (counts[width], width))
    kept: dict[str, dict[str, ObservationRow]] = {}
    affected: list[str] = []
    for place, rows_by_date in series.items():
        filtered = {
            date: row
            for date, row in rows_by_date.items()
            if len(date) == precision
        }
        if len(filtered) < len(rows_by_date):
            affected.append(place)
        if filtered:
            kept[place] = filtered
    return kept, affected, precision


def _describe_dropped_precision(
    table: ObservationTable, places: Sequence[str], precision: int
) -> str:
    """States which places lost observations of another precision."""
    names = format_place_names(
        [table.place_names.get(place, place) for place in places]
    )
    granularity = _PRECISION_NAMES[precision]
    return (
        f"{names} {conjugate_have(len(places))} dates at a precision other "
        f"than the cohort's {granularity} dates, so only {granularity} "
        "observations are compared."
    )


def _select_consecutive_window(
    series: Mapping[str, Mapping[str, ObservationRow]],
    cohort_size: int,
    min_coverage: float,
) -> tuple[str, str] | None:
    """Selects the latest pair of consecutive dates the places share.

    A pair is counted for a place only when the two dates are adjacent in
    that place's own series, so a place missing the dates in between never
    reports a multi-period gap as one period. The latest pair whose count
    meets `min_coverage` is chosen; when none does, the pair with the
    largest count, the latest on a tie, is chosen so that the coverage
    check reports it.

    Returns:
        The `(start, end)` pair, or None when no place has two dates.
    """
    pair_counts = Counter(
        pair for rows in series.values() for pair in pairwise(sorted(rows))
    )
    if not pair_counts:
        return None
    adequate = [
        pair
        for pair, count in pair_counts.items()
        if has_adequate_coverage(count, cohort_size, min_coverage)
    ]
    if adequate:
        return max(adequate, key=lambda pair: (pair[1], pair[0]))
    return max(
        pair_counts, key=lambda pair: (pair_counts[pair], pair[1], pair[0])
    )


def _select_span_window(
    series: Mapping[str, Mapping[str, ObservationRow]],
    cohort_size: int,
    min_coverage: float,
    *,
    should_require_year_span: bool,
) -> tuple[str, str] | None:
    """Selects the window between two dates that enough places share.

    End dates are tried from the latest and start dates from the earliest,
    so the chosen window ends on the latest date for which a window meets
    `min_coverage`, and is the widest such window ending there. When no
    window meets it, the window most places share is chosen (the latest
    end, then the earliest start, on a tie) so that the coverage check
    reports it. A pair whose shared count can neither meet `min_coverage`
    nor beat the best fallback is skipped without counting its places.

    Args:
        series: Each place's observations by date, at one precision.
        cohort_size: The number of target places; at least 1.
        min_coverage: The share of the target places a window must hold.
        should_require_year_span: Whether the window must span at least
            `_MIN_GROWTH_SPAN_YEARS`, as a growth rate requires.

    Returns:
        The `(start, end)` window, or None when no place has observations on
        two dates that the window rules allow.
    """
    # Each date's places are an integer bitmask, so the places two dates
    # share are counted with one `&` and `bit_count` rather than a set
    # intersection, which keeps the full scan of a refused window fast.
    bits_by_place = {
        place: 1 << index for index, place in enumerate(sorted(series))
    }
    masks: dict[str, int] = {}
    for place, rows_by_date in series.items():
        for date in rows_by_date:
            masks[date] = masks.get(date, 0) | bits_by_place[place]
    counts = {date: mask.bit_count() for date, mask in masks.items()}
    years = {date: _compute_fractional_year(date) for date in masks}
    required = _count_required_places(cohort_size, min_coverage)
    dates = sorted(masks)
    fallback: tuple[str, str] | None = None
    fallback_count = 0
    for end in reversed(dates):
        for start in dates:
            if start >= end:
                break
            if (
                should_require_year_span
                and years[end] - years[start] < _MIN_GROWTH_SPAN_YEARS
            ):
                break
            upper_bound = min(counts[end], counts[start])
            if upper_bound < required and upper_bound <= fallback_count:
                continue
            count = (masks[end] & masks[start]).bit_count()
            if count >= required:
                return start, end
            if count > fallback_count:
                fallback, fallback_count = (start, end), count
    return fallback


def _count_required_places(cohort_size: int, min_coverage: float) -> int:
    """Returns the fewest places, at least one, that meet `min_coverage`.

    The count comes from `has_adequate_coverage`, so a window that holds it
    is exactly a window the coverage check accepts.
    """
    return next(
        (
            count
            for count in range(1, cohort_size + 1)
            if has_adequate_coverage(count, cohort_size, min_coverage)
        ),
        cohort_size + 1,
    )


def _select_window(
    table: ObservationTable,
    series: Mapping[str, Mapping[str, ObservationRow]],
    metric: SeriesMetric,
    cohort_size: int,
    min_coverage: float,
) -> tuple[str, str] | _WindowRefusal:
    """Selects the shared window of a metric, or states why there is none.

    The consecutive metrics use `_select_consecutive_window`; the others use
    `_select_span_window`, which for `cagr` admits only windows of at least
    a year.
    """
    if metric in _CONSECUTIVE_METRICS:
        window = _select_consecutive_window(series, cohort_size, min_coverage)
    else:
        window = _select_span_window(
            series,
            cohort_size,
            min_coverage,
            should_require_year_span=metric == "cagr",
        )
    if window is not None:
        return window
    if metric == "cagr" and (
        _select_span_window(
            series, cohort_size, min_coverage, should_require_year_span=False
        )
        is not None
    ):
        return _WindowRefusal(
            reason="invalid_parameters",
            caveat=(
                f"No place has two observations of {table.variable_name} "
                "in the requested date window at least a year apart, so "
                "the compound annual growth rate is undefined."
            ),
        )
    label = format_series_metric_label(metric, table.variable_name)
    return _WindowRefusal(
        reason="insufficient_coverage",
        caveat=(
            f"No place has two observations of {table.variable_name} in the "
            f"requested date window, so no {label} can be computed."
        ),
    )


def _is_window_member(
    rows_by_date: Mapping[str, ObservationRow],
    window: tuple[str, str],
    *,
    should_require_adjacency: bool,
) -> bool:
    """Returns whether a place has observations at both ends of `window`.

    With `should_require_adjacency`, the place must also have no
    observation strictly between the two ends, so that a consecutive
    metric never spans a gap in the place's series.
    """
    start, end = window
    if start not in rows_by_date or end not in rows_by_date:
        return False
    if should_require_adjacency:
        return not any(start < date < end for date in rows_by_date)
    return True


def _compute_exact_mean(values: Sequence[float]) -> float:
    """Returns the mean of `values`, summed exactly and rounded once.

    Every finite float is an integer over a power of two, so the values are
    summed exactly as integers over their largest denominator, which is
    much faster than summing `Fraction` objects. Rounding once keeps the
    mean within the values' range and finite. `values` must not be empty.
    """
    ratios = [value.as_integer_ratio() for value in values]
    denominator = max(ratio_denominator for _, ratio_denominator in ratios)
    total = sum(
        numerator * (denominator // ratio_denominator)
        for numerator, ratio_denominator in ratios
    )
    return float(Fraction(total, denominator * len(values)))


def _reduce_place(
    rows_by_date: Mapping[str, ObservationRow],
    window: tuple[str, str],
    metric: SeriesMetric,
) -> tuple[WindowRow | None, _PlaceIssue | None]:
    """Computes one place's figure over `window`, or why it is undefined.

    `period_mean` averages every observation within the window, both ends
    included, summed exactly; the change metrics compare the observations
    at the two ends.
    """
    start, end = rows_by_date[window[0]], rows_by_date[window[1]]
    value: float | None
    issue: _PlaceIssue | None = None
    match metric:
        case "latest_period_change" | "absolute_change":
            value = end.value - start.value
            if not math.isfinite(value):
                value, issue = None, "change_not_finite"
        case "latest_period_percent_change" | "percent_change":
            value = _compute_percent_change(start.value, end.value)
            if value is None:
                issue = (
                    "zero_start" if start.value == 0.0 else "percent_not_finite"
                )
        case "cagr":
            value, issue = _compute_compound_annual_growth_rate(start, end)
        case "period_mean":
            value = _compute_exact_mean(
                [
                    row.value
                    for date, row in rows_by_date.items()
                    if window[0] <= date <= window[1]
                ]
            )
    if value is None:
        return None, issue
    return (
        WindowRow(
            place_dcid=start.place_dcid,
            place_name=start.place_name,
            from_date=start.date,
            to_date=end.date,
            from_value=start.value,
            to_value=end.value,
            value=value,
        ),
        None,
    )


def _reduce_places(
    series: Mapping[str, Mapping[str, ObservationRow]],
    window: tuple[str, str],
    metric: SeriesMetric,
) -> tuple[list[WindowRow], list[str]]:
    """Reduces every place in the window, with one caveat per issue.

    Returns:
        The rows sorted by place DCID, and the caveats naming the places
        whose figure is undefined.
    """
    should_require_adjacency = metric in _CONSECUTIVE_METRICS
    rows: list[WindowRow] = []
    names_by_issue: dict[_PlaceIssue, list[str]] = {}
    for place in sorted(series):
        rows_by_date = series[place]
        if not _is_window_member(
            rows_by_date,
            window,
            should_require_adjacency=should_require_adjacency,
        ):
            continue
        row, issue = _reduce_place(rows_by_date, window, metric)
        if row is not None:
            rows.append(row)
        elif issue is not None:
            place_name = rows_by_date[window[0]].place_name
            names_by_issue.setdefault(issue, []).append(place_name)
    caveats = [
        _PLACE_ISSUE_CAVEATS[issue].format(places=format_place_names(names))
        for issue, names in names_by_issue.items()
    ]
    return rows, caveats


def _resolve_reduced_unit(
    table: ObservationTable, metric: SeriesMetric
) -> tuple[str | None, float | None]:
    """Returns the unit and scaling factor of a metric's figures."""
    if metric in _PERCENT_METRICS:
        return _PERCENT_UNIT, None
    if metric == "cagr":
        return _GROWTH_RATE_UNIT, None
    return table.unit, table.scaling_factor


def _describe_source_unit(
    table: ObservationTable, reduced_unit: str | None
) -> str | None:
    """States the source unit of the endpoints of a percentage figure.

    `reduced_unit` is the unit of the figure itself, such as `Percent`.

    Returns:
        The caveat, or None when the table has no unit and no scaling
        factor other than 1.
    """
    details: list[str] = []
    if table.unit is not None:
        details.append(f"in {table.unit}")
    if table.scaling_factor is not None and table.scaling_factor != 1.0:
        details.append(
            f"scaled by {format_scaling_factor(table.scaling_factor)}"
        )
    if not details:
        return None
    return (
        "Each place's from_value and to_value are reported "
        f"{' and '.join(details)}, as the source reports them, while the "
        f"figure itself is in {reduced_unit}."
    )


def _build_window_coverage(
    target_places: Sequence[str],
    rows: Sequence[WindowRow],
    window: tuple[str, str],
) -> CoverageReport:
    """Reports how many target places have a figure over `window`."""
    reduced = {row.place_dcid for row in rows}
    return CoverageReport(
        contributing_places=len(rows),
        requested_places=len(target_places),
        coverage_ratio=len(rows) / len(target_places),
        reference_date=f"{window[0]}{WINDOW_DATE_SEPARATOR}{window[1]}",
        missing_places=tuple(
            place for place in target_places if place not in reduced
        ),
    )


def _describe_insufficient_window_coverage(
    table: ObservationTable,
    metric_label: str,
    coverage: CoverageReport,
    min_coverage: float,
) -> str:
    """Returns the message of an `insufficient_coverage` reduction refusal."""
    label = f"{metric_label} ({table.variable_dcid})"
    if coverage.contributing_places == 0:
        return f"No place has a value for {label} ({coverage.describe()})."
    verb = conjugate_have(coverage.contributing_places)
    return (
        f"Only {coverage.describe()} {verb} a value for {label}, below the "
        f"required {format_percent(min_coverage)} coverage."
    )


def _build_empty_coverage(
    target_places: Sequence[str],
) -> CoverageReport | None:
    """Reports that no target place has a figure, or None without places."""
    if not target_places:
        return None
    return CoverageReport(
        contributing_places=0,
        requested_places=len(target_places),
        coverage_ratio=0.0,
        reference_date=None,
        missing_places=tuple(target_places),
    )


def _refuse_without_observations(
    table: ObservationTable, target_places: Sequence[str], step_id: str
) -> RefusedScriptResult:
    """Refuses a reduction with no observation in the places and window."""
    return build_refusal(
        table,
        script=_REDUCE_SCRIPT_NAME,
        step_id=step_id,
        reason="no_observations",
        coverage=_build_empty_coverage(target_places),
        caveat="No observations match the requested places and date "
        f"window for {table.variable_name}.",
    )


def _build_window_cohort(
    table: ObservationTable,
    metric: SeriesMetric,
    window: tuple[str, str],
    rows: Sequence[WindowRow],
    coverage: CoverageReport,
    caveats: Sequence[str],
    *,
    unit: str | None,
    scaling_factor: float | None,
) -> WindowCohort:
    """Assembles the reduced cohort with its methodology."""
    label = format_series_metric_label(metric, table.variable_name)
    phrase = format_reference_date_phrase(
        f"{window[0]}{WINDOW_DATE_SEPARATOR}{window[1]}"
    )
    return WindowCohort(
        variable_dcid=table.variable_dcid,
        variable_name=table.variable_name,
        metric=metric,
        start_date=window[0],
        end_date=window[1],
        unit=unit,
        scaling_factor=scaling_factor,
        provenance=merge_provenance(
            table.provenance,
            methodology=(
                f"{label[0].upper()}{label[1:]} computed for each place "
                f"{phrase}, using {_REDUCTION_METHODS[metric]}."
            ),
        ),
        rows=tuple(rows),
        place_names=dict(table.place_names),
        coverage=coverage,
        caveats=tuple(caveats),
    )


def reduce_series(
    table: ObservationTable,
    metric: SeriesMetric,
    *,
    places: Sequence[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
    step_id: str = "s1",
) -> WindowCohort | RefusedScriptResult:
    """Reduces each place's series to one figure over a shared date window.

    Every observation is first kept at one date precision for the whole
    cohort (`_keep_dominant_precision`). The window is then selected once
    for every place: for `latest_period_change` and
    `latest_period_percent_change`, the latest pair of consecutive dates
    that `min_coverage` of the target places share, each place counting only
    when the two dates are adjacent in its own series; for the other
    metrics, the latest end date and earliest start date that
    `min_coverage` of the target places share, at least a year apart for
    `cagr`. Each place observed at both ends of the window contributes one
    `WindowRow`: the change, the percentage change, the compound annual
    growth rate, or the exact mean of its observations within the window.
    A place whose figure is undefined (a zero start for a percentage, a
    start or end that is not positive for a growth rate, or a figure too
    large to represent) is left out with a caveat.

    Args:
        table: The table whose series are reduced.
        metric: The figure computed for each place.
        places: The target places. When None or empty, the table's
            requested places, or its places with data when it requests
            none.
        start_date: The inclusive start of the dates considered, compared
            as `is_within_date_range` does.
        end_date: The inclusive end of the dates considered.
        min_coverage: The share of the target places that must have a figure
            over the window, from 0 to 1.
        step_id: Identifier of the analysis step, for a refusal.

    Returns:
        A `WindowCohort` whose rows are sorted by place DCID, in `Percent`
        for the percentage metrics, `Percent per year` for `cagr`, and the
        table's unit and scaling factor otherwise, with a caveat on the
        source unit of the endpoints of a percentage figure. Otherwise a
        refusal with `invalid_parameters` when a parameter is invalid or no
        two `cagr` dates are a year apart, with `no_observations` when no
        row matches the places and dates, and with `insufficient_coverage`
        when no place has two dates or too few places have a figure.
    """
    error = _validate_parameters(
        places, start_date, end_date
    ) or validate_alignment_parameters(min_coverage=min_coverage)
    if error is not None:
        return build_invalid_parameters_refusal(
            table, script=_REDUCE_SCRIPT_NAME, step_id=step_id, caveat=error
        )
    target_places = (
        tuple(dict.fromkeys(places)) if places else resolve_target_places(table)
    )
    grouped = _group_series_by_place(table, target_places, start_date, end_date)
    if not grouped:
        return _refuse_without_observations(table, target_places, step_id)

    series, dropped, precision = _keep_dominant_precision(grouped)
    caveats: list[str] = []
    if dropped:
        caveats.append(
            _describe_dropped_precision(
                table, _order_places(dropped, target_places), precision
            )
        )
    unit, scaling_factor = _resolve_reduced_unit(table, metric)
    window = _select_window(
        table, series, metric, len(target_places), min_coverage
    )
    if isinstance(window, _WindowRefusal):
        return build_refusal(
            table,
            script=_REDUCE_SCRIPT_NAME,
            step_id=step_id,
            reason=window.reason,
            coverage=(
                _build_empty_coverage(target_places)
                if window.reason == "insufficient_coverage"
                else None
            ),
            caveat=window.caveat,
            extra_caveats=caveats,
            unit=unit,
            scaling_factor=scaling_factor,
        )

    rows, issue_caveats = _reduce_places(series, window, metric)
    caveats.extend(issue_caveats)
    coverage = _build_window_coverage(target_places, rows, window)
    label = format_series_metric_label(metric, table.variable_name)
    if not rows or not has_adequate_coverage(
        len(rows), len(target_places), min_coverage
    ):
        return build_refusal(
            table,
            script=_REDUCE_SCRIPT_NAME,
            step_id=step_id,
            reason="insufficient_coverage",
            coverage=coverage,
            caveat=_describe_insufficient_window_coverage(
                table, label, coverage, min_coverage
            ),
            extra_caveats=caveats,
            unit=unit,
            scaling_factor=scaling_factor,
        )
    if coverage.contributing_places < coverage.requested_places:
        verb = conjugate_have(coverage.contributing_places)
        caveats.append(f"{coverage.describe()} {verb} a value for {label}.")
    if metric in _PERCENT_METRICS or metric == "cagr":
        source_unit = _describe_source_unit(table, unit)
        if source_unit is not None:
            caveats.append(source_unit)
    return _build_window_cohort(
        table,
        metric,
        window,
        rows,
        coverage,
        caveats,
        unit=unit,
        scaling_factor=scaling_factor,
    )
