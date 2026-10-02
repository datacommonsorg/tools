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
"""Extracts the places, variables, and date ranges queried in a turn.

Each `QueryScope` (a "scope") records the entities and variables that one
data query or chart in the turn was about: the places (either specific
places or a parent place and child place type, such as every county in a
state), the statistical variables, and the observation date range, with
each place and variable DCID mapped to its display name.

These scopes are stored in the `Transcript` (on each turn's `state_slots`)
and included in the context of later turns so follow-up questions can
resolve references such as "them" or "that period" to the exact DCIDs and
dates from earlier turns.

To keep unverified model output out of the conversation history, a scope
only includes DCIDs that were confirmed by a successful MCP tool call
(either returned in a tool result or passed to an observation call that
returned data rows). DCIDs that appear only in model-written chart
configurations, or in search or observation calls that returned no data,
are not included.

A scope is built for each observation call that returned data and for each
displayed chart. Scopes are deduplicated in order of appearance, with
observation calls first, and capped at `MAX_SCOPES_PER_TURN`.
"""

import logging
import re
from collections.abc import Iterable, Iterator, Sequence
from typing import Any, TypeIs

from pydantic import ValidationError

from narratives_agent.mcp.data_utils import (
    has_observation_rows,
    parse_tool_result,
)
from narratives_agent.workflows.transcript import (
    DATE_PATTERN,
    DCID_PATTERN,
    MAX_DCID_CHARS,
    MAX_ENTRIES_PER_SCOPE,
    MAX_NAME_CHARS,
    MAX_PLACE_TYPE_CHARS,
    MAX_SCOPES_PER_TURN,
    PLACE_TYPE_PATTERN,
    ConversationStateSlots,
    QueryScope,
)

logger = logging.getLogger(__name__)

# Tool argument names that hold DCIDs in MCP tool calls.
_DCID_ARGUMENTS = (
    "variable_dcid",
    "variable_dcids",
    "place_dcid",
    "parent_place_dcid",
    "entity_dcids",
    "entities",
    "parent_entity_dcid",
)
# Tool result keys whose string values are DCIDs.
_DCID_RESULT_KEYS = ("dcid", "entity", "place", "variable")
# Keys that pair an entity's DCID with its display name in the same dict.
_ENTITY_ID_KEYS = ("dcid", "entity", "place")
_ENTITY_NAME_KEYS = ("name", "entityName", "entity_name", "displayName")
# Keys whose dict values map DCIDs directly to display names.
_NAME_MAPPING_KEYS = ("dcid_name_mappings", "dcidNameMappings")
# Maximum recursion depth when traversing an MCP tool result payload.
_MAX_PAYLOAD_DEPTH = 8
# Observation tools whose returned data rows confirm that their input DCIDs
# exist.
_OBSERVATION_TOOLS = (
    "get_observations",
    "get_child_observations",
    "get_multi_entity_observations",
)
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0e-\x1f\x7f]")


def _is_dcid(value: object) -> TypeIs[str]:
    """Returns True when `value` is a well-formed DCID."""
    return (
        isinstance(value, str)
        and len(value) <= MAX_DCID_CHARS
        and re.fullmatch(DCID_PATTERN, value) is not None
    )


def _is_place_type(value: object) -> TypeIs[str]:
    """Returns True when `value` is a well-formed place type."""
    return (
        isinstance(value, str)
        and len(value) <= MAX_PLACE_TYPE_CHARS
        and re.fullmatch(PLACE_TYPE_PATTERN, value) is not None
    )


def _is_date(value: object) -> TypeIs[str]:
    """Returns True when `value` is a year, a year and month, or a full date."""
    return (
        isinstance(value, str) and re.fullmatch(DATE_PATTERN, value) is not None
    )


def _strings(value: object) -> Iterator[str]:
    """Yields the strings in a scalar, a list, or a dict of lists."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                yield item
    elif isinstance(value, dict):
        for item in value.values():
            if isinstance(item, list):
                yield from _strings(item)


def _argument_dcids(arguments: dict[str, Any]) -> Iterator[str]:
    """Yields the well-formed DCIDs among a tool call's arguments."""
    for key in _DCID_ARGUMENTS:
        for value in _strings(arguments.get(key)):
            if _is_dcid(value):
                yield value


def _clean_name(value: object) -> str:
    """Strips control characters and collapses whitespace in a display name."""
    if not isinstance(value, str):
        return ""
    return " ".join(_CONTROL_CHARACTERS.sub("", value).split())


