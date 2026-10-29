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
"""Tests for observation table parsing and merging in `mcp.observations`."""

import logging
import re
from dataclasses import replace

import pytest
from pydantic import ValidationError

from narratives_agent.analytics.provenance import (
    AlternativeSource,
    Source,
)
from narratives_agent.analytics.tables import (
    MAX_NAME_CHARS,
    ObservationRow,
)
from narratives_agent.json_value import JsonObject, JsonValue
from narratives_agent.mcp.metadata import (
    VariableMetadataEnrichment,
    get_variable_metadata_enrichment,
)
from narratives_agent.mcp.observations import (
    ObservationPayloadError,
    ObservationPayloadOutline,
    apply_variable_metadata,
    merge_observation_payloads,
    parse_observation_table,
    read_payload_outline,
)

_WDI_URL = "https://datatopics.worldbank.org/world-development-indicators/"
_WIKIDATA_URL = "https://www.wikidata.org/wiki/Wikidata:Main_Page"
# The MCP server includes a `variable` block in every observation response.
_VARIABLE: JsonObject = {"dcid": "Count_Person"}


def _data(rows: list[JsonValue]) -> JsonObject:
    """A columnar `data` block keyed by `observationAbout`."""
    return {"columns": ["observationAbout", "date", "value"], "rows": rows}


def _live_series_payload() -> JsonObject:
    """The shape of a live single-place `get_observations` response."""
    return {
        "alternativeSources": [
            {
                "sourceMetadata": {
                    "measurementMethod": "WikidataPopulation",
                    "provenanceUrl": _WIKIDATA_URL,
                    "sourceId": "12850099660527362240",
                }
            },
            {"sourceMetadata": {"provenanceUrl": "https://insee.example"}},
        ],
        "data": _data(
            [
                ["country/FRA", "2021", 67764304],
                ["country/FRA", "2022", 67971311],
                ["country/FRA", "2023", 68287487],
            ]
        ),
        "entityMetadata": {
            "columns": ["dcid", "name", "typeOf"],
            "rows": [["country/FRA", "France", ["Country"]]],
        },
        "sourceMetadata": {
            "observationPeriod": "P1Y",
            "provenanceUrl": _WDI_URL,
            "sourceId": "18369491376878146239",
        },
        "variable": {"dcid": "Count_Person", "name": "Total population"},
    }


def _live_metadata_payload() -> JsonObject:
    """The shape of a live `get_variable_metadata` response."""
    return {
        "provenances": {
            "dc/base/WorldDevelopmentIndicators": {
                "id": "dc/base/WorldDevelopmentIndicators",
                "properties": {
                    "isPartOf": "World Development Indicators",
                    "licenseType": "Creative Commons Attribution License",
                    "source": "World Bank",
                    "url": _WDI_URL,
                },
            }
        },
        "status": "SUCCESS",
        "variables": {
            "Count_Person": {
                "facets": [
                    {
                        "dateRange": {"end": "2025", "start": "1960"},
                        "id": "18369491376878146239",
                        "obsCount": 66,
                        "properties": {"observationPeriod": "P1Y"},
                        "provenanceId": "dc/base/WorldDevelopmentIndicators",
                    }
                ],
                "id": "Count_Person",
                "name": "Total population",
            }
        },
    }


def _cohort_payload() -> JsonObject:
    """A child-place payload with mixed vintages and sub-year dates."""
    return {
        "alternativeSources": [
            {
                "placesFoundCount": 3,
                "sourceMetadata": {
                    "provenanceUrl": _WDI_URL,
                    "sourceId": "18369491376878146239",
                    "observationPeriod": "P1Y",
                },
            }
        ],
        "data": _data(
            [
                ["country/ABW", "2019", 109241],
                ["country/ABW", "2021", 107457],
                ["country/AFG", "2017", 35000000],
                ["country/AFG", "2023-07-31", 41000000],
                ["country/ALB", "2010", 2900000],
                ["country/ALB", "2017", 2870000],
            ]
        ),
        "entityMetadata": {
            "columns": ["dcid", "name"],
            "rows": [
                ["country/ABW", "Aruba"],
                ["country/AFG", "Afghanistan"],
                ["country/ALB", "Albania"],
                ["country/AND", "Andorra"],
            ],
        },
        "sourceMetadata": {
            "measurementMethod": "WikidataPopulation",
            "provenanceUrl": _WIKIDATA_URL,
            "sourceId": "12850099660527362240",
        },
        "variable": {"dcid": "Count_Person", "name": "Total population"},
    }


def test_live_columnar_payload_parses_rows_names_and_metadata() -> None:
    # Test: Parsing a live single-place `get_observations` payload.
    # Situation: The payload holds a columnar `data` table keyed by
    #   `observationAbout`, a columnar `entityMetadata` table
    #   with a `typeOf` column, a `sourceMetadata` block, a `variable`
    #   block, and `alternativeSources` wrappers, one of which has no id.
    # Expectation: Three rows sorted by date carry the display name from
    #   `entityMetadata` and the served facet id; the variable name, the
    #   observation period, the inline `Source`, and the one identifiable
    #   `AlternativeSource` are populated.
    table = parse_observation_table(
        _live_series_payload(),
        variable_dcid="Count_Person",
        requested_places=["country/FRA"],
    )
    assert table.rows == (
        ObservationRow(
            "country/FRA", "France", "2021", 67764304.0, "18369491376878146239"
        ),
        ObservationRow(
            "country/FRA", "France", "2022", 67971311.0, "18369491376878146239"
        ),
        ObservationRow(
            "country/FRA", "France", "2023", 68287487.0, "18369491376878146239"
        ),
    )
    assert table.variable_name == "Total population"
    assert table.facet_id == "18369491376878146239"
    assert table.observation_period == "P1Y"
    assert table.measurement_method is None
    assert table.source == Source(
        name="datatopics.worldbank.org",
        url=_WDI_URL,
    )
    assert table.alternative_sources == (
        AlternativeSource(
            facet_id="12850099660527362240",
            provenance_url=_WIKIDATA_URL,
            measurement_method="WikidataPopulation",
        ),
    )
    assert table.provenance.sources == (table.source,)
    assert table.provenance.facet_ids == ("18369491376878146239",)
    assert table.place_names == {"country/FRA": "France"}


def test_metadata_enrichment_supplies_source_and_facet_fields() -> None:
    # Test: Enrichment from a `get_variable_metadata` payload.
    # Situation: The metadata payload describes the served facet with a
    #   provenance node, a license, a date range, and an observation
    #   period, and the observation payload's own `sourceMetadata` lacks a
    #   dataset name.
    # Expectation: The table's source is the named `Source` entry from the
    #   metadata and `table.provenance.sources` matches `(table.source,)`.
    enrichment = get_variable_metadata_enrichment([_live_metadata_payload()])
    table = parse_observation_table(
        _live_series_payload(),
        variable_dcid="Count_Person",
        requested_places=["country/FRA"],
        enrichment=enrichment,
    )
    assert table.source == Source(
        name="World Development Indicators",
        url=_WDI_URL,
        license="Creative Commons Attribution License",
        dataset="World Development Indicators",
        provider="World Bank",
        date_range="1960 \u2013 2025",
    )
    assert table.observation_period == "P1Y"
    assert table.provenance.sources == (table.source,)


