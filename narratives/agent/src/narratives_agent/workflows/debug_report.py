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
"""Builds structured turn debug reports from telemetry and cache state.

This module models the typed server debug report and constructs it from
operational turn telemetry and cached observation tables without exposing
untyped internal maps or sensitive conversation content.
"""

from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import Literal

from narratives_agent.analytics.summarize import SUMMARY_PLACE_LIST_CAP
from narratives_agent.analytics.tables import ObservationTable
from narratives_agent.gemini.schemas import QueryPattern
from narratives_agent.json_value import JsonObject
from narratives_agent.settings import DebugReportMode
from narratives_agent.telemetry import TurnTelemetry
from narratives_agent.workflows.turn_cache import (
    DERIVED_TABLE_PREFIX,
    CachedTable,
    TurnCache,
)

__all__ = [
    "DebugPlaceRef",
    "DebugReport",
    "DebugSourceRecord",
    "DebugTableRecord",
    "DebugTerminalState",
    "DebugTokenCall",
    "DebugTokenUsage",
    "SourceSelection",
    "build_debug_report",
    "should_emit_debug_report",
]

type DebugTerminalState = Literal["complete", "refused", "error"]
type SourceSelection = Literal["chosen", "server_default", "derived"]


def should_emit_debug_report(
    mode: DebugReportMode, *, request_debug: bool
) -> bool:
    """Returns whether the debug report should be emitted for a turn.

    Args:
        mode: The server's configured debug report mode.
        request_debug: Whether the client requested debug mode (?debug).

    Returns:
        False for "off", True for "on", and request_debug for "flag".
    """
    match mode:
        case "off":
            return False
        case "on":
            return True
        case "flag":
            return request_debug


@dataclass(frozen=True, kw_only=True)
class DebugTokenCall:
    """Token counts from a single model call within a turn."""

    phase: str
    model: str
    round_number: int | None
    prompt_token_count: int
    candidates_token_count: int
    thoughts_token_count: int
    total_token_count: int


@dataclass(frozen=True, kw_only=True)
class DebugTokenUsage:
    """Aggregated token usage and per-call token breakdown for a turn."""

    prompt_token_count: int
    candidates_token_count: int
    thoughts_token_count: int
    total_token_count: int
    calls: tuple[DebugTokenCall, ...]


@dataclass(frozen=True, kw_only=True)
class DebugPlaceRef:
    """Reference to a place entity in an observation table."""

    dcid: str
    name: str


@dataclass(frozen=True, kw_only=True)
class DebugSourceRecord:
    """Citation and provenance record for a data source."""

    name: str
    url: str
    license: str | None = None
    dataset: str | None = None
    provider: str | None = None
    date_range: str | None = None


@dataclass(frozen=True, kw_only=True)
class DebugTableRecord:
    """Summary of a cached observation table evaluated during the turn."""

    table_id: str
    used_in_answer: bool
    variable_dcid: str
    variable_name: str
    unit: str | None
    scaling_factor: float | None
    measurement_method: str | None
    observation_period: str | None
    parent_place_dcid: str | None
    child_place_type: str | None
    places_with_data_count: int
    places: tuple[DebugPlaceRef, ...]
    facet_id: str | None
    source_selection: SourceSelection
    source: DebugSourceRecord | None
    date_range: tuple[str, str] | None
    row_count: int


