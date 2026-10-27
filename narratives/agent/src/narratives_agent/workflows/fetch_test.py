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
"""Tests for `workflows.fetch`.

Covers date resolution, `fetch_observations`, `fetch_child_observations`,
`fetch_multi_entity_observations`, `serialize_fetch_result`, and the
Pydantic-generated Gemini `FunctionDeclaration` schemas.
"""

import asyncio
import calendar
import itertools
import json
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pytest
from pydantic import BaseModel

from narratives_agent.json_value import JsonObject, JsonValue
from narratives_agent.mcp import client as mcp_client
from narratives_agent.workflows import fetch
from narratives_agent.workflows.fetch_requests import (
    COHORT_WINDOW_YEARS,
    FETCH_FUNCTION_NAMES,
    NAMED_PLACE_SERIES_LIMIT,
    DateSelection,
    FetchArgumentError,
    FetchChildObservationsRequest,
    FetchMultiEntityRequest,
    FetchObservationsRequest,
    parse_fetch_request,
)
from narratives_agent.workflows.turn_cache import TurnCache

_WDI_URL = "https://datatopics.worldbank.org/world-development-indicators/"
_TODAY = datetime(2026, 10, 12, tzinfo=UTC)


def _build_payload(
    rows: Sequence[Sequence[JsonValue]],
    *,
    facet: str | None = "f1",
    names: Mapping[str, str] | None = None,
    alternatives: Sequence[str] = (),
    variable: JsonObject | None = None,
) -> JsonObject:
    """Builds a 1.3.x observation payload with `[place, date, value]` rows."""
    json_rows: list[JsonValue] = [list(row) for row in rows]
    payload: JsonObject = {
        "data": {
            "columns": ["observationAbout", "date", "value"],
            "rows": json_rows,
        },
        "entityMetadata": {
            "columns": ["dcid", "name"],
            "rows": [[dcid, name] for dcid, name in (names or {}).items()],
        },
        "variable": variable
        or {"dcid": "Count_Person", "name": "Total population"},
        "alternativeSources": [
            {"sourceMetadata": {"sourceId": item, "provenanceUrl": _WDI_URL}}
            for item in alternatives
        ],
    }
    if facet is not None:
        payload["sourceMetadata"] = {
            "sourceId": facet,
            "provenanceUrl": _WDI_URL,
        }
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


class _FakeMcp:
    """Records observation calls and answers them from a script.

    A call is keyed by its place, its parent place, or else the tool name.
    Keys in `blocked` wait until the call is canceled. When `gate` is set,
    every call waits on it, and the call that brings the number of calls in
    flight to `gate_count` opens it, so `peak_in_flight` records the largest
    number of calls that were ever running together.
    """

    def __init__(self) -> None:
        self.answers: dict[str, JsonObject] = {}
        self.errors: dict[str, str] = {}
        self.transport_errors: set[str] = set()
        self.blocked: set[str] = set()
        self.canceled: list[str] = []
        self.calls: list[tuple[str, JsonObject]] = []
        self.gate: asyncio.Event | None = None
        self.gate_count = 0
        self.in_flight = 0
        self.peak_in_flight = 0

    async def __call__(self, name: str, arguments: JsonObject) -> JsonObject:
        self.calls.append((name, dict(arguments)))
        key = str(
            arguments.get("place_dcid")
            or arguments.get("parent_place_dcid", name)
        )
        self.in_flight += 1
        self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
        try:
            if self.gate is not None:
                if self.in_flight >= self.gate_count:
                    self.gate.set()
                await self.gate.wait()
                # A zero-length sleep yields to the event loop, without a
                # wall-clock wait, so that calls started later overlap this one.
                await asyncio.sleep(0)
            if key in self.blocked:
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    self.canceled.append(key)
                    raise
            if key in self.transport_errors:
                raise mcp_client.McpTransportError()
            if key in self.errors:
                raise mcp_client.McpToolError(name, self.errors[key])
            return self.answers[key]
        finally:
            self.in_flight -= 1


@pytest.fixture(name="mcp")
def install_fake_mcp(monkeypatch: pytest.MonkeyPatch) -> _FakeMcp:
    """Installs a fake MCP client answering by place or parent."""
    fake = _FakeMcp()
    monkeypatch.setattr(mcp_client, "async_call_tool", fake)
    return fake


async def _execute_fetch(
    name: str, arguments: Mapping[str, JsonValue], cache: TurnCache
) -> JsonObject:
    """Validates `arguments`, runs `run_fetch`, and returns the wire dict."""
    try:
        request = parse_fetch_request(name, arguments)
        outcome = await fetch.run_fetch(request, cache)
    except FetchArgumentError as error:
        return error.build_error_response()
    return fetch.serialize_fetch_result(outcome)


def test_named_places_fetch_the_full_series_and_cohorts_a_window() -> None:
    # Test: The default date rule.
    # Situation: No date arguments, for a named-place fetch and for a
    #   cohort, on 2026-10-12.
    # Expectation: The named-place fetch asks for `all` with no window; the
    #   cohort asks for a range from 2017 to 2026 and filters to it.
    series = fetch.resolve_dates(None, None, None, None, is_cohort=False)
    assert series == fetch.DateRequest(date="all", date_range=None)

    cohort = fetch.resolve_dates(
        None, None, None, None, is_cohort=True, today=_TODAY
    )
    assert cohort == fetch.DateRequest(
        date="range",
        date_range_start="2017",
        date_range_end="2026",
        date_range=("2017", "2026"),
    )


