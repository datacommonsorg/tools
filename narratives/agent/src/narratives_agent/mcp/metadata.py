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
"""Reads MCP variable metadata and inline observation source metadata.

Builds typed `Source`, `FacetEnrichment`, `VariableEnrichment`, and
`VariableMetadataEnrichment` values from `get_variable_metadata` and
observation `sourceMetadata` blocks.
"""

import math
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from urllib.parse import urlparse

from narratives_agent.analytics.provenance import Source
from narratives_agent.json_value import JsonObject, JsonValue


def get_first_present_value(
    mapping: Mapping[str, JsonValue], *keys: str
) -> str:
    """Returns the first non-empty string value among `keys`, or "".

    The MCP server returns camelCase, while earlier revisions of this code and
    some fixtures use snake_case, so callers pass both spellings.
    """
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _get_provenance_url(properties: Mapping[str, JsonValue]) -> str:
    """Returns a provenance node's `url`, else its first `descriptionUrl`.

    MCP 1.3.x sends `descriptionUrl` as a string or a list of strings.
    """
    url = get_first_present_value(properties, "url", "descriptionUrl")
    if url:
        return url
    description_urls = properties.get("descriptionUrl")
    if isinstance(description_urls, list):
        for item in description_urls:
            if isinstance(item, str) and item.strip():
                return item.strip()
    return ""


def _looks_like_a_name(value: str) -> bool:
    """True when a property value is a publisher name rather than a locator.

    `source` holds `"World Bank"` on one import and `"dc/base/..."` or a bare
    URL on the next. Locators are rejected so the caller omits `provider`
    rather than printing an internal handle.
    """
    if not value:
        return False
    if "://" in value or value.startswith("dc/"):
        return False
    # A dotted single token is `domain` wearing another hat; a name either has
    # a space in it or has no dot.
    return " " in value or "." not in value


def _get_year_of(date: str) -> str:
    """Returns the four-digit year at the head of `date`, or ""."""
    # Require four leading digits so empty or two-digit dates (like "90") are
    # rejected.
    head = date[:4]
    return head if len(head) == 4 and head.isdigit() else ""


def _get_date_range(facet: Mapping[str, JsonValue]) -> str:
    """Renders a facet's coverage as a year range, one year, or "".

    A range is the start and end years joined by a spaced en dash.

    Reads the facet's own `dateRange`, the shape MCP 1.3.0 returns. Inferring
    from the rows that happened to be fetched would describe this query rather
    than the dataset.
    """
    date_range = facet.get("dateRange")
    if not isinstance(date_range, dict):
        return ""
    start = _get_year_of(get_first_present_value(date_range, "start"))
    end = _get_year_of(get_first_present_value(date_range, "end"))
    if start and end:
        if start == end:
            return start
        return f"{start} \u2013 {end}"
    return start or end


