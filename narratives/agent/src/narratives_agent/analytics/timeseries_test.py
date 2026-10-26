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
"""Tests for `analyze_timeseries` in `analytics.timeseries`.

Covers single-point and multi-point series statistics, undefined growth-rate
caveats, fractional-year arithmetic across date granularities, local extrema
caps, window and place filtering, and multi-place comparisons.
"""

import datetime
import random
from collections import Counter
from collections.abc import Sequence
from itertools import pairwise

import pytest

from narratives_agent.analytics.digest import PLACE_NAME_CAP
from narratives_agent.analytics.metrics import (
    CrossPlaceComparison,
    LeaderDelta,
    LocalExtremum,
    PeriodChange,
    PlaceValue,
    TimeseriesMetrics,
)
from narratives_agent.analytics.provenance import Provenance, Source
from narratives_agent.analytics.tables import ObservationRow, ObservationTable
from narratives_agent.analytics.timeseries import (
    LOCAL_EXTREMA_CAP,
    analyze_timeseries,
)

_SOURCE = Source(name="World Development Indicators", url="https://wdi")


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


def _series(
    place: str, values: Sequence[tuple[str, float]]
) -> list[tuple[str, str, float]]:
    """Expands `(date, value)` pairs for one place into table triples."""
    return [(place, date, value) for date, value in values]


def _metrics(table: ObservationTable) -> TimeseriesMetrics:
    """Runs `analyze_timeseries` and narrows its metrics."""
    result = analyze_timeseries(table)
    assert isinstance(result.metrics, TimeseriesMetrics)
    return result.metrics


def test_single_point_series_reports_the_value_and_no_change() -> None:
    # Test: A series of one observation.
    # Situation: One place with a single row.
    # Expectation: The summary carries the point as start, end, min, and
    #   max with no absolute or percentage change, no growth rate, no
    #   extrema, no period changes, no comparison, and a caveat
    #   saying no change is computed.
    result = analyze_timeseries(_table([("a", "2023", 5.0)]))
    assert result.status == "ok"
    assert isinstance(result.metrics, TimeseriesMetrics)
    assert result.metrics.place_count == 1
    assert result.metrics.cross_place_comparison is None
    series = result.metrics.series[0]
    assert series.point_count == 1
    assert (series.start_date, series.start_value) == ("2023", 5.0)
    assert (series.end_date, series.end_value) == ("2023", 5.0)
    assert (series.min_date, series.max_date) == ("2023", "2023")
    assert series.absolute_change is None
    assert series.percent_change is None
    assert series.cagr is None
    assert series.local_extrema == ()
    assert series.max_period_increase is None
    assert series.max_period_decrease is None
    assert result.caveats == (
        "Only one observation is available for A, so no change over time is "
        "computed.",
    )


def test_multi_decade_series_reports_extrema_shocks_and_exact_growth() -> None:
    # Test: The full statistics of a positive series.
    # Situation: One place observed annually from 2000 to 2020 with a rise
    #   to a peak in 2005, a fall to a trough in 2010, and a rise to the
    #   end, where the value doubles from start to end. The largest
    #   single-year increase is 2004 to 2005 and the largest decrease is
    #   2005 to 2006.
    # Expectation: Start, end, global minimum (the start, earliest on
    #   ties) and maximum are reported; the peak and trough are the local
    #   extrema; the largest period changes are identified with their
    #   percentage; the net change is 100 and 100%; and the growth rate is
    #   exactly `(2 ** (1 / 20) - 1) * 100`.
    values = [
        ("2000", 100.0),
        ("2001", 110.0),
        ("2002", 120.0),
        ("2003", 130.0),
        ("2004", 140.0),
        ("2005", 180.0),
        ("2006", 150.0),
        ("2007", 140.0),
        ("2008", 130.0),
        ("2009", 120.0),
        ("2010", 100.0),
        ("2011", 110.0),
        ("2012", 120.0),
        ("2013", 130.0),
        ("2014", 140.0),
        ("2015", 150.0),
        ("2016", 160.0),
        ("2017", 170.0),
        ("2018", 180.0),
        ("2019", 190.0),
        ("2020", 200.0),
    ]
    result = analyze_timeseries(_table(_series("a", values)))
    assert isinstance(result.metrics, TimeseriesMetrics)
    series = result.metrics.series[0]
    assert series.point_count == 21
    assert (series.start_date, series.start_value) == ("2000", 100.0)
    assert (series.end_date, series.end_value) == ("2020", 200.0)
    assert (series.min_date, series.min_value) == ("2000", 100.0)
    assert (series.max_date, series.max_value) == ("2020", 200.0)
    assert series.local_extrema == (
        LocalExtremum(date="2005", value=180.0, kind="peak"),
        LocalExtremum(date="2010", value=100.0, kind="trough"),
    )
    assert series.max_period_increase == PeriodChange(
        from_date="2004",
        to_date="2005",
        from_value=140.0,
        to_value=180.0,
        absolute_change=40.0,
        percent_change=40.0 / 140.0 * 100.0,
    )
    assert series.max_period_decrease == PeriodChange(
        from_date="2005",
        to_date="2006",
        from_value=180.0,
        to_value=150.0,
        absolute_change=-30.0,
        percent_change=-30.0 / 180.0 * 100.0,
    )
    assert series.absolute_change == 100.0
    assert series.percent_change == 100.0
    assert series.cagr == (2.0 ** (1.0 / 20.0) - 1.0) * 100.0
    assert result.caveats == ()
    assert result.provenance.sources == (_SOURCE,)
    assert result.provenance.methodology is not None


