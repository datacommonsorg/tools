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
"""Requests variable metadata for the fetched tables a specification reads.

When no `get_variable_metadata` call has described a fetched table's facet,
the table cites the inline observation source, which names no provider,
dataset, date range, or license. Before a specification runs, the server
requests that metadata for the tables it references, best effort, and
records it in `TurnCache`. These requests are not model tool calls: they
produce no tool-call record.
"""

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from narratives_agent.analytics.tables import ObservationTable
from narratives_agent.json_value import JsonObject
from narratives_agent.mcp import client as mcp_client
from narratives_agent.mcp.capabilities import (
    TOOL_GET_VARIABLE_METADATA,
    Capabilities,
)
from narratives_agent.workflows.specification import AnalysisSpecification
from narratives_agent.workflows.turn_cache import TurnCache

__all__ = ["backfill_variable_metadata"]

logger = logging.getLogger(__name__)

# `get_variable_metadata` rejects a call whose `variable_dcids` or
# `entity_dcids` is empty or holds more than 10 items ("cannot exceed 10");
# the input schema it lists in `tools/list` states no bound.
_MAX_METADATA_VARIABLES = 10
_MAX_METADATA_ENTITIES = 10
# At most this many backfill calls run at once. A specification reads few
# tables, so a typical backfill completes in one wave of calls.
_MAX_CONCURRENT_BACKFILL_CALLS = 8
# One budget covers every backfill call before a specification runs. At
# half of `_MCP_TOOLS_TIMEOUT_SECONDS` (20 s), it bounds the delay that the
# backfill can add to processing.
_BACKFILL_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class _BackfillTarget:
    """A fetched table's variable and facet, and the places to describe.

    Attributes:
        variable_dcid: The table's variable.
        facet_id: The facet that served the table.
        entity_dcids: The table's first places, in row order.
    """

    variable_dcid: str
    facet_id: str
    entity_dcids: tuple[str, ...]


@dataclass(frozen=True)
class _MetadataRequest:
    """The arguments of one `get_variable_metadata` call.

    Attributes:
        variable_dcids: The variables to describe.
        entity_dcids: The places whose facets the response describes.
    """

    variable_dcids: tuple[str, ...]
    entity_dcids: tuple[str, ...]

    def build_arguments(self) -> JsonObject:
        """Returns the MCP tool arguments of the call."""
        return {
            "variable_dcids": list(self.variable_dcids),
            "entity_dcids": list(self.entity_dcids),
        }


async def backfill_variable_metadata(
    specification: AnalysisSpecification,
    cache: TurnCache,
    capabilities: Capabilities,
) -> None:
    """Records variable metadata for the fetched tables a specification reads.

    Each referenced fetched table with rows and a facet id, whose variable
    and facet have no metadata and were not requested earlier in the turn,
    is requested once. Each successful response is recorded with
    `TurnCache.record_variable_metadata`, which applies it to the fetched
    tables, so the specification's results cite the enriched sources. A
    failed or timed-out call is logged as a warning and leaves its tables
    citing the inline source; no MCP failure propagates.

    Args:
        specification: The specification about to run.
        cache: The turn's cache, which receives the metadata and records
            which variables and facets were requested.
        capabilities: The MCP server's tools; nothing is requested when it
            does not provide `get_variable_metadata`.
    """
    if not capabilities.supports_source_attribution:
        return
    targets = _select_targets(specification, cache)
    if not targets:
        return
    for target in targets:
        cache.mark_metadata_requested(target.variable_dcid, target.facet_id)
    requests = _batch_requests(targets)
    logger.info(
        "Requesting variable metadata: %d tables, %d calls",
        len(targets),
        len(requests),
    )
    await _run_requests(requests, cache)


def _select_targets(
    specification: AnalysisSpecification, cache: TurnCache
) -> list[_BackfillTarget]:
    """Returns the referenced tables whose metadata is still to request.

    The enrichment index is read by exact `(variable, facet)` key, because
    `VariableMetadataEnrichment.facet` falls back to another variable's
    entry for the same facet, which has no date range.
    """
    targets: dict[tuple[str, str], _BackfillTarget] = {}
    for table_id in specification.list_referenced_table_ids():
        entry = cache.get(table_id)
        if entry is None:
            continue
        table = entry.table
        # Metadata for a table without a facet id cannot be matched to the
        # facet that served it.
        if not table.rows or table.facet_id is None:
            continue
        key = (table.variable_dcid, table.facet_id)
        if (
            key in targets
            or key in cache.enrichment.facets
            or cache.has_requested_metadata(*key)
        ):
            continue
        targets[key] = _BackfillTarget(
            variable_dcid=table.variable_dcid,
            facet_id=table.facet_id,
            entity_dcids=_sample_entities(table),
        )
    return list(targets.values())


def _sample_entities(table: ObservationTable) -> tuple[str, ...]:
    """Returns the table's first places with data, at most the tool's limit.

    Each sampled place has observations under the table's facet.
    """
    return table.places_with_data[:_MAX_METADATA_ENTITIES]


def _batch_requests(
    targets: Sequence[_BackfillTarget],
) -> list[_MetadataRequest]:
    """Groups targets that sample the same places into calls within limits."""
    variables_by_entities: dict[tuple[str, ...], list[str]] = {}
    for target in targets:
        variables = variables_by_entities.setdefault(target.entity_dcids, [])
        if target.variable_dcid not in variables:
            variables.append(target.variable_dcid)
    return [
        _MetadataRequest(
            variable_dcids=tuple(
                variables[start : start + _MAX_METADATA_VARIABLES]
            ),
            entity_dcids=entity_dcids,
        )
        for entity_dcids, variables in variables_by_entities.items()
        for start in range(0, len(variables), _MAX_METADATA_VARIABLES)
    ]


async def _run_requests(
    requests: Sequence[_MetadataRequest], cache: TurnCache
) -> None:
    """Runs the calls concurrently under one shared timeout.

    The timeout cancels the calls still running; the responses already
    recorded are kept.
    """
    limit = asyncio.Semaphore(_MAX_CONCURRENT_BACKFILL_CALLS)
    try:
        async with (
            asyncio.timeout(_BACKFILL_TIMEOUT_SECONDS),
            asyncio.TaskGroup() as group,
        ):
            for request in requests:
                group.create_task(_run_request(request, cache, limit))
    except TimeoutError as error:
        logger.warning(
            "Variable metadata backfill for %s did not finish within %.0f "
            "seconds (%s); tables without a response cite the inline source",
            [dcid for request in requests for dcid in request.variable_dcids],
            _BACKFILL_TIMEOUT_SECONDS,
            type(error).__name__,
        )


async def _run_request(
    request: _MetadataRequest, cache: TurnCache, limit: asyncio.Semaphore
) -> None:
    """Runs one call and records its response, or logs its failure.

    A failure is handled here, so it does not cancel the sibling calls.
    """
    try:
        async with limit:
            result = await mcp_client.async_call_tool(
                TOOL_GET_VARIABLE_METADATA, request.build_arguments()
            )
    except (mcp_client.McpToolError, mcp_client.McpTransportError) as error:
        logger.warning(
            "Variable metadata backfill for %s failed with %s; the tables "
            "cite the inline source",
            list(request.variable_dcids),
            type(error).__name__,
        )
        return
    cache.record_variable_metadata(result)
