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
"""Tests for the observation table domain types and validators."""

import math

import pytest

from narratives_agent.analytics.provenance import (
    AlternativeSource,
    Provenance,
    Source,
)
from narratives_agent.analytics.tables import (
    MAX_DCID_CHARS,
    MAX_NAME_CHARS,
    ObservationRow,
    ObservationTable,
    clean_display_name,
    is_inverted_date_range,
    is_valid_dcid,
    is_valid_observation_date,
    is_within_date_range,
)


def test_observation_table_places_with_data_returns_sorted_distinct_dcids() -> (
    None
):
    # Test: `ObservationTable.places_with_data` property.
    # Situation: An `ObservationTable` holds multiple rows for `country/USA`
    #   and `country/CAN` along with a requested place `country/MEX` that has
    #   no rows.
    # Expectation: `places_with_data` returns `("country/CAN", "country/USA")`
    #   in sorted order and omits `country/MEX`.
    source = Source(name="World Bank", url="https://wdi.example")
    table = ObservationTable(
        variable_dcid="Count_Person",
        variable_name="Total Population",
        unit=None,
        scaling_factor=None,
        provenance=Provenance(sources=(source,), facet_ids=("f1",)),
        rows=(
            ObservationRow(
                place_dcid="country/USA",
                place_name="United States",
                date="2021",
                value=332.0,
                facet_id="f1",
            ),
            ObservationRow(
                place_dcid="country/CAN",
                place_name="Canada",
                date="2020",
                value=38.0,
                facet_id="f1",
            ),
            ObservationRow(
                place_dcid="country/USA",
                place_name="United States",
                date="2022",
                value=333.0,
                facet_id="f1",
            ),
        ),
        requested_places=("country/USA", "country/CAN", "country/MEX"),
        place_names={
            "country/USA": "United States",
            "country/CAN": "Canada",
            "country/MEX": "Mexico",
        },
        source=source,
        alternative_sources=(AlternativeSource(facet_id="f2"),),
    )
    assert table.places_with_data == ("country/CAN", "country/USA")


def test_clean_display_name_strips_control_characters_and_caps_length() -> None:
    # Test: Display-name sanitization and fallback handling in
    #   `clean_display_name`.
    # Situation: `clean_display_name` is called on inputs with newlines, NUL
    #   bytes, and repeated spaces; invisible C1 control and format characters
    #   (bidirectional override and zero-width space); a Persian word containing
    #   a zero-width non-joiner (`\u200c`); strings exceeding `MAX_NAME_CHARS`
    #   (including one where the truncation cut falls on a space); and `None`
    #   or whitespace-only values paired with a fallback that itself contains
    #   control characters.
    # Expectation: Control and invisible format characters are removed while
    #   preserving `\u200c`, runs of whitespace collapse to a single space,
    #   overlong names are truncated to `MAX_NAME_CHARS` with trailing spaces
    #   stripped, and non-string or blank values return the sanitized
    #   `fallback`.
    assert (
        clean_display_name("New\nYork\x00  City ", "geoId/3651000")
        == "New York City"
    )
    assert clean_display_name("Evil\u202eName\x9b\u200bX", "f") == "EvilNameX"
    assert clean_display_name("\u0645\u06cc\u200c\u0631\u0648", "f") == (
        "\u0645\u06cc\u200c\u0631\u0648"
    )
    long_name = "x" * (MAX_NAME_CHARS + 20)
    assert clean_display_name(long_name, "x") == "x" * MAX_NAME_CHARS
    cut_at_space = "x" * (MAX_NAME_CHARS - 1) + " bcd"
    assert clean_display_name(cut_at_space, "x") == "x" * (MAX_NAME_CHARS - 1)
    assert (
        clean_display_name(None, "geoId/06\nIGNORE\x00  PREVIOUS")
        == "geoId/06 IGNORE PREVIOUS"
    )
    assert clean_display_name("   \n\t  ", "country/FRA") == "country/FRA"


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_an_observation_row_rejects_a_value_that_is_not_finite(
    value: float,
) -> None:
    # Test: The finite-value invariant of `ObservationRow`.
    # Situation: A row is constructed with `NaN`, infinity, or negative
    #   infinity.
    # Expectation: `ValueError` naming the place and date.
    with pytest.raises(ValueError, match=r"must be finite.*geoId/06 on 2022"):
        ObservationRow("geoId/06", "California", "2022", value)