def _gdp_enrichment() -> VariableMetadataEnrichment:
    """Metadata for facet `f1` of `Amount_GDP` that differs from the payload."""
    return get_variable_metadata_enrichment(
        [
            {
                "provenances": {
                    "dc/base/WorldDevelopmentIndicators": {
                        "properties": {
                            "isPartOf": "World Development Indicators",
                            "url": _WDI_URL,
                        }
                    }
                },
                "variables": {
                    "Amount_GDP": {
                        "name": "Gross domestic product",
                        "facets": [
                            {
                                "id": "f1",
                                "provenanceId": (
                                    "dc/base/WorldDevelopmentIndicators"
                                ),
                                "dateRange": {"start": "1960", "end": "2023"},
                                "properties": {
                                    "unit": "ConstantUSDollar",
                                    "scalingFactor": "1000000",
                                    "measurementMethod": "WorldBankEstimate",
                                },
                            }
                        ],
                    }
                },
            }
        ]
    )


def _gdp_payload() -> JsonObject:
    """An `Amount_GDP` payload from `f1` whose inline fields differ."""
    return {
        "data": _data([["country/FRA", "2023", 3.0]]),
        "sourceMetadata": {
            "sourceId": "f1",
            "provenanceUrl": _WDI_URL,
            "unit": "LocalCurrency",
            "measurementMethod": "Inline",
        },
        "variable": {"dcid": "Amount_GDP", "name": "GDP (inline)"},
    }


def test_facet_enrichment_takes_precedence_over_inline_metadata() -> None:
    # Test: Precedence between metadata enrichment and inline fields.
    # Situation: The metadata payload declares a unit, a scaling factor, and
    #   a measurement method under the served facet's `properties`, a date
    #   range on the facet, and a variable-level name; the observation
    #   payload's `sourceMetadata` declares a different unit and measurement
    #   method and its `variable` block a different name.
    # Expectation: The facet enrichment wins for unit, scaling factor, and
    #   measurement method, the variable-level entry wins for the variable
    #   name, and the source is the `Source` built from the provenance node
    #   and the date range.
    table = parse_observation_table(
        _gdp_payload(),
        variable_dcid="Amount_GDP",
        enrichment=_gdp_enrichment(),
    )
    assert table.unit == "ConstantUSDollar"
    assert table.scaling_factor == 1_000_000.0
    assert table.measurement_method == "WorldBankEstimate"
    assert table.variable_name == "Gross domestic product"
    assert table.source == Source(
        name="World Development Indicators",
        url=_WDI_URL,
        dataset="World Development Indicators",
        date_range="1960 \u2013 2023",
    )


def test_applying_metadata_afterwards_matches_parsing_with_it() -> None:
    # Test: `apply_variable_metadata` against the parser's own precedence.
    # Situation: The same payload is parsed once without metadata and then
    #   has the metadata applied, and once with the metadata from the start;
    #   the payload's inline unit, measurement method, and name all differ
    #   from the metadata, and a third parse applies no metadata at all.
    # Expectation: The two tables are equal in every field, including
    #   `provenance.sources`; with no metadata the table is returned
    #   unchanged.
    enrichment = _gdp_enrichment()
    parsed_first = parse_observation_table(
        _gdp_payload(), variable_dcid="Amount_GDP"
    )
    assert parsed_first.unit == "LocalCurrency"
    assert parsed_first.variable_name == "GDP (inline)"

    applied = apply_variable_metadata(parsed_first, enrichment)
    with_metadata = parse_observation_table(
        _gdp_payload(),
        variable_dcid="Amount_GDP",
        enrichment=enrichment,
    )

    assert applied == with_metadata
    assert applied.provenance.sources == (with_metadata.source,)
    assert apply_variable_metadata(parsed_first, None) is parsed_first


def test_applying_metadata_keeps_other_provenance_sources() -> None:
    # Test: `apply_variable_metadata` on a table with combined provenance.
    # Situation: A parsed table's provenance also lists a second source
    #   before the metadata that names the served facet is applied.
    # Expectation: The inline source is replaced by the metadata source and
    #   the second source is kept.
    other = Source(name="Other", url="https://other.example")
    parsed = parse_observation_table(_gdp_payload(), variable_dcid="Amount_GDP")
    combined = replace(
        parsed,
        provenance=replace(
            parsed.provenance,
            sources=(*parsed.provenance.sources, other),
        ),
    )
    applied = apply_variable_metadata(combined, _gdp_enrichment())
    assert applied.source is not None
    assert applied.source.name == "World Development Indicators"
    assert applied.provenance.sources == (applied.source, other)


def test_inline_metadata_and_variable_block_are_the_fallbacks() -> None:
    # Test: Fallbacks when no metadata enrichment matches the facet.
    # Situation: The enrichment describes a different facet, and the
    #   observation payload carries a unit, scaling factor, measurement
    #   method, and variable name inline.
    # Expectation: The inline `sourceMetadata` and `variable` values are
    #   used, except that the variable-level name from the enrichment
    #   still applies because it is keyed by variable DCID.
    enrichment = get_variable_metadata_enrichment(
        [
            {
                "variables": {
                    "Amount_GDP": {
                        "name": "Gross domestic product",
                        "facets": [{"id": "other", "provenanceId": "p"}],
                    }
                },
                "provenances": {"p": {"properties": {"url": _WDI_URL}}},
            }
        ]
    )
    payload: JsonObject = {
        "data": _data([["country/BEL", "2021", 1]]),
        "sourceMetadata": {
            "sourceId": "f9",
            "importName": "Eurostat",
            "provenanceUrl": "https://eurostat.example",
            "unit": "Euro",
            "scalingFactor": 1000,
            "measurementMethod": "EurostatRegionalStatistics",
            "observationPeriod": "P1Y",
        },
        "variable": {"dcid": "Amount_GDP", "name": "GDP"},
    }
    table = parse_observation_table(
        payload,
        variable_dcid="Amount_GDP",
        enrichment=enrichment,
    )
    assert table.unit == "Euro"
    assert table.scaling_factor == 1000.0
    assert table.measurement_method == "EurostatRegionalStatistics"
    assert table.observation_period == "P1Y"
    assert table.variable_name == "Gross domestic product"
    assert table.source == Source(
        name="Eurostat",
        url="https://eurostat.example",
    )
    assert table.rows[0].place_dcid == "country/BEL"


def test_inline_source_name_names_the_source() -> None:
    # Test: The `sourceName` display name in `sourceMetadata`.
    # Situation: The payload's `sourceMetadata` carries a `sourceName` and a
    #   `provenanceUrl`, and no metadata enrichment is given.
    # Expectation: The inline `Source` is named by `sourceName` rather than
    #   by the URL's hostname.
    table = parse_observation_table(
        {
            "variable": _VARIABLE,
            "sourceMetadata": {
                "sourceId": "f1",
                "sourceName": "US Census Bureau",
                "provenanceUrl": "https://www.census.gov/x",
            },
        },
        variable_dcid="Count_Person",
    )
    assert table.source == Source(
        name="US Census Bureau", url="https://www.census.gov/x"
    )


