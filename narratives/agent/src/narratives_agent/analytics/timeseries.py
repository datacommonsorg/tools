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

from collections import Counter
from collections.abc import Sequence
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
    RefusalReason,
    RefusedScriptResult,
    ScriptResult,
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
_MONTHS_PER_YEAR = 12.0
_DAYS_PER_YEAR = 365.25
# Places are compared only on a date that at least this many share.
_MIN_PLACES_SHARING_DATE = 2

# Why a change or growth rate is not reported for a place.
type _PlaceIssue = Literal[
    "single_point",
    "zero_start",
    "cagr_start_not_positive",
    "cagr_end_not_positive",
    "cagr_short_span",
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
}


def _compute_fractional_year(date: str) -> float:
    """Converts a `YYYY`, `YYYY-MM`, or `YYYY-MM-DD` date to a decimal year.

    A year counts from its start, a month adds its offset as twelfths of a
    year, and a day adds its offset within the month as a fraction of an
    average year, so annual, monthly, and daily series all yield the elapsed
    years that a growth rate needs.

    Args:
        date: A date that `is_valid_observation_date` accepts.

    Returns:
        The date as a decimal year, for example 2020.5 for `2020-07`.

    Raises:
        ValueError: If a date component is not numeric.
    """
    parts = date.split("-")
    year = float(parts[0])
    if len(parts) > 1:
        year += (float(parts[1]) - 1.0) / _MONTHS_PER_YEAR
    if len(parts) > 2:
        year += (float(parts[2]) - 1.0) / _DAYS_PER_YEAR
    return year


def _compute_percent_change(start: float, end: float) -> float | None:
    """Returns the percentage change from `start` to `end`, or None at zero."""
    if start == 0.0:
        return None
    return (end - start) / abs(start) * PERCENT_SCALE


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
    estimated. Over at least a year the annualized ratio lies between 1 and
    the ratio itself, so the result is finite whenever the ratio is.
    """
    if start.value <= 0.0:
        return None, "cagr_start_not_positive"
    if end.value <= 0.0:
        return None, "cagr_end_not_positive"
    start_year = _compute_fractional_year(start.date)
    years = _compute_fractional_year(end.date) - start_year
    if years < _MIN_GROWTH_SPAN_YEARS:
        return None, "cagr_short_span"
    growth = (end.value / start.value) ** (1.0 / years) - 1.0
    return growth * PERCENT_SCALE, None


def _summarize_place(
    points: list[ObservationRow],
) -> tuple[PlaceSeriesSummary, list[_PlaceIssue]]:
    """Summarizes one place's series, sorted by date, with its issues."""
    start, end = points[0], points[-1]
    place_name = start.place_name
    issues: list[_PlaceIssue] = []
    lowest = min(points, key=lambda row: (row.value, row.date))
    highest = min(points, key=lambda row: (-row.value, row.date))

    absolute_change: float | None
    percent_change: float | None
    cagr: float | None
    if len(points) == 1:
        issues.append("single_point")
        absolute_change = None
        percent_change = None
        cagr = None
    else:
        absolute_change = end.value - start.value
        percent_change = _compute_percent_change(start.value, end.value)
        if percent_change is None:
            issues.append("zero_start")
        cagr, cagr_issue = _compute_compound_annual_growth_rate(start, end)
        if cagr_issue is not None:
            issues.append(cagr_issue)

    changes = _compute_period_changes(points)
    increases = [change for change in changes if change.absolute_change > 0.0]
    decreases = [change for change in changes if change.absolute_change < 0.0]
    summary = PlaceSeriesSummary(
        place_dcid=start.place_dcid,
        place_name=place_name,
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
        absolute_change=absolute_change,
        percent_change=percent_change,
        cagr=cagr,
        # On a tie in size, the earliest step is reported for both the
        # largest increase and the largest decrease.
        max_period_increase=(
            min(
                increases,
                key=lambda change: (-change.absolute_change, change.to_date),
            )
            if increases
            else None
        ),
        max_period_decrease=(
            min(
                decreases,
                key=lambda change: (change.absolute_change, change.to_date),
            )
            if decreases
            else None
        ),
    )
    return summary, issues