def test_is_valid_dcid_checks_printable_ascii_and_length_cap() -> None:
    # Test: `is_valid_dcid` character and length validation.
    # Situation: `is_valid_dcid` is called with a standard DCID, an empty
    #   string, strings containing spaces or newlines, a string of exactly
    #   `MAX_DCID_CHARS` characters, and a string of `MAX_DCID_CHARS + 1`
    #   characters.
    # Expectation: Returns `True` only for non-empty printable ASCII strings
    #   without whitespace that do not exceed `MAX_DCID_CHARS`.
    assert is_valid_dcid("geoId/06") is True
    assert is_valid_dcid("d" * MAX_DCID_CHARS) is True
    assert is_valid_dcid("") is False
    assert is_valid_dcid("geoId/06\nIGNORE") is False
    assert is_valid_dcid("geoId 06") is False
    assert is_valid_dcid("d" * (MAX_DCID_CHARS + 1)) is False


@pytest.mark.parametrize(
    ("date", "expected"),
    [
        ("2020", True),
        ("2020-07", True),
        ("2020-07-31", True),
        ("2020-02-29", True),
        ("2020\n", False),
        ("2020-7", False),
        ("latest", False),
        ("", False),
        ("0000", False),
        ("0000-01-01", False),
        ("2021-00", False),
        ("2021-13", False),
        ("2021-02-29", False),
        ("2021-04-31", False),
        ("2021-04-00", False),
    ],
)
def test_observation_date_validation_matches_the_whole_string(
    date: str, expected: bool
) -> None:
    # Test: `is_valid_observation_date` format and calendar validation.
    # Situation: `is_valid_observation_date` is called with `"YYYY"`,
    #   `"YYYY-MM"`, and `"YYYY-MM-DD"` dates including a leap day, as well
    #   as a year with a trailing newline, a single-digit month (`"2020-7"`),
    #   `"latest"`, an empty string, year 0000, months 00 and 13, February
    #   29 in a non-leap year, April 31, and day 00.
    # Expectation: Returns `True` only for real `"YYYY"`, `"YYYY-MM"`, and
    #   `"YYYY-MM-DD"` dates, rejecting partial matches, trailing newlines,
    #   and months or days that do not exist.
    assert is_valid_observation_date(date) is expected


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        ("2020", "2020", False),
        ("2020-07", "2020", False),
        ("2020-07", "2020-03", True),
        ("2021", "2020-12", True),
    ],
)
def test_is_inverted_date_range_compares_at_shared_granularity(
    start: str, end: str, expected: bool
) -> None:
    # Test: `is_inverted_date_range` across mixed date precisions.
    # Situation: `is_inverted_date_range` is called with equal years, a month
    #   start bound within the same end year (`"2020-07"` to `"2020"`), an
    #   inverted month range (`"2020-07"` to `"2020-03"`), and an inverted
    #   year-to-month range (`"2021"` to `"2020-12"`).
    # Expectation: Returns `True` only when `start` comes after `end` at their
    #   shared prefix length.
    assert is_inverted_date_range(start, end) is expected


@pytest.mark.parametrize(
    ("date", "start", "end", "expected"),
    [
        ("2023-07-31", "2015", "2023", True),
        ("2015", "2015-01", "2016", True),
        ("2015-03", "2015-07", None, False),
        ("2024", None, "2023", False),
        ("2015-06-30", None, "2015-06", True),
        ("1999", None, None, True),
    ],
)
def test_date_range_bounds_compare_at_the_coarser_granularity(
    date: str, start: str | None, end: str | None, expected: bool
) -> None:
    # Test: `is_within_date_range` across mixed date precisions and open
    #   bounds.
    # Situation: Year, month, and day observation dates are checked against
    #   year bounds, month bounds, and `None` (unbounded) endpoints.
    # Expectation: Returns `True` when the date and each non-`None` bound
    #   match or are in order at their shared prefix length, and `False`
    #   otherwise.
    assert is_within_date_range(date, start, end) is expected