def test_explicit_date_modes_are_honored() -> None:
    # Test: Explicit `date_mode` values.
    # Situation: `range` with both bounds, a range implied by a lone
    #   `start_date`, `year`, `latest`, and `all` on a cohort.
    # Expectation: A full range filters client-side; a half-open range is
    #   passed to the server without a client-side window; `year` filters
    #   to that year; `latest` and `all` carry no window even for a cohort.
    full = fetch.resolve_dates("range", "2000-01", "2010", None, is_cohort=True)
    assert full == fetch.DateRequest(
        date="range",
        date_range_start="2000-01",
        date_range_end="2010",
        date_range=("2000-01", "2010"),
    )
    open_end = fetch.resolve_dates(None, "2015", None, None, is_cohort=False)
    assert open_end == fetch.DateRequest(
        date="range", date_range_start="2015", date_range=None
    )
    year = fetch.resolve_dates("year", None, None, "2020", is_cohort=True)
    assert year == fetch.DateRequest(date="2020", date_range=("2020", "2020"))
    assert fetch.resolve_dates("latest", None, None, None, is_cohort=True) == (
        fetch.DateRequest(date="latest", date_range=None)
    )
    assert fetch.resolve_dates("all", None, None, None, is_cohort=True) == (
        fetch.DateRequest(date="all", date_range=None)
    )


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (("soon", None, None, None), "date_mode must be one of"),
        ((None, "last year", None, None), "start_date must be"),
        ((None, "2020", "2010", None), "is after end_date"),
        ((None, "2020-07", "2020-03", None), "is after end_date"),
        (("range", None, None, None), "needs start_date, end_date, or both"),
        (("year", None, None, "2020-05"), "needs year as YYYY"),
    ],
    ids=["mode", "bound", "inverted", "inverted months", "empty range", "year"],
)
def test_malformed_date_arguments_are_rejected(
    arguments: tuple[str | None, str | None, str | None, str | None],
    message: str,
) -> None:
    # Test: Date argument validation.
    # Situation: An unknown mode, a bound that is not a date, an inverted
    #   range of years, an inverted range of months within one year, a
    #   range mode without bounds, and a `year` that is a month.
    # Expectation: Each raises `FetchArgumentError` with a message naming
    #   the problem, which the model receives as the tool error.
    with pytest.raises(FetchArgumentError, match=message):
        fetch.resolve_dates(*arguments, is_cohort=False)


# Each accepted date precision, keyed by its length, with its `strptime`
# format. The oracle helpers below check dates with `strptime` rather than
# with the validator `resolve_dates` uses.
_ORACLE_DATE_FORMATS = {4: "%Y", 7: "%Y-%m", 10: "%Y-%m-%d"}
_ORACLE_DATE_SHAPE = re.compile(r"[0-9]{4}(-[0-9]{2}){0,2}")
_ORACLE_MODES = (None, "latest", "all", "range", "year")
# A `year` argument is four digits, stated here rather than read from the
# module under test, as are the other oracle constants.
_ORACLE_YEAR_LENGTH = 4
# A `YYYY-MM` bound names a month.
_ORACLE_MONTH_LENGTH = 7
# A failing sweep reports at most this many mismatched combinations.
_MAX_REPORTED_MISMATCHES = 10
# A cohort fetch defaults to this many calendar years.
_ORACLE_COHORT_YEARS = 10
# The swept argument values: every mode and an unknown one; bounds at each
# precision, including impossible, short, and non-ASCII-digit values; `year`
# values that are a year, a month, `0000`, short, or superscript digits; and
# `today` on both sides of a new year and in 2000.
_SWEPT_MODES = (*_ORACLE_MODES, "monthly")
_SWEPT_BOUNDS = (
    None,
    "2019",
    "2020",
    "2020-01",
    "2020-07",
    "2020-12-31",
    "2021-01-01",
    "2020-02-29",
    "2021-02-29",
    "2020-13",
    "0000",
    "20",
    "\uff12\uff10\uff12\uff10",
)
_SWEPT_YEARS = (
    None,
    "2020",
    "2020-05",
    "0000",
    "20",
    "\u00b2\u2070\u00b2\u2070",
)
_SWEPT_TODAYS = (
    datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC),
    datetime(2026, 1, 1, tzinfo=UTC),
    datetime(2000, 6, 15, tzinfo=UTC),
)


@dataclass(frozen=True)
class _DateArguments:
    """One swept combination of `resolve_dates` arguments."""

    date_mode: str | None
    start_date: str | None
    end_date: str | None
    year: str | None
    is_cohort: bool
    today: datetime


def _sweep_date_arguments() -> Iterator[_DateArguments]:
    """Yields every combination of the swept `resolve_dates` arguments."""
    for combination in itertools.product(
        _SWEPT_MODES,
        _SWEPT_BOUNDS,
        _SWEPT_BOUNDS,
        _SWEPT_YEARS,
        (False, True),
        _SWEPT_TODAYS,
    ):
        yield _DateArguments(*combination)


def _resolve_swept_dates(arguments: _DateArguments) -> fetch.DateRequest | None:
    """Calls `resolve_dates`, returning `None` when it rejects the arguments."""
    try:
        return fetch.resolve_dates(
            arguments.date_mode,
            arguments.start_date,
            arguments.end_date,
            arguments.year,
            is_cohort=arguments.is_cohort,
            today=arguments.today,
        )
    except FetchArgumentError:
        return None


def _is_oracle_date(text: str) -> bool:
    """Returns whether `text` is a real `YYYY`, `YYYY-MM`, or `YYYY-MM-DD`."""
    if _ORACLE_DATE_SHAPE.fullmatch(text) is None:
        return False
    try:
        datetime.strptime(text, _ORACLE_DATE_FORMATS[len(text)])
    except ValueError:
        return False
    return True


def _has_oracle_bound(arguments: _DateArguments) -> bool:
    """Returns whether either range bound is given."""
    return arguments.start_date is not None or arguments.end_date is not None


def _get_oracle_first_day(bound: str) -> date:
    """Returns the first calendar day of the period a valid bound names."""
    parsed = datetime.strptime(bound, _ORACLE_DATE_FORMATS[len(bound)])
    return parsed.date()


def _get_oracle_last_day(bound: str) -> date:
    """Returns the last calendar day of the period a valid bound names."""
    first = _get_oracle_first_day(bound)
    if len(bound) == _ORACLE_YEAR_LENGTH:
        return date(first.year, 12, 31)
    if len(bound) == _ORACLE_MONTH_LENGTH:
        last_day = calendar.monthrange(first.year, first.month)[1]
        return date(first.year, first.month, last_day)
    return first


def _is_oracle_inverted(start_date: str, end_date: str) -> bool:
    """Returns whether the period of `start_date` begins after `end_date`'s.

    Each bound names a calendar period, so `2020-07` to `2020` is a valid
    range, while `2020-07` to `2020-03` is not.
    """
    return _get_oracle_first_day(start_date) > _get_oracle_last_day(end_date)


def _is_oracle_valid(arguments: _DateArguments) -> bool:
    """Returns whether the oracle accepts a combination of arguments."""
    if arguments.date_mode not in _ORACLE_MODES:
        return False
    bounds = [
        bound
        for bound in (arguments.start_date, arguments.end_date)
        if bound is not None
    ]
    if not all(_is_oracle_date(bound) for bound in bounds):
        return False
    if bounds or arguments.date_mode == "range":
        return bool(bounds) and not (
            arguments.start_date is not None
            and arguments.end_date is not None
            and _is_oracle_inverted(arguments.start_date, arguments.end_date)
        )
    if arguments.date_mode == "year":
        year = arguments.year
        return (
            year is not None
            and len(year) == _ORACLE_YEAR_LENGTH
            and _is_oracle_date(year)
        )
    return True


