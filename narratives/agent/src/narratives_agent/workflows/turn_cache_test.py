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
"""Tests for `TurnCache` and `CachedTable`.

Covers sequential table IDs, counters, derived-table storage,
variable-metadata enrichment backfill, and facet locking.
"""

import pytest

from narratives_agent.analytics.provenance import Provenance, Source
from narratives_agent.analytics.tables import (
    ObservationRow,
    ObservationTable,
)
from narratives_agent.json_value import JsonObject
from narratives_agent.mcp.observations import parse_observation_table
from narratives_agent.workflows.turn_cache import (
    CachedTable,
    FacetScope,
    TurnCache,
)

_WDI_URL = "https://datatopics.worldbank.org/world-development-indicators/"
_FACET = "18369491376878146239"


def _build_cached_table(
    table_id: str,
    variable_dcid: str = "Count_Person",
    *,
    source: Source | None = None,
    row_count: int = 2,
) -> CachedTable:
    """Builds a `CachedTable` with `row_count` observations for one place."""
    table = ObservationTable(
        variable_dcid=variable_dcid,
        variable_name=variable_dcid,
        unit=None,
        scaling_factor=None,
        provenance=Provenance(
            sources=(source,) if source is not None else (),
            facet_ids=("f1",),
        ),
        rows=tuple(
            ObservationRow("country/FRA", "France", str(2020 + index), 1.0)
            for index in range(row_count)
        ),
        requested_places=("country/FRA",),
        place_names={"country/FRA": "France"},
        facet_id="f1",
        source=source,
    )
    return CachedTable(table_id=table_id, table=table)


def _build_observation_payload() -> JsonObject:
    """Builds a one-place payload with source metadata and no facet metadata."""
    return {
        "data": {
            "columns": ["observationAbout", "date", "value"],
            "rows": [["country/FRA", "2023", 68287487]],
        },
        "entityMetadata": {
            "columns": ["dcid", "name"],
            "rows": [["country/FRA", "France"]],
        },
        "sourceMetadata": {"provenanceUrl": _WDI_URL, "sourceId": _FACET},
        "variable": {"dcid": "Count_Person"},
    }


def _build_metadata_payload(*, facet_unit: str | None = None) -> JsonObject:
    """Builds metadata for the facet of `_build_observation_payload`."""
    facet_properties: JsonObject = {
        "observationPeriod": "P1Y",
        "measurementMethod": "Census",
        "scalingFactor": 1000,
    }
    if facet_unit is not None:
        facet_properties["unit"] = facet_unit
    return {
        "provenances": {
            "dc/base/WDI": {
                "properties": {
                    "isPartOf": "World Development Indicators",
                    "licenseType": "CC BY 4.0",
                    "source": "World Bank",
                    "url": _WDI_URL,
                }
            }
        },
        "variables": {
            "Count_Person": {
                "name": "Total population",
                "properties": {"unit": "Person"},
                "facets": [
                    {
                        "id": _FACET,
                        "provenanceId": "dc/base/WDI",
                        "properties": facet_properties,
                    }
                ],
            }
        },
    }


def test_fetched_tables_take_sequential_ids_and_are_counted() -> None:
    # Test: Table ids and counters.
    # Situation: Two tables are stored under the ids the cache hands out,
    #   with two and three rows.
    # Expectation: The ids are `t1` and `t2`, both entries are retrievable in
    #   fetch order, and the counters report two tables and five rows.
    cache = TurnCache()
    assert cache.get_next_table_id() == "t1"
    cache.store_fetched(_build_cached_table("t1", row_count=2))
    assert cache.get_next_table_id() == "t2"
    cache.store_fetched(
        _build_cached_table("t2", "Count_Household", row_count=3)
    )

    assert cache.table_ids == ("t1", "t2")
    assert [entry.table_id for entry in cache.list_fetched_tables()] == [
        "t1",
        "t2",
    ]
    entry = cache.get("t2")
    assert entry is not None
    assert entry.table.variable_dcid == "Count_Household"
    assert cache.get("t3") is None
    assert cache.tables_fetched == 2
    assert cache.total_rows_fetched == 5