def _index_payload(
    payload: object, names: dict[str, str], seen: set[str], depth: int = 0
) -> None:
    """Records the DCIDs and display names found in a result payload."""
    if depth > _MAX_PAYLOAD_DEPTH:
        return
    if isinstance(payload, list):
        for item in payload:
            _index_payload(item, names, seen, depth + 1)
        return
    if not isinstance(payload, dict):
        return
    for key in _NAME_MAPPING_KEYS:
        mapping = payload.get(key)
        if isinstance(mapping, dict):
            for dcid, raw_name in mapping.items():
                cleaned = _clean_name(raw_name)
                if _is_dcid(dcid) and cleaned:
                    names.setdefault(dcid, cleaned)
                    seen.add(dcid)
    # Variable metadata payloads map each variable DCID to a dict with "name".
    variables = payload.get("variables")
    if isinstance(variables, dict):
        for dcid, info in variables.items():
            if _is_dcid(dcid) and isinstance(info, dict):
                seen.add(dcid)
                cleaned = _clean_name(info.get("name"))
                if cleaned:
                    names.setdefault(dcid, cleaned)
    entity = next(
        (payload[key] for key in _ENTITY_ID_KEYS if _is_dcid(payload.get(key))),
        None,
    )
    name = next(
        (
            cleaned
            for key in _ENTITY_NAME_KEYS
            if (cleaned := _clean_name(payload.get(key)))
        ),
        None,
    )
    if entity is not None and name is not None:
        names.setdefault(entity, name)
    for key in _DCID_RESULT_KEYS:
        if _is_dcid(payload.get(key)):
            seen.add(payload[key])
    for value in payload.values():
        _index_payload(value, names, seen, depth + 1)


def _payload_dates(payload: dict[str, Any]) -> Iterator[str]:
    """Yields the observation dates in a result payload.

    MCP server 1.3.0 returns `data.rows[].date`, whereas 1.2.1 returned
    `place_observations[].time_series` as `[date, value]` pairs.
    """
    data = payload.get("data")
    rows = data.get("rows") if isinstance(data, dict) else None
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and _is_date(row.get("date")):
            yield row["date"]
    entries = payload.get("place_observations")
    for entry in entries if isinstance(entries, list) else []:
        series = entry.get("time_series") if isinstance(entry, dict) else None
        for point in series if isinstance(series, list) else []:
            if isinstance(point, list) and point and _is_date(point[0]):
                yield point[0]


def _date_range(
    payload: dict[str, Any], arguments: dict[str, Any]
) -> tuple[str, str] | None:
    """Returns the min-to-max date range from the result or the arguments."""
    dates = list(_payload_dates(payload))
    if dates:
        return min(dates), max(dates)
    start = arguments.get("date_range_start")
    end = arguments.get("date_range_end")
    start = start if _is_date(start) else None
    end = end if _is_date(end) else None
    if start or end:
        return (start or end or "", end or start or "")
    date = arguments.get("date")
    return (date, date) if _is_date(date) else None


def _display_name(dcid: str, names: dict[str, str]) -> str:
    """Returns the sanitized display name for a DCID, or the DCID itself.

    Control characters and newlines are stripped and runs of whitespace are
    collapsed to a single space so that display names can be safely formatted
    onto single lines in model prompts.
    """
    name = _clean_name(names.get(dcid, ""))
    return (name or dcid)[:MAX_NAME_CHARS]


def _entities(dcids: Iterable[str], names: dict[str, str]) -> dict[str, str]:
    """Maps DCIDs to display names, deduplicated and capped in length."""
    entities: dict[str, str] = {}
    for dcid in dcids:
        if len(entities) == MAX_ENTRIES_PER_SCOPE:
            break
        if dcid not in entities:
            entities[dcid] = _display_name(dcid, names)
    return entities


def _scope(
    names: dict[str, str],
    *,
    variables: Sequence[str],
    places: Sequence[str] = (),
    parent: object = None,
    child_type: object = None,
    date_range: tuple[str, str] | None = None,
) -> QueryScope | None:
    """Builds a `QueryScope`, or returns `None` if required fields are missing.

    A scope requires at least one statistical variable and either explicit
    places or a complete cohort (both a valid parent place DCID and a valid
    child place type).
    """
    has_cohort = _is_dcid(parent) and _is_place_type(child_type)
    if not variables or not (places or has_cohort):
        return None
    try:
        return QueryScope(
            places=_entities(places, names),
            parent_place=(
                _entities([str(parent)], names) if has_cohort else None
            ),
            child_place_type=str(child_type) if has_cohort else None,
            variables=_entities(variables, names),
            date_range=date_range,
        )
    except ValidationError as error:
        logger.warning(
            "Dropped a state-slot scope that failed validation: %d errors",
            error.error_count(),
        )
        return None