@pytest.mark.parametrize(
    ("values", "expected_caveats"),
    [
        (
            [("2010", 0.0), ("2020", 50.0)],
            (
                "The percentage change is undefined for A because the "
                "starting value is zero.",
                "The compound annual growth rate is undefined for A because "
                "the starting value is not positive.",
            ),
        ),
        (
            [("2010", 50.0), ("2020", -5.0)],
            (
                "The compound annual growth rate is undefined for A because "
                "the ending value is not positive.",
            ),
        ),
        (
            [("2010", -5.0), ("2020", 50.0)],
            (
                "The compound annual growth rate is undefined for A because "
                "the starting value is not positive.",
            ),
        ),
    ],
    ids=["zero start", "negative end", "negative start"],
)
def test_growth_rate_is_undefined_for_non_positive_endpoints(
    values: list[tuple[str, float]], expected_caveats: tuple[str, ...]
) -> None:
    # Test: The undefined growth-rate cases.
    # Situation: Two-point series whose start is zero, whose end is
    #   negative, and whose start is negative.
    # Expectation: `cagr` is None and a caveat names the place and the
    #   reason; a zero start also leaves `percent_change` undefined, with its
    #   own caveat first.
    result = analyze_timeseries(_table(_series("a", values)))
    assert isinstance(result.metrics, TimeseriesMetrics)
    assert result.metrics.series[0].cagr is None
    assert result.caveats == expected_caveats


def test_place_caveats_name_a_few_places_per_reason() -> None:
    # Test: One caveat per reason across many places.
    # Situation: `PLACE_NAME_CAP + 2` places each have one observation, and
    #   two more places start at zero.
    # Expectation: One single-point caveat names the first `PLACE_NAME_CAP`
    #   places and counts the other two, and one zero-start caveat and one
    #   growth-rate caveat name both zero-start places.
    single = [(f"p{index}", "2020", 1.0) for index in range(PLACE_NAME_CAP + 2)]
    zero = [
        *_series("y", [("2010", 0.0), ("2020", 5.0)]),
        *_series("z", [("2010", 0.0), ("2020", 6.0)]),
    ]
    result = analyze_timeseries(_table([*single, *zero]))
    assert result.caveats == (
        "Only one observation is available for P0, P1, P2, P3, P4, and 2 "
        "other places, so no change over time is computed.",
        "The percentage change is undefined for Y and Z because the starting "
        "value is zero.",
        "The compound annual growth rate is undefined for Y and Z because the "
        "starting value is not positive.",
    )


def test_duplicate_dates_collapse_to_the_last_row() -> None:
    # Test: A series whose two observations share a date.
    # Situation: Two rows for one place on the same date, which the script
    #   reduces to the last one, leaving a single point.
    # Expectation: The duplicate is dropped, so the single-point caveat
    #   applies and no growth rate is reported.
    metrics = _metrics(_table([("a", "2020", 1.0), ("a", "2020", 2.0)]))
    series = metrics.series[0]
    assert series.point_count == 1
    assert series.end_value == 2.0
    assert series.cagr is None


@pytest.mark.parametrize(
    ("start_date", "end_date"),
    [
        ("2020", "2020-01"),
        ("2020-03-01", "2020-03-03"),
        ("2026-06", "2026-07"),
        ("2020-01", "2020-07"),
    ],
    ids=["no time", "two days", "one month", "six months"],
)
def test_growth_rate_is_undefined_over_less_than_a_year(
    start_date: str, end_date: str
) -> None:
    # Test: The minimum span of the growth rate.
    # Situation: Two-point series spanning no time (`2020` and `2020-01`
    #   both resolve to the start of 2020), two days, one month, and six
    #   months, each with positive endpoints and a rise.
    # Expectation: Both points are kept and the percentage change is
    #   reported, but `cagr` is None and the caveat says the series spans
    #   less than a year, because annualizing a shorter change extrapolates
    #   it.
    result = analyze_timeseries(
        _table([("a", start_date, 3.5), ("a", end_date, 4.0)])
    )
    assert isinstance(result.metrics, TimeseriesMetrics)
    series = result.metrics.series[0]
    assert series.point_count == 2
    assert series.percent_change is not None
    assert series.cagr is None
    assert result.caveats == (
        "The compound annual growth rate is undefined for A because the "
        "series spans less than a year.",
    )