def test_variable_unit_ranks_below_inline_source_metadata() -> None:
    # Test: The place of the variable-level unit in the unit precedence.
    # Situation: The metadata declares a unit on the variable but none on
    #   the served facet; one observation payload reports a unit in
    #   `sourceMetadata` and another reports none.
    # Expectation: The payload's own unit wins over the variable's, and the
    #   variable's unit applies only when the payload reports none.
    enrichment = get_variable_metadata_enrichment(
        [
            {
                "variables": {
                    "Amount_GDP": {
                        "name": "Gross domestic product",
                        "properties": {"unit": "USDollar"},
                        "facets": [{"id": "f1", "provenanceId": "p"}],
                    }
                },
                "provenances": {"p": {"properties": {"url": _WDI_URL}}},
            }
        ]
    )
    rows: JsonObject = _data([["country/BEL", "2021", 1]])
    with_inline_unit = parse_observation_table(
        {
            "data": rows,
            "sourceMetadata": {"sourceId": "f1", "unit": "Euro"},
            "variable": {"dcid": "Amount_GDP"},
        },
        variable_dcid="Amount_GDP",
        enrichment=enrichment,
    )
    without_inline_unit = parse_observation_table(
        {
            "data": rows,
            "sourceMetadata": {"sourceId": "f1"},
            "variable": {"dcid": "Amount_GDP"},
        },
        variable_dcid="Amount_GDP",
        enrichment=enrichment,
    )
    assert with_inline_unit.unit == "Euro"
    assert without_inline_unit.unit == "USDollar"


def test_facet_shared_by_two_variables_does_not_leak_between_tables() -> None:
    # Test: Two variables served by one facet id.
    # Situation: The metadata describes `Count_Person` and
    #   `Count_Person_Urban`, both served by the same facet with different
    #   date ranges; an observation payload for the second variable names
    #   that facet.
    # Expectation: The second variable's table carries its own name and its
    #   own date range, not the first variable's.
    enrichment = get_variable_metadata_enrichment(
        [
            {
                "variables": {
                    "Count_Person": {
                        "name": "Total population",
                        "facets": [
                            {
                                "id": "f1",
                                "provenanceId": "p",
                                "dateRange": {"start": "1960", "end": "2025"},
                            }
                        ],
                    },
                    "Count_Person_Urban": {
                        "name": "Urban population",
                        "facets": [
                            {
                                "id": "f1",
                                "provenanceId": "p",
                                "dateRange": {"start": "1960", "end": "2023"},
                            }
                        ],
                    },
                },
                "provenances": {"p": {"properties": {"url": _WDI_URL}}},
            }
        ]
    )
    table = parse_observation_table(
        {
            "data": _data([["country/BEL", "2021", 1]]),
            "sourceMetadata": {"sourceId": "f1", "provenanceUrl": _WDI_URL},
            "variable": {"dcid": "Count_Person_Urban"},
        },
        variable_dcid="Count_Person_Urban",
        enrichment=enrichment,
    )
    assert table.variable_name == "Urban population"
    assert table.source == Source(
        name=_WDI_URL,
        url=_WDI_URL,
        date_range="1960 \u2013 2023",
    )


@pytest.mark.parametrize(
    "data",
    [{}, {"columns": ["observationAbout", "date", "value"]}],
    ids=["empty dict", "columns without rows"],
)
def test_empty_data_shapes_parse_as_an_empty_table(data: JsonValue) -> None:
    # Test: The empty-response shapes of the `data` field.
    # Situation: `data` is `{}` or a dict with `columns` and no
    #   `rows`, with `entityMetadata` likewise holding `columns` and no
    #   `rows`; parsed once with a requested place and once without.
    # Expectation: A table with no rows and no error; the requested place
    #   is preserved when given, and `requested_places` is empty when not,
    #   with no phantom place read from the `columns` key.
    payload: JsonObject = {
        "data": data,
        "entityMetadata": {"columns": ["dcid", "name", "typeOf"]},
        "sourceMetadata": {"sourceId": "f1", "provenanceUrl": _WDI_URL},
        "variable": _VARIABLE,
    }
    table = parse_observation_table(
        payload,
        variable_dcid="Count_Person",
        requested_places=["country/FRA"],
    )
    assert table.rows == ()
    assert table.requested_places == ("country/FRA",)
    assert table.places_with_data == ()
    assert table.facet_id == "f1"
    cohort = parse_observation_table(
        payload,
        variable_dcid="Count_Person",
        parent_place_dcid="Earth",
        child_place_type="Country",
    )
    assert cohort.rows == ()
    assert cohort.requested_places == ()
    assert cohort.place_names == {}


@pytest.mark.parametrize(
    "payload",
    [
        {"error": "Variable not found"},
        {"content": [{"type": "text", "text": "{}"}]},
    ],
    ids=["error object", "undecoded envelope"],
)
def test_non_observation_payload_raises(payload: JsonObject) -> None:
    # Test: A JSON object that is not an observation response.
    # Situation: The object is an error mapping, or an MCP tool result
    #   envelope passed without decoding; neither has a `variable` block.
    # Expectation: `ObservationPayloadError` naming the variable, rather than
    #   a silent empty table.
    with pytest.raises(ObservationPayloadError, match="Count_Person"):
        parse_observation_table(payload, variable_dcid="Count_Person")


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"data": "oops"}, "data"),
        ({"data": [["geoId/01", "2023", 1]]}, "data"),
        (
            {
                "data": {
                    "columns": ["observationAbout", 7, "date", "value"],
                    "rows": [["geoId/01", "2023", "2024", 5]],
                }
            },
            "data.columns.1",
        ),
        ({"variable": {"name": "No DCID"}}, "variable.dcid"),
        ({"variable": {"dcid": "Count\nPerson"}}, "variable.dcid"),
        ({"variable": {"dcid": "x" * 300}}, "variable.dcid"),
        ({"sourceMetadata": {"sourceId": ["f1"]}}, "sourceMetadata.sourceId"),
        (
            {"sourceMetadata": {"sourceId": "f1\nINFO forged"}},
            "sourceMetadata.sourceId",
        ),
        ({"sourceMetadata": {"sourceId": 10**300}}, "sourceMetadata.sourceId"),
    ],
    ids=[
        "data string",
        "data list",
        "non-string column",
        "variable without dcid",
        "variable dcid with a newline",
        "variable dcid too long",
        "list facet id",
        "facet id with a newline",
        "numeric facet id too long",
    ],
)
def test_malformed_structural_key_raises(
    payload: JsonObject, field: str
) -> None:
    # Test: A malformed structural key.
    # Situation: `data` is a string or a bare list of rows; a column name is
    #   a number (which would shift every later column); the `variable`
    #   block has no `dcid`, or one with a newline or over the DCID length
    #   limit; or the served facet ID is a list, contains a newline, or is a
    #   number too long for an identifier.
    # Expectation: `ObservationPayloadError` naming the variable and the
    #   malformed field, rather than an empty table, shifted values, or an
    #   unvalidated identifier in the table.
    with pytest.raises(
        ObservationPayloadError,
        match=rf"Count_Person has malformed fields: {re.escape(field)}\.",
    ):
        parse_observation_table(
            {"variable": _VARIABLE, **payload}, variable_dcid="Count_Person"
        )