def _parse_scaling_factor(value: JsonValue) -> float | None:
    """Parses `scalingFactor` as a finite float, rejecting booleans."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value)
        except ValueError:
            return None
    else:
        return None
    return number if math.isfinite(number) else None


def _provenance_entry_from_properties(
    properties: Mapping[str, JsonValue], facet: Mapping[str, JsonValue]
) -> Source | None:
    """Builds a typed `Source` from a provenance node's `properties` and facet.

    Prefers `isPartOf` over `source` for the display name because `isPartOf`
    names the dataset whereas `source` names the publishing organization.
    Returns `None` when the provenance node carries no URL.
    """
    url = _get_provenance_url(properties)
    if not url:
        return None

    dataset = get_first_present_value(properties, "isPartOf")
    provider = get_first_present_value(properties, "source")
    name = (
        dataset
        or provider
        or get_first_present_value(properties, "domain")
        or url
    )
    license_type = get_first_present_value(properties, "licenseType")
    date_range = _get_date_range(facet)
    return Source(
        name=name,
        url=url,
        license=license_type or None,
        provider=provider if _looks_like_a_name(provider) else None,
        dataset=dataset or None,
        date_range=date_range or None,
    )


def _facet_entries(
    result_data: Mapping[str, JsonValue],
) -> Iterator[tuple[str, str, JsonObject, Source | None]]:
    """Yields `(variable_dcid, facet_id, facet, provenance)` from metadata.

    Walks `result_data["variables"]` and yields every facet that carries a
    non-empty `id`. `provenance` is the `Source` built from the matching entry
    in `result_data["provenances"]`, or `None` when the facet's `provenanceId`
    is absent or carries no URL.
    """
    variables = result_data.get("variables")
    if not isinstance(variables, dict):
        return
    raw_provenances = result_data.get("provenances")
    provenances: JsonObject = (
        raw_provenances if isinstance(raw_provenances, dict) else {}
    )

    for variable_dcid, variable in variables.items():
        if not isinstance(variable, dict):
            continue
        facets = variable.get("facets")
        if not isinstance(facets, list):
            continue
        for facet in facets:
            if not isinstance(facet, dict):
                continue
            raw_id = facet.get("id")
            if raw_id is None:
                continue
            facet_id = str(raw_id)
            if not facet_id:
                continue

            provenance_source: Source | None = None
            provenance_id = facet.get("provenanceId")
            provenance = (
                provenances.get(provenance_id)
                if isinstance(provenance_id, str)
                else None
            )
            if isinstance(provenance, dict):
                properties = provenance.get("properties")
                if isinstance(properties, dict):
                    provenance_source = _provenance_entry_from_properties(
                        properties, facet
                    )
            yield variable_dcid, facet_id, facet, provenance_source


def get_source_from_observation_metadata(
    metadata: Mapping[str, JsonValue],
) -> Source | None:
    """Builds a fallback `Source` from an observation `sourceMetadata` block.

    Used when no `get_variable_metadata` call described the served facet. The
    display name is read from `importName` or `sourceName`, falling back to
    the URL's hostname with any leading `www.` stripped, and then to
    `"Data Source"`. Returns `None` when `metadata` carries no `provenanceUrl`.
    """
    url = get_first_present_value(metadata, "provenanceUrl", "provenance_url")
    if not url:
        return None
    name = get_first_present_value(
        metadata,
        "importName",
        "import_name",
        "sourceName",
        "source_name",
    )
    if not name:
        name = urlparse(url).netloc.removeprefix("www.")
    return Source(name=name or "Data Source", url=url)


@dataclass(frozen=True)
class FacetEnrichment:
    """Facet-level metadata extracted from `get_variable_metadata`.

    Read from `facets[].properties`. `scalingFactor` is read when present; the
    probed MCP 1.3.x responses did not include it.
    """

    provenance: Source | None = None
    unit: str | None = None
    scaling_factor: float | None = None
    measurement_method: str | None = None
    observation_period: str | None = None


@dataclass(frozen=True)
class VariableEnrichment:
    """Variable-level metadata extracted from `get_variable_metadata`.

    `unit` is read from the variable or its `properties` when present; the
    probed MCP 1.3.x responses did not include it.
    """

    variable_name: str | None = None
    unit: str | None = None


@dataclass(frozen=True)
class VariableMetadataEnrichment:
    """Indexed facet and variable metadata across `get_variable_metadata` calls.

    Facet entries are keyed by `(variable_dcid, facet_id)` because each
    variable's facet entry carries that variable's `dateRange`. When a facet
    is looked up for a variable whose metadata was not fetched, `.facet()`
    falls back to the first-seen entry with the same `facet_id` and strips
    `date_range` from its `Source` so another variable's coverage years never
    leak across tables. The other facet fields are shared, because Data
    Commons derives a facet id from its import, measurement method,
    observation period, scaling factor, and unit.

    `merge()` keeps the first facet entry whole and fills missing variable
    fields from later payloads.
    """

    facets: Mapping[tuple[str, str], FacetEnrichment] = field(
        default_factory=dict
    )
    variables: Mapping[str, VariableEnrichment] = field(default_factory=dict)

    def facet(
        self, variable_dcid: str, facet_id: str
    ) -> FacetEnrichment | None:
        """Returns the enrichment for `(variable_dcid, facet_id)`, or None."""
        direct = self.facets.get((variable_dcid, facet_id))
        if direct is not None:
            return direct
        for (_, candidate_id), facet in self.facets.items():
            if candidate_id != facet_id:
                continue
            if facet.provenance is None or facet.provenance.date_range is None:
                return facet
            return replace(
                facet,
                provenance=replace(facet.provenance, date_range=None),
            )
        return None

    def merge(
        self, other: VariableMetadataEnrichment
    ) -> VariableMetadataEnrichment:
        """Combines two metadata indexes, keeping the first description seen.

        Entries of `self` precede entries of `other`, so the cross-variable
        fallback in `facet()` also finds the first-seen entry.
        """
        facets = dict(self.facets)
        for key, facet in other.facets.items():
            facets.setdefault(key, facet)
        variables = dict(self.variables)
        for variable_dcid, other_entry in other.variables.items():
            entry = variables.get(variable_dcid)
            if entry is None:
                variables[variable_dcid] = other_entry
            else:
                variables[variable_dcid] = VariableEnrichment(
                    variable_name=entry.variable_name
                    or other_entry.variable_name,
                    unit=entry.unit or other_entry.unit,
                )
        return VariableMetadataEnrichment(facets=facets, variables=variables)


def _single_payload_enrichment(
    payload: Mapping[str, JsonValue],
) -> VariableMetadataEnrichment:
    """Extracts a `VariableMetadataEnrichment` from one metadata payload."""
    facets: dict[tuple[str, str], FacetEnrichment] = {}
    variables: dict[str, VariableEnrichment] = {}

    raw_variables = payload.get("variables")
    if isinstance(raw_variables, dict):
        for variable_dcid, variable in raw_variables.items():
            if not isinstance(variable, dict):
                continue
            var_props = variable.get("properties")
            var_props_map: Mapping[str, JsonValue] = (
                var_props if isinstance(var_props, dict) else {}
            )
            variable_name = get_first_present_value(variable, "name") or None
            variable_unit = (
                get_first_present_value(variable, "unit")
                or get_first_present_value(var_props_map, "unit")
                or None
            )
            if variable_name is not None or variable_unit is not None:
                variables[variable_dcid] = VariableEnrichment(
                    variable_name=variable_name,
                    unit=variable_unit,
                )

    for variable_dcid, facet_id, facet, provenance in _facet_entries(payload):
        key = (variable_dcid, facet_id)
        if key in facets:
            continue
        facet_props = facet.get("properties")
        props: Mapping[str, JsonValue] = (
            facet_props if isinstance(facet_props, dict) else {}
        )
        facets[key] = FacetEnrichment(
            provenance=provenance,
            unit=get_first_present_value(props, "unit") or None,
            scaling_factor=_parse_scaling_factor(props.get("scalingFactor")),
            measurement_method=(
                get_first_present_value(props, "measurementMethod") or None
            ),
            observation_period=(
                get_first_present_value(props, "observationPeriod") or None
            ),
        )

    return VariableMetadataEnrichment(facets=facets, variables=variables)


def get_variable_metadata_enrichment(
    payloads: Sequence[Mapping[str, JsonValue]],
) -> VariableMetadataEnrichment:
    """Indexes facet and variable metadata from decoded metadata payloads.

    Args:
        payloads: Decoded `get_variable_metadata` payload dicts in call order.

    Returns:
        A `VariableMetadataEnrichment` combining all payloads, keeping the
        first description of each facet and variable field.
    """
    combined = VariableMetadataEnrichment()
    for payload in payloads:
        combined = combined.merge(_single_payload_enrichment(payload))
    return combined