def _compare_places(
    series: dict[str, dict[str, ObservationRow]],
    ordered_places: list[str],
    place_names: dict[str, str],
) -> tuple[CrossPlaceComparison | None, list[str]]:
    """Compares the places on one date most of them share.

    Among the dates at least two places share, `select_reference_date`
    (the rule `align_cohort` uses) picks the latest date that
    `DEFAULT_MIN_COVERAGE` of the places share, or else the date most places
    share, the latest on a tie. The places counted are those with
    observations in the window, whereas `align_cohort` counts the requested
    places. A caveat names the places left out. When no two places share a
    date, there is no comparison.
    """
    dates = {place: set(series[place]) for place in ordered_places}
    counts = Counter(
        date for place_dates in dates.values() for date in place_dates
    )
    shared = {
        date: count
        for date, count in counts.items()
        if count >= _MIN_PLACES_SHARING_DATE
    }
    if not shared:
        return None, [
            "The places share no observation date, so they are not "
            "compared against each other."
        ]
    reference_date = select_reference_date(shared, len(ordered_places))
    covered = has_adequate_coverage(shared[reference_date], len(ordered_places))
    participants = [
        place for place in ordered_places if reference_date in dates[place]
    ]
    left_out = [
        place_names.get(place, place)
        for place in ordered_places
        if reference_date not in dates[place]
    ]
    caveats: list[str] = []
    if left_out:
        share = format_percent(DEFAULT_MIN_COVERAGE)
        names = format_place_names(left_out)
        caveats.append(
            f"The comparison uses {reference_date}, the latest date at least "
            f"{share} of the places share, which leaves out {names}."
            if covered
            else f"No date is shared by at least {share} of the places; the "
            f"comparison uses {reference_date}, the date the most places "
            f"share, which leaves out {names}."
        )

    entries = sorted(
        (series[place][reference_date] for place in participants),
        key=lambda row: (-row.value, row.place_dcid),
    )
    leader = entries[0]
    comparison = CrossPlaceComparison(
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
    return comparison, caveats


def _build_refusal(
    table: ObservationTable,
    step_id: str,
    reason: RefusalReason,
    caveat: str,
) -> ScriptResult:
    """Builds a refused result for `table` with one caveat."""
    return RefusedScriptResult(
        step_id=step_id,
        script=_SCRIPT_NAME,
        refusal_reason=reason,
        variables=(table.variable_dcid,),
        variable_names={table.variable_dcid: table.variable_name},
        unit=table.unit,
        scaling_factor=table.scaling_factor,
        provenance=table.provenance,
        caveats=(caveat,),
    )


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
    is used.

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
        falls after the end, or `places` is a string, and with
        `no_observations` when no row matches the places and the window.
    """
    # A `str` is a `Sequence[str]`, so the type does not exclude it.
    if isinstance(places, str):
        return _build_refusal(
            table,
            step_id,
            "invalid_parameters",
            f"places must be a sequence of DCIDs, not the string {places!r}.",
        )
    for bound in (start_date, end_date):
        if bound is not None and not is_valid_observation_date(bound):
            return _build_refusal(
                table,
                step_id,
                "invalid_parameters",
                f"The date bound {bound!r} is not a year, a year and month, "
                "or a full date.",
            )
    if (
        start_date is not None
        and end_date is not None
        and is_inverted_date_range(start_date, end_date)
    ):
        return _build_refusal(
            table,
            step_id,
            "invalid_parameters",
            f"The date window starts at {start_date} and ends at "
            f"{end_date}, which is before it starts.",
        )
    requested = tuple(dict.fromkeys(places)) if places else ()
    place_filter = set(requested) if requested else None
    series: dict[str, dict[str, ObservationRow]] = {}
    for row in table.rows:
        if place_filter is not None and row.place_dcid not in place_filter:
            continue
        if not is_within_date_range(row.date, start_date, end_date):
            continue
        series.setdefault(row.place_dcid, {})[row.date] = row
    if not series:
        return _build_refusal(
            table,
            step_id,
            "no_observations",
            "No observations match the requested places and date window "
            f"for {table.variable_name}.",
        )

    preferred = tuple(dict.fromkeys(requested or table.requested_places))
    ordered_places = [place for place in preferred if place in series]
    seen = set(ordered_places)
    ordered_places.extend(
        place for place in sorted(series) if place not in seen
    )

    summaries: list[PlaceSeriesSummary] = []
    caveats: list[str] = []
    missing_places = tuple(place for place in preferred if place not in series)
    if missing_places:
        caveats.append(
            _describe_missing_places(
                table,
                missing_places,
                windowed=start_date is not None or end_date is not None,
            )
        )
    places_by_issue: dict[_PlaceIssue, list[str]] = {}
    for place in ordered_places:
        points = sorted(series[place].values(), key=lambda row: row.date)
        summary, issues = _summarize_place(points)
        summaries.append(summary)
        for issue in issues:
            places_by_issue.setdefault(issue, []).append(summary.place_name)
    caveats.extend(
        _PLACE_ISSUE_CAVEATS[issue].format(places=format_place_names(names))
        for issue, names in places_by_issue.items()
    )

    comparison: CrossPlaceComparison | None = None
    if len(ordered_places) > 1:
        comparison, comparison_caveats = _compare_places(
            series, ordered_places, table.place_names
        )
        caveats.extend(comparison_caveats)

    window = ""
    if start_date is not None or end_date is not None:
        window = (
            f" from {start_date or 'the earliest date'} to "
            f"{end_date or 'the latest date'}"
        )
    provenance = merge_provenance(
        table.provenance,
        methodology=(
            "Start-to-end change, extrema, largest period-over-period "
            "changes, and compound annual growth rate computed per place "
            f"over the observed series{window}."
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
