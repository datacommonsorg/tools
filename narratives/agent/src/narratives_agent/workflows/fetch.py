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
"""Server-side observation fetch functions and their Gemini declarations.

Wraps the MCP observation tools (`get_observations`, `get_child_observations`,
`get_multi_entity_observations`), caches parsed `ObservationTable` instances in
`TurnCache`, returns typed `FetchResult` summaries and their model-facing
serialization, and generates the fetch functions' `FunctionDeclaration`s from
their request models.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from google.genai import types
from pydantic import BaseModel

from narratives_agent.analytics.provenance import AlternativeSource, Source
from narratives_agent.analytics.summarize import (
    SAMPLE_ROW_CAP,
    TableSummary,
    summarize_table,
)
from narratives_agent.analytics.tables import ObservationRow, ObservationTable
from narratives_agent.json_value import JsonObject, JsonValue
from narratives_agent.mcp import client as mcp_client
from narratives_agent.mcp.capabilities import (
    TOOL_GET_CHILD_OBSERVATIONS,
    TOOL_GET_MULTI_ENTITY_OBSERVATIONS,
    TOOL_GET_OBSERVATIONS,
)
from narratives_agent.mcp.observations import (
    ObservationPayloadError,
    ObservationPayloadOutline,
    merge_observation_payloads,
    parse_observation_table,
    read_payload_outline,
)
from narratives_agent.mcp.wire import (
    ChildObservationsToolArguments,
    MultiEntityObservationsToolArguments,
    ObservationsToolArguments,
)
from narratives_agent.workflows.fetch_requests import (
    COHORT_WINDOW_YEARS,
    FETCH_CHILD_OBSERVATIONS,
    FETCH_CHILD_OBSERVATIONS_DESCRIPTION,
    FETCH_MULTI_ENTITY_OBSERVATIONS,
    FETCH_MULTI_ENTITY_OBSERVATIONS_DESCRIPTION,
    FETCH_OBSERVATIONS,
    FETCH_OBSERVATIONS_DESCRIPTION,
    NAMED_PLACE_SERIES_LIMIT,
    FetchArgumentError,
    FetchChildObservationsRequest,
    FetchMultiEntityRequest,
    FetchObservationsRequest,
    FetchRequest,
    validate_date_selection_fields,
)
from narratives_agent.workflows.turn_cache import (
    CachedTable,
    FacetScope,
    TurnCache,
)

__all__ = [
    "DateRequest",
    "FetchResult",
    "build_fetch_declarations",
    "resolve_dates",
    "run_fetch",
    "serialize_fetch_result",
]

logger = logging.getLogger(__name__)

# At most this many per-place observation calls run concurrently per fetch.
_MAX_CONCURRENT_PLACE_FETCHES = 8
# Every named-place fetch of a variable shares one facet lock, so a cohort
# named across several calls is served from one source.
_NAMED_PLACES_SCOPE: FacetScope = ("named_places",)
# The model-facing notes on a multi-entity response that was not cached:
# one whose rows are keyed by entity role, and one with no rows to keep.
_ENTITY_ROLE_RESPONSE_NOTE = (
    "The response did not parse as place observations, so it was not cached "
    "as a table and has no table_id."
)
_EMPTY_PLACE_RESPONSE_NOTE = (
    "The response has no observations in the requested dates, so it was not "
    "cached as a table and has no table_id."
)


@dataclass(frozen=True)
class DateRequest:
    """The date arguments of one MCP observation call and its window.

    Attributes:
        date: The MCP `date` argument (`latest`, `all`, `range`, or a 4-digit
            year).
        date_range_start: Inclusive range start passed to the MCP tool, or
            `None` when `date` is not `range` or the range is open at the
            start.
        date_range_end: Inclusive range end passed to the MCP tool, or `None`
            when `date` is not `range` or the range is open at the end.
        date_range: The inclusive window applied to the parsed rows, as a
            safety net for a server that returns rows outside the requested
            range, or `None` when the request has no window (`latest`, `all`,
            or a range with an open bound).
    """

    date: str
    date_range_start: str | None = None
    date_range_end: str | None = None
    date_range: tuple[str, str] | None = None


@dataclass(frozen=True)
class FetchResult:
    """The outcome of a fetch function that cached an observation table.

    Attributes:
        table_id: Turn-scoped identifier (`t<n>`) assigned in `TurnCache`.
        summary: The discovery-time summary of the cached `ObservationTable`.
    """

    table_id: str
    summary: TableSummary


@dataclass(frozen=True)
class MultiEntityPayloadSummary:
    """Compact summary of a multi-entity response that is not a place table.

    Attributes:
        columns: The column names of the response's `data` table.
        has_place_column: Whether the rows are keyed by place. Such a
            response is summarized only when no row falls in the requested
            dates.
        row_count: The number of list rows in the response, before the
            requested dates are applied.
        sample_rows: The first rows, at most `SAMPLE_ROW_CAP`, as sent.
            A row's cells are typed by the variable's entity roles, so they
            stay JSON values.
        facet_id: The facet the response was served from, or `None` when the
            response names no facet.
        source: The source of that facet, or `None` when the response
            carries no provenance URL.
        alternative_sources: The other facets the server offered.
    """

    columns: tuple[str, ...]
    has_place_column: bool
    row_count: int
    sample_rows: tuple[tuple[JsonValue, ...], ...]
    facet_id: str | None
    source: Source | None
    alternative_sources: tuple[AlternativeSource, ...]


type FetchOutcome = FetchResult | MultiEntityPayloadSummary


def _get_current_year(today: datetime | None) -> int:
    """Returns the calendar year of `today`, or of now in UTC."""
    return (today or datetime.now(UTC)).year


def resolve_dates(
    date_mode: str | None,
    start_date: str | None,
    end_date: str | None,
    year: str | None,
    *,
    is_cohort: bool,
    today: datetime | None = None,
) -> DateRequest:
    """Turns the model's date arguments into an MCP date request.

    The MCP observation tools take `date` as `latest`, `all`, a single year,
    or `range` with `date_range_start` and `date_range_end`; the server
    accepts a range with one bound open. A `start_date` or `end_date` selects
    a range whatever the mode, and only a range with both bounds gets a
    client-side window. Otherwise an explicit mode is honored as given. When
    there is no mode and no bound, a named-place series fetches its full
    history and a cohort fetches the last `COHORT_WINDOW_YEARS` calendar years
    ending at the current year.

    Args:
        date_mode: `latest`, `all`, `range`, `year`, or `None` for the default.
            Any other value is rejected.
        start_date: The inclusive start of a range, `YYYY`, `YYYY-MM`, or
            `YYYY-MM-DD`, or `None` when the range is open at the start or
            no range is requested.
        end_date: The inclusive end of a range, in the same form, or `None`
            when the range is open at the end or no range is requested.
        year: The year a `year` fetch retrieves, or `None`; it is read only
            when `date_mode` is `year`.
        is_cohort: Whether the fetch is a cohort, which selects the bounded
            default window.
        today: The current time, for tests; now in UTC when `None`.

    Returns:
        The MCP date arguments and the client-side window.

    Raises:
        FetchArgumentError: If the mode is unknown, a bound or year is not a
            valid date, the range is inverted, or a mode lacks its argument.
    """
    validate_date_selection_fields(date_mode, start_date, end_date, year)
    if date_mode == "range" or start_date is not None or end_date is not None:
        window = (
            (start_date, end_date)
            if start_date is not None and end_date is not None
            else None
        )
        return DateRequest(
            date="range",
            date_range_start=start_date,
            date_range_end=end_date,
            date_range=window,
        )
    if date_mode == "year" and year is not None:
        return DateRequest(date=year, date_range=(year, year))
    if date_mode == "latest":
        return DateRequest(date="latest")
    if date_mode == "all" or not is_cohort:
        return DateRequest(date="all")
    end_year = _get_current_year(today)
    start_year = str(end_year - COHORT_WINDOW_YEARS + 1)
    return DateRequest(
        date="range",
        date_range_start=start_year,
        date_range_end=str(end_year),
        date_range=(start_year, str(end_year)),
    )


@contextmanager
def _convert_payload_errors() -> Iterator[None]:
    """Logs a malformed MCP payload and re-raises it as the model's error.

    Raises:
        FetchArgumentError: If the block raises `ObservationPayloadError`.
    """
    try:
        yield
    except ObservationPayloadError as error:
        logger.warning("Malformed MCP observation payload: %s", error)
        raise FetchArgumentError(str(error)) from error


def _read_served_facet_id(
    payload: JsonObject, variable_dcid: str
) -> str | None:
    """Returns the facet an observation payload says it was served from.

    Returns `None` for an empty response, which names no facet, and for a
    malformed one, which `merge_observation_payloads` rejects afterward
    with the error the model receives.
    """
    try:
        return read_payload_outline(payload, variable_dcid).facet_id
    except ObservationPayloadError:
        return None


async def _call_observations(
    tool: str,
    arguments: (
        ObservationsToolArguments
        | ChildObservationsToolArguments
        | MultiEntityObservationsToolArguments
    ),
    *,
    place_dcid: str | None = None,
) -> JsonObject:
    """Calls one MCP observation tool and returns its decoded payload.

    Raises:
        FetchArgumentError: If the tool reports an error, or the result does
            not decode to a JSON object. It names `place_dcid` when given.
        McpTransportError: If the request fails below the tool layer.
    """
    try:
        result = await mcp_client.async_call_tool(
            tool, arguments.model_dump(exclude_none=True)
        )
    except mcp_client.McpToolError as error:
        raise FetchArgumentError(error.message, place_dcid=place_dcid) from (
            error
        )
    payload = mcp_client.decode_tool_payload(result)
    if payload is None:
        raise FetchArgumentError(
            f"The {tool} result is not a readable observation payload.",
            place_dcid=place_dcid,
        )
    return payload


def _resolve_source_override(
    requested: str | None,
    cache: TurnCache,
    variable_dcid: str,
    scope: FacetScope,
) -> str | None:
    """Returns the facet a fetch asks for: the requested or the locked one."""
    return requested or cache.get_locked_facet(variable_dcid, scope)


def _store_table(
    cache: TurnCache,
    variable_dcid: str,
    scope: FacetScope,
    table: ObservationTable,
) -> FetchResult:
    """Caches a fetched table, locks its facet, and summarizes it."""
    table_id = cache.get_next_table_id()
    cache.store_fetched(CachedTable(table_id=table_id, table=table))
    if table.facet_id is not None:
        cache.lock_facet(variable_dcid, scope, table.facet_id)
    return FetchResult(table_id=table_id, summary=summarize_table(table))


def _serialize_source(source: Source) -> JsonObject:
    """Serializes a `Source` into its discovery-summary JSON object."""
    entry: JsonObject = {"name": source.name, "url": source.url}
    if source.license is not None:
        entry["license"] = source.license
    if source.provider is not None:
        entry["provider"] = source.provider
    if source.dataset is not None:
        entry["dataset"] = source.dataset
    if source.date_range is not None:
        entry["date_range"] = source.date_range
    return entry


def _serialize_alternative_source(alternative: AlternativeSource) -> JsonObject:
    """Serializes an `AlternativeSource` with snake_case keys (`source_id`)."""
    entry: JsonObject = {"source_id": alternative.facet_id}
    if alternative.provenance_url is not None:
        entry["provenance_url"] = alternative.provenance_url
    if alternative.measurement_method is not None:
        entry["measurement_method"] = alternative.measurement_method
    if alternative.observation_period is not None:
        entry["observation_period"] = alternative.observation_period
    if alternative.unit is not None:
        entry["unit"] = alternative.unit
    if alternative.places_found_count is not None:
        entry["places_found_count"] = alternative.places_found_count
    return entry


def _serialize_row(row: ObservationRow) -> JsonObject:
    """Serializes an `ObservationRow` for `sample_rows`."""
    return {
        "place_dcid": row.place_dcid,
        "place_name": row.place_name,
        "date": row.date,
        "value": row.value,
        "facet_id": row.facet_id,
    }


def _serialize_multi_entity_summary(
    summary: MultiEntityPayloadSummary,
) -> JsonObject:
    """Serializes a `MultiEntityPayloadSummary` for the model."""
    return {
        "table_id": None,
        "note": (
            _EMPTY_PLACE_RESPONSE_NOTE
            if summary.row_count == 0 or summary.has_place_column
            else _ENTITY_ROLE_RESPONSE_NOTE
        ),
        "columns": list(summary.columns),
        "row_count": summary.row_count,
        "sample_rows": [list(row) for row in summary.sample_rows],
        "facet_id": summary.facet_id,
        "source": (
            _serialize_source(summary.source)
            if summary.source is not None
            else None
        ),
        "alternative_sources": [
            _serialize_alternative_source(item)
            for item in summary.alternative_sources
        ],
    }


def serialize_fetch_result(result: FetchOutcome) -> JsonObject:
    """Serializes a `FetchOutcome` into the JSON object sent to the model.

    Args:
        result: The outcome `run_fetch` returned.

    Returns:
        For a `FetchResult`, the table summary with its `table_id`; for a
        `MultiEntityPayloadSummary`, the compact summary with a null
        `table_id` and a note that the response was not cached. Both use
        snake_case keys for the source and the alternative sources.
    """
    if isinstance(result, MultiEntityPayloadSummary):
        return _serialize_multi_entity_summary(result)
    summary = result.summary
    return {
        "table_id": result.table_id,
        "variable_dcid": summary.variable_dcid,
        "variable_name": summary.variable_name,
        "observation_count": summary.observation_count,
        "places_with_data_count": summary.places_with_data_count,
        "places_with_data": list(summary.places_with_data),
        "places_without_data_count": summary.places_without_data_count,
        "places_without_data": list(summary.places_without_data),
        "date_range": (
            list(summary.date_range) if summary.date_range is not None else None
        ),
        "source": (
            _serialize_source(summary.source)
            if summary.source is not None
            else None
        ),
        "facet_id": summary.facet_id,
        "unit": summary.unit,
        "scaling_factor": summary.scaling_factor,
        "measurement_method": summary.measurement_method,
        "observation_period": summary.observation_period,
        "alternative_sources": [
            _serialize_alternative_source(item)
            for item in summary.alternative_sources
        ],
        "value_range": (
            list(summary.value_range)
            if summary.value_range is not None
            else None
        ),
        "sample_rows": [_serialize_row(row) for row in summary.sample_rows],
    }


def _select_raised_failure(errors: ExceptionGroup[Exception]) -> Exception:
    """Returns the failure of a group of place calls to raise alone.

    A transport failure is chosen when there is one, because it aborts the
    turn; otherwise the first failure. The other failures are logged.
    """
    failures = list(errors.exceptions)
    selected = next(
        (
            failure
            for failure in failures
            if isinstance(failure, mcp_client.McpTransportError)
        ),
        failures[0],
    )
    if len(failures) > 1:
        logger.warning(
            "%d other concurrent place call(s) also failed: %s",
            len(failures) - 1,
            [str(failure) for failure in failures if failure is not selected],
        )
    return selected


async def _fetch_places_concurrently(
    places: list[str],
    fetch_place: Callable[[str], Awaitable[JsonObject]],
) -> list[JsonObject]:
    """Calls `fetch_place` for each place, at most a bounded number at once.

    Returns the payloads in the order of `places`. The first failure cancels
    the calls still running, and one failure is raised on its own.
    """
    concurrency_limit = asyncio.Semaphore(_MAX_CONCURRENT_PLACE_FETCHES)

    async def fetch_limited(place_dcid: str) -> JsonObject:
        async with concurrency_limit:
            return await fetch_place(place_dcid)

    try:
        async with asyncio.TaskGroup() as group:
            tasks = [
                group.create_task(fetch_limited(place)) for place in places
            ]
    except ExceptionGroup as errors:
        # The task group has canceled the other calls; callers handle one
        # exception, not a group.
        raise _select_raised_failure(errors) from None
    return [task.result() for task in tasks]


async def _fetch_place_payloads(
    request: FetchObservationsRequest,
    dates: DateRequest,
    override: str | None,
) -> list[tuple[str, JsonObject]]:
    """Fetches one payload per requested place, in request order.

    Without an `override`, the places are called one at a time until a
    response names the facet it was served from, and that facet locks the
    remaining calls. The locked calls run concurrently, at most
    `_MAX_CONCURRENT_PLACE_FETCHES` at a time. When no place names a facet,
    every place is called one at a time.

    Raises:
        FetchArgumentError: If a call fails at the tool layer, naming its
            place, or returns a result that is not a JSON object.
        McpTransportError: If a call fails below the tool layer.
    """

    async def fetch_place(
        place_dcid: str, source_override: str | None
    ) -> JsonObject:
        return await _call_observations(
            TOOL_GET_OBSERVATIONS,
            ObservationsToolArguments(
                variable_dcid=request.variable_dcid,
                place_dcid=place_dcid,
                date=dates.date,
                date_range_start=dates.date_range_start,
                date_range_end=dates.date_range_end,
                source_override=source_override,
            ),
            place_dcid=place_dcid,
        )

    payloads: list[tuple[str, JsonObject]] = []
    pending = list(request.place_dcids)
    while pending and override is None:
        place_dcid = pending.pop(0)
        payload = await fetch_place(place_dcid, None)
        payloads.append((place_dcid, payload))
        override = _read_served_facet_id(payload, request.variable_dcid)
    if pending:
        locked = override
        results = await _fetch_places_concurrently(
            pending, lambda place: fetch_place(place, locked)
        )
        payloads.extend(zip(pending, results, strict=True))
    return payloads


async def fetch_observations(
    request: FetchObservationsRequest, cache: TurnCache
) -> FetchResult:
    """Fetches one variable for named places.

    The places are fetched through `get_observations`, one call per place,
    and the per-place payloads are merged into one table from a single
    facet: `source_override`, the facet the variable's named-place fetches
    are locked to, or the facet the first answering place was served from.

    Args:
        request: Validated `FetchObservationsRequest`.
        cache: The turn's cache, which receives the `CachedTable`.

    Returns:
        The typed `FetchResult` holding the assigned `table_id` and
        `TableSummary`.

    Raises:
        FetchArgumentError: If a tool-layer MCP error occurs or the payload
            cannot be parsed into a table.
        McpTransportError: If an MCP request fails below the tool layer.
    """
    dates = resolve_dates(
        request.date_mode,
        request.start_date,
        request.end_date,
        request.year,
        is_cohort=len(request.place_dcids) > NAMED_PLACE_SERIES_LIMIT,
    )
    override = _resolve_source_override(
        request.source_override,
        cache,
        request.variable_dcid,
        _NAMED_PLACES_SCOPE,
    )
    payloads = await _fetch_place_payloads(request, dates, override)
    with _convert_payload_errors():
        table = parse_observation_table(
            merge_observation_payloads(payloads),
            variable_dcid=request.variable_dcid,
            requested_places=request.place_dcids,
            date_range=dates.date_range,
            enrichment=cache.enrichment,
        )
    return _store_table(
        cache, request.variable_dcid, _NAMED_PLACES_SCOPE, table
    )


async def fetch_child_observations(
    request: FetchChildObservationsRequest, cache: TurnCache
) -> FetchResult:
    """Fetches one variable across every child place of a parent.

    Args:
        request: Validated `FetchChildObservationsRequest`.
        cache: The turn's cache, which receives the `CachedTable`.

    Returns:
        The typed `FetchResult` holding the assigned `table_id` and
        `TableSummary`.

    Raises:
        FetchArgumentError: If a tool-layer MCP error occurs or the payload
            cannot be parsed into a table.
        McpTransportError: If the MCP request fails below the tool layer.
    """
    dates = resolve_dates(
        request.date_mode,
        request.start_date,
        request.end_date,
        request.year,
        is_cohort=True,
    )
    scope: FacetScope = (
        "children",
        request.parent_place_dcid,
        request.child_place_type,
    )
    payload = await _call_observations(
        TOOL_GET_CHILD_OBSERVATIONS,
        ChildObservationsToolArguments(
            variable_dcid=request.variable_dcid,
            parent_place_dcid=request.parent_place_dcid,
            child_place_type=request.child_place_type,
            date=dates.date,
            date_range_start=dates.date_range_start,
            date_range_end=dates.date_range_end,
            source_override=_resolve_source_override(
                request.source_override, cache, request.variable_dcid, scope
            ),
        ),
    )
    with _convert_payload_errors():
        table = parse_observation_table(
            payload,
            variable_dcid=request.variable_dcid,
            parent_place_dcid=request.parent_place_dcid,
            child_place_type=request.child_place_type,
            date_range=dates.date_range,
            enrichment=cache.enrichment,
        )
    return _store_table(cache, request.variable_dcid, scope, table)


def _summarize_outline(
    outline: ObservationPayloadOutline,
) -> MultiEntityPayloadSummary:
    """Builds the compact summary of a multi-entity response's outline."""
    return MultiEntityPayloadSummary(
        columns=outline.columns,
        has_place_column=outline.has_place_column,
        row_count=len(outline.rows),
        sample_rows=outline.rows[:SAMPLE_ROW_CAP],
        facet_id=outline.facet_id,
        source=outline.source,
        alternative_sources=outline.alternative_sources,
    )


