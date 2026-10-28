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
"""Per-turn observation table cache and variable metadata index.

Stores fetched and derived `CachedTable` entries for a single chat turn,
merges `get_variable_metadata` responses into `VariableMetadataEnrichment`,
backfills already-cached tables when metadata arrives after a fetch, and
locks each variable to the first facet it was served from over each scope of
places.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from narratives_agent.analytics.tables import ObservationTable
from narratives_agent.json_value import JsonValue
from narratives_agent.mcp.client import decode_tool_payload
from narratives_agent.mcp.metadata import (
    VariableMetadataEnrichment,
    get_variable_metadata_enrichment,
)
from narratives_agent.mcp.observations import apply_variable_metadata

__all__ = [
    "DERIVED_TABLE_PREFIX",
    "FETCHED_TABLE_PREFIX",
    "TABLE_ID_NUMBER_PATTERN",
    "CachedTable",
    "FacetScope",
    "TurnCache",
]

# Fetched tables are stored as `t1`, `t2`, ... in fetch order.
FETCHED_TABLE_PREFIX = "t"
# Derived tables are stored under the id of the step that derived them, such
# as `s1`, so a derived table never shares an id with a fetched one.
DERIVED_TABLE_PREFIX = "s"
# A table id is its prefix and a positive integer without leading zeros.
TABLE_ID_NUMBER_PATTERN = "[1-9][0-9]*"
_DERIVED_TABLE_ID = re.compile(
    rf"{DERIVED_TABLE_PREFIX}{TABLE_ID_NUMBER_PATTERN}"
)

# The places a facet lock covers, such as every named place or the children
# of one type within one parent. A facet chosen for one set of places can
# lack data for another, so each scope is locked separately.
type FacetScope = tuple[str, ...]


@dataclass(frozen=True)
class CachedTable:
    """A cached observation table with its turn-scoped identity.

    Attributes:
        table_id: Turn-scoped identifier (`t<n>` for fetched tables, `s<n>` for
            derived tables).
        table: The immutable `ObservationTable`.
    """

    table_id: str
    table: ObservationTable


@dataclass
class TurnCache:
    """The tables, metadata enrichment, and counters of one turn.

    The cache is not synchronized. Fetches of one variable over one facet
    scope must not overlap, because each reads the locked facet before the
    first of them records one.

    Attributes:
        tables_fetched: The number of tables the fetch functions stored.
        total_rows_fetched: The number of rows across those tables.
    """

    tables_fetched: int = field(default=0, init=False)
    total_rows_fetched: int = field(default=0, init=False)
    _tables: dict[str, CachedTable] = field(
        default_factory=dict, init=False, repr=False
    )
    _enrichment: VariableMetadataEnrichment = field(
        default_factory=VariableMetadataEnrichment, init=False, repr=False
    )
    _locked_facets: dict[tuple[str, FacetScope], str] = field(
        default_factory=dict, init=False, repr=False
    )

    @property
    def enrichment(self) -> VariableMetadataEnrichment:
        """The metadata index built from every payload recorded so far."""
        return self._enrichment

    @property
    def table_ids(self) -> tuple[str, ...]:
        """Every cached table id, in storage order."""
        return tuple(self._tables)

    def get_next_table_id(self) -> str:
        """Returns the id the next fetched table must be stored under.

        Returns:
            `t<n>`, where `n` is one more than the number of fetched tables.
        """
        return f"{FETCHED_TABLE_PREFIX}{self.tables_fetched + 1}"

    def get(self, table_id: str) -> CachedTable | None:
        """Returns the `CachedTable` stored under `table_id`.

        Args:
            table_id: A fetched (`t<n>`) or derived (`s<n>`) table id.

        Returns:
            The cached entry, or `None` when no table is stored under the id.
        """
        return self._tables.get(table_id)

    def list_fetched_tables(self) -> tuple[CachedTable, ...]:
        """Returns the `CachedTable` entries the fetch functions stored.

        Returns:
            The fetched entries in fetch order, without derived tables.
        """
        return tuple(
            entry
            for table_id, entry in self._tables.items()
            if table_id.startswith(FETCHED_TABLE_PREFIX)
        )

    def store_fetched(self, entry: CachedTable) -> None:
        """Stores a `CachedTable` parsed by a fetch function and counts it.

        Args:
            entry: The table, built under the id `get_next_table_id` returned.

        Raises:
            ValueError: If `entry.table_id` is not the id `get_next_table_id`
                returns, which means the caller built the entry against a
                stale id and a later lookup by id would return the wrong
                table.
        """
        expected = self.get_next_table_id()
        if entry.table_id != expected:
            raise ValueError(
                f"A fetched table must be stored as {expected}, not "
                f"{entry.table_id}."
            )
        self._tables[entry.table_id] = entry
        self.tables_fetched += 1
        self.total_rows_fetched += len(entry.table.rows)

    def store_derived(self, entry: CachedTable) -> None:
        """Stores a derived table under its step id, replacing any earlier one.

        Args:
            entry: The derived table, under a step id `s<n>` such as `s1`.

        Raises:
            ValueError: If `entry.table_id` is not a step id, so that a derived
                table can never shadow a fetched one.
        """
        if _DERIVED_TABLE_ID.fullmatch(entry.table_id) is None:
            raise ValueError(
                f"A derived table must be stored under a step id such as "
                f"s1, not {entry.table_id}."
            )
        self._tables[entry.table_id] = entry

    def clear_derived(self) -> None:
        """Drops every derived table and keeps the fetched ones.

        A caller that derives tables again clears the earlier ones first, so
        that no derived table from an earlier run remains to be referenced.
        """
        for table_id in [
            table_id
            for table_id in self._tables
            if table_id.startswith(DERIVED_TABLE_PREFIX)
        ]:
            del self._tables[table_id]

    def record_variable_metadata(
        self, payload: JsonValue | Mapping[str, JsonValue]
    ) -> None:
        """Indexes a `get_variable_metadata` result and updates fetched tables.

        The payload is merged into the enrichment index that later fetches
        read, and every fetched table already cached has the index applied
        through `apply_variable_metadata`, the same function the parser uses,
        so that a table reads the same whether its metadata arrived before or
        after it was fetched. Derived tables are not changed, because their
        unit and source come from the step that derived them. A payload that
        does not decode to a JSON object, such as a tool error string, is
        ignored, because the tool error itself is the result the caller
        reports.

        Args:
            payload: The tool result, as the MCP envelope or its decoded
                payload.
        """
        parsed = decode_tool_payload(payload)
        if parsed is None:
            return
        self._enrichment = self._enrichment.merge(
            get_variable_metadata_enrichment((parsed,))
        )
        for entry in self.list_fetched_tables():
            self._tables[entry.table_id] = replace(
                entry,
                table=apply_variable_metadata(entry.table, self._enrichment),
            )

    def lock_facet(
        self, variable_dcid: str, scope: FacetScope, facet_id: str
    ) -> None:
        """Records the facet a variable was first served from over a scope.

        The first recorded facet is retained so that every later fetch of the
        same variable over the same places defaults to it, and a cohort
        fetched in several calls is never blended across sources.

        Args:
            variable_dcid: The statistical variable DCID.
            scope: The places the fetch covered.
            facet_id: The facet the variable was served from.
        """
        self._locked_facets.setdefault((variable_dcid, scope), facet_id)

    def get_locked_facet(
        self, variable_dcid: str, scope: FacetScope
    ) -> str | None:
        """Returns the facet a variable is locked to over a scope.

        Args:
            variable_dcid: The statistical variable DCID.
            scope: The places the fetch covers.

        Returns:
            The first facet recorded for the variable over `scope`, or `None`
            when no fetch of it over `scope` has recorded a facet.
        """
        return self._locked_facets.get((variable_dcid, scope))