def test_tied_period_changes_report_the_earliest_step() -> None:
    # Test: Tie-breaking for the largest period changes.
    # Situation: A series that alternates 10, 20, 10, 20, 10, so every rise
    #   and every fall has the same size.
    # Expectation: Both the largest increase and the largest decrease report
    #   the earliest step of their kind.
    values = [
        ("2000", 10.0),
        ("2001", 20.0),
        ("2002", 10.0),
        ("2003", 20.0),
        ("2004", 10.0),
    ]
    series = _metrics(_table(_series("a", values))).series[0]
    assert series.max_period_increase is not None
    assert series.max_period_decrease is not None
    assert series.max_period_increase.to_date == "2001"
    assert series.max_period_decrease.to_date == "2002"


@pytest.mark.parametrize(
    ("start", "end", "expected_cagr"),
    [
        ("2010", "2012", 100.0),
        ("2020-01", "2022-01", 100.0),
        ("2020-01-01", "2022-01-01", 100.0),
        ("2020-03-01", "2021-03-01", 300.0),
    ],
    ids=["annual", "monthly", "daily two years", "daily one year"],
)
def test_growth_rate_measures_elapsed_years_at_every_granularity(
    start: str, end: str, expected_cagr: float
) -> None:
    # Test: Elapsed years behind the growth rate for each date granularity.
    # Situation: A value that quadruples between two annual, two monthly,
    #   or two daily dates that are two years apart, and between two daily
    #   dates exactly one year apart.
    # Expectation: The growth rate is 100% per year over two years and 300%
    #   over one year, whatever the granularity.
    metrics = _metrics(_table([("a", start, 1.0), ("a", end, 4.0)]))
    assert metrics.series[0].cagr == pytest.approx(expected_cagr)


@pytest.mark.parametrize(
    ("start", "end", "start_month_days"),
    [
        ("2020-01-31", "2021-02-01", 31),
        ("2021-02-28", "2022-03-01", 28),
        ("2020-02-29", "2021-03-01", 29),
        ("2020-06-15", "2021-06-16", 30),
    ],
    ids=["month end", "february", "leap day", "mid month"],
)
def test_daily_growth_span_adds_one_day_across_month_boundaries(
    start: str, end: str, start_month_days: int
) -> None:
    # Test: Elapsed years between daily dates one day past an anniversary.
    # Situation: A value that quadruples between a daily date and the next
    #   day a year later, where that day crosses a month boundary, follows
    #   February 29, or stays within a month.
    # Expectation: The span is one year plus one day, measured as one
    #   twelfth of a year divided by the starting month's length, so a day
    #   step across a month boundary is the same size as one within it.
    metrics = _metrics(_table([("a", start, 1.0), ("a", end, 4.0)]))
    years = 1.0 + 1.0 / (12.0 * start_month_days)
    assert metrics.series[0].cagr == pytest.approx(
        (4.0 ** (1.0 / years) - 1.0) * 100.0
    )


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2021-04-31", "2022-04-31"),
        ("2020-00-15", "2021-00-15"),
        ("2020-13-01", "2021-13-01"),
    ],
    ids=["day past month end", "month zero", "month thirteen"],
)
def test_impossible_daily_dates_do_not_raise(start: str, end: str) -> None:
    # Test: Daily dates that match the date pattern but not the calendar.
    # Situation: The same impossible month and day in two consecutive
    #   years; `is_valid_observation_date` checks only the digit pattern.
    # Expectation: The analysis completes and measures the span as one
    #   year, so the growth rate is 300% for a value that quadruples.
    metrics = _metrics(_table([("a", start, 1.0), ("a", end, 4.0)]))
    assert metrics.series[0].cagr == pytest.approx(300.0)


def test_monthly_series_uses_elapsed_years_for_growth() -> None:
    # Test: Growth over a monthly series.
    # Situation: A value that doubles between 2020-01 and 2021-01.
    # Expectation: The growth rate is 100% per year, not 100% over twelve
    #   periods.
    metrics = _metrics(
        _table(
            _series("a", [("2020-01", 1.0), ("2020-07", 1.5), ("2021-01", 2.0)])
        )
    )
    assert metrics.series[0].cagr == pytest.approx(100.0)


def test_local_extrema_are_capped_to_the_most_prominent() -> None:
    # Test: The extrema cap on a zigzag series.
    # Situation: Thirty alternating observations whose swings grow over
    #   time, giving 28 interior turning points.
    # Expectation: `LOCAL_EXTREMA_CAP` extrema are kept, they are the
    #   latest (most prominent) ones, and they are in date order.
    values = [
        (str(1990 + index), float(index) * (1.0 if index % 2 == 0 else -1.0))
        for index in range(30)
    ]
    extrema = _metrics(_table(_series("a", values))).series[0].local_extrema
    assert len(extrema) == LOCAL_EXTREMA_CAP
    dates = [item.date for item in extrema]
    assert dates == sorted(dates)
    assert dates[-1] == "2018"
    assert {item.kind for item in extrema} == {"peak", "trough"}