async def fetch_multi_entity_observations(
    request: FetchMultiEntityRequest, cache: TurnCache
) -> FetchOutcome:
    """Fetches a relationship variable, such as bilateral trade or aid.

    The call passes through to `get_multi_entity_observations`. A response
    whose rows name a place is cached as a table like any other; a response
    keyed by entity role, or one with no rows, is returned as a
    `MultiEntityPayloadSummary` and not cached.

    Args:
        request: Validated `FetchMultiEntityRequest`.
        cache: The turn's cache, which receives a parsed `CachedTable`.

    Returns:
        The typed `FetchResult` or `MultiEntityPayloadSummary`.

    Raises:
        FetchArgumentError: If a tool-layer MCP error occurs or the payload
            is malformed.
        McpTransportError: If the MCP request fails below the tool layer.
    """
    dates = resolve_dates(
        request.date_mode,
        request.start_date,
        request.end_date,
        request.year,
        is_cohort=request.child_entity_type is not None,
    )
    scope: FacetScope = (
        "entities",
        *sorted(request.entities),
        request.parent_entity_property or "",
        request.parent_entity_dcid or "",
        request.child_entity_type or "",
    )
    payload = await _call_observations(
        TOOL_GET_MULTI_ENTITY_OBSERVATIONS,
        MultiEntityObservationsToolArguments(
            variable_dcid=request.variable_dcid,
            entities=request.entities,
            parent_entity_property=request.parent_entity_property,
            parent_entity_dcid=request.parent_entity_dcid,
            child_entity_type=request.child_entity_type,
            date=dates.date,
            date_range_start=dates.date_range_start,
            date_range_end=dates.date_range_end,
            source_override=_resolve_source_override(
                request.source_override, cache, request.variable_dcid, scope
            ),
        ),
    )
    with _convert_payload_errors():
        outline = read_payload_outline(payload, request.variable_dcid)
    compact = _summarize_outline(outline)
    if not outline.has_place_column:
        return compact
    with _convert_payload_errors():
        table = parse_observation_table(
            payload,
            variable_dcid=request.variable_dcid,
            parent_place_dcid=request.parent_entity_dcid,
            child_place_type=request.child_entity_type,
            date_range=dates.date_range,
            enrichment=cache.enrichment,
        )
    if not table.rows:
        return compact
    return _store_table(cache, request.variable_dcid, scope, table)