def _sweep_valid_date_arguments() -> Iterator[_DateArguments]:
    """Yields the swept combinations the oracle accepts."""
    return (item for item in _sweep_date_arguments() if _is_oracle_valid(item))


def _assert_no_mismatches(mismatches: list[str]) -> None:
    """Fails with the first mismatches, each naming its arguments."""
    assert not mismatches, "\n".join(mismatches[:_MAX_REPORTED_MISMATCHES])


def test_resolve_dates_rejects_exactly_the_invalid_arguments() -> None:
    # Test: Which date arguments `resolve_dates` rejects.
    # Situation: Every swept combination of mode, bounds, `year`, cohort
    #   flag, and `today`.
    # Expectation: `resolve_dates` raises `FetchArgumentError` exactly when
    #   the oracle rejects the combination: an unknown mode, a bound that is
    #   not a real date, a range with no bound or an inverted range, or a
    #   `year` mode without a real four-digit year.
    mismatches: list[str] = []
    for arguments in _sweep_date_arguments():
        is_accepted = _resolve_swept_dates(arguments) is not None
        if is_accepted != _is_oracle_valid(arguments):
            mismatches.append(f"{arguments}: accepted={is_accepted}")
    _assert_no_mismatches(mismatches)


def test_resolve_dates_selects_a_range_whenever_a_bound_is_given() -> None:
    # Test: The range rule.
    # Situation: Every accepted combination with a bound or the `range`
    #   mode, whatever the mode.
    # Expectation: The request is a `range` with the bounds as given, and
    #   it has a client-side window exactly when both bounds are given.
    mismatches: list[str] = []
    for arguments in _sweep_valid_date_arguments():
        if not _has_oracle_bound(arguments):
            continue
        start, end = arguments.start_date, arguments.end_date
        window = (start, end) if start is not None and end is not None else None
        expected = fetch.DateRequest(
            date="range",
            date_range_start=start,
            date_range_end=end,
            date_range=window,
        )
        actual = _resolve_swept_dates(arguments)
        if actual != expected:
            mismatches.append(f"{arguments}: {actual} != {expected}")
    _assert_no_mismatches(mismatches)


def test_resolve_dates_fetches_the_one_year_of_a_year_mode() -> None:
    # Test: The `year` rule.
    # Situation: Every accepted `year`-mode combination without a bound.
    # Expectation: The request asks for that year and filters to it.
    mismatches: list[str] = []
    for arguments in _sweep_valid_date_arguments():
        if arguments.date_mode != "year" or _has_oracle_bound(arguments):
            continue
        assert arguments.year is not None
        expected = fetch.DateRequest(
            date=arguments.year, date_range=(arguments.year, arguments.year)
        )
        actual = _resolve_swept_dates(arguments)
        if actual != expected:
            mismatches.append(f"{arguments}: {actual} != {expected}")
    _assert_no_mismatches(mismatches)


def test_resolve_dates_passes_latest_and_all_through() -> None:
    # Test: The `latest` and `all` modes.
    # Situation: Every accepted `latest` or `all` combination without a
    #   bound, for named places and cohorts.
    # Expectation: The request carries the mode as its `date` and no window.
    mismatches: list[str] = []
    for arguments in _sweep_valid_date_arguments():
        mode = arguments.date_mode
        if mode not in ("latest", "all") or _has_oracle_bound(arguments):
            continue
        assert mode is not None
        expected = fetch.DateRequest(date=mode)
        actual = _resolve_swept_dates(arguments)
        if actual != expected:
            mismatches.append(f"{arguments}: {actual} != {expected}")
    _assert_no_mismatches(mismatches)


def test_resolve_dates_defaults_to_the_series_or_the_cohort_window() -> None:
    # Test: The default when no mode and no bound are given.
    # Situation: Every such combination, for named places and cohorts, with
    #   `today` on both sides of a new year and in 2000.
    # Expectation: Named places fetch `all`; a cohort fetches the ten
    #   calendar years ending in `today`'s year and filters to them.
    mismatches: list[str] = []
    for arguments in _sweep_valid_date_arguments():
        if arguments.date_mode is not None or _has_oracle_bound(arguments):
            continue
        if arguments.is_cohort:
            last = arguments.today.year
            first = str(last - _ORACLE_COHORT_YEARS + 1)
            expected = fetch.DateRequest(
                date="range",
                date_range_start=first,
                date_range_end=str(last),
                date_range=(first, str(last)),
            )
        else:
            expected = fetch.DateRequest(date="all")
        actual = _resolve_swept_dates(arguments)
        if actual != expected:
            mismatches.append(f"{arguments}: {actual} != {expected}")
    _assert_no_mismatches(mismatches)


@pytest.mark.asyncio
async def test_a_single_place_fetch_caches_the_series_and_locks_the_facet(
    mcp: _FakeMcp,
) -> None:
    # Test: The single-place path of `fetch_observations`.
    # Situation: One place is requested with no date arguments; the server
    #   answers three years from facet `f1`.
    # Expectation: `get_observations` is called once with `date=all` and no
    #   override; the table is cached as `t1` with three rows; the response
    #   is the table summary; and the variable is locked to `f1`.
    mcp.answers["country/FRA"] = _build_payload(
        [["country/FRA", str(year), 1.0] for year in (2021, 2022, 2023)],
        names={"country/FRA": "France"},
    )
    cache = TurnCache()

    summary = await _execute_fetch(
        "fetch_observations",
        {"variable_dcid": "Count_Person", "place_dcids": ["country/FRA"]},
        cache,
    )

    assert mcp.calls == [
        (
            "get_observations",
            {
                "variable_dcid": "Count_Person",
                "place_dcid": "country/FRA",
                "date": "all",
            },
        )
    ]
    assert summary["table_id"] == "t1"
    assert summary["observation_count"] == 3
    assert summary["facet_id"] == "f1"
    assert summary["places_with_data"] == ["France (country/FRA)"]
    assert (
        cache.get_locked_facet("Count_Person", fetch._NAMED_PLACES_SCOPE)
        == "f1"
    )
    cached = cache.get("t1")
    assert cached is not None
    assert len(cached.table.rows) == 3
    assert cache.tables_fetched == 1