def test_a_flat_topped_peak_is_not_a_local_extremum() -> None:
    # Test: A reversal across a plateau.
    # Situation: The series 1, 3, 3, 1 rises, holds for one step, and falls.
    # Expectation: No local extremum is reported, because each interior
    #   point has a flat step on one side, as `LocalExtremum` documents.
    series = _series(
        "a", [("2020", 1.0), ("2021", 3.0), ("2022", 3.0), ("2023", 1.0)]
    )
    assert _metrics(_table(series)).series[0].local_extrema == ()


def test_places_and_window_filters_apply_and_order_is_preserved() -> None:
    # Test: The `places`, `start_date`, and `end_date` arguments.
    # Situation: Three places with rows from 2018 to 2022; the call asks
    #   for places `c` then `a` from 2019 to 2021.
    # Expectation: Only `c` and `a` are summarized, in that order, over the
    #   three years inside the window, and the methodology names the
    #   window.
    rows: list[tuple[str, str, float]] = []
    for place in ("a", "b", "c"):
        rows.extend(
            (place, str(year), float(year)) for year in range(2018, 2023)
        )
    result = analyze_timeseries(
        _table(rows), places=["c", "a"], start_date="2019", end_date="2021"
    )
    assert isinstance(result.metrics, TimeseriesMetrics)
    series = result.metrics.series
    assert [item.place_dcid for item in series] == ["c", "a"]
    assert all(item.point_count == 3 for item in series)
    assert series[0].start_date == "2019"
    assert series[0].end_date == "2021"
    assert result.provenance.methodology is not None
    assert "from 2019 to 2021" in result.provenance.methodology


def test_requested_place_order_is_used_when_no_places_are_given() -> None:
    # Test: Place ordering without a `places` argument.
    # Situation: The table requested `b` then `a`, and a third place `c`
    #   has rows without being requested.
    # Expectation: The series follow request order, then the extra place.
    metrics = _metrics(
        _table(
            [("a", "2020", 1.0), ("b", "2020", 2.0), ("c", "2020", 3.0)],
            requested_places=["b", "a"],
        )
    )
    assert [item.place_dcid for item in metrics.series] == [
        "b",
        "a",
        "c",
    ]


def test_empty_window_is_refused() -> None:
    # Test: A window that matches no rows.
    # Situation: The table has rows for 2020 and the call asks for 2021
    #   onward.
    # Expectation: A `no_observations` refusal with `metrics=None` and a
    #   caveat naming the variable.
    result = analyze_timeseries(_table([("a", "2020", 1.0)]), start_date="2021")
    assert result.status == "refused"
    assert result.refusal_reason == "no_observations"
    assert result.metrics is None
    assert result.caveats == (
        "No observations match the requested places and date window for "
        "Total population.",
    )


def test_an_empty_places_sequence_means_every_place() -> None:
    # Test: The `places` contract for an empty sequence.
    # Situation: Two places have rows and the call passes `places=[]`.
    # Expectation: Both places are analyzed, as with `places=None`, and no
    #   place is reported missing.
    table = _table([("a", "2020", 1.0), ("b", "2020", 2.0)])
    result = analyze_timeseries(table, places=[])
    assert result.status == "ok"
    assert isinstance(result.metrics, TimeseriesMetrics)
    assert result.metrics.place_count == 2
    assert result.metrics.missing_places == ()
    assert result.metrics == analyze_timeseries(table, places=None).metrics


def test_requested_places_without_rows_are_reported_as_missing() -> None:
    # Test: A requested place that has no row in the window.
    # Situation: The call asks for places `a` and `z`; only `a` has rows.
    #   A second call also sets a start date.
    # Expectation: `a` is analyzed, `z` is listed in `missing_places`, and a
    #   caveat names it by its display name, mentioning the window only
    #   when the call sets one.
    table = _table(
        [("a", "2020", 1.0), ("a", "2021", 2.0)], requested_places=["a", "z"]
    )
    result = analyze_timeseries(table, places=["a", "z"])
    assert result.status == "ok"
    assert isinstance(result.metrics, TimeseriesMetrics)
    assert [item.place_dcid for item in result.metrics.series] == ["a"]
    assert result.metrics.missing_places == ("z",)
    assert result.caveats == (
        "No observations are available for Z, so it is left out of the "
        "analysis.",
    )
    windowed = analyze_timeseries(table, places=["a", "z"], start_date="2020")
    assert windowed.caveats == (
        "No observations are available for Z within the requested window, "
        "so it is left out of the analysis.",
    )


