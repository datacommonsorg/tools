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
"""Tests for typed source and variable metadata readers in `mcp.metadata`."""

import pytest

from narratives_agent.analytics.provenance import Source
from narratives_agent.json_value import JsonObject, JsonValue
from narratives_agent.mcp.metadata import (
    FacetEnrichment,
    VariableEnrichment,
    get_source_from_observation_metadata,
    get_variable_metadata_enrichment,
)

_WDI_URL = "https://datatopics.worldbank.org/world-development-indicators"


def _metadata_payload(
    provenance_properties: JsonObject, **facet_fields: JsonValue
) -> JsonObject:
    """Builds a minimal `get_variable_metadata` payload for one facet."""
    facet: JsonObject = {
        "id": "facet1",
        "provenanceId": "prov1",
        **facet_fields,
    }
    return {
        "variables": {
            "Count_Person": {
                "name": "Total Population",
                "facets": [facet],
            }
        },
        "provenances": {"prov1": {"properties": provenance_properties}},
    }


def test_get_source_from_observation_metadata_extracts_named_or_domain() -> (
    None
):
    # Test: Inline observation `sourceMetadata` parsing into `Source`.
    # Situation: Observation metadata blocks carry an explicit `importName`,
    #   a URL with a `www.` host and no name, a URL whose host is only
    #   `www.`, and no URL at all.
    # Expectation: `get_source_from_observation_metadata` returns a `Source`
    #   with the explicit name, a `Source` with the bare hostname, a `Source`
    #   named `"Data Source"`, and `None` respectively.
    named = get_source_from_observation_metadata(
        {"provenanceUrl": "https://www.bls.gov/", "importName": "BLS_LAUS"}
    )
    assert named == Source(name="BLS_LAUS", url="https://www.bls.gov/")

    domain_fallback = get_source_from_observation_metadata(
        {"provenanceUrl": "https://www.example.org/x"}
    )
    assert domain_fallback == Source(
        name="example.org", url="https://www.example.org/x"
    )

    bare_www = get_source_from_observation_metadata(
        {"provenanceUrl": "https://www./"}
    )
    assert bare_www == Source(name="Data Source", url="https://www./")

    assert get_source_from_observation_metadata({"sourceId": "f1"}) is None


_UNSAFE_PROVENANCE_URLS = [
    pytest.param("javascript:alert(1)", id="javascript"),
    pytest.param("javascript://evil.example/%0Aalert(1)", id="javascript-host"),
    pytest.param("data:text/html,<script>alert(1)</script>", id="data"),
    pytest.param("vbscript:msgbox(1)", id="vbscript"),
    pytest.param("//evil.example/path", id="protocol-relative"),
    pytest.param("/datasets/wdi", id="relative-path"),
    pytest.param("https://trusted.example\\@evil.example", id="backslash"),
    pytest.param("https://trusted.example/\x00path", id="control-character"),
    pytest.param("urn:datacommons:source", id="hostless"),
    pytest.param("https://", id="empty-host"),
    pytest.param("https://@", id="empty-host-with-userinfo"),
    pytest.param("https://:80", id="empty-host-with-port"),
]


@pytest.mark.parametrize("unsafe_url", _UNSAFE_PROVENANCE_URLS)
def test_observation_metadata_with_unsafe_url_has_no_source(
    unsafe_url: str,
) -> None:
    # Test: Scheme and form check on an inline `provenanceUrl`.
    # Situation: `sourceMetadata` names an import and carries a `provenanceUrl`
    #   that is not an absolute http(s) URL with a host, or that holds a
    #   backslash or an ASCII control character.
    # Expectation: `get_source_from_observation_metadata` returns `None`.
    metadata: JsonObject = {
        "provenanceUrl": unsafe_url,
        "importName": "BLS_LAUS",
    }
    assert get_source_from_observation_metadata(metadata) is None


@pytest.mark.parametrize("unsafe_url", _UNSAFE_PROVENANCE_URLS)
def test_provenance_with_unsafe_url_has_no_source(unsafe_url: str) -> None:
    # Test: Scheme and form check on a provenance node's `url`.
    # Situation: The provenance node's only URL is unsafe.
    # Expectation: The facet carries no provenance `Source`.
    payload = _metadata_payload({"url": unsafe_url, "isPartOf": "WDI"})
    facet = get_variable_metadata_enrichment([payload]).facet(
        "Count_Person", "facet1"
    )
    assert facet is not None and facet.provenance is None