@pytest.mark.asyncio
async def test_a_multi_place_fetch_locks_later_places_to_the_first_facet(
    mcp: _FakeMcp,
) -> None:
    # Test: Facet locking across the places of one fetch.
    # Situation: Three places are requested without an override; the first
    #   place is served from facet `f1`.
    # Expectation: The first call carries no override and every later call
    #   carries `source_override=f1`; the three payloads merge into one
    #   `t1` table whose requested places are the three in request order.
    for place in ("country/FRA", "country/DEU", "country/ESP"):
        mcp.answers[place] = _build_payload([[place, "2023", 1.0]], facet="f1")
    cache = TurnCache()

    summary = await _execute_fetch(
        "fetch_observations",
        {
            "variable_dcid": "Count_Person",
            "place_dcids": ["country/FRA", "country/DEU", "country/ESP"],
        },
        cache,
    )

    overrides = [arguments.get("source_override") for _, arguments in mcp.calls]
    assert overrides == [None, "f1", "f1"]
    assert summary["table_id"] == "t1"
    assert summary["places_with_data_count"] == 3
    cached = cache.get("t1")
    assert cached is not None
    assert cached.table.requested_places == (
        "country/FRA",
        "country/DEU",
        "country/ESP",
    )
    assert cached.table.facet_id == "f1"


@pytest.mark.asyncio
async def test_an_empty_first_place_does_not_let_the_facets_blend(
    mcp: _FakeMcp,
) -> None:
    # Test: Facet locking when the first place has no data.
    # Situation: Four places are requested without an override. The first
    #   answers with no rows and no facet, the second is served from `f1`,
    #   and the fake server serves the third from `f2` and the fourth from
    #   `f1` whatever override it receives.
    # Expectation: The first two calls carry no override (no facet is known
    #   until the second place answers), the last two are locked to `f1`,
    #   and the cached table holds only `f1` rows: the second and fourth
    #   places have data, the third is listed without data, and the table
    #   reports `f1`.
    places: list[JsonValue] = [
        "country/AAA",
        "country/FRA",
        "country/DEU",
        "country/ESP",
    ]
    mcp.answers["country/AAA"] = _build_payload([], facet=None)
    mcp.answers["country/FRA"] = _build_payload([["country/FRA", "2023", 1.0]])
    mcp.answers["country/DEU"] = _build_payload(
        [["country/DEU", "2023", 2.0]], facet="f2"
    )
    mcp.answers["country/ESP"] = _build_payload([["country/ESP", "2023", 3.0]])
    cache = TurnCache()

    summary = await _execute_fetch(
        "fetch_observations",
        {"variable_dcid": "Count_Person", "place_dcids": places},
        cache,
    )

    overrides = [arguments.get("source_override") for _, arguments in mcp.calls]
    assert overrides == [None, None, "f1", "f1"]
    assert summary["facet_id"] == "f1"
    assert summary["places_with_data"] == [
        "country/FRA (country/FRA)",
        "country/ESP (country/ESP)",
    ]
    assert summary["places_without_data"] == [
        "country/AAA (country/AAA)",
        "country/DEU (country/DEU)",
    ]
    cached = cache.get("t1")
    assert cached is not None
    assert {row.facet_id for row in cached.table.rows} == {"f1"}
    assert (
        cache.get_locked_facet("Count_Person", fetch._NAMED_PLACES_SCOPE)
        == "f1"
    )


@pytest.mark.asyncio
async def test_a_later_fetch_of_the_same_variable_reuses_the_locked_facet(
    mcp: _FakeMcp,
) -> None:
    # Test: Facet locking across calls, and an explicit override.
    # Situation: France is fetched and served from `f1`; Germany is then
    #   fetched for the same variable without an override; Spain is fetched
    #   with an explicit `source_override=f9`.
    # Expectation: The Germany call carries `source_override=f1` and the
    #   Spain call carries `f9`, and the lock stays on `f1`.
    mcp.answers["country/FRA"] = _build_payload([["country/FRA", "2023", 1.0]])
    mcp.answers["country/DEU"] = _build_payload([["country/DEU", "2023", 1.0]])
    mcp.answers["country/ESP"] = _build_payload(
        [["country/ESP", "2023", 1.0]], facet="f9"
    )
    cache = TurnCache()
    calls: tuple[tuple[str, JsonObject], ...] = (
        ("country/FRA", {}),
        ("country/DEU", {}),
        ("country/ESP", {"source_override": "f9"}),
    )
    for place, extra in calls:
        await _execute_fetch(
            "fetch_observations",
            {
                "variable_dcid": "Count_Person",
                "place_dcids": [place],
                **extra,
            },
            cache,
        )

    assert [arguments.get("source_override") for _, arguments in mcp.calls] == [
        None,
        "f1",
        "f9",
    ]
    assert (
        cache.get_locked_facet("Count_Person", fetch._NAMED_PLACES_SCOPE)
        == "f1"
    )
    assert cache.table_ids == ("t1", "t2", "t3")


@pytest.mark.asyncio
async def test_more_than_the_series_limit_fetches_the_cohort_window(
    mcp: _FakeMcp,
) -> None:
    # Test: The cohort date rule on a large named-place list.
    # Situation: Eleven places are requested with no date arguments.
    # Expectation: Every call asks for a `range` rather than `all`, because
    #   eleven places are a cohort to be aligned, not series to be read.
    places: list[JsonValue] = [
        f"geoId/{index:02d}" for index in range(NAMED_PLACE_SERIES_LIMIT + 1)
    ]
    for place in places:
        assert isinstance(place, str)
        mcp.answers[place] = _build_payload([[place, "2023", 1.0]])

    await _execute_fetch(
        "fetch_observations",
        {"variable_dcid": "Count_Person", "place_dcids": places},
        TurnCache(),
    )

    assert len(mcp.calls) == NAMED_PLACE_SERIES_LIMIT + 1
    assert {arguments["date"] for _, arguments in mcp.calls} == {"range"}