def test_table_places_without_rows_are_missing_when_places_is_omitted() -> None:
    # Test: `missing_places` without a `places` argument.
    # Situation: The table requested `a` and `z`, `z` has no rows at
    #   all, and the call passes no `places` (and then an empty list).
    # Expectation: `z` is reported in `missing_places` with the caveat in
    #   both calls, because the table's requested places are the places the
    #   analysis was asked for.
    table = _table(
        [("a", "2020", 1.0), ("a", "2021", 2.0)], requested_places=["a", "z"]
    )
    options: tuple[Sequence[str] | None, ...] = (None, [])
    for places in options:
        result = analyze_timeseries(table, places=places)
        assert result.status == "ok"
        assert isinstance(result.metrics, TimeseriesMetrics)
        assert result.metrics.missing_places == ("z",)
        assert result.caveats == (
            "No observations are available for Z, so it is left out of the "
            "analysis.",
        )


def test_missing_place_caveat_names_a_few_places_and_counts_the_rest() -> None:
    # Test: The cap on names in the missing-places caveat.
    # Situation: The table requested eight places and only one has
    #   rows in the window.
    # Expectation: `missing_places` lists all seven absent places, while the
    #   caveat names the first `PLACE_NAME_CAP` of them and counts
    #   the other two.
    missing = ("p1", "p2", "p3", "p4", "p5", "p6", "p7")
    table = _table(
        [("a", "2020", 1.0), ("a", "2021", 2.0)],
        requested_places=["a", *missing],
    )
    result = analyze_timeseries(table)
    assert isinstance(result.metrics, TimeseriesMetrics)
    assert result.metrics.missing_places == missing
    assert len(missing) - PLACE_NAME_CAP == 2
    assert result.caveats == (
        "No observations are available for P1, P2, P3, P4, P5, and 2 other "
        "places, so they are left out of the analysis.",
    )


def test_a_bare_string_of_places_is_refused() -> None:
    # Test: The `places` argument given as one string.
    # Situation: `places="a"`, which the `Sequence[str]` type admits.
    # Expectation: The result is refused with `invalid_parameters` rather
    #   than treating each character as a place.
    result = analyze_timeseries(_table([("a", "2020", 1.0)]), places="a")
    assert result.refusal_reason == "invalid_parameters"
    assert result.caveats == (
        "places must be a sequence of DCIDs, not the string 'a'.",
    )


def test_a_malformed_date_bound_is_refused_as_invalid_parameters() -> None:
    # Test: Validation of the window bounds.
    # Situation: `end_date` is `2020-1`, which is not a year, a year and
    #   month, or a full date.
    # Expectation: An `invalid_parameters` refusal naming the bound, with no
    #   metrics.
    result = analyze_timeseries(_table([("a", "2020", 1.0)]), end_date="2020-1")
    assert result.status == "refused"
    assert result.refusal_reason == "invalid_parameters"
    assert result.metrics is None
    assert result.caveats == (
        "The date bound '2020-1' is not a year, a year and month, or a full "
        "date.",
    )


def test_an_inverted_window_is_refused_as_invalid_parameters() -> None:
    # Test: A window whose start falls after its end.
    # Situation: The table has rows for 2015 through 2023 and the call asks
    #   for 2023 to 2015; a second call asks for July 2020 to the year
    #   2020, which does not conflict at the year's granularity.
    # Expectation: The first is an `invalid_parameters` refusal naming the
    #   window rather than a `no_observations` refusal; the second succeeds.
    table = _table(
        _series("a", [(str(year), float(year)) for year in range(2015, 2024)])
    )
    inverted = analyze_timeseries(table, start_date="2023", end_date="2015")
    assert inverted.status == "refused"
    assert inverted.refusal_reason == "invalid_parameters"
    assert inverted.caveats == (
        "The date window starts at 2023 and ends at 2015, which is before "
        "it starts.",
    )
    nested = analyze_timeseries(table, start_date="2020-07", end_date="2020")
    assert nested.status == "ok"
    assert isinstance(nested.metrics, TimeseriesMetrics)
    assert nested.metrics.series[0].point_count == 1


def test_places_sharing_a_latest_date_are_compared_on_it() -> None:
    # Test: The cross-place comparison on a shared date.
    # Situation: Two places both observed in 2020 and 2021, the second
    #   larger.
    # Expectation: The comparison uses 2021, orders the places by value,
    #   names the leader, reports the spread, and gives the other place's
    #   absolute and percentage delta from the leader.
    result = analyze_timeseries(
        _table(
            [
                ("a", "2020", 10.0),
                ("a", "2021", 20.0),
                ("b", "2020", 30.0),
                ("b", "2021", 25.0),
            ]
        )
    )
    assert isinstance(result.metrics, TimeseriesMetrics)
    comparison = result.metrics.cross_place_comparison
    assert comparison == CrossPlaceComparison(
        reference_date="2021",
        entries=(
            PlaceValue(place_dcid="b", place_name="B", value=25.0),
            PlaceValue(place_dcid="a", place_name="A", value=20.0),
        ),
        spread=5.0,
        leader=PlaceValue(place_dcid="b", place_name="B", value=25.0),
        deltas_from_leader=(
            LeaderDelta(
                place_dcid="a",
                place_name="A",
                absolute_delta=-5.0,
                percent_delta=-20.0,
            ),
        ),
    )
    assert result.caveats == ()