async def run_fetch(request: FetchRequest, cache: TurnCache) -> FetchOutcome:
    """Dispatches a validated `FetchRequest` to its fetch implementation.

    Fetches of one variable over the same places on one `TurnCache` must not
    overlap: each reads the locked facet before it calls MCP, so two
    overlapping fetches can each be served from a different facet.

    Args:
        request: The request `parse_fetch_request` returned.
        cache: The turn's cache, which receives any cached table.

    Returns:
        The outcome of the fetch function for the request's type.

    Raises:
        FetchArgumentError: If the fetch fails at the argument or tool layer.
        McpTransportError: If the MCP request fails below the tool layer.
    """
    if isinstance(request, FetchObservationsRequest):
        return await fetch_observations(request, cache)
    if isinstance(request, FetchChildObservationsRequest):
        return await fetch_child_observations(request, cache)
    return await fetch_multi_entity_observations(request, cache)


def _build_parameters_schema(model: type[BaseModel]) -> JsonObject:
    """Returns the JSON schema of a request model's parameters.

    The model's docstring documents it for developers. Pydantic copies it
    into the schema's top-level `description`, so it is removed; the
    model-facing text is the function description and the field
    descriptions.
    """
    schema: JsonObject = model.model_json_schema()
    schema.pop("description", None)
    return schema


def build_fetch_declarations() -> list[types.FunctionDeclaration]:
    """Builds Gemini `FunctionDeclaration`s from the fetch request models.

    Returns:
        One declaration per fetch function, in the order
        `fetch_observations`, `fetch_child_observations`, and
        `fetch_multi_entity_observations`, each with its model's parameter
        schema.
    """
    return [
        types.FunctionDeclaration(
            name=FETCH_OBSERVATIONS,
            description=FETCH_OBSERVATIONS_DESCRIPTION,
            parameters_json_schema=_build_parameters_schema(
                FetchObservationsRequest
            ),
        ),
        types.FunctionDeclaration(
            name=FETCH_CHILD_OBSERVATIONS,
            description=FETCH_CHILD_OBSERVATIONS_DESCRIPTION,
            parameters_json_schema=_build_parameters_schema(
                FetchChildObservationsRequest
            ),
        ),
        types.FunctionDeclaration(
            name=FETCH_MULTI_ENTITY_OBSERVATIONS,
            description=FETCH_MULTI_ENTITY_OBSERVATIONS_DESCRIPTION,
            parameters_json_schema=_build_parameters_schema(
                FetchMultiEntityRequest
            ),
        ),
    ]
