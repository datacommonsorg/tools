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
"""Builds the places, variables, and date ranges a turn retrieved.

Constructs deduplicated `QueryScope` entries from the fetched `CachedTable`
instances and displayed chart configurations for the signed `Transcript`.
"""

import logging
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence, Set
from typing import TypeIs

from pydantic import ValidationError

from narratives_agent.analytics.tables import ObservationTable
from narratives_agent.json_value import JsonValue
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
from narratives_agent.workflows.turn_cache import (
    DERIVED_TABLE_PREFIX,
    CachedTable,
)

logger = logging.getLogger(__name__)

# Matches ASCII control characters that must be stripped from display names.
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0e-\x1f\x7f]")


def _is_dcid(value: object) -> TypeIs[str]:
    """Returns True when `value` is a well-formed DCID.

    Args:
        value: The candidate DCID object to check.

    Returns:
        `True` when `value` is a string matching `DCID_PATTERN` within
        `MAX_DCID_CHARS`.
    """
    return (
        isinstance(value, str)
        and len(value) <= MAX_DCID_CHARS
        and re.fullmatch(DCID_PATTERN, value) is not None
    )


def _is_place_type(value: object) -> TypeIs[str]:
    """Returns True when `value` is a well-formed place type.

    Args:
        value: The candidate place-type object to check.

    Returns:
        `True` when `value` is a string matching `PLACE_TYPE_PATTERN` within
        `MAX_PLACE_TYPE_CHARS`.
    """
    return (
        isinstance(value, str)
        and len(value) <= MAX_PLACE_TYPE_CHARS
        and re.fullmatch(PLACE_TYPE_PATTERN, value) is not None
    )


def _is_date(value: object) -> TypeIs[str]:
    """Returns True when `value` is a year, a year and month, or a full date.

    Args:
        value: The candidate date object to check.

    Returns:
        `True` when `value` is a string matching `DATE_PATTERN`.
    """
    return (
        isinstance(value, str) and re.fullmatch(DATE_PATTERN, value) is not None
    )


def _iter_strings(value: object) -> Iterator[str]:
    """Yields the strings in a scalar or a list.

    Args:
        value: A string, a list of candidate items, or any other object.

    Yields:
        Each string item in `value`.
    """
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                yield item


def _clean_name(value: object) -> str:
    """Strips control characters and collapses whitespace in a display name.

    Args:
        value: The raw display-name value to sanitize.

    Returns:
        The single-line cleaned string, or `""` when `value` is not a string
        or contains only control characters and whitespace.
    """
    if not isinstance(value, str):
        return ""
    return " ".join(_CONTROL_CHARACTERS.sub("", value).split())


def _build_entity_map(
    dcids: Iterable[str], names: Mapping[str, str]
) -> dict[str, str]:
    """Maps DCIDs to display names, deduplicated and capped in length.

    Args:
        dcids: Entity DCIDs in priority order.
        names: Mapping of entity DCIDs to raw display names.

    Returns:
        A dictionary of up to `MAX_ENTRIES_PER_SCOPE` DCIDs mapped to their
        sanitized display names (or to the DCID itself when unnamed).
    """
    entities: dict[str, str] = {}
    for dcid in dcids:
        if len(entities) == MAX_ENTRIES_PER_SCOPE:
            break
        if dcid not in entities:
            name = _clean_name(names.get(dcid, ""))
            entities[dcid] = (name or dcid)[:MAX_NAME_CHARS]
    return entities