@pytest.mark.asyncio
async def test_rows_outside_the_window_are_dropped_and_the_rest_kept(
    mcp: _FakeMcp,
) -> None:
    # Test: Date-window filtering of a cohort fetch.
    # Situation: A cohort fetch for 2020 to 2023 receives six rows, three of
    #   them from 2010 to 2012, which a server may return despite the range.
    # Expectation: The three out-of-window rows are dropped, every
    #   in-window row is kept.
    mcp.answers["country/USA"] = _build_payload(
        [
            ["geoId/01", "2010", 1.0],
            ["geoId/01", "2011", 1.0],
            ["geoId/01", "2012", 1.0],
            ["geoId/01", "2021", 1.0],
            ["geoId/02", "2022", 1.0],
            ["geoId/03", "2023", 1.0],
        ]
    )

    summary = await _execute_fetch(
        "fetch_child_observations",
        {
            "variable_dcid": "Count_Person",
            "parent_place_dcid": "country/USA",
            "child_place_type": "State",
            "date_mode": "range",
            "start_date": "2020",
            "end_date": "2023",
        },
        TurnCache(),
    )

    assert summary["observation_count"] == 3
    assert summary["date_range"] == ["2021", "2023"]


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"variable_dcid": "X"}, "place_dcids is required"),
        ({"variable_dcid": "X", "place_dcids": []}, "place_dcids is required"),
        ({"place_dcids": ["a"]}, "variable_dcid is required"),
        (
            {"variable_dcid": "X", "place_dcids": [f"p{i}" for i in range(51)]},
            "at most 50 places",
        ),
        (
            {"variable_dcid": "X", "place_dcids": ["a"], "date_mode": "soon"},
            "date_mode must be one of",
        ),
        (
            {
                "variable_dcid": "X",
                "place_dcids": ["a", "a", "country/U SA"],
            },
            "place_dcids: String should match pattern",
        ),
    ],
    ids=[
        "no places",
        "empty places",
        "no variable",
        "too many",
        "bad date",
        "bad dcid",
    ],
)
@pytest.mark.asyncio
async def test_malformed_fetch_arguments_return_an_error_without_a_call(
    mcp: _FakeMcp, arguments: JsonObject, message: str
) -> None:
    # Test: Argument validation of `fetch_observations`.
    # Situation: A missing and an empty place list, a missing variable, more
    #   than fifty places, a bad date mode, and a place DCID with a space
    #   listed after a duplicated place.
    # Expectation: Each returns `{"error": ...}` naming the problem, and for
    #   the DCID the argument it concerns without an index, which would
    #   count the deduplicated list rather than the list the model sent,
    #   and makes no MCP call.
    result = await _execute_fetch("fetch_observations", arguments, TurnCache())
    assert isinstance(result["error"], str)
    assert message in result["error"]
    assert mcp.calls == []


@pytest.mark.asyncio
async def test_a_tool_error_from_mcp_is_returned_with_its_place(
    mcp: _FakeMcp,
) -> None:
    # Test: Propagation of a tool-level MCP error (`McpToolError`).
    # Situation: The server rejects the second of two places with
    #   `McpToolError`.
    # Expectation: The fetch returns `{"error": ..., "place_dcid": ...}`
    #   naming the rejected place and caches no table.
    mcp.answers["country/FRA"] = _build_payload([["country/FRA", "2023", 1.0]])
    mcp.errors["nope"] = "Unknown place."
    cache = TurnCache()

    result = await _execute_fetch(
        "fetch_observations",
        {"variable_dcid": "X", "place_dcids": ["country/FRA", "nope"]},
        cache,
    )

    assert result == {"error": "Unknown place.", "place_dcid": "nope"}
    assert cache.tables_fetched == 0


@pytest.mark.asyncio
async def test_a_child_fetch_defaults_to_the_recent_window_and_keeps_the_cohort(
    monkeypatch: pytest.MonkeyPatch, mcp: _FakeMcp
) -> None:
    # Test: `fetch_child_observations`.
    # Situation: A cohort fetch with no date arguments and a locked facet
    #   for the variable over the same parent and child type.
    # Expectation: `get_child_observations` is called with the parent, the
    #   child type, a ten-year range, and the locked facet; the table is
    #   cached as `t1` with the parent and child type recorded; and the
    #   response is the summary with the alternative sources.
    monkeypatch.setattr(fetch, "_get_current_year", lambda _today: 2026)
    mcp.answers["country/USA"] = _build_payload(
        [["geoId/01", "2023", 1.0], ["geoId/02", "2023", 2.0]],
        alternatives=["f2", "f3"],
    )
    cache = TurnCache()
    cache.lock_facet("Count_Person", ("children", "country/USA", "State"), "f1")

    summary = await _execute_fetch(
        "fetch_child_observations",
        {
            "variable_dcid": "Count_Person",
            "parent_place_dcid": "country/USA",
            "child_place_type": "State",
        },
        cache,
    )

    assert mcp.calls == [
        (
            "get_child_observations",
            {
                "variable_dcid": "Count_Person",
                "parent_place_dcid": "country/USA",
                "child_place_type": "State",
                "source_override": "f1",
                "date": "range",
                "date_range_start": "2017",
                "date_range_end": "2026",
            },
        )
    ]
    cached = cache.get("t1")
    assert cached is not None
    assert cached.table.parent_place_dcid == "country/USA"
    assert cached.table.child_place_type == "State"
    alternatives = summary["alternative_sources"]
    assert isinstance(alternatives, list)
    assert [
        item["source_id"] for item in alternatives if isinstance(item, dict)
    ] == ["f2", "f3"]


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (
            {"variable_dcid": "X", "parent_place_dcid": "country/USA"},
            "child_place_type is required.",
        ),
        (
            {
                "variable_dcid": "X",
                "parent_place_dcid": "country/USA",
                "child_place_type": "State or County",
            },
            "child_place_type: String should match pattern",
        ),
    ],
    ids=["missing", "not a place type"],
)
@pytest.mark.asyncio
async def test_a_child_fetch_with_a_bad_argument_returns_an_error(
    mcp: _FakeMcp, arguments: JsonObject, message: str
) -> None:
    # Test: Argument validation of `fetch_child_observations`.
    # Situation: The call omits `child_place_type`, or passes one that is not
    #   a schema class name.
    # Expectation: The fetch returns an error naming the argument and makes
    #   no MCP call.
    result = await _execute_fetch(
        "fetch_child_observations", arguments, TurnCache()
    )
    assert isinstance(result["error"], str)
    assert result["error"].startswith(message)
    assert mcp.calls == []


@pytest.mark.asyncio
async def test_a_multi_entity_payload_without_a_variable_returns_an_error(
    mcp: _FakeMcp,
) -> None:
    # Test: A malformed relationship response.
    # Situation: The server answers a JSON object without the `variable`
    #   block every observation response carries.
    # Expectation: The fetch returns an error naming the missing block and
    #   caches nothing.
    mcp.answers["get_multi_entity_observations"] = {
        "content": [{"type": "text", "text": json.dumps({"data": {}})}]
    }
    cache = TurnCache()

    result = await _execute_fetch(
        "fetch_multi_entity_observations",
        {"variable_dcid": "Aid", "entities": {"donor": ["country/ARE"]}},
        cache,
    )

    assert result == {
        "error": (
            "The observation payload for Aid has malformed fields: variable."
        )
    }
    assert cache.tables_fetched == 0