def test_uppercase_https_scheme_is_accepted() -> None:
    # Test: Case-insensitive scheme check.
    # Situation: Inline metadata and a provenance node carry an `HTTPS://` URL.
    # Expectation: The inline `Source` and the facet's provenance `Source`
    #   both keep the URL unchanged.
    url = "HTTPS://WWW.BLS.GOV/lau"
    inline = get_source_from_observation_metadata({"provenanceUrl": url})
    assert inline is not None and inline.url == url
    payload = _metadata_payload({"url": url, "isPartOf": "LAUS"})
    facet = get_variable_metadata_enrichment([payload]).facet(
        "Count_Person", "facet1"
    )
    assert facet is not None and facet.provenance is not None
    assert facet.provenance.url == url


def test_unsafe_url_falls_through_to_safe_description_url() -> None:
    # Test: Fallthrough from an unsafe `url` to `descriptionUrl`.
    # Situation: The provenance node's `url` is a `javascript:` URL, and its
    #   `descriptionUrl` list holds a `data:` URL and then an https URL.
    # Expectation: The facet's provenance `Source` uses the https URL from
    #   `descriptionUrl`.
    payload = _metadata_payload(
        {
            "url": "javascript:alert(1)",
            "descriptionUrl": [
                "data:text/html,x",
                "https://data.worldbank.org/indicator",
            ],
            "isPartOf": "WDI",
        }
    )
    facet = get_variable_metadata_enrichment([payload]).facet(
        "Count_Person", "facet1"
    )
    assert facet is not None and facet.provenance is not None
    assert facet.provenance.url == "https://data.worldbank.org/indicator"


def test_facet_enrichment_extracts_provenance_unit_scaling_and_period() -> None:
    # Test: Facet and variable enrichment from `get_variable_metadata`.
    # Situation: A `get_variable_metadata` payload describes `Amount_GDP` with
    #   variable-level `name` and `unit`, and `facet1` with `unit`,
    #   `scalingFactor`, `measurementMethod`, `observationPeriod`, `dateRange`,
    #   and provenance properties including `isPartOf`, `source`, `url`, and
    #   `licenseType`.
    # Expectation: `get_variable_metadata_enrichment` populates both the
    #   `FacetEnrichment` (with a full `Source`) and the `VariableEnrichment`.
    payload: JsonObject = {
        "variables": {
            "Amount_GDP": {
                "name": "Gross Domestic Product",
                "properties": {"unit": "USDollar"},
                "facets": [
                    {
                        "id": "facet1",
                        "provenanceId": "prov1",
                        "dateRange": {"start": "1960", "end": "2023-12"},
                        "properties": {
                            "unit": "ConstantUSDollar",
                            "scalingFactor": "1000000",
                            "measurementMethod": "WorldBankEstimate",
                            "observationPeriod": "P1Y",
                        },
                    }
                ],
            }
        },
        "provenances": {
            "prov1": {
                "properties": {
                    "url": _WDI_URL,
                    "isPartOf": "World Development Indicators",
                    "source": "World Bank",
                    "licenseType": "CC-BY-4.0",
                }
            }
        },
    }
    enrichment = get_variable_metadata_enrichment([payload])
    assert enrichment.variables["Amount_GDP"] == VariableEnrichment(
        variable_name="Gross Domestic Product",
        unit="USDollar",
    )
    assert enrichment.facet("Amount_GDP", "facet1") == FacetEnrichment(
        provenance=Source(
            name="World Development Indicators",
            url=_WDI_URL,
            license="CC-BY-4.0",
            provider="World Bank",
            dataset="World Development Indicators",
            date_range="1960 \u2013 2023",
        ),
        unit="ConstantUSDollar",
        scaling_factor=1_000_000.0,
        measurement_method="WorldBankEstimate",
        observation_period="P1Y",
    )


