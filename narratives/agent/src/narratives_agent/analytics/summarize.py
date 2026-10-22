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
"""Summarizes an observation table without its full row set.

`summarize_table` produces a `TableSummary` with place counts, date and value
ranges, source and unit metadata, alternative facets, and evenly spaced sample
rows.
"""

from dataclasses import dataclass

from narratives_agent.analytics.provenance import AlternativeSource, Source
from narratives_agent.analytics.tables import ObservationRow, ObservationTable

__all__ = [
    "SAMPLE_ROW_CAP",
    "SUMMARY_PLACE_LIST_CAP",
    "TableSummary",
    "summarize_table",
]

# Summaries include up to this many evenly spaced sample rows.
SAMPLE_ROW_CAP: int = 5
# Summaries list up to this many places by name before counting the rest.
SUMMARY_PLACE_LIST_CAP: int = 25


@dataclass(frozen=True)
class TableSummary:
    """A compact profile of one observation table.

    Attributes:
        variable_dcid: The variable the table measures.
        variable_name: The variable's display name.
        observation_count: The number of rows in the table.
        places_with_data_count: How many places have at least one row.
        places_with_data: Up to `SUMMARY_PLACE_LIST_CAP` of those places,
            each as `name (dcid)`.
        places_without_data_count: How many requested places have no row;
            0 when the table records no requested places.
        places_without_data: Up to `SUMMARY_PLACE_LIST_CAP` of those places,
            each as `name (dcid)`.
        date_range: The earliest and latest dates, or None for an empty table.
        source: The citation entry of the table's source, when known.
        facet_id: The facet that served the rows, when known.
        unit: The unit of the values, when known.
        scaling_factor: The scaling factor of the values, when known.
        measurement_method: The facet's measurement method, when known.
        observation_period: The facet's observation period, when known.
        alternative_sources: The other facets the server could serve.
        value_range: The smallest and largest values, or None when empty.
        sample_rows: Up to `SAMPLE_ROW_CAP` rows spread evenly across the
            table in place-then-date order.
    """

    variable_dcid: str
    variable_name: str
    observation_count: int
    places_with_data_count: int
    places_with_data: tuple[str, ...]
    places_without_data_count: int
    places_without_data: tuple[str, ...]
    date_range: tuple[str, str] | None
    source: Source | None
    facet_id: str | None
    unit: str | None
    scaling_factor: float | None
    measurement_method: str | None
    observation_period: str | None
    alternative_sources: tuple[AlternativeSource, ...]
    value_range: tuple[float, float] | None
    sample_rows: tuple[ObservationRow, ...]


def _sample_indices(count: int, cap: int) -> list[int]:
    """Returns up to `cap` indices spread evenly over `count` positions.

    The first and last positions are always included when `count` exceeds
    `cap`, so a series sample shows its span rather than its first rows.
    """
    if count <= cap:
        return list(range(count))
    return sorted(
        {round(index * (count - 1) / (cap - 1)) for index in range(cap)}
    )


def _labels(table: ObservationTable, places: list[str]) -> tuple[str, ...]:
    """Formats places as `name (dcid)`, capped at the list limit."""
    return tuple(
        f"{table.place_names.get(place, place)} ({place})"
        for place in places[:SUMMARY_PLACE_LIST_CAP]
    )


def summarize_table(table: ObservationTable) -> TableSummary:
    """Builds the compact summary of `table`.

    Places are listed in request order, followed by any places with rows
    that were not requested, in sorted order. A place requested more than
    once is listed and counted once.

    Args:
        table: The table to summarize.

    Returns:
        The summary, with place lists capped at `SUMMARY_PLACE_LIST_CAP` and
        samples capped at `SAMPLE_ROW_CAP`.
    """
    with_data = set(table.places_with_data)
    requested = list(dict.fromkeys(table.requested_places))
    ordered_places = list(dict.fromkeys([*requested, *table.places_with_data]))
    places_with_data = [place for place in ordered_places if place in with_data]
    places_without_data = [
        place for place in requested if place not in with_data
    ]

    dates = [row.date for row in table.rows]
    values = [row.value for row in table.rows]

    return TableSummary(
        variable_dcid=table.variable_dcid,
        variable_name=table.variable_name,
        observation_count=len(table.rows),
        places_with_data_count=len(places_with_data),
        places_with_data=_labels(table, places_with_data),
        places_without_data_count=len(places_without_data),
        places_without_data=_labels(table, places_without_data),
        date_range=(min(dates), max(dates)) if dates else None,
        source=table.source,
        facet_id=table.facet_id,
        unit=table.unit,
        scaling_factor=table.scaling_factor,
        measurement_method=table.measurement_method,
        observation_period=table.observation_period,
        alternative_sources=table.alternative_sources,
        value_range=(min(values), max(values)) if values else None,
        sample_rows=tuple(
            table.rows[index]
            for index in _sample_indices(len(table.rows), SAMPLE_ROW_CAP)
        ),
    )