@pytest.mark.asyncio
async def test_a_multi_entity_fetch_caches_a_tabular_response(
    mcp: _FakeMcp,
) -> None:
    # Test: The pass-through for a relationship variable.
    # Situation: The server answers rows keyed by `observationAbout` for a
    #   bilateral pair.
    # Expectation: The call passes the entities through with `date=all`,
    #   the table is cached as `t1`, and the summary is returned.
    mcp.answers["get_multi_entity_observations"] = _build_payload(
        [["country/AFG", "2020", 5.0]], variable={"dcid": "Aid"}
    )
    cache = TurnCache()
    entities: JsonObject = {
        "donor": ["country/ARE"],
        "recipient": ["country/AFG"],
    }

    summary = await _execute_fetch(
        "fetch_multi_entity_observations",
        {"variable_dcid": "Aid", "entities": entities},
        cache,
    )

    (call,) = mcp.calls
    assert call[0] == "get_multi_entity_observations"
    assert call[1]["entities"] == entities
    assert call[1]["date"] == "all"
    assert summary["table_id"] == "t1"
    assert cache.tables_fetched == 1


@pytest.mark.asyncio
async def test_a_multi_entity_response_without_places_is_summarized(
    mcp: _FakeMcp,
) -> None:
    # Test: A relationship response keyed by entity role.
    # Situation: The server answers rows whose columns are `donor`,
    #   `recipient`, `date`, and `value`, which name no place column; and
    #   separately a call omits `entities`.
    # Expectation: The response is a compact summary with the columns, the
    #   row count, at most five sample rows, the facet, and the source and
    #   alternatives with the same snake_case keys as a table summary, with
    #   `table_id` null and nothing cached; the call without entities
    #   returns an error.
    rows: list[JsonValue] = [
        ["country/ARE", "country/AFG", str(2015 + i), 1.0] for i in range(7)
    ]
    mcp.answers["get_multi_entity_observations"] = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "data": {
                            "columns": ["donor", "recipient", "date", "value"],
                            "rows": rows,
                        },
                        "sourceMetadata": {
                            "sourceId": "f1",
                            "provenanceUrl": _WDI_URL,
                        },
                        "alternativeSources": [
                            {"sourceMetadata": {"sourceId": "f2"}}
                        ],
                        "variable": {"dcid": "Aid"},
                    }
                ),
            }
        ]
    }
    cache = TurnCache()

    summary = await _execute_fetch(
        "fetch_multi_entity_observations",
        {"variable_dcid": "Aid", "entities": {"donor": ["country/ARE"]}},
        cache,
    )

    assert summary == {
        "table_id": None,
        "note": (
            "The response did not parse as place observations, so it was not "
            "cached as a table and has no table_id."
        ),
        "columns": ["donor", "recipient", "date", "value"],
        "row_count": 7,
        "sample_rows": rows[:5],
        "facet_id": "f1",
        "source": {"name": "datatopics.worldbank.org", "url": _WDI_URL},
        "alternative_sources": [{"source_id": "f2"}],
    }
    assert cache.tables_fetched == 0

    missing = await _execute_fetch(
        "fetch_multi_entity_observations",
        {"variable_dcid": "Aid"},
        cache,
    )
    assert isinstance(missing["error"], str)
    assert "entities must map" in missing["error"]


@pytest.mark.asyncio
async def test_run_fetch_dispatches_by_request_type(mcp: _FakeMcp) -> None:
    # Test: `parse_fetch_request` and `run_fetch`.
    # Situation: `parse_fetch_request` and `run_fetch` are called with a
    #   valid fetch function name and with an unknown name.
    # Expectation: The request is validated and dispatched to produce a
    #   `FetchResult`, while an unknown name raises `KeyError`.
    mcp.answers["country/FRA"] = _build_payload([["country/FRA", "2023", 1.0]])
    cache = TurnCache()
    request = parse_fetch_request(
        "fetch_observations",
        {"variable_dcid": "Count_Person", "place_dcids": ["country/FRA"]},
    )
    outcome = await fetch.run_fetch(request, cache)
    assert isinstance(outcome, fetch.FetchResult)
    assert outcome.table_id == "t1"
    with pytest.raises(KeyError):
        parse_fetch_request("fetch_nothing", {})


def test_fetch_declarations_come_from_described_models() -> None:
    # Test: Gemini `FunctionDeclaration` generation for the fetch functions.
    # Situation: `build_fetch_declarations()` builds `FunctionDeclaration`
    #   instances from `FetchObservationsRequest`,
    #   `FetchChildObservationsRequest`, and `FetchMultiEntityRequest`, and
    #   every field of the request models is inspected for a description.
    # Expectation: All three declarations carry their model's JSON schema and
    #   expected `required` fields without the model docstring as a top-level
    #   `description`, and every field across the request models has a
    #   non-empty `description`.
    declarations = fetch.build_fetch_declarations()
    assert [declaration.name for declaration in declarations] == [
        "fetch_observations",
        "fetch_child_observations",
        "fetch_multi_entity_observations",
    ]
    assert {declaration.name for declaration in declarations} == (
        FETCH_FUNCTION_NAMES
    )

    schemas = [
        declaration.parameters_json_schema for declaration in declarations
    ]
    for schema in schemas:
        assert isinstance(schema, dict)
        assert "description" not in schema
    assert isinstance(schemas[0], dict)
    assert set(schemas[0].get("required", [])) == {
        "variable_dcid",
        "place_dcids",
    }
    properties = schemas[0].get("properties")
    assert isinstance(properties, dict)
    assert set(properties) == {
        "variable_dcid",
        "place_dcids",
        "date_mode",
        "start_date",
        "end_date",
        "year",
        "source_override",
    }
    assert isinstance(schemas[1], dict)
    assert set(schemas[1].get("required", [])) == {
        "variable_dcid",
        "parent_place_dcid",
        "child_place_type",
    }
    assert isinstance(schemas[2], dict)
    assert set(schemas[2].get("required", [])) == {
        "variable_dcid",
        "entities",
    }

    models: tuple[type[BaseModel], ...] = (
        DateSelection,
        FetchObservationsRequest,
        FetchChildObservationsRequest,
        FetchMultiEntityRequest,
    )
    for model_class in models:
        for field_name, field_info in model_class.model_fields.items():
            assert field_info.description and field_info.description.strip(), (
                f"{model_class.__name__}.{field_name} is missing a description"
            )
    date_mode = DateSelection.model_fields["date_mode"].description or ""
    assert f"up to {NAMED_PLACE_SERIES_LIMIT} named places" in date_mode
    assert f"the last {COHORT_WINDOW_YEARS} calendar years" in date_mode