def test_partial_overlap_compares_the_places_that_share_a_date() -> None:
    # Test: The comparison when no date is shared by every place.
    # Situation: Places `a` and `b` share 2020, and place `c` is observed
    #   only in 2019.
    # Expectation: The comparison uses 2020 for `a` and `b`, and a caveat
    #   says the comparison leaves out `C`.
    result = analyze_timeseries(
        _table([("a", "2020", 1.0), ("b", "2020", 2.0), ("c", "2019", 3.0)])
    )
    assert isinstance(result.metrics, TimeseriesMetrics)
    comparison = result.metrics.cross_place_comparison
    assert comparison is not None
    assert comparison.reference_date == "2020"
    assert [entry.place_dcid for entry in comparison.entries] == [
        "b",
        "a",
    ]
    assert (
        "The comparison uses 2020, the latest date at least 50% of the places "
        "share, which leaves out C."
    ) in result.caveats


def test_partial_overlap_prefers_the_date_most_of_the_cohort_shares() -> None:
    # Test: The comparison date under a staggered release.
    # Situation: Of twelve places, eleven share 2024, `p11` is observed only
    #   in 2023, and two places also report 2025.
    # Expectation: The comparison uses 2024 for the eleven places, as
    #   `align_cohort` would, rather than 2025 for two places, and the caveat
    #   leaves out only `P11`.
    places = [f"p{index:02d}" for index in range(12)]
    observations = [
        (place, "2024", float(index)) for index, place in enumerate(places[:11])
    ]
    observations += [("p00", "2025", 1.0), ("p01", "2025", 2.0)]
    observations.append(("p11", "2023", 3.0))
    result = analyze_timeseries(_table(observations))
    assert isinstance(result.metrics, TimeseriesMetrics)
    comparison = result.metrics.cross_place_comparison
    assert comparison is not None
    assert comparison.reference_date == "2024"
    assert len(comparison.entries) == 11
    assert (
        "The comparison uses 2024, the latest date at least 50% of the places "
        "share, which leaves out P11."
    ) in result.caveats


def test_sparse_overlap_uses_the_most_shared_date_and_caps_names() -> None:
    # Test: The comparison date when no date reaches the coverage threshold.
    # Situation: Of eleven places, `a`, `b`, and `c` share 2019, `d` and `e`
    #   share 2021, and six other places each have one distinct year.
    # Expectation: The comparison uses 2019, which most places share, over
    #   the later 2021, and the caveat names the first
    #   `PLACE_NAME_CAP` places it leaves out and counts the rest.
    observations = [
        ("a", "2019", 1.0),
        ("b", "2019", 2.0),
        ("c", "2019", 3.0),
        ("d", "2021", 4.0),
        ("e", "2021", 5.0),
    ]
    observations += [
        (place, str(2010 + index), 6.0)
        for index, place in enumerate(["f", "g", "h", "i", "j", "k"])
    ]
    result = analyze_timeseries(_table(observations))
    assert isinstance(result.metrics, TimeseriesMetrics)
    comparison = result.metrics.cross_place_comparison
    assert comparison is not None
    assert comparison.reference_date == "2019"
    assert [entry.place_dcid for entry in comparison.entries] == [
        "c",
        "b",
        "a",
    ]
    assert (
        "No date is shared by at least 50% of the places; the comparison uses "
        "2019, the date the most places share, which leaves out D, E, F, G, "
        "H, and 3 other places."
    ) in result.caveats


def test_a_stale_place_does_not_pull_the_comparison_back() -> None:
    # Test: The comparison date when the only date every place shares is old.
    # Situation: Ten places all report 2000, and nine of them also report
    #   2024; `p9` stopped reporting after 2000.
    # Expectation: The comparison uses 2024 for the nine places, as
    #   `align_cohort` would, rather than 2000 for all ten, and a caveat
    #   names the date rule and leaves out `P9`.
    places = [f"p{index}" for index in range(10)]
    observations = [(place, "2000", 1.0) for place in places]
    observations += [
        (place, "2024", float(index)) for index, place in enumerate(places[:9])
    ]
    result = analyze_timeseries(_table(observations))
    assert isinstance(result.metrics, TimeseriesMetrics)
    comparison = result.metrics.cross_place_comparison
    assert comparison is not None
    assert comparison.reference_date == "2024"
    assert len(comparison.entries) == 9
    assert comparison.leader.place_dcid == "p8"
    assert (
        "The comparison uses 2024, the latest date at least 50% of the "
        "places share, which leaves out P9."
    ) in result.caveats