def test_malformed_alternative_sources_are_dropped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Test: Malformed `alternativeSources` entries.
    # Situation: Of four alternatives, one has a facet ID with a newline, one
    #   has a list as its facet ID, one is a string rather than an object,
    #   and one is valid.
    # Expectation: The payload's row is kept, only the valid alternative is
    #   listed, and one warning names the variable and counts the three
    #   dropped entries.
    with caplog.at_level(logging.WARNING, logger="narratives_agent"):
        table = parse_observation_table(
            {
                "data": _data([["country/FRA", "2023", 1.0]]),
                "sourceMetadata": {"sourceId": "f1"},
                "alternativeSources": [
                    {"sourceMetadata": {"sourceId": "f2\nINFO forged"}},
                    {"sourceMetadata": {"sourceId": ["f3"]}},
                    "f4",
                    {"sourceMetadata": {"sourceId": "f5"}},
                ],
                "variable": _VARIABLE,
            },
            variable_dcid="Count_Person",
        )

    assert len(table.rows) == 1
    assert table.alternative_sources == (AlternativeSource(facet_id="f5"),)
    assert [record.getMessage() for record in caplog.records] == [
        "Dropped 3 malformed alternative source(s) for Count_Person."
    ]


def test_payload_errors_do_not_repeat_upstream_values() -> None:
    # Test: The text of a payload validation error.
    # Situation: The served facet ID contains a newline followed by text
    #   that imitates a log entry.
    # Expectation: Neither `ObservationPayloadError` nor the validation
    #   error it is raised from contains that text.
    with pytest.raises(ObservationPayloadError) as raised:
        parse_observation_table(
            {
                "sourceMetadata": {"sourceId": "f1\nINFO forged entry"},
                "variable": _VARIABLE,
            },
            variable_dcid="Count_Person",
        )

    assert isinstance(raised.value.__cause__, ValidationError)
    assert "forged" not in str(raised.value)
    assert "forged" not in str(raised.value.__cause__)