def _build_scope(
    names: Mapping[str, str],
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

    Args:
        names: Mapping of entity DCIDs to display names.
        variables: Grounded variable DCIDs for the scope.
        places: Grounded place DCIDs for the scope.
        parent: Optional parent place DCID for a cohort scope.
        child_type: Optional child place type for a cohort scope.
        date_range: Optional `(earliest_date, latest_date)` span for the scope.

    Returns:
        The validated `QueryScope`, or `None` when required fields are missing
        or fail validation.
    """
    has_cohort = _is_dcid(parent) and _is_place_type(child_type)
    if not variables or not (places or has_cohort):
        return None
    try:
        return QueryScope(
            places=_build_entity_map(places, names),
            parent_place=(
                _build_entity_map([str(parent)], names) if has_cohort else None
            ),
            child_place_type=str(child_type) if has_cohort else None,
            variables=_build_entity_map(variables, names),
            date_range=date_range,
        )
    except ValidationError as error:
        logger.warning(
            "Dropped a state-slot scope that failed validation: %d errors",
            error.error_count(),
        )
        return None


def _is_derived(cached: CachedTable) -> bool:
    """Returns True for a table that a processing step derived.

    The check reads the table id, which the server assigns, rather than the
    variable DCID, which the specification may set to any name.

    Args:
        cached: The cached table entry to inspect.

    Returns:
        `True` when `cached.table_id` starts with `DERIVED_TABLE_PREFIX`.
    """
    return cached.table_id.startswith(DERIVED_TABLE_PREFIX)


def _build_table_scope(
    table: ObservationTable, names: Mapping[str, str]
) -> QueryScope | None:
    """Builds the scope of one fetched table.

    A child-place table is recorded as a cohort of its parent and child
    type; any other table lists the places that have data. The date range
    spans the table's rows.

    Args:
        table: The fetched observation table.
        names: Mapping of entity DCIDs to display names.

    Returns:
        The table's `QueryScope`, or `None` when the table has no rows or no
        valid variable and place/cohort.
    """
    if not table.rows or not _is_dcid(table.variable_dcid):
        return None
    dates = [row.date for row in table.rows if _is_date(row.date)]
    date_range = (min(dates), max(dates)) if dates else None
    has_cohort = _is_dcid(table.parent_place_dcid) and _is_place_type(
        table.child_place_type
    )
    # `table.places_with_data` is already sorted and deduplicated by
    # `ObservationTable`, so `_build_entity_map` caps places in sorted DCID
    # order.
    return _build_scope(
        names,
        variables=[table.variable_dcid],
        places=()
        if has_cohort
        else [p for p in table.places_with_data if _is_dcid(p)],
        parent=table.parent_place_dcid if has_cohort else None,
        child_type=table.child_place_type if has_cohort else None,
        date_range=date_range,
    )


def _iter_chart_scopes(
    chart_config: Mapping[str, JsonValue],
    names: Mapping[str, str],
    known: Set[str],
) -> Iterator[QueryScope]:
    """Yields a `QueryScope` per displayed chart, keeping known DCIDs only.

    Args:
        chart_config: The chart configuration sent to the browser.
        names: Mapping of grounded entity DCIDs to display names.
        known: Set of grounded variable and place DCIDs from fetched tables.

    Yields:
        A `QueryScope` for each displayed chart that retains at least one
        grounded variable and place or cohort.
    """
    if not chart_config.get("should_render") or chart_config.get("hide_charts"):
        return
    charts = chart_config.get("charts")
    # The legacy single-chart format stores the chart fields at the top level.
    items: Sequence[JsonValue | Mapping[str, JsonValue]] = (
        charts if isinstance(charts, list) and charts else [chart_config]
    )
    for chart in items:
        if not isinstance(chart, Mapping):
            continue
        variables = [
            dcid
            for dcid in _iter_strings(chart.get("variable_dcids"))
            if dcid in known
        ]
        places = [
            dcid
            for dcid in _iter_strings(chart.get("place_dcids"))
            if dcid in known
        ]
        parent = chart.get("parent_place")
        date = chart.get("date")
        scope = _build_scope(
            names,
            variables=variables,
            places=places,
            parent=parent
            if isinstance(parent, str) and parent in known
            else None,
            child_type=chart.get("child_place_type"),
            date_range=(date, date) if _is_date(date) else None,
        )
        if scope is not None:
            yield scope


def build_state_slots(
    tables: Sequence[CachedTable], chart_config: Mapping[str, JsonValue]
) -> ConversationStateSlots:
    """Builds the query scopes (places, variables, and dates) of a turn.

    Args:
        tables: The cached tables the turn's specification used, in order of
            first use, including any derived tables.
        chart_config: The chart configuration sent to the browser.

    Returns:
        The deduplicated scopes, with one per fetched table first and then
        one per displayed chart, capped at `MAX_SCOPES_PER_TURN`.
    """
    names: dict[str, str] = {}
    known: set[str] = set()
    fetched = [cached.table for cached in tables if not _is_derived(cached)]
    for table in fetched:
        names.setdefault(table.variable_dcid, table.variable_name)
        known.add(table.variable_dcid)
        for dcid, name in table.place_names.items():
            names.setdefault(dcid, name)
            known.add(dcid)
        # A row's place may be missing from `place_names`; its row still
        # carries the place's display name.
        for row in table.rows:
            if _is_dcid(row.place_dcid):
                names.setdefault(row.place_dcid, row.place_name)
                known.add(row.place_dcid)
        if table.parent_place_dcid is not None:
            known.add(table.parent_place_dcid)
    candidates = [
        scope
        for table in fetched
        if (scope := _build_table_scope(table, names)) is not None
    ]
    candidates.extend(_iter_chart_scopes(chart_config, names, known))
    scopes: dict[str, QueryScope] = {}
    for scope in candidates:
        if len(scopes) == MAX_SCOPES_PER_TURN:
            break
        scopes.setdefault(scope.model_dump_json(), scope)
    return ConversationStateSlots(scopes=list(scopes.values()))


__all__ = ["build_state_slots"]