def test_zero_and_negative_bases_follow_the_percentage_convention() -> None:
    # Test: Percentages measured from a zero or negative base.
    # Situation: Place `a` rises from -10 to 0 to 5 and is compared with
    #   place `b`; a second table compares a leader valued 0 with a place
    #   valued -4.
    # Expectation: Percentages divide by the absolute base, so the series
    #   change is +150% and the step from -10 to 0 is +100%, and a delta
    #   from a zero-valued leader has no percentage.
    metrics = _metrics(
        _table(
            [
                *_series("a", [("2020", -10.0), ("2021", 0.0), ("2022", 5.0)]),
                ("b", "2022", 0.0),
            ]
        )
    )
    series_a = metrics.series[0]
    assert series_a.percent_change == 150.0
    assert series_a.max_period_increase == PeriodChange(
        from_date="2020",
        to_date="2021",
        from_value=-10.0,
        to_value=0.0,
        absolute_change=10.0,
        percent_change=100.0,
    )
    zero_leader = _metrics(
        _table([("a", "2022", 0.0), ("b", "2022", -4.0)])
    ).cross_place_comparison
    assert zero_leader is not None
    assert zero_leader.deltas_from_leader == (
        LeaderDelta(
            place_dcid="b",
            place_name="B",
            absolute_delta=-4.0,
            percent_delta=None,
        ),
    )


def test_disjoint_series_are_not_compared() -> None:
    # Test: The comparison when the places share no date.
    # Situation: Two places observed in different years.
    # Expectation: `cross_place_comparison` is None and a caveat says the
    #   places share no observation date.
    result = analyze_timeseries(
        _table([("a", "2010", 1.0), ("a", "2011", 2.0), ("b", "2020", 3.0)])
    )
    assert isinstance(result.metrics, TimeseriesMetrics)
    assert result.metrics.cross_place_comparison is None
    assert (
        "The places share no observation date, so they are not compared "
        "against each other."
    ) in result.caveats


def _elapsed_years(start: str, end: str) -> float:
    """Years between two dates, counting months and days as fractions.

    A day is a fraction of its own month's length, measured here with
    `datetime.date` as the gap to the first day of the next month.
    """

    def as_year(date: str) -> float:
        parts = [int(part) for part in date.split("-")]
        year = float(parts[0])
        if len(parts) > 1:
            year += (parts[1] - 1) / 12.0
        if len(parts) > 2:
            first = datetime.date(parts[0], parts[1], 1)
            following = (first + datetime.timedelta(days=31)).replace(day=1)
            year += (parts[2] - 1) / (following - first).days / 12.0
        return year

    return as_year(end) - as_year(start)


# Date sets of each granularity, from sub-annual to multi-year spans.
_DATE_POOLS: tuple[tuple[str, ...], ...] = (
    ("2016", "2017", "2018", "2019", "2020", "2021", "2022"),
    ("2020-01", "2020-04", "2020-07", "2020-12", "2021-01", "2021-06"),
    (
        "2020-01-31",
        "2020-03-01",
        "2020-03-02",
        "2020-09-01",
        "2021-02-01",
        "2021-03-01",
        "2021-03-02",
    ),
)