@pytest.mark.asyncio
async def test_a_single_place_summary_has_every_model_facing_field(
    mcp: _FakeMcp,
) -> None:
    # Test: The full JSON object `serialize_fetch_result` sends the model.
    # Situation: France is fetched with two years from facet `f1`, which
    #   offers one alternative facet `f2`.
    # Expectation: The response holds exactly the table summary fields, with
    #   snake_case keys for the source and the alternative.
    mcp.answers["country/FRA"] = _build_payload(
        [["country/FRA", "2022", 1.0], ["country/FRA", "2023", 2.0]],
        names={"country/FRA": "France"},
        alternatives=["f2"],
    )

    summary = await _execute_fetch(
        "fetch_observations",
        {"variable_dcid": "Count_Person", "place_dcids": ["country/FRA"]},
        TurnCache(),
    )

    assert summary == {
        "table_id": "t1",
        "variable_dcid": "Count_Person",
        "variable_name": "Total population",
        "observation_count": 2,
        "places_with_data_count": 1,
        "places_with_data": ["France (country/FRA)"],
        "places_without_data_count": 0,
        "places_without_data": [],
        "date_range": ["2022", "2023"],
        "source": {"name": "datatopics.worldbank.org", "url": _WDI_URL},
        "facet_id": "f1",
        "unit": None,
        "scaling_factor": None,
        "measurement_method": None,
        "observation_period": None,
        "alternative_sources": [
            {"source_id": "f2", "provenance_url": _WDI_URL}
        ],
        "value_range": [1.0, 2.0],
        "sample_rows": [
            {
                "place_dcid": "country/FRA",
                "place_name": "France",
                "date": observation_date,
                "value": value,
                "facet_id": "f1",
            }
            for observation_date, value in (("2022", 1.0), ("2023", 2.0))
        ],
    }


@pytest.mark.asyncio
async def test_an_unreadable_result_returns_an_error_naming_the_place(
    mcp: _FakeMcp,
) -> None:
    # Test: A tool result that does not decode to a JSON object.
    # Situation: The server answers France with an envelope whose text is
    #   not JSON.
    # Expectation: The fetch returns an error naming the tool and the place
    #   and caches nothing.
    mcp.answers["country/FRA"] = {
        "content": [{"type": "text", "text": "upstream unavailable"}]
    }
    cache = TurnCache()

    result = await _execute_fetch(
        "fetch_observations",
        {"variable_dcid": "Count_Person", "place_dcids": ["country/FRA"]},
        cache,
    )

    assert result == {
        "error": "The get_observations result is not a readable observation "
        "payload.",
        "place_dcid": "country/FRA",
    }
    assert cache.tables_fetched == 0


@pytest.mark.asyncio
async def test_a_malformed_payload_is_logged_and_returned_as_an_error(
    mcp: _FakeMcp, caplog: pytest.LogCaptureFixture
) -> None:
    # Test: An `ObservationPayloadError` from the parser.
    # Situation: The server answers a child fetch with a JSON object that
    #   lacks the `variable` block.
    # Expectation: The fetch returns the parser's error naming the missing
    #   block, logs a warning, and caches nothing.
    mcp.answers["country/USA"] = {
        "content": [{"type": "text", "text": json.dumps({"data": {}})}]
    }
    cache = TurnCache()

    with caplog.at_level("WARNING"):
        result = await _execute_fetch(
            "fetch_child_observations",
            {
                "variable_dcid": "Count_Person",
                "parent_place_dcid": "country/USA",
                "child_place_type": "State",
            },
            cache,
        )

    assert result == {
        "error": (
            "The observation payload for Count_Person has malformed fields: "
            "variable."
        )
    }
    assert "Malformed MCP observation payload" in caplog.text
    assert cache.tables_fetched == 0


@pytest.mark.asyncio
async def test_a_transport_failure_propagates_out_of_run_fetch(
    mcp: _FakeMcp,
) -> None:
    # Test: An MCP failure below the tool layer.
    # Situation: The request for France fails with `McpTransportError`.
    # Expectation: `run_fetch` raises `McpTransportError` rather than a
    #   `FetchArgumentError` for the model, so the caller can abort the turn.
    mcp.transport_errors.add("country/FRA")
    request = parse_fetch_request(
        "fetch_observations",
        {"variable_dcid": "Count_Person", "place_dcids": ["country/FRA"]},
    )

    with pytest.raises(mcp_client.McpTransportError):
        await fetch.run_fetch(request, TurnCache())


@pytest.mark.asyncio
async def test_a_failed_concurrent_call_cancels_the_others(
    mcp: _FakeMcp,
) -> None:
    # Test: Cleanup of concurrent place calls on failure.
    # Situation: The variable is locked to `f1`, so three places are called
    #   concurrently; Germany fails with a tool error while Spain's call is
    #   still running.
    # Expectation: The fetch returns Germany's error, Spain's call is
    #   canceled rather than left running, and nothing is cached.
    mcp.answers["country/FRA"] = _build_payload([["country/FRA", "2023", 1.0]])
    mcp.errors["country/DEU"] = "Unknown place."
    mcp.blocked.add("country/ESP")
    cache = TurnCache()
    cache.lock_facet("Count_Person", fetch._NAMED_PLACES_SCOPE, "f1")

    result = await _execute_fetch(
        "fetch_observations",
        {
            "variable_dcid": "Count_Person",
            "place_dcids": ["country/FRA", "country/DEU", "country/ESP"],
        },
        cache,
    )

    assert result == {"error": "Unknown place.", "place_dcid": "country/DEU"}
    assert mcp.canceled == ["country/ESP"]
    assert cache.tables_fetched == 0


@pytest.mark.asyncio
async def test_concurrent_place_calls_are_bounded(mcp: _FakeMcp) -> None:
    # Test: `_MAX_CONCURRENT_PLACE_FETCHES`.
    # Situation: Four more places than the bound are requested for a variable
    #   locked to `f1`, and no call returns until the bound is reached.
    # Expectation: Exactly the bound runs at once, and every place is still
    #   fetched and cached.
    limit = fetch._MAX_CONCURRENT_PLACE_FETCHES
    places: list[JsonValue] = [
        f"geoId/{index:02d}" for index in range(limit + 4)
    ]
    for place in places:
        assert isinstance(place, str)
        mcp.answers[place] = _build_payload([[place, "2023", 1.0]])
    mcp.gate = asyncio.Event()
    mcp.gate_count = limit
    cache = TurnCache()
    cache.lock_facet("Count_Person", fetch._NAMED_PLACES_SCOPE, "f1")

    summary = await _execute_fetch(
        "fetch_observations",
        {"variable_dcid": "Count_Person", "place_dcids": places},
        cache,
    )

    assert mcp.peak_in_flight == limit
    assert summary["places_with_data_count"] == len(places)