def test_storing_under_the_wrong_id_is_rejected() -> None:
    # Test: The id guards of `store_fetched` and `store_derived`.
    # Situation: A fetched table is stored as `t2` while the next id is
    #   `t1`, and derived tables are stored under a fetched-table id and
    #   under ids that are not `s` followed by a positive integer.
    # Expectation: Both raise `ValueError`, so a lookup by id can never
    #   return a table stored under an id the cache did not hand out.
    cache = TurnCache()
    with pytest.raises(ValueError, match="stored as t1"):
        cache.store_fetched(_build_cached_table("t2"))
    for table_id in ("t1", "s", "s0", "s01", "sx", "summary"):
        with pytest.raises(ValueError, match="step id"):
            cache.store_derived(_build_cached_table(table_id))


def test_derived_tables_are_stored_under_their_step_id_and_replaced() -> None:
    # Test: Derived tables.
    # Situation: A table is stored as `s1`, then another under the same id,
    #   as rerunning the step that derives it does.
    # Expectation: The second table replaces the first, `s1` is listed
    #   after the fetched tables, and it is not counted as fetched.
    cache = TurnCache()
    cache.store_fetched(_build_cached_table("t1"))
    cache.store_derived(_build_cached_table("s1", "derived_a", row_count=1))
    cache.store_derived(_build_cached_table("s1", "derived_b", row_count=1))

    derived = cache.get("s1")
    assert derived is not None
    assert derived.table.variable_dcid == "derived_b"
    assert cache.table_ids == ("t1", "s1")
    assert [entry.table_id for entry in cache.list_fetched_tables()] == ["t1"]
    assert cache.tables_fetched == 1


def test_clearing_derived_tables_keeps_the_fetched_ones() -> None:
    # Test: `clear_derived`.
    # Situation: A cache holds one fetched table and two derived tables.
    # Expectation: After clearing, only the fetched table remains, its
    #   counters are unchanged, and clearing an empty set is harmless.
    cache = TurnCache()
    cache.store_fetched(_build_cached_table("t1"))
    cache.store_derived(_build_cached_table("s1", "derived_a", row_count=1))
    cache.store_derived(_build_cached_table("s2", "derived_b", row_count=1))

    cache.clear_derived()
    cache.clear_derived()

    assert cache.table_ids == ("t1",)
    assert cache.get("s1") is None
    assert cache.tables_fetched == 1
    assert cache.total_rows_fetched == 2


def test_metadata_recorded_after_a_fetch_backfills_the_table() -> None:
    # Test: Metadata enrichment in either order.
    # Situation: A table is parsed from an observation payload before any
    #   metadata was recorded, then the facet's metadata payload arrives;
    #   separately, a second table is parsed after the metadata.
    # Expectation: The first table is backfilled with the variable name,
    #   unit, scaling factor, measurement method, observation period, and
    #   the named source with its license, and reads the same as the table
    #   parsed after the metadata.
    cache = TurnCache()
    early_id = cache.get_next_table_id()
    early = parse_observation_table(
        _build_observation_payload(),
        variable_dcid="Count_Person",
        requested_places=("country/FRA",),
        enrichment=cache.enrichment,
    )
    cache.store_fetched(CachedTable(table_id=early_id, table=early))
    assert early.variable_name == "Count_Person"
    assert early.unit is None
    assert early.source == Source(name="datatopics.worldbank.org", url=_WDI_URL)

    cache.record_variable_metadata(_build_metadata_payload())

    late_id = cache.get_next_table_id()
    late = parse_observation_table(
        _build_observation_payload(),
        variable_dcid="Count_Person",
        requested_places=("country/FRA",),
        enrichment=cache.enrichment,
    )
    cache.store_fetched(CachedTable(table_id=late_id, table=late))
    backfilled_entry = cache.get("t1")
    assert backfilled_entry is not None
    backfilled = backfilled_entry.table
    assert backfilled.variable_name == "Total population"
    assert backfilled.unit == "Person"
    assert backfilled.scaling_factor == 1000.0
    assert backfilled.measurement_method == "Census"
    assert backfilled.observation_period == "P1Y"
    assert backfilled.source == Source(
        name="World Development Indicators",
        url=_WDI_URL,
        license="CC BY 4.0",
        dataset="World Development Indicators",
        provider="World Bank",
    )
    assert backfilled.provenance.sources == (backfilled.source,)
    assert backfilled.rows == early.rows
    assert backfilled == late