def test_analyze_timeseries_invariants_hold_across_generated_series() -> None:
    # Test: The time-series invariants checked by brute force.
    # Situation: 400 seeded random tables of one to six places drawn from
    #   annual, monthly, or daily dates, with partial and stale overlaps,
    #   zero and negative endpoints, and requested places that have no rows.
    # Expectation: Each summary's endpoints, minimum and maximum (earliest
    #   on a tie), local extrema, absolute and percentage change, and largest
    #   period increase and decrease (earliest on a tie) match a direct
    #   computation over the place's points; `cagr` is None exactly when a
    #   series has one point, an endpoint is not positive, or the span is
    #   under a year, and matches the closed form otherwise; the comparison
    #   date is the latest date shared by at least half of the observed
    #   places, or else the date the most places share (the latest on a
    #   tie), counting only dates two or more places share; the entries are
    #   exactly the places with a value on that date, ordered by value and
    #   then DCID, with the spread, the leader, and each other entry's
    #   absolute and percentage difference from the leader; and every
    #   requested place is in `series` or `missing_places`, never both.
    generator = random.Random(20261025)
    for _ in range(400):
        pool = generator.choice(_DATE_POOLS)
        place_count = generator.randint(1, 6)
        places = [f"p{index}" for index in range(place_count)]
        observations: list[tuple[str, str, float]] = []
        for place in places:
            dates = generator.sample(pool, generator.randint(1, len(pool)))
            for date in dates:
                value = generator.choice([-2.0, 0.0, 1.0, 2.5, 4.0, 10.0])
                observations.append((place, date, value))
        requested = [*places, "absent"]
        table = _table(observations, requested_places=requested)
        result = analyze_timeseries(table)
        assert isinstance(result.metrics, TimeseriesMetrics)
        metrics = result.metrics
        by_place: dict[str, dict[str, float]] = {}
        for place, date, value in observations:
            by_place.setdefault(place, {})[date] = value
        reported = {summary.place_dcid for summary in metrics.series}
        for place in requested:
            assert (place in reported) != (place in metrics.missing_places)
        for summary in metrics.series:
            points = sorted(by_place[summary.place_dcid].items())
            (start, first), (end, last) = points[0], points[-1]
            assert (summary.start_date, summary.start_value) == (start, first)
            assert (summary.end_date, summary.end_value) == (end, last)
            lowest = min(points, key=lambda point: (point[1], point[0]))
            highest = min(points, key=lambda point: (-point[1], point[0]))
            assert (summary.min_date, summary.min_value) == lowest
            assert (summary.max_date, summary.max_value) == highest
            if len(points) == 1:
                assert summary.absolute_change is None
                assert summary.percent_change is None
            else:
                assert summary.absolute_change == last - first
                if first == 0.0:
                    assert summary.percent_change is None
                else:
                    assert summary.percent_change == pytest.approx(
                        (last - first) / abs(first) * 100.0
                    )
            steps = [
                (later_date, later - earlier)
                for (_, earlier), (later_date, later) in pairwise(points)
            ]
            rises = [step for step in steps if step[1] > 0.0]
            falls = [step for step in steps if step[1] < 0.0]
            increase = summary.max_period_increase
            decrease = summary.max_period_decrease
            if rises:
                largest = max(step[1] for step in rises)
                expected = min(date for date, size in rises if size == largest)
                assert increase is not None
                assert (increase.to_date, increase.absolute_change) == (
                    expected,
                    largest,
                )
            else:
                assert increase is None
            if falls:
                largest = min(step[1] for step in falls)
                expected = min(date for date, size in falls if size == largest)
                assert decrease is not None
                assert (decrease.to_date, decrease.absolute_change) == (
                    expected,
                    largest,
                )
            else:
                assert decrease is None
            # Series hold at most seven points, below `LOCAL_EXTREMA_CAP`, so
            # every turning point is reported, in date order.
            turning = [
                (date, value, "peak" if value > before else "trough")
                for (_, before), (date, value), (_, after) in zip(
                    points, points[1:], points[2:], strict=False
                )
                if (value - before) * (after - value) < 0.0
            ]
            assert [
                (extremum.date, extremum.value, extremum.kind)
                for extremum in summary.local_extrema
            ] == turning
            years = _elapsed_years(start, end)
            undefined = (
                len(points) == 1 or first <= 0.0 or last <= 0.0 or years < 1.0
            )
            if undefined:
                assert summary.cagr is None
            else:
                assert summary.cagr == pytest.approx(
                    ((last / first) ** (1.0 / years) - 1.0) * 100.0
                )
        comparison = metrics.cross_place_comparison
        counts = Counter(
            date for values in by_place.values() for date in values
        )
        shared = {date: count for date, count in counts.items() if count >= 2}
        if len(by_place) < 2 or not shared:
            assert comparison is None
            continue
        assert comparison is not None
        half_covered = [
            date for date, count in shared.items() if count * 2 >= len(by_place)
        ]
        expected_date = (
            max(half_covered)
            if half_covered
            else max(shared, key=lambda date: (shared[date], date))
        )
        assert comparison.reference_date == expected_date
        participants = {
            place
            for place, values in by_place.items()
            if comparison.reference_date in values
        }
        assert {entry.place_dcid for entry in comparison.entries} == (
            participants
        )
        expected_entries = sorted(
            (
                (place, values[comparison.reference_date])
                for place, values in by_place.items()
                if comparison.reference_date in values
            ),
            key=lambda entry: (-entry[1], entry[0]),
        )
        assert [
            (entry.place_dcid, entry.value) for entry in comparison.entries
        ] == expected_entries
        assert comparison.spread == (
            expected_entries[0][1] - expected_entries[-1][1]
        )
        assert comparison.leader == comparison.entries[0]
        assert len(comparison.deltas_from_leader) == len(comparison.entries) - 1
        for entry, delta in zip(
            comparison.entries[1:], comparison.deltas_from_leader, strict=True
        ):
            assert delta.place_dcid == entry.place_dcid
            assert delta.absolute_delta == entry.value - comparison.leader.value
            assert delta.absolute_delta <= 0.0
            leader_value = comparison.leader.value
            if leader_value == 0.0:
                assert delta.percent_delta is None
            else:
                assert delta.percent_delta == pytest.approx(
                    (entry.value - leader_value) / abs(leader_value) * 100.0
                )