def _observation_scope(
    call: dict[str, Any], names: dict[str, str]
) -> QueryScope | None:
    """Builds a `QueryScope` from an observation call that returned rows."""
    payload = parse_tool_result(call.get("result"))
    if payload is None or not has_observation_rows(payload):
        return None
    arguments = call.get("arguments")
    if not isinstance(arguments, dict):
        return None
    variable = arguments.get("variable_dcid")
    if not _is_dcid(variable):
        return None
    variables = [str(variable)]
    date_range = _date_range(payload, arguments)
    match call.get("name"):
        case "get_observations":
            place = arguments.get("place_dcid")
            places = [str(place)] if _is_dcid(place) else []
            return _scope(
                names, variables=variables, places=places, date_range=date_range
            )
        case "get_child_observations":
            return _scope(
                names,
                variables=variables,
                parent=arguments.get("parent_place_dcid"),
                child_type=arguments.get("child_place_type"),
                date_range=date_range,
            )
        case "get_multi_entity_observations":
            places = [
                value
                for value in _strings(arguments.get("entities"))
                if _is_dcid(value)
            ]
            return _scope(
                names,
                variables=variables,
                places=places,
                parent=arguments.get("parent_entity_dcid"),
                child_type=arguments.get("child_entity_type"),
                date_range=date_range,
            )
    return None


def _chart_scopes(
    chart_config: dict[str, Any], names: dict[str, str], seen: set[str]
) -> Iterator[QueryScope]:
    """Yields a `QueryScope` per displayed chart, keeping confirmed DCIDs."""
    if not chart_config.get("should_render") or chart_config.get("hide_charts"):
        return
    charts = chart_config.get("charts")
    # The legacy single-chart format stores the chart fields at the top level.
    items = charts if isinstance(charts, list) and charts else [chart_config]
    for chart in items:
        if not isinstance(chart, dict):
            continue
        variables = [
            dcid
            for dcid in _strings(chart.get("variable_dcids"))
            if dcid in seen
        ]
        places = [
            dcid for dcid in _strings(chart.get("place_dcids")) if dcid in seen
        ]
        parent = chart.get("parent_place")
        date = chart.get("date")
        scope = _scope(
            names,
            variables=variables,
            places=places,
            parent=parent
            if isinstance(parent, str) and parent in seen
            else None,
            child_type=chart.get("child_place_type"),
            date_range=(date, date) if _is_date(date) else None,
        )
        if scope is not None:
            yield scope


def extract_state_slots(
    tool_calls: Sequence[dict[str, Any]], chart_config: dict[str, Any]
) -> ConversationStateSlots:
    """Extracts the query scopes (places, variables, and dates) from a turn.

    Args:
        tool_calls: The turn's tool-call records, each with `name`,
            `arguments`, `result`, and `status`. Failed calls are ignored.
        chart_config: The chart configuration sent to the browser.

    Returns:
        The deduplicated scopes, with observation calls first, capped at
        `MAX_SCOPES_PER_TURN`.
    """
    successful = [
        call
        for call in tool_calls
        if isinstance(call, dict) and call.get("status") == "success"
    ]
    names: dict[str, str] = {}
    seen: set[str] = set()
    for call in successful:
        payload = parse_tool_result(call.get("result"))
        _index_payload(payload, names, seen)
        arguments = call.get("arguments")
        if (
            isinstance(arguments, dict)
            and call.get("name") in _OBSERVATION_TOOLS
            and has_observation_rows(payload)
        ):
            seen.update(_argument_dcids(arguments))
    candidates = [
        scope
        for call in successful
        if (scope := _observation_scope(call, names)) is not None
    ]
    candidates.extend(_chart_scopes(chart_config, names, seen))
    scopes: dict[str, QueryScope] = {}
    for scope in candidates:
        if len(scopes) == MAX_SCOPES_PER_TURN:
            break
        scopes.setdefault(scope.model_dump_json(), scope)
    return ConversationStateSlots(scopes=list(scopes.values()))