@dataclass(frozen=True, kw_only=True)
class DebugReport:
    """Structured operational and analytical debug report for a turn."""

    turn_id: str
    terminal_state: DebugTerminalState
    terminal_reason: str | None
    is_clarification: bool
    pattern: QueryPattern | None
    duration_ms: float
    phase_durations_ms: Mapping[str, float]
    nested_phases: Mapping[str, str]
    mcp_iterations: int
    scripts: tuple[str, ...]
    processing_retries: int
    charts_emitted: int
    charts_rejected: int
    tokens: DebugTokenUsage
    tables: tuple[DebugTableRecord, ...]

    def to_dict(self) -> JsonObject:
        """Serializes the report to a finite snake_case JSON object."""
        return {
            "turn_id": self.turn_id,
            "terminal_state": self.terminal_state,
            "terminal_reason": self.terminal_reason,
            "is_clarification": self.is_clarification,
            "pattern": self.pattern,
            "duration_ms": self.duration_ms,
            "phase_durations_ms": dict(self.phase_durations_ms),
            "nested_phases": dict(self.nested_phases),
            "mcp_iterations": self.mcp_iterations,
            "scripts": list(self.scripts),
            "processing_retries": self.processing_retries,
            "charts_emitted": self.charts_emitted,
            "charts_rejected": self.charts_rejected,
            "tokens": {
                "prompt_token_count": self.tokens.prompt_token_count,
                "candidates_token_count": self.tokens.candidates_token_count,
                "thoughts_token_count": self.tokens.thoughts_token_count,
                "total_token_count": self.tokens.total_token_count,
                "calls": [
                    {
                        "phase": call.phase,
                        "model": call.model,
                        "round": call.round_number,
                        "prompt_token_count": call.prompt_token_count,
                        "candidates_token_count": call.candidates_token_count,
                        "thoughts_token_count": call.thoughts_token_count,
                        "total_token_count": call.total_token_count,
                    }
                    for call in self.tokens.calls
                ],
            },
            "tables": [
                {
                    "table_id": table.table_id,
                    "used_in_answer": table.used_in_answer,
                    "variable_dcid": table.variable_dcid,
                    "variable_name": table.variable_name,
                    "unit": table.unit,
                    "scaling_factor": table.scaling_factor,
                    "measurement_method": table.measurement_method,
                    "observation_period": table.observation_period,
                    "parent_place_dcid": table.parent_place_dcid,
                    "child_place_type": table.child_place_type,
                    "places_with_data_count": table.places_with_data_count,
                    "places": [
                        {"dcid": place.dcid, "name": place.name}
                        for place in table.places
                    ],
                    "facet_id": table.facet_id,
                    "source_selection": table.source_selection,
                    "source": (
                        {
                            "name": table.source.name,
                            "url": table.source.url,
                            "license": table.source.license,
                            "dataset": table.source.dataset,
                            "provider": table.source.provider,
                            "date_range": table.source.date_range,
                        }
                        if table.source is not None
                        else None
                    ),
                    "date_range": (
                        list(table.date_range)
                        if table.date_range is not None
                        else None
                    ),
                    "row_count": table.row_count,
                }
                for table in self.tables
            ],
        }


def _resolve_place_name(table: ObservationTable, dcid: str) -> str:
    """Resolves place name from table place names, row place names, or dcid."""
    if name := table.place_names.get(dcid):
        return name
    for row in table.rows:
        if row.place_dcid == dcid and row.place_name:
            return row.place_name
    return dcid


