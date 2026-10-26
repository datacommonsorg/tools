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
"""Tests for the table summary in `analytics.summarize`.

Covers the place lists and counts, the date and value ranges, the sampled
rows, the metadata passed through from the table, the list cap, and the JSON
form of the summary via `json_safe`.
"""

import json

from narratives_agent.analytics.provenance import (
    AlternativeSource,
    Provenance,
    Source,
)
from narratives_agent.analytics.summarize import (
    SAMPLE_ROW_CAP,
    SUMMARY_PLACE_LIST_CAP,
    summarize_table,
)
from narratives_agent.analytics.tables import ObservationRow, ObservationTable
from narratives_agent.json_value import json_safe

_SOURCE = Source(name="World Development Indicators", url="https://wdi")
_ALTERNATIVE = AlternativeSource(facet_id="f2", provenance_url="https://other")


def _table(
    rows: tuple[ObservationRow, ...],
    requested_places: tuple[str, ...],
) -> ObservationTable:
    """Builds a table with fixed metadata around `rows`."""
    names = {place: place.upper() for place in requested_places}
    names.update({row.place_dcid: row.place_name for row in rows})
    return ObservationTable(
        variable_dcid="Count_Person",
        variable_name="Total population",
        unit="Person",
        scaling_factor=None,
        provenance=Provenance(sources=(_SOURCE,)),
        rows=rows,
        requested_places=requested_places,
        place_names=names,
        measurement_method="WikidataPopulation",
        observation_period="P1Y",
        facet_id="f1",
        source=_SOURCE,
        alternative_sources=(_ALTERNATIVE,),
    )


def test_summary_reports_places_ranges_metadata_and_samples() -> None:
    # Test: The summary of a small cohort table.
    # Situation: Three places requested in the order b, a, c; `a` and `b`
    #   have rows across two dates, and `c` has none.
    # Expectation: Places with data are listed in request order with their
    #   names and DCIDs, `c` is listed without data, the date and value
    #   ranges span the rows, every row is a sample because there are fewer
    #   than the cap, and the metadata is passed through.
    rows = (
        ObservationRow("a", "Alpha", "2020", 1.0, "f1"),
        ObservationRow("a", "Alpha", "2021", 3.0, "f1"),
        ObservationRow("b", "Beta", "2020", 2.0, "f1"),
        ObservationRow("b", "Beta", "2022", -1.0, "f1"),
    )
    summary = summarize_table(_table(rows, ("b", "a", "c")))
    assert summary.observation_count == 4
    assert summary.places_with_data_count == 2
    assert summary.places_with_data == ("Beta (b)", "Alpha (a)")
    assert summary.places_without_data_count == 1
    assert summary.places_without_data == ("C (c)",)
    assert summary.date_range == ("2020", "2022")
    assert summary.value_range == (-1.0, 3.0)
    assert summary.sample_rows == rows
    assert summary.source == _SOURCE
    assert summary.facet_id == "f1"
    assert summary.unit == "Person"
    assert summary.scaling_factor is None
    assert summary.measurement_method == "WikidataPopulation"
    assert summary.observation_period == "P1Y"
    assert summary.alternative_sources == (_ALTERNATIVE,)


def test_unrequested_places_are_sorted_and_duplicates_count_once() -> None:
    # Test: Place ordering and counting.
    # Situation: One table requests no places and has rows for `c`, `a`,
    #   and `b` in that order; another requests `x` twice and has no rows.
    # Expectation: The first lists the places with data in sorted order and
    #   none without data; the second lists and counts `x` once.
    rows = (
        ObservationRow("c", "Gamma", "2022", 1.0),
        ObservationRow("a", "Alpha", "2022", 2.0),
        ObservationRow("b", "Beta", "2022", 3.0),
    )
    unrequested = summarize_table(_table(rows, ()))
    assert unrequested.places_with_data == (
        "Alpha (a)",
        "Beta (b)",
        "Gamma (c)",
    )
    assert unrequested.places_without_data_count == 0
    assert unrequested.places_without_data == ()

    duplicated = summarize_table(_table((), ("x", "x")))
    assert duplicated.places_without_data_count == 1
    assert duplicated.places_without_data == ("X (x)",)


def test_empty_table_summary_has_no_ranges_or_samples() -> None:
    # Test: The summary of a table without rows.
    # Situation: Two places were requested and neither has a row.
    # Expectation: Zero observations, both places without data, no date or
    #   value range, and no samples.
    summary = summarize_table(_table((), ("a", "b")))
    assert summary.observation_count == 0
    assert summary.places_with_data == ()
    assert summary.places_without_data == ("A (a)", "B (b)")
    assert summary.date_range is None
    assert summary.value_range is None
    assert summary.sample_rows == ()


def test_samples_are_spread_across_a_long_series() -> None:
    # Test: Sample selection on a table larger than the cap.
    # Situation: One place with 66 annual rows from 1960 to 2025.
    # Expectation: Exactly `SAMPLE_ROW_CAP` samples, the first and last rows
    #   among them, evenly spaced in date order.
    rows = tuple(
        ObservationRow("a", "Alpha", str(1960 + index), float(index))
        for index in range(66)
    )
    summary = summarize_table(_table(rows, ("a",)))
    assert len(summary.sample_rows) == SAMPLE_ROW_CAP
    assert summary.sample_rows[0] == rows[0]
    assert summary.sample_rows[-1] == rows[-1]
    dates = [row.date for row in summary.sample_rows]
    assert dates == ["1960", "1976", "1992", "2009", "2025"]


def test_place_lists_are_capped_while_counts_are_not() -> None:
    # Test: The place list cap on a large cohort.
    # Situation: Thirty requested places, each with one row, and thirty
    #   more requested places without rows.
    # Expectation: Both lists hold `SUMMARY_PLACE_LIST_CAP` entries while
    #   both counts say 30.
    with_data = tuple(f"d{index:02d}" for index in range(30))
    without = tuple(f"n{index:02d}" for index in range(30))
    rows = tuple(
        ObservationRow(place, place, "2022", 1.0) for place in with_data
    )
    summary = summarize_table(_table(rows, with_data + without))
    assert summary.places_with_data_count == 30
    assert len(summary.places_with_data) == SUMMARY_PLACE_LIST_CAP
    assert summary.places_without_data_count == 30
    assert len(summary.places_without_data) == SUMMARY_PLACE_LIST_CAP


def test_summary_is_json_serializable_via_json_safe() -> None:
    # Test: The JSON form of a summary via `json_safe`.
    # Situation: A summary with sample rows, tuples, and typed source models.
    # Expectation: `json_safe` returns plain types that `json.dumps` accepts
    #   without NaN, with rows and sources as dicts and tuples as lists.
    rows = (ObservationRow("a", "Alpha", "2020", 1.0, "f1"),)
    payload = json_safe(summarize_table(_table(rows, ("a",))))
    assert isinstance(payload, dict)
    json.dumps(payload, allow_nan=False)
    assert payload["sample_rows"] == [
        {
            "place_dcid": "a",
            "place_name": "Alpha",
            "date": "2020",
            "value": 1.0,
            "facet_id": "f1",
        }
    ]
    assert payload["date_range"] == ["2020", "2020"]