def test_description_url_list_and_single_year_date_range_are_supported() -> (
    None
):
    # Test: `descriptionUrl` list handling and single-year `dateRange`.
    # Situation: A provenance node omits `url` and provides `descriptionUrl`
    #   as a list of strings (as MCP 1.3.x does), and the facet's `dateRange`
    #   starts and ends in the same year.
    # Expectation: The first non-empty URL in `descriptionUrl` is used and
    #   `date_range` is rendered as a single year.
    payload = _metadata_payload(
        {
            "descriptionUrl": ["https://data.worldbank.org/indicator"],
            "isPartOf": "WDI",
        },
        dateRange={"start": "2023", "end": "2023"},
    )
    enrichment = get_variable_metadata_enrichment([payload])
    facet = enrichment.facet("Count_Person", "facet1")
    assert facet is not None
    assert facet.provenance == Source(
        name="WDI",
        url="https://data.worldbank.org/indicator",
        dataset="WDI",
        date_range="2023",
    )


@pytest.mark.parametrize(
    "handle",
    ["dc/base/WorldBank", "https://worldbank.org", "worldbank.org"],
)
def test_machine_handle_in_source_is_rejected_as_provider(handle: str) -> None:
    # Test: Rejection of internal handles and domains in `properties.source`.
    # Situation: `properties.source` holds a DCID, a URL, or a dotted domain.
    # Expectation: `Source.provider` is `None`.
    payload = _metadata_payload(
        {"url": _WDI_URL, "isPartOf": "WDI", "source": handle}
    )
    enrichment = get_variable_metadata_enrichment([payload])
    facet = enrichment.facet("Count_Person", "facet1")
    assert facet is not None and facet.provenance is not None
    assert facet.provenance.provider is None


@pytest.mark.parametrize(
    "raw_scaling",
    [True, False, "not-a-number", "inf", "nan", ["100"]],
)
def test_invalid_scaling_factors_are_ignored(raw_scaling: JsonValue) -> None:
    # Test: Rejection of malformed `scalingFactor` values.
    # Situation: `facet.properties.scalingFactor` is a boolean, a non-numeric
    #   string, an infinite or NaN string, or a list.
    # Expectation: `FacetEnrichment.scaling_factor` is `None`.
    payload = _metadata_payload(
        {"url": _WDI_URL, "isPartOf": "WDI"},
        properties={"scalingFactor": raw_scaling},
    )
    enrichment = get_variable_metadata_enrichment([payload])
    facet = enrichment.facet("Count_Person", "facet1")
    assert facet is not None
    assert facet.scaling_factor is None


def test_cross_variable_facet_lookup_strips_other_variable_date_range() -> None:
    # Test: Cross-variable fallback in `VariableMetadataEnrichment.facet`.
    # Situation: Metadata was fetched only for `Count_Person` (which has a
    #   1960-2023 `dateRange` on `facet1`), and `.facet()` is queried for
    #   `Count_Household` with `facet1` and with an unknown facet ID.
    # Expectation: The fallback for `Count_Household` returns `facet1`'s
    #   enrichment with `provenance.date_range` stripped to `None`, while the
    #   direct lookup for `Count_Person` retains both years, and the
    #   unknown facet returns `None`.
    payload = _metadata_payload(
        {"url": _WDI_URL, "isPartOf": "WDI"},
        dateRange={"start": "1960", "end": "2023"},
        properties={"unit": "Person"},
    )
    enrichment = get_variable_metadata_enrichment([payload])
    direct = enrichment.facet("Count_Person", "facet1")
    fallback = enrichment.facet("Count_Household", "facet1")
    assert direct is not None and direct.provenance is not None
    assert direct.provenance.date_range == "1960 \u2013 2023"
    assert fallback is not None and fallback.provenance is not None
    assert fallback.provenance.date_range is None
    assert fallback.unit == "Person"
    assert enrichment.facet("Count_Household", "unknown") is None