def test_dropped_alternatives_are_logged_once_per_valid_payload(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Test: Where the parser logs the warning for dropped alternatives.
    # Situation: A payload with a malformed alternative is rejected because
    #   its `variable` block has no DCID; and two per-place payloads are
    #   merged, and only Germany's lists a malformed alternative.
    # Expectation: The rejected payload logs no dropped-alternative warning,
    #   and the merge logs one warning naming Germany.
    bad_alternative: JsonValue = [{"sourceMetadata": {"sourceId": ["f9"]}}]
    with caplog.at_level(logging.WARNING, logger="narratives_agent"):
        with pytest.raises(ObservationPayloadError):
            parse_observation_table(
                {"alternativeSources": bad_alternative, "variable": {}},
                variable_dcid="Count_Person",
            )
        rejected = [record.getMessage() for record in caplog.records]
        caplog.clear()

        germany = _served("country/DEU", "f1")
        germany["alternativeSources"] = bad_alternative
        merge_observation_payloads(
            [
                ("country/FRA", _served("country/FRA", "f1")),
                ("country/DEU", germany),
            ]
        )
        merged = [record.getMessage() for record in caplog.records]

    assert rejected == []
    assert merged == [
        "Dropped 1 malformed alternative source(s) for country/DEU."
    ]


def test_descriptive_scalars_are_coerced_or_read_as_absent() -> None:
    # Test: Descriptive `sourceMetadata` and `alternativeSources` scalars.
    # Situation: The `scalingFactor` is the string `"1000"` (Data Commons
    #   declares it as a string), the `sourceId` is a number, the `unit` is a
    #   number, and an alternative's `placesFoundCount` is a boolean.
    # Expectation: The rows survive; the scaling factor is `1000.0`, the
    #   facet ID is its decimal string, and the unit and the count are absent.
    table = parse_observation_table(
        {
            "data": _data([["country/FRA", "2023", 1.0]]),
            "sourceMetadata": {
                "sourceId": 7,
                "provenanceUrl": _WDI_URL,
                "scalingFactor": "1000",
                "unit": 5,
            },
            "alternativeSources": [
                {"placesFoundCount": True, "sourceMetadata": {"sourceId": "f2"}}
            ],
            "variable": _VARIABLE,
        },
        variable_dcid="Count_Person",
    )
    assert len(table.rows) == 1
    assert table.scaling_factor == 1000.0
    assert table.facet_id == "7"
    assert table.unit is None
    assert table.alternative_sources == (AlternativeSource(facet_id="f2"),)


def test_invalid_arguments_are_reported_before_the_payload() -> None:
    # Test: The order of argument and payload validation.
    # Situation: A payload without a `variable` block is parsed with an
    #   invalid requested place; a valid payload is parsed with a variable
    #   DCID that has a leading space; and a valid payload is parsed with a
    #   single string as `requested_places`.
    # Expectation: `ValueError` naming the requested place (not
    #   `ObservationPayloadError`), `ValueError` for the variable DCID, and
    #   `TypeError` for the string.
    with pytest.raises(ValueError, match="requested place"):
        parse_observation_table(
            {"error": "Variable not found"},
            variable_dcid="x",
            requested_places=["bad place"],
        )
    with pytest.raises(ValueError, match="not a valid DCID"):
        parse_observation_table(
            _live_series_payload(), variable_dcid=" Count_Person"
        )
    with pytest.raises(TypeError, match="requested_places"):
        parse_observation_table(
            _live_series_payload(),
            variable_dcid="Count_Person",
            requested_places="country/FRA",
        )


@pytest.mark.parametrize(
    ("parent", "child", "argument"),
    [
        ("country/USA\nINFO forged", "State", "parent_place_dcid"),
        ("x" * 300, "State", "parent_place_dcid"),
        ("country/USA", "State\nINFO forged", "child_place_type"),
        ("country/USA", "", "child_place_type"),
    ],
    ids=[
        "parent with a newline",
        "parent too long",
        "child type with a newline",
        "empty child type",
    ],
)
def test_invalid_child_cohort_arguments_raise(
    parent: str, child: str, argument: str
) -> None:
    # Test: Validation of the child-cohort arguments.
    # Situation: A payload without a `variable` block is parsed with a
    #   `parent_place_dcid` or `child_place_type` that contains a newline, is
    #   too long, or is empty.
    # Expectation: `ValueError` naming the argument, raised before the
    #   payload is read, as for the other arguments.
    with pytest.raises(ValueError, match=rf"The {argument} .* for x is not"):
        parse_observation_table(
            {"error": "Variable not found"},
            variable_dcid="x",
            parent_place_dcid=parent,
            child_place_type=child,
        )


def test_dropped_rows_are_logged(caplog: pytest.LogCaptureFixture) -> None:
    # Test: The warning for malformed rows.
    # Situation: Of three rows, one is valid, one has a malformed date, and
    #   one is `null` rather than a list.
    # Expectation: The valid row is kept, and one warning names the variable
    #   and counts both dropped rows.
    with caplog.at_level(logging.WARNING, logger="narratives_agent"):
        table = parse_observation_table(
            {
                "data": _data([["a", "2020", 1], ["a", "20-20", 2], None]),
                "variable": _VARIABLE,
            },
            variable_dcid="Count_Person",
        )
    assert [(row.place_dcid, row.date) for row in table.rows] == [("a", "2020")]
    messages = [record.getMessage() for record in caplog.records]
    assert messages == [
        "Dropped 2 of 3 malformed or repeated observation rows for "
        "Count_Person."
    ]


@pytest.mark.parametrize(
    ("columns", "missing"),
    [
        (["donor", "recipient", "date", "value"], "observationAbout"),
        (["observationAbout", "value"], "date"),
        (["observationAbout", "date", "amount"], "value"),
    ],
    ids=["no place column", "no date column", "no value column"],
)
def test_data_without_a_required_column_raises(
    columns: list[JsonValue], missing: str
) -> None:
    # Test: A `data` table with rows but without a required column.
    # Situation: The table names its columns differently from the
    #   `observationAbout`, `date`, and `value` columns the observation
    #   tools return, once directly and once inside a merged payload.
    # Expectation: `ObservationPayloadError` naming the subject and the
    #   missing column, rather than a table that reports no data.
    payload: JsonObject = {
        "data": {"columns": columns, "rows": [["a", "2015", 1.0]]},
        "variable": _VARIABLE,
    }
    with pytest.raises(
        ObservationPayloadError,
        match=(
            rf"for Count_Person has rows but lacks the column\(s\): "
            rf"{missing}\."
        ),
    ):
        parse_observation_table(payload, variable_dcid="Count_Person")
    with pytest.raises(
        ObservationPayloadError,
        match=(
            rf"for country/FRA has rows but lacks the column\(s\): "
            rf"{missing}\."
        ),
    ):
        merge_observation_payloads([("country/FRA", payload)])


def test_payload_for_another_variable_raises() -> None:
    # Test: The binding between a payload and the requested variable.
    # Situation: A `Count_Person` payload is parsed as `Median_Age_Person`,
    #   and two per-place payloads for different variables are merged.
    # Expectation: Both raise `ObservationPayloadError` naming the variable
    #   the payload describes (and, for the merge, both variables) rather
    #   than labeling one variable's rows as another's.
    with pytest.raises(
        ObservationPayloadError, match="different variable, 'Count_Person'"
    ):
        parse_observation_table(
            _live_series_payload(), variable_dcid="Median_Age_Person"
        )
    with pytest.raises(
        ObservationPayloadError,
        match="different variables: 'Count_Person' and 'Median_Age_Person'",
    ):
        merge_observation_payloads(
            [
                ("country/FRA", _live_series_payload()),
                (
                    "country/DEU",
                    {"data": {}, "variable": {"dcid": "Median_Age_Person"}},
                ),
            ]
        )


def test_malformed_or_inverted_date_range_raises() -> None:
    # Test: Validation of the `date_range` bounds.
    # Situation: One window ends at `2020-1`, which is not a year, a year
    #   and month, or a full date; one starts in July and ends in March of
    #   the same year; and one starts in July 2020 and ends in the year
    #   2020, which is not a conflict at the year's granularity.
    # Expectation: `ValueError` naming the bound for the first, `ValueError`
    #   naming the window for the second, and an empty table for the third.
    with pytest.raises(ValueError, match=r"'2020-1' for Count_Person"):
        parse_observation_table(
            {"data": {}, "variable": _VARIABLE},
            variable_dcid="Count_Person",
            date_range=("2015", "2020-1"),
        )
    with pytest.raises(ValueError, match=r"starts after it ends"):
        parse_observation_table(
            {"data": {}, "variable": _VARIABLE},
            variable_dcid="Count_Person",
            date_range=("2020-07", "2020-03"),
        )
    table = parse_observation_table(
        {"data": {}, "variable": _VARIABLE},
        variable_dcid="Count_Person",
        date_range=("2020-07", "2020"),
    )
    assert table.rows == ()


def test_rows_for_unrequested_places_are_dropped() -> None:
    # Test: Rows outside a given `requested_places`.
    # Situation: Two places are requested, and the payload also holds rows
    #   for a third place.
    # Expectation: The third place's rows are dropped, and both requested
    #   places keep their row.
    table = parse_observation_table(
        {
            "data": _data(
                [
                    ["geoId/01", "2023", 1.0],
                    ["geoId/02", "2023", 2.0],
                    ["geoId/99", "2024", 9.0],
                    ["geoId/99", "2023", 9.0],
                ]
            ),
            "variable": _VARIABLE,
        },
        variable_dcid="Count_Person",
        requested_places=["geoId/01", "geoId/02"],
    )
    assert [row.place_dcid for row in table.rows] == ["geoId/01", "geoId/02"]
    assert set(table.place_names) == {"geoId/01", "geoId/02"}


def test_repeated_place_dates_in_one_payload_keep_the_first() -> None:
    # Test: A `(place, date)` repeated within one payload.
    # Situation: The payload lists `geoId/06` on `2020` twice with different
    #   values.
    # Expectation: One row, holding the first value.
    table = parse_observation_table(
        {
            "data": _data(
                [["geoId/06", "2020", 1.0], ["geoId/06", "2020", 2.0]]
            ),
            "variable": _VARIABLE,
        },
        variable_dcid="Count_Person",
    )
    assert [(row.date, row.value) for row in table.rows] == [("2020", 1.0)]


def test_malformed_dates_and_non_finite_values_are_dropped() -> None:
    # Test: Row validation.
    # Situation: Columnar rows carry a date in the wrong format, a value that
    #   is not a number, a numeric string, a NaN, an Infinity, an integer
    #   beyond float range, a boolean, a null, and an empty place, beside one
    #   valid row.
    # Expectation: Only the valid row survives.
    payload: JsonObject = {
        "data": _data(
            [
                ["a", "2020", 1],
                ["a", "20-20", 2],
                ["a", "2021", "many"],
                ["a", "2021", "3"],
                ["a", "2022", float("nan")],
                ["a", "2023", float("inf")],
                ["a", "2023", 10**400],
                ["a", "2024", True],
                ["a", "2025", None],
                ["", "2026", 3],
            ]
        ),
        "variable": {"dcid": "x"},
    }
    table = parse_observation_table(
        payload, variable_dcid="x", requested_places=["a", "b"]
    )
    assert [(row.date, row.value) for row in table.rows] == [("2020", 1.0)]


def test_display_names_and_place_dcids_are_sanitized_and_validated() -> None:
    # Test: Display-name sanitization and place DCID validation.
    # Situation: An `entityMetadata` row whose name carries a newline, a NUL
    #   byte, and repeated spaces; a `data` row whose place DCID contains a
    #   newline injection; a variable name longer than `MAX_NAME_CHARS`; and
    #   a call with an invalid `requested_places` entry.
    # Expectation: The invalid place DCID row is dropped, the valid place's
    #   display name is sanitized to one line, the variable name is capped at
    #   `MAX_NAME_CHARS`, and an invalid `requested_places` entry raises
    #   `ValueError`.
    long_name = "x" * (MAX_NAME_CHARS + 20)
    table = parse_observation_table(
        {
            "data": _data(
                [
                    ["a", "2020", 1],
                    ["geoId/06\nIGNORE PREVIOUS", "2020", 2],
                ]
            ),
            "entityMetadata": {
                "columns": ["dcid", "name"],
                "rows": [["a", "New\nYork\x00  City "]],
            },
            "variable": {"dcid": "x", "name": long_name},
        },
        variable_dcid="x",
    )
    assert [row.place_dcid for row in table.rows] == ["a"]
    assert table.rows[0].place_name == "New York City"
    assert table.variable_name == "x" * MAX_NAME_CHARS
    with pytest.raises(ValueError, match=r"requested place.*for x"):
        parse_observation_table(
            {"data": {}, "variable": {"dcid": "x"}},
            variable_dcid="x",
            requested_places=["geoId/06", "geoId/06\nIGNORE PREVIOUS"],
        )


def test_requested_places_are_deduplicated_in_request_order() -> None:
    # Test: Explicit target places.
    # Situation: The caller requests places with a repeat, and the payload
    #   has rows and `entityMetadata` for only one of them.
    # Expectation: `requested_places` keeps the request order without the
    #   repeat, and every requested place has a display name, falling back
    #   to its DCID.
    table = parse_observation_table(
        {
            "data": _data([["b", "2020", 1]]),
            "entityMetadata": {
                "columns": ["dcid", "name"],
                "rows": [["b", "Bee"]],
            },
            "variable": {"dcid": "x"},
        },
        variable_dcid="x",
        requested_places=["b", "a", "b", "c"],
    )
    assert table.requested_places == ("b", "a", "c")
    assert table.place_names == {"b": "Bee", "a": "a", "c": "c"}


def test_date_range_filters_rows_and_sets_target_places() -> None:
    # Test: `date_range` on a cohort payload.
    # Situation: A child-place payload with six rows across three places,
    #   a fourth place listed only in `entityMetadata`, and a `date_range` of
    #   2015 to 2023 that excludes Albania's 2010 row and admits
    #   Afghanistan's `2023-07-31` row.
    # Expectation: The five rows inside the range are kept, in place and
    #   date order; `requested_places` is the three places those rows belong
    #   to; and `place_names` names exactly those places, without Andorra.
    table = parse_observation_table(
        _cohort_payload(),
        variable_dcid="Count_Person",
        parent_place_dcid="Earth",
        child_place_type="Country",
        date_range=("2015", "2023"),
    )
    assert table.requested_places == (
        "country/ABW",
        "country/AFG",
        "country/ALB",
    )
    assert [(row.place_dcid, row.date) for row in table.rows] == [
        ("country/ABW", "2019"),
        ("country/ABW", "2021"),
        ("country/AFG", "2017"),
        ("country/AFG", "2023-07-31"),
        ("country/ALB", "2017"),
    ]
    assert table.parent_place_dcid == "Earth"
    assert table.child_place_type == "Country"
    assert table.place_names == {
        "country/ABW": "Aruba",
        "country/AFG": "Afghanistan",
        "country/ALB": "Albania",
    }
    assert table.alternative_sources == (
        AlternativeSource(
            facet_id="18369491376878146239",
            provenance_url=_WDI_URL,
            observation_period="P1Y",
            places_found_count=3,
        ),
    )


@pytest.mark.parametrize(
    ("date_range", "expected_places"),
    [
        (("2000", "2005"), ()),
        (("2020", "2025"), ("country/ABW", "country/AFG")),
    ],
    ids=["no row in range", "some rows in range"],
)
def test_target_places_without_requested_places_are_the_places_with_rows(
    date_range: tuple[str, str], expected_places: tuple[str, ...]
) -> None:
    # Test: The target places when no places are requested.
    # Situation: A cohort payload lists four places in `entityMetadata`
    #   (Andorra without any rows), parsed with a `date_range` that excludes
    #   every row, and with one that keeps rows for two places.
    # Expectation: `requested_places` is the places that still have rows in
    #   both cases: empty when no row is in range, rather than every place in
    #   `entityMetadata`.
    table = parse_observation_table(
        _cohort_payload(),
        variable_dcid="Count_Person",
        parent_place_dcid="Earth",
        child_place_type="Country",
        date_range=date_range,
    )
    assert table.requested_places == expected_places
    assert tuple(table.place_names) == expected_places


def test_merged_payloads_parse_as_one_multi_place_table() -> None:
    # Test: `merge_observation_payloads` followed by `parse_observation_table`.
    # Situation: Three single-place payloads for one variable: France
    #   with 3 rows, Germany with 2 rows served from the same facet as
    #   France, and Spain with an empty `data` dict.
    # Expectation: The merged payload parses as one table of five rows with
    #   both display names resolved from the concatenated `entityMetadata`,
    #   Spain counted as requested without data, and the source, facet, and
    #   alternative sources taken from France, the first payload from the
    #   facet that serves both France and Germany.
    france = _live_series_payload()
    germany: JsonObject = {
        "data": _data(
            [
                ["country/DEU", "2022", 84000000],
                ["country/DEU", "2023", 84400000],
            ]
        ),
        "entityMetadata": {
            "columns": ["dcid", "name"],
            "rows": [["country/DEU", "Germany"]],
        },
        "sourceMetadata": {
            "provenanceUrl": _WDI_URL,
            "sourceId": "18369491376878146239",
        },
        "variable": _VARIABLE,
    }
    spain: JsonObject = {
        "data": {},
        "entityMetadata": {},
        "variable": _VARIABLE,
    }

    merged = merge_observation_payloads(
        [
            ("country/FRA", france),
            ("country/DEU", germany),
            ("country/ESP", spain),
        ]
    )
    table = parse_observation_table(
        merged,
        variable_dcid="Count_Person",
        requested_places=("country/FRA", "country/DEU", "country/ESP"),
    )

    assert [(row.place_dcid, row.date) for row in table.rows] == [
        ("country/DEU", "2022"),
        ("country/DEU", "2023"),
        ("country/FRA", "2021"),
        ("country/FRA", "2022"),
        ("country/FRA", "2023"),
    ]
    assert table.requested_places == (
        "country/FRA",
        "country/DEU",
        "country/ESP",
    )
    assert table.places_with_data == ("country/DEU", "country/FRA")
    assert table.place_names["country/FRA"] == "France"
    assert table.place_names["country/DEU"] == "Germany"
    assert table.place_names["country/ESP"] == "country/ESP"
    assert table.facet_id == "18369491376878146239"
    assert table.source == Source(
        name="datatopics.worldbank.org",
        url=_WDI_URL,
    )
    assert [item.facet_id for item in table.alternative_sources] == [
        "12850099660527362240"
    ]
    assert table.variable_name == "Total population"


def test_merged_entity_metadata_lists_each_entity_once() -> None:
    # Test: Entities listed by more than one per-place payload.
    # Situation: France and Germany both list `Earth`; France gives it no
    #   name and Germany names it.
    # Expectation: The merged `entityMetadata` lists each entity once, in
    #   first-seen order, and `Earth` takes the name Germany gives it, "World".
    def payload(place: str, name: str, earth_name: str | None) -> JsonObject:
        return {
            "data": _data([[place, "2023", 1.0]]),
            "entityMetadata": {
                "columns": ["dcid", "name"],
                "rows": [[place, name], ["Earth", earth_name]],
            },
            "sourceMetadata": {"sourceId": "f1"},
            "variable": _VARIABLE,
        }

    merged = merge_observation_payloads(
        [
            ("country/FRA", payload("country/FRA", "France", None)),
            ("country/DEU", payload("country/DEU", "Germany", "World")),
        ]
    )

    assert merged.entity_metadata.rows == (
        ["country/FRA", "France"],
        ["Earth", "World"],
        ["country/DEU", "Germany"],
    )


def _served(place: str, facet: str | None) -> JsonObject:
    """A single-place payload with one 2023 row, served from `facet`."""
    source: JsonObject = {"provenanceUrl": _WDI_URL}
    if facet is not None:
        source["sourceId"] = facet
    return {
        "data": _data([[place, "2023", 1.0]]),
        "sourceMetadata": source,
        "variable": _VARIABLE,
    }


@pytest.mark.parametrize(
    "places",
    [
        ["country/FRA", "country/DEU", "country/ESP", "country/ITA"],
        ["country/ITA", "country/ESP", "country/DEU", "country/FRA"],
    ],
    ids=["minority facet first", "minority facet last"],
)
def test_merged_payloads_keep_the_facet_serving_the_most_places(
    places: list[str],
) -> None:
    # Test: The single-facet rule across merged payloads.
    # Situation: France is served from facet `eurostat`, and Germany, Spain,
    #   and Italy from facet `wdi`; the places are merged in two orders.
    # Expectation: In both orders the table keeps `wdi` and the three places
    #   it serves, drops France's row, and records `eurostat` in
    #   `alternative_sources`.
    facets = {"country/FRA": "eurostat"}
    merged = merge_observation_payloads(
        [(place, _served(place, facets.get(place, "wdi"))) for place in places]
    )
    table = parse_observation_table(
        merged, variable_dcid="Count_Person", requested_places=places
    )

    assert table.facet_id == "wdi"
    assert table.places_with_data == (
        "country/DEU",
        "country/ESP",
        "country/ITA",
    )
    assert [alt.facet_id for alt in table.alternative_sources] == ["eurostat"]


def test_merged_payloads_break_a_facet_tie_by_request_order() -> None:
    # Test: The single-facet rule when two facets serve equally many places.
    # Situation: France is served from facet `f1` and Germany from `f2`.
    # Expectation: The facet of the first requested place, `f1`, is kept,
    #   Germany's row is dropped, and `f2` is recorded in
    #   `alternative_sources`.
    merged = merge_observation_payloads(
        [
            ("country/FRA", _served("country/FRA", "f1")),
            ("country/DEU", _served("country/DEU", "f2")),
        ]
    )
    table = parse_observation_table(
        merged,
        variable_dcid="Count_Person",
        requested_places=("country/FRA", "country/DEU"),
    )

    assert table.facet_id == "f1"
    assert [(row.place_dcid, row.facet_id) for row in table.rows] == [
        ("country/FRA", "f1")
    ]
    assert [alt.facet_id for alt in table.alternative_sources] == ["f2"]


def test_merged_payloads_count_each_place_once_per_facet() -> None:
    # Test: Facet coverage when a place is merged more than once.
    # Situation: France is passed twice under facet `f1`, and Germany and
    #   Spain once each under facet `f2`.
    # Expectation: `f2`, which serves two distinct places, is kept over `f1`,
    #   which serves one place twice.
    merged = merge_observation_payloads(
        [
            ("country/FRA", _served("country/FRA", "f1")),
            ("country/FRA", _served("country/FRA", "f1")),
            ("country/DEU", _served("country/DEU", "f2")),
            ("country/ESP", _served("country/ESP", "f2")),
        ]
    )
    table = parse_observation_table(merged, variable_dcid="Count_Person")

    assert table.facet_id == "f2"
    assert table.places_with_data == ("country/DEU", "country/ESP")
    assert [alt.facet_id for alt in table.alternative_sources] == ["f1"]


def test_merged_payloads_without_facet_ids_never_blend_sources() -> None:
    # Test: The single-facet rule when payloads name no facet.
    # Situation: France and Spain have rows and `sourceMetadata` without a
    #   `sourceId`; they are merged on their own, and again with Germany,
    #   whose rows are served from facet `f2`.
    # Expectation: On their own, only France's rows are kept, so two
    #   unidentified facets are not blended, and the table has no facet ID.
    #   With Germany, the identified facet `f2` is kept with Germany's rows,
    #   and the unidentified facets, which cannot be requested, are not
    #   recorded as alternatives.
    france = ("country/FRA", _served("country/FRA", None))
    spain = ("country/ESP", _served("country/ESP", None))
    germany = ("country/DEU", _served("country/DEU", "f2"))

    unidentified = parse_observation_table(
        merge_observation_payloads([france, spain]),
        variable_dcid="Count_Person",
    )
    mixed = parse_observation_table(
        merge_observation_payloads([france, germany, spain]),
        variable_dcid="Count_Person",
    )

    assert unidentified.facet_id is None
    assert unidentified.places_with_data == ("country/FRA",)
    assert mixed.facet_id == "f2"
    assert mixed.places_with_data == ("country/DEU",)
    assert mixed.alternative_sources == ()


def test_merged_payloads_keep_only_rows_for_their_own_place(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Test: The binding between a merged payload and its place.
    # Situation: The payload listed under Germany holds a row for Germany
    #   and a row for France; separately, a place label that is not a valid
    #   DCID is merged.
    # Expectation: France's row is dropped with a warning naming Germany,
    #   and the invalid label raises `ValueError` before any payload is
    #   read.
    germany: JsonObject = {
        "data": _data(
            [["country/DEU", "2023", 1.0], ["country/FRA", "2023", 2.0]]
        ),
        "sourceMetadata": {"sourceId": "f1"},
        "variable": _VARIABLE,
    }
    with caplog.at_level(logging.WARNING, logger="narratives_agent"):
        merged = merge_observation_payloads([("country/DEU", germany)])

    assert merged.data.rows == (["country/DEU", "2023", 1.0],)
    assert [record.getMessage() for record in caplog.records] == [
        "Dropped 1 observation row(s) for other places from the payload for "
        "country/DEU."
    ]
    with pytest.raises(ValueError, match=r"'country/DEU\\nx' is not a valid"):
        merge_observation_payloads(
            [("country/DEU\nx", {"error": "Variable not found"})]
        )


def test_merged_alternatives_drop_the_per_place_coverage_count() -> None:
    # Test: `placesFoundCount` across merged payloads.
    # Situation: Two single-place payloads served from `f1` both list `f2`
    #   as an alternative with `placesFoundCount: 1`; the France payload is
    #   also merged on its own.
    # Expectation: The two-payload merge records `f2` without a count,
    #   because each count covers one place only; the single-payload merge
    #   keeps the count.
    def served(place: str) -> JsonObject:
        return {
            "data": _data([[place, "2023", 1.0]]),
            "sourceMetadata": {"sourceId": "f1", "provenanceUrl": _WDI_URL},
            "alternativeSources": [
                {"placesFoundCount": 1, "sourceMetadata": {"sourceId": "f2"}}
            ],
            "variable": _VARIABLE,
        }

    both = parse_observation_table(
        merge_observation_payloads(
            [
                ("country/FRA", served("country/FRA")),
                ("country/DEU", served("country/DEU")),
            ]
        ),
        variable_dcid="Count_Person",
    )
    alone = parse_observation_table(
        merge_observation_payloads([("country/FRA", served("country/FRA"))]),
        variable_dcid="Count_Person",
    )

    assert both.alternative_sources == (AlternativeSource(facet_id="f2"),)
    assert alone.alternative_sources == (
        AlternativeSource(facet_id="f2", places_found_count=1),
    )


def test_merged_payloads_drop_repeated_place_dates() -> None:
    # Test: A place merged twice.
    # Situation: The same single-place payload is passed twice.
    # Expectation: Each `(place, date)` row appears once.
    payload: JsonObject = {
        "data": _data([["geoId/01", "2023", 1.0]]),
        "sourceMetadata": {"sourceId": "f1"},
        "variable": _VARIABLE,
    }
    merged = merge_observation_payloads(
        [("geoId/01", payload), ("geoId/01", payload)]
    )
    assert merged.data.rows == (["geoId/01", "2023", 1.0],)


def test_merged_payloads_keep_the_alternatives_of_every_place() -> None:
    # Test: `alternativeSources` across merged payloads.
    # Situation: France has rows under facet `f1` and lists `f2` as an
    #   alternative; Germany has no rows under `f1` and lists `f3`, `f2`, and
    #   `f1`; Spain was served from `f4`, whose rows the single-facet rule
    #   drops.
    # Expectation: The table lists `f2`, `f3`, and `f4` once each, in that
    #   order, without the served facet `f1`.
    def alternative(facet: str, domain: str) -> JsonObject:
        return {
            "sourceMetadata": {
                "sourceId": facet,
                "provenanceUrl": f"https://{domain}.example",
            }
        }

    france: JsonObject = {
        "data": _data([["country/FRA", "2023", 1.0]]),
        "sourceMetadata": {"sourceId": "f1", "provenanceUrl": _WDI_URL},
        "alternativeSources": [alternative("f2", "wikidata")],
        "variable": _VARIABLE,
    }
    germany: JsonObject = {
        "data": {},
        "sourceMetadata": {"sourceId": "f1", "provenanceUrl": _WDI_URL},
        "alternativeSources": [
            alternative("f3", "destatis"),
            alternative("f2", "wikidata"),
            alternative("f1", "wdi"),
        ],
        "variable": _VARIABLE,
    }
    spain: JsonObject = {
        "data": _data([["country/ESP", "2023", 2.0]]),
        "sourceMetadata": {
            "sourceId": "f4",
            "provenanceUrl": "https://ine.example",
        },
        "variable": _VARIABLE,
    }

    merged = merge_observation_payloads(
        [
            ("country/FRA", france),
            ("country/DEU", germany),
            ("country/ESP", spain),
        ]
    )
    table = parse_observation_table(
        merged,
        variable_dcid="Count_Person",
        requested_places=("country/FRA", "country/DEU", "country/ESP"),
    )

    assert table.facet_id == "f1"
    assert table.places_with_data == ("country/FRA",)
    assert [
        (item.facet_id, item.provenance_url)
        for item in table.alternative_sources
    ] == [
        ("f2", "https://wikidata.example"),
        ("f3", "https://destatis.example"),
        ("f4", "https://ine.example"),
    ]


def test_merge_falls_back_to_first_header_and_rejects_invalid_payloads() -> (
    None
):
    # Test: Header selection and error handling in `merge_observation_payloads`.
    # Situation: Two payloads with no rows, the first carrying `sourceMetadata`
    #   and `entityMetadata`; then a payload without a `variable` block; then no
    #   payloads at all.
    # Expectation: The merged payload carries the first payload's source
    #   metadata and entity metadata with no rows, the unparseable payload
    #   raises `ObservationPayloadError` naming its place, and an empty list
    #   raises `ValueError`.
    merged = merge_observation_payloads(
        [
            (
                "a",
                {
                    "data": {},
                    "sourceMetadata": {"sourceId": "f1"},
                    "variable": _VARIABLE,
                    "entityMetadata": {
                        "columns": ["dcid", "name"],
                        "rows": [["a", "Alpha"]],
                    },
                },
            ),
            ("b", {"data": {}, "variable": _VARIABLE}),
        ]
    )
    assert merged.data.rows == ()
    assert merged.source_metadata.source_id == "f1"
    assert merged.entity_metadata.rows == (["a", "Alpha"],)

    with pytest.raises(ObservationPayloadError, match="payload for b"):
        merge_observation_payloads(
            [
                ("a", {"data": {}, "variable": _VARIABLE}),
                ("b", {"error": "Variable not found"}),
            ]
        )
    with pytest.raises(ValueError, match="requires a payload"):
        merge_observation_payloads([])


def test_payload_outline_reads_entity_role_rows_and_sources() -> None:
    # Test: `read_payload_outline` on a payload keyed by entity role.
    # Situation: A relationship payload has `donor`, `recipient`, `date`, and
    #   `value` columns, two list rows and one row that is not a list, a
    #   served facet with a provenance URL, and two alternatives, one without
    #   a facet ID; separately, a place-keyed payload and one without the
    #   `variable` block.
    # Expectation: The outline keeps the columns and the list rows as sent,
    #   reports no place column, reads the facet and source, and drops the
    #   alternative without a facet ID; the place-keyed payload reports a
    #   place column; the payload without `variable` raises.
    payload: JsonObject = {
        "variable": {"dcid": "Aid"},
        "data": {
            "columns": ["donor", "recipient", "date", "value"],
            "rows": [
                ["country/ARE", "country/AFG", "2020", 1.0],
                ["country/ARE", "country/PAK", "2020", 2.0],
                "not a row",
            ],
        },
        "sourceMetadata": {"sourceId": "f1", "provenanceUrl": _WDI_URL},
        "alternativeSources": [
            {"sourceMetadata": {"sourceId": "f2", "unit": "USDollar"}},
            {"sourceMetadata": {"provenanceUrl": _WIKIDATA_URL}},
        ],
    }

    outline = read_payload_outline(payload, "Aid")

    assert outline == ObservationPayloadOutline(
        columns=("donor", "recipient", "date", "value"),
        rows=(
            ("country/ARE", "country/AFG", "2020", 1.0),
            ("country/ARE", "country/PAK", "2020", 2.0),
        ),
        has_place_column=False,
        facet_id="f1",
        source=Source(name="datatopics.worldbank.org", url=_WDI_URL),
        alternative_sources=(
            AlternativeSource(facet_id="f2", unit="USDollar"),
        ),
    )
    place_payload: JsonObject = {
        "variable": _VARIABLE,
        "data": _data([["country/FRA", "2020", 1.0]]),
    }
    assert read_payload_outline(place_payload, "Count_Person").has_place_column
    with pytest.raises(ObservationPayloadError, match="variable"):
        read_payload_outline({"data": {}}, "Aid")
