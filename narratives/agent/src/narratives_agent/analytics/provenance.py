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
"""Provenance domain types shared across the analytics and MCP layers.

`Source`, `AlternativeSource`, and `Provenance` represent the citation and
facet metadata attached to an `ObservationTable` and propagated through
`ScriptResult` into `AnalysisDigest`. Keeping these value objects in their own
leaf module allows both `mcp/metadata.py` (which parses raw MCP metadata into
`Source` records) and `analytics/` (which aggregates provenance across tables
and script results) to depend on the same canonical types without introducing a
cycle between layers.
"""

from dataclasses import dataclass

__all__ = [
    "AlternativeSource",
    "Provenance",
    "Source",
    "merge_provenance",
]

# Merged provenance joins each input's methodology with this separator.
_METHODOLOGY_SEPARATOR = "; "


@dataclass(frozen=True)
class Source:
    """One data source cited by an observation table or script result.

    Attributes:
        name: Display name of the dataset or publishing organization.
        url: Provenance URL for the source.
        license: License identifier or name when reported by metadata.
        provider: Publishing organization name when distinct from a handle.
        dataset: Dataset name (`isPartOf`) when reported by metadata.
        date_range: Year coverage: one year, or start and end years joined by
            a spaced en dash.
    """

    name: str
    url: str
    license: str | None = None
    provider: str | None = None
    dataset: str | None = None
    date_range: str | None = None


@dataclass(frozen=True)
class AlternativeSource:
    """An alternate facet the MCP server reported alongside the chosen facet.

    Attributes:
        facet_id: Facet ID (`sourceMetadata.sourceId`) in the MCP response.
        provenance_url: Canonical source URL when reported.
        measurement_method: Measurement method identifier when reported.
        observation_period: ISO-8601 observation period (such as `"P1Y"`).
        unit: Unit name or symbol when reported.
        places_found_count: Number of requested places covered by the facet.
    """

    facet_id: str
    provenance_url: str | None = None
    measurement_method: str | None = None
    observation_period: str | None = None
    unit: str | None = None
    places_found_count: int | None = None


@dataclass(frozen=True)
class Provenance:
    """Data sources, facet IDs, and methodology for a table or script result.

    Attributes:
        sources: Ordered, deduplicated `Source` entries in contribution order.
        facet_ids: Ordered, deduplicated facet IDs in contribution order.
        methodology: Plain-English description of how the data was aligned or
            calculated, if applicable.
    """

    sources: tuple[Source, ...] = ()
    facet_ids: tuple[str, ...] = ()
    methodology: str | None = None


def merge_provenance(
    *items: Provenance, methodology: str | None = None
) -> Provenance:
    """Combines multiple `Provenance` records into a single record.

    Deduplicates `sources` and `facet_ids` in the order they first appear.
    Non-empty `methodology` strings from `items`, followed by the optional
    `methodology` argument, are deduplicated and joined with `"; "`.

    Args:
        *items: Input provenance records in contribution order.
        methodology: Optional description of the calculation that combined
            the inputs.

    Returns:
        The combined `Provenance`.
    """
    sources = tuple(
        dict.fromkeys(source for item in items for source in item.sources)
    )
    facet_ids = tuple(
        dict.fromkeys(facet_id for item in items for facet_id in item.facet_ids)
    )
    # Strip trailing periods from all but the final methodology clause before
    # joining with "; ", and treat clauses that differ only by a trailing
    # period as duplicates.
    text_by_clause: dict[str, str] = {}
    for text in (*(item.methodology for item in items), methodology):
        if text:
            text_by_clause.setdefault(text.removesuffix("."), text)
    clauses = list(text_by_clause)
    joined = _METHODOLOGY_SEPARATOR.join(
        [*clauses[:-1], *list(text_by_clause.values())[-1:]]
    )
    return Provenance(
        sources=sources,
        facet_ids=facet_ids,
        methodology=joined or None,
    )