def test_merge_keeps_first_seen_facet_and_variable_descriptions() -> None:
    # Test: Merging multiple `VariableMetadataEnrichment` instances.
    # Situation: The first payload names `Count_Person` without a unit and
    #   describes `facet1`; the second payload gives `Count_Person` a different
    #   name plus a unit and re-describes `facet1` alongside a new `facet2`.
    # Expectation: The merged enrichment keeps the first `variable_name` and
    #   first `facet1` entry, fills the missing variable `unit` from the second
    #   payload, and adds `facet2`.
    first = get_variable_metadata_enrichment(
        [
            {
                "variables": {
                    "Count_Person": {
                        "name": "First Name",
                        "facets": [
                            {
                                "id": "facet1",
                                "provenanceId": "p1",
                                "properties": {"unit": "FirstUnit"},
                            }
                        ],
                    }
                },
                "provenances": {"p1": {"properties": {"url": _WDI_URL}}},
            }
        ]
    )
    second = get_variable_metadata_enrichment(
        [
            {
                "variables": {
                    "Count_Person": {
                        "name": "Second Name",
                        "properties": {"unit": "Person"},
                        "facets": [
                            {
                                "id": "facet1",
                                "provenanceId": "p1",
                                "properties": {"unit": "SecondUnit"},
                            },
                            {
                                "id": "facet2",
                                "provenanceId": "p1",
                                "properties": {"unit": "Household"},
                            },
                        ],
                    }
                },
                "provenances": {"p1": {"properties": {"url": _WDI_URL}}},
            }
        ]
    )
    merged = first.merge(second)
    assert merged.variables["Count_Person"] == VariableEnrichment(
        variable_name="First Name",
        unit="Person",
    )
    facet1 = merged.facet("Count_Person", "facet1")
    facet2 = merged.facet("Count_Person", "facet2")
    assert facet1 is not None and facet1.unit == "FirstUnit"
    assert facet2 is not None and facet2.unit == "Household"


def test_fallback_after_merge_returns_first_seen_variable_entry() -> None:
    # Test: Cross-variable fallback order after `merge`.
    # Situation: The first payload describes `facet1` for `Count_Person` and
    #   the second describes `facet1` for `Count_Household` with another
    #   unit; `.facet()` is queried for `Count_Female`, which neither fetched.
    # Expectation: The fallback returns the first payload's entry.
    first = get_variable_metadata_enrichment(
        [_metadata_payload({"url": _WDI_URL}, properties={"unit": "Person"})]
    )
    second_payload = _metadata_payload(
        {"url": _WDI_URL}, properties={"unit": "Household"}
    )
    second_variables = second_payload["variables"]
    assert isinstance(second_variables, dict)
    second_payload["variables"] = {
        "Count_Household": second_variables["Count_Person"]
    }
    second = get_variable_metadata_enrichment([second_payload])
    fallback = first.merge(second).facet("Count_Female", "facet1")
    assert fallback is not None and fallback.unit == "Person"


def test_merge_keeps_variables_in_first_seen_order() -> None:
    # Test: Key order of `variables` after successive merges.
    # Situation: Three payloads each name a different variable, merged in
    #   call order.
    # Expectation: `variables` lists the variables in call order.
    dcids = ["Count_Person", "Count_Household", "Count_Female"]
    combined = get_variable_metadata_enrichment(
        [{"variables": {dcid: {"name": dcid}}} for dcid in dcids]
    )
    assert list(combined.variables) == dcids


def test_numeric_scaling_factor_is_read_as_float() -> None:
    # Test: `scalingFactor` sent as a JSON number.
    # Situation: `facet.properties.scalingFactor` is the integer 100.
    # Expectation: `FacetEnrichment.scaling_factor` is 100.0.
    payload = _metadata_payload(
        {"url": _WDI_URL}, properties={"scalingFactor": 100}
    )
    facet = get_variable_metadata_enrichment([payload]).facet(
        "Count_Person", "facet1"
    )
    assert facet is not None and facet.scaling_factor == 100.0


def test_facet_without_provenance_id_has_no_provenance() -> None:
    # Test: A facet that carries no `provenanceId`.
    # Situation: The facet omits `provenanceId`, and `provenances` holds an
    #   entry keyed `"None"` with a URL.
    # Expectation: No provenance is attached to the facet.
    payload: JsonObject = {
        "variables": {
            "Count_Person": {"facets": [{"id": "facet1"}]},
        },
        "provenances": {"None": {"properties": {"url": _WDI_URL}}},
    }
    facet = get_variable_metadata_enrichment([payload]).facet(
        "Count_Person", "facet1"
    )
    assert facet is not None and facet.provenance is None