def test_metadata_overrides_inline_fields_in_either_order() -> None:
    # Test: Order independence of metadata and inline fields.
    # Situation: An observation payload carries an inline variable name,
    #   unit, scaling factor, measurement method, and observation period
    #   that all differ from the facet's metadata. One table is parsed
    #   before the metadata payload is recorded and another after it.
    # Expectation: The metadata takes precedence in both cases, so once the
    #   metadata is recorded the table fetched first is equal, field for field,
    #   to the table fetched second.
    payload = _build_observation_payload()
    payload["variable"] = {"dcid": "Count_Person", "name": "People (inline)"}
    payload["sourceMetadata"] = {
        "provenanceUrl": _WDI_URL,
        "sourceId": _FACET,
        "unit": "Persons",
        "scalingFactor": 1,
        "measurementMethod": "Estimate",
        "observationPeriod": "P5Y",
    }
    cache = TurnCache()
    early_id = cache.get_next_table_id()
    early = parse_observation_table(
        payload,
        variable_dcid="Count_Person",
        requested_places=("country/FRA",),
        enrichment=cache.enrichment,
    )
    cache.store_fetched(CachedTable(table_id=early_id, table=early))
    assert early.variable_name == "People (inline)"
    assert early.unit == "Persons"
    assert early.observation_period == "P5Y"

    # The facet unit overrides the payload unit; the variable-level unit
    # in `_build_metadata_payload` does not, so the facet declares one here.
    cache.record_variable_metadata(_build_metadata_payload(facet_unit="Person"))

    late_id = cache.get_next_table_id()
    late = parse_observation_table(
        payload,
        variable_dcid="Count_Person",
        requested_places=("country/FRA",),
        enrichment=cache.enrichment,
    )
    cache.store_fetched(CachedTable(table_id=late_id, table=late))
    updated_entry = cache.get("t1")
    assert updated_entry is not None
    updated = updated_entry.table
    assert updated.variable_name == "Total population"
    assert updated.unit == "Person"
    assert updated.scaling_factor == 1000.0
    assert updated.measurement_method == "Census"
    assert updated.observation_period == "P1Y"
    assert updated == late


def test_an_unparseable_metadata_payload_is_ignored() -> None:
    # Test: Robustness of `record_variable_metadata`.
    # Situation: A plain-text tool error is recorded as a metadata payload.
    # Expectation: The index stays empty and nothing raises, because the
    #   model receives the tool error itself.
    cache = TurnCache()
    cache.record_variable_metadata("Error: upstream timed out")
    assert cache.enrichment.variables == {}
    assert cache.enrichment.facets == {}


def test_the_first_facet_of_a_variable_is_locked_per_scope() -> None:
    # Test: Facet locking across fetches of one variable.
    # Situation: A variable is locked to facet `a` over one scope, then an
    #   attempt is made to lock it to `b` over the same scope; it is locked
    #   to `c` over another scope; another variable has no lock.
    # Expectation: The variable stays locked to `a` over the first scope and
    #   to `c` over the second, and the other variable reports no lock.
    states: FacetScope = ("children", "country/USA", "State")
    named: FacetScope = ("named_places",)
    cache = TurnCache()
    cache.lock_facet("Count_Person", states, "a")
    cache.lock_facet("Count_Person", states, "b")
    cache.lock_facet("Count_Person", named, "c")
    assert cache.get_locked_facet("Count_Person", states) == "a"
    assert cache.get_locked_facet("Count_Person", named) == "c"
    assert cache.get_locked_facet("Count_Household", states) is None


def test_metadata_recorded_later_leaves_derived_tables_unchanged() -> None:
    # Test: The backfill scope of `record_variable_metadata`.
    # Situation: A fetched table and a derived table for the same variable
    #   are cached, then the variable's metadata payload is recorded.
    # Expectation: The fetched table is backfilled with the variable name,
    #   and the derived table is unchanged.
    cache = TurnCache()
    fetched = parse_observation_table(
        _build_observation_payload(),
        variable_dcid="Count_Person",
        requested_places=("country/FRA",),
        enrichment=cache.enrichment,
    )
    cache.store_fetched(CachedTable(table_id="t1", table=fetched))
    derived = _build_cached_table("s1")
    cache.store_derived(derived)

    cache.record_variable_metadata(_build_metadata_payload())

    backfilled = cache.get("t1")
    assert backfilled is not None
    assert backfilled.table.variable_name == "Total population"
    assert cache.get("s1") == derived