@pytest.mark.asyncio
async def test_a_place_keyed_multi_entity_response_without_rows_is_summarized(
    mcp: _FakeMcp,
) -> None:
    # Test: A multi-entity response that names places but has no rows.
    # Situation: The server answers with the `observationAbout` columns and
    #   no rows.
    # Expectation: The response is the compact summary with no rows, a null
    #   `table_id`, and a note that no observation fell in the requested
    #   dates, and nothing is cached.
    mcp.answers["get_multi_entity_observations"] = _build_payload(
        [], variable={"dcid": "Aid"}
    )
    cache = TurnCache()

    summary = await _execute_fetch(
        "fetch_multi_entity_observations",
        {"variable_dcid": "Aid", "entities": {"donor": ["country/ARE"]}},
        cache,
    )

    assert summary["table_id"] is None
    assert summary["row_count"] == 0
    assert summary["note"] == (
        "The response has no observations in the requested dates, so it was "
        "not cached as a table and has no table_id."
    )
    assert cache.tables_fetched == 0


@pytest.mark.asyncio
async def test_a_multi_entity_child_expansion_defaults_to_the_cohort_window(
    monkeypatch: pytest.MonkeyPatch, mcp: _FakeMcp
) -> None:
    # Test: The default date window of a multi-entity child expansion.
    # Situation: A relationship variable is fetched with all three expansion
    #   fields and no date arguments in 2026.
    # Expectation: The call passes the expansion through and asks for the
    #   ten calendar years from 2017 to 2026, as a cohort does.
    monkeypatch.setattr(fetch, "_get_current_year", lambda _today: 2026)
    mcp.answers["get_multi_entity_observations"] = _build_payload(
        [["country/AFG", "2020", 5.0]], variable={"dcid": "Aid"}
    )

    await _execute_fetch(
        "fetch_multi_entity_observations",
        {
            "variable_dcid": "Aid",
            "entities": {"donor": ["country/ARE"]},
            "parent_entity_property": "recipient",
            "parent_entity_dcid": "Earth",
            "child_entity_type": "Country",
        },
        TurnCache(),
    )

    ((_, arguments),) = mcp.calls
    assert arguments == {
        "variable_dcid": "Aid",
        "entities": {"donor": ["country/ARE"]},
        "parent_entity_property": "recipient",
        "parent_entity_dcid": "Earth",
        "child_entity_type": "Country",
        "date": "range",
        "date_range_start": "2017",
        "date_range_end": "2026",
    }


@pytest.mark.asyncio
async def test_a_transport_failure_wins_over_a_concurrent_tool_error(
    mcp: _FakeMcp,
) -> None:
    # Test: The failure raised when concurrent place calls fail in two ways.
    # Situation: The variable is locked to `f1`; France fails with a tool
    #   error and Germany, called after it, with a transport failure.
    # Expectation: `run_fetch` raises `McpTransportError`, so the caller
    #   aborts the turn instead of returning a tool error to the model.
    mcp.errors["country/FRA"] = "Unknown place."
    mcp.transport_errors.add("country/DEU")
    cache = TurnCache()
    cache.lock_facet("Count_Person", fetch._NAMED_PLACES_SCOPE, "f1")
    request = parse_fetch_request(
        "fetch_observations",
        {
            "variable_dcid": "Count_Person",
            "place_dcids": ["country/FRA", "country/DEU"],
        },
    )

    with pytest.raises(mcp_client.McpTransportError):
        await fetch.run_fetch(request, cache)


@pytest.mark.asyncio
async def test_places_without_a_facet_are_all_called_in_turn(
    mcp: _FakeMcp,
) -> None:
    # Test: The facet search when no place names a facet.
    # Situation: Three places are requested without an override, and every
    #   response is empty with no facet.
    # Expectation: Every call carries no override, the table lists the
    #   three places without data, and no facet is locked.
    places: list[JsonValue] = ["country/FRA", "country/DEU", "country/ESP"]
    for place in places:
        assert isinstance(place, str)
        mcp.answers[place] = _build_payload([], facet=None)
    cache = TurnCache()

    summary = await _execute_fetch(
        "fetch_observations",
        {"variable_dcid": "Count_Person", "place_dcids": places},
        cache,
    )

    assert [arguments.get("source_override") for _, arguments in mcp.calls] == [
        None,
        None,
        None,
    ]
    assert summary["places_without_data_count"] == 3
    assert (
        cache.get_locked_facet("Count_Person", fetch._NAMED_PLACES_SCOPE)
        is None
    )


@pytest.mark.asyncio
async def test_a_facet_lock_applies_only_to_the_same_places(
    mcp: _FakeMcp,
) -> None:
    # Test: The scope of a facet lock.
    # Situation: A child fetch of US states is served from `f1`; the same
    #   variable is then fetched for France by name, for US states again,
    #   and for US counties.
    # Expectation: Only the second fetch of US states carries
    #   `source_override=f1`; the named fetch and the county fetch let the
    #   server choose, because a facet chosen for states can lack data for
    #   other places.
    mcp.answers["country/USA"] = _build_payload([["geoId/01", "2023", 1.0]])
    mcp.answers["country/FRA"] = _build_payload(
        [["country/FRA", "2023", 1.0]], facet="f2"
    )
    cache = TurnCache()
    child_arguments: JsonObject = {
        "variable_dcid": "Count_Person",
        "parent_place_dcid": "country/USA",
        "child_place_type": "State",
    }

    await _execute_fetch("fetch_child_observations", child_arguments, cache)
    await _execute_fetch(
        "fetch_observations",
        {"variable_dcid": "Count_Person", "place_dcids": ["country/FRA"]},
        cache,
    )
    await _execute_fetch("fetch_child_observations", child_arguments, cache)
    await _execute_fetch(
        "fetch_child_observations",
        {**child_arguments, "child_place_type": "County"},
        cache,
    )

    assert [arguments.get("source_override") for _, arguments in mcp.calls] == [
        None,
        None,
        "f1",
        None,
    ]


@pytest.mark.asyncio
async def test_an_empty_multi_entity_response_is_summarized_as_empty(
    mcp: _FakeMcp,
) -> None:
    # Test: The live shape of an empty relationship response.
    # Situation: The server answers `{"data": {}}` with the `variable` block,
    #   as it does for a variable without data.
    # Expectation: The compact summary has no columns and no rows, and its
    #   note says that no observation fell in the requested dates rather than
    #   that the rows are keyed by entity role.
    mcp.answers["get_multi_entity_observations"] = {
        "content": [
            {
                "type": "text",
                "text": json.dumps({"data": {}, "variable": {"dcid": "Aid"}}),
            }
        ]
    }

    summary = await _execute_fetch(
        "fetch_multi_entity_observations",
        {"variable_dcid": "Aid", "entities": {"donor": ["country/ARE"]}},
        TurnCache(),
    )

    assert summary["columns"] == []
    assert summary["row_count"] == 0
    assert summary["note"] == (
        "The response has no observations in the requested dates, so it was "
        "not cached as a table and has no table_id."
    )
