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
"""

import calendar
import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Literal

from narratives_agent.analytics.alignment import (
    DEFAULT_MIN_COVERAGE,
    has_adequate_coverage,
    select_reference_date,
)
from narratives_agent.analytics.digest import (
    PERCENT_SCALE,
    OkScriptResult,
    ScriptResult,
    conjugate_have,
    format_percent,
    format_place_names,
)
from narratives_agent.analytics.metrics import (
    CrossPlaceComparison,
    ExtremumKind,
    LeaderDelta,
    LocalExtremum,
    PeriodChange,
    PlaceSeriesSummary,
    PlaceValue,
    TimeseriesMetrics,
)
from narratives_agent.analytics.provenance import merge_provenance
from narratives_agent.analytics.script_inputs import (
    build_invalid_parameters_refusal,
    build_refusal,
    validate_place_dcids,
)
from narratives_agent.analytics.tables import (
    ObservationRow,
    ObservationTable,
    is_inverted_date_range,
    is_valid_observation_date,
    is_within_date_range,
)

__all__ = [
    "LOCAL_EXTREMA_CAP",
    "analyze_timeseries",
]

_SCRIPT_NAME: Literal["analyze_timeseries"] = "analyze_timeseries"
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
        metrics=TimeseriesMetrics(
            place_count=len(summaries),
            series=tuple(summaries),
            missing_places=missing_places,
            cross_place_comparison=comparison,
        ),
        caveats=tuple(caveats),
    )
