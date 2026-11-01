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
instances and resolved charts for the signed `Transcript`.
"""

import logging
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence, Set
from typing import TypeIs

from pydantic import ValidationError

from narratives_agent.analytics.tables import ObservationTable
from narratives_agent.workflows.charts import (
    ChildCohort,
    PlaceList,
    ResolvedBarChart,
    ResolvedChart,
    ResolvedHighlightChart,
    ResolvedLineChart,
    ResolvedMapChart,
    ResolvedRankingChart,
    ResolvedScatterChart,
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
    child place type). A complete cohort takes the place of `places`, so a
    scope never records both.

    Args:
        names: Mapping of entity DCIDs to display names.
        variables: Grounded variable DCIDs for the scope.
        places: Grounded place DCIDs for the scope, ignored when the scope
            has a complete cohort.
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
            places=_build_entity_map(() if has_cohort else places, names),
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
    # `table.places_with_data` is already sorted and deduplicated by
    # `ObservationTable`, so `_build_entity_map` caps places in sorted DCID
    # order.
    return _build_scope(
        names,
        variables=[table.variable_dcid],
        places=[p for p in table.places_with_data if _is_dcid(p)],
        parent=table.parent_place_dcid,
        child_type=table.child_place_type,
        date_range=date_range,
    )


def _read_chart_places(
    chart: ResolvedChart,
) -> tuple[tuple[str, ...], ChildCohort | None]:
    """Returns the places a resolved chart draws, or the cohort it draws.

    Args:
        chart: A resolved chart of any kind.

    Returns:
        The chart's explicit place DCIDs and None, or no places and the
        cohort it draws.
    """
    match chart:
        case ResolvedLineChart(scope=scope) | ResolvedBarChart(scope=scope):
            if isinstance(scope, PlaceList):
                return scope.place_dcids, None
            return (), scope
        case ResolvedHighlightChart(place_dcid=place_dcid):
            return (place_dcid,), None
        case (
            ResolvedRankingChart(cohort=cohort)
            | ResolvedMapChart(cohort=cohort)
            | ResolvedScatterChart(cohort=cohort)
        ):
            return (), cohort


def _iter_chart_scopes(
    charts: Sequence[ResolvedChart],
    names: Mapping[str, str],
    known: Set[str],
) -> Iterator[QueryScope]:
    """Yields a `QueryScope` per emitted chart, keeping known DCIDs only.

    Args:
        charts: The resolved charts emitted to the browser.
        names: Mapping of grounded entity DCIDs to display names.
        known: Set of grounded variable and place DCIDs from fetched tables.

    Yields:
        A `QueryScope` for each emitted chart that retains at least one
        grounded variable and place or cohort.
    """
    for chart in charts:
        places, cohort = _read_chart_places(chart)
        parent = cohort.parent_place if cohort is not None else None
        date = None if isinstance(chart, ResolvedLineChart) else chart.date
        scope = _build_scope(
            names,
            variables=[dcid for dcid in chart.variable_dcids if dcid in known],
            places=[dcid for dcid in places if dcid in known],
            parent=parent if parent in known else None,
            child_type=cohort.child_place_type if cohort is not None else None,
            date_range=(date, date) if _is_date(date) else None,
        )
        if scope is not None:
            yield scope


def build_state_slots(
    tables: Sequence[CachedTable], charts: Sequence[ResolvedChart] = ()
) -> ConversationStateSlots:
    """Builds the query scopes (places, variables, and dates) of a turn.

    Args:
        tables: The cached tables the turn's specification used, in order of
            first use, including any derived tables.
        charts: The resolved charts emitted to the browser.

    Returns:
        The deduplicated scopes, with one per fetched table first and then
        one per emitted chart, capped at `MAX_SCOPES_PER_TURN`.
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
    candidates.extend(_iter_chart_scopes(charts, names, known))
    # Scopes compare by value, and dict equality ignores key order, so two
    # scopes listing the same places in a different order are one scope.
    scopes: list[QueryScope] = []
    for scope in candidates:
        if len(scopes) == MAX_SCOPES_PER_TURN:
            break
        if scope not in scopes:
            scopes.append(scope)
    return ConversationStateSlots(scopes=scopes)


__all__ = ["build_state_slots"]