def _build_debug_table_record(
    entry: CachedTable, *, used_in_answer: bool
) -> DebugTableRecord:
    """Builds a DebugTableRecord from a cached table entry."""
    table = entry.table
    dates = [row.date for row in table.rows]
    date_range = (min(dates), max(dates)) if dates else None

    # Derive source selection: derived for s-prefixed tables, chosen if
    # explicit source override was requested, else server default.
    if entry.table_id.startswith(DERIVED_TABLE_PREFIX):
        source_selection: SourceSelection = "derived"
    elif entry.source_selected_explicitly:
        source_selection = "chosen"
    else:
        source_selection = "server_default"

    # Places with rows, ordered with requested places first, then remaining
    # places in sorted order, capped at SUMMARY_PLACE_LIST_CAP.
    with_data = set(table.places_with_data)
    seen: set[str] = set()
    places_ordered: list[str] = []
    for dcid in table.requested_places:
        if dcid in with_data and dcid not in seen:
            seen.add(dcid)
            places_ordered.append(dcid)
    for dcid in table.places_with_data:
        if dcid not in seen:
            seen.add(dcid)
            places_ordered.append(dcid)

    places = tuple(
        DebugPlaceRef(
            dcid=dcid,
            name=_resolve_place_name(table, dcid),
        )
        for dcid in places_ordered[:SUMMARY_PLACE_LIST_CAP]
    )

    source = (
        DebugSourceRecord(
            name=table.source.name,
            url=table.source.url,
            license=table.source.license,
            dataset=table.source.dataset,
            provider=table.source.provider,
            date_range=table.source.date_range,
        )
        if table.source is not None
        else None
    )

    return DebugTableRecord(
        table_id=entry.table_id,
        used_in_answer=used_in_answer,
        variable_dcid=table.variable_dcid,
        variable_name=table.variable_name,
        unit=table.unit,
        scaling_factor=table.scaling_factor,
        measurement_method=table.measurement_method,
        observation_period=table.observation_period,
        parent_place_dcid=table.parent_place_dcid,
        child_place_type=table.child_place_type,
        places_with_data_count=len(table.places_with_data),
        places=places,
        facet_id=table.facet_id,
        source_selection=source_selection,
        source=source,
        date_range=date_range,
        row_count=len(table.rows),
    )


def build_debug_report(
    *,
    telemetry: TurnTelemetry,
    terminal_state: DebugTerminalState,
    terminal_reason: str | None = None,
    is_clarification: bool = False,
    cache: TurnCache | None = None,
    used_table_ids: AbstractSet[str] = frozenset(),
) -> DebugReport:
    """Builds a structured TurnDebugReport from telemetry and cache state.

    Args:
        telemetry: Operational telemetry collected during the turn.
        terminal_state: Terminal outcome state ('complete', 'refused', 'error').
        terminal_reason: Optional terminal failure or refusal reason code.
        is_clarification: Whether the turn was answered with a clarification.
        cache: Optional turn cache holding fetched and derived tables.
        used_table_ids: Table IDs incorporated into the synthesis response.

    Returns:
        The validated DebugReport dataclass.
    """
    phase_durations_ms = dict(telemetry.phase_durations_ms)
    nested_phases = (
        {"processing": "discovery"}
        if "processing" in phase_durations_ms
        else {}
    )

    tokens = DebugTokenUsage(
        prompt_token_count=telemetry.tokens.prompt_token_count,
        candidates_token_count=telemetry.tokens.candidates_token_count,
        thoughts_token_count=telemetry.tokens.thoughts_token_count,
        total_token_count=telemetry.tokens.total_token_count,
        calls=tuple(
            DebugTokenCall(
                phase=call.phase,
                model=call.model,
                round_number=call.round_number,
                prompt_token_count=call.counts.prompt,
                candidates_token_count=call.counts.candidates,
                thoughts_token_count=call.counts.thoughts,
                total_token_count=call.counts.total,
            )
            for call in telemetry.tokens.calls
        ),
    )

    pattern = None if terminal_state == "refused" else telemetry.pattern

    tables: list[DebugTableRecord] = []
    if cache is not None:
        for table_id in cache.table_ids:
            entry = cache.get(table_id)
            if entry is not None:
                tables.append(
                    _build_debug_table_record(
                        entry,
                        used_in_answer=table_id in used_table_ids,
                    )
                )

    return DebugReport(
        turn_id=telemetry.turn_id,
        terminal_state=terminal_state,
        terminal_reason=terminal_reason,
        is_clarification=is_clarification,
        pattern=pattern,
        duration_ms=telemetry.elapsed_ms(),
        phase_durations_ms=phase_durations_ms,
        nested_phases=nested_phases,
        mcp_iterations=telemetry.mcp_iterations,
        scripts=tuple(telemetry.scripts),
        processing_retries=telemetry.processing_retries,
        charts_emitted=telemetry.charts_emitted,
        charts_rejected=telemetry.charts_rejected,
        tokens=tokens,
        tables=tuple(tables),
    )
