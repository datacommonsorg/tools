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
"""Builds the `chat_turn` record that the server logs for each chat turn.

Each record describes one turn in identifiers, codes, dates, and counts, so
that operators can measure usage from the logs. It does not contain any text
from the conversation. `build_usage_record` reads the turn's `TurnRecord`, and
the agent loop writes the result with `telemetry.write_structured_record`.
"""

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import assert_never

from narratives_agent.analytics.digest import AnalysisDigest
from narratives_agent.analytics.metrics import (
    CompositionMetrics,
    DerivedMetrics,
    DistributionMetrics,
    RankingMetrics,
    RelationMetrics,
    ScriptMetrics,
    ScriptName,
    TimeseriesMetrics,
)
from narratives_agent.analytics.tables import (
    is_valid_dcid,
    is_valid_observation_date,
)
from narratives_agent.gemini.schemas import QueryPattern
from narratives_agent.json_value import json_safe
from narratives_agent.telemetry import (
    MAX_RECORD_LINE_BYTES,
    NESTED_PHASES,
    TURN_PHASES,
    ErrorType,
    Severity,
    StructuredRecord,
    TerminalState,
    TitleOutcome,
    TokenUsage,
    TurnPhase,
    TurnTelemetry,
)
from narratives_agent.workflows.classify import RefusedReason
from narratives_agent.workflows.transcript import (
    MAX_PLACE_TYPE_CHARS,
    PLACE_TYPE_PATTERN,
    Transcript,
)
from narratives_agent.workflows.turn_cache import (
    FETCHED_TABLE_PREFIX,
    TABLE_ID_NUMBER_PATTERN,
    CachedTable,
)
from narratives_agent.workflows.turn_record import TurnRecord

__all__ = [
    "CHAT_TURN_EVENT",
    "CHAT_TURN_SCHEMA_VERSION",
    "MAX_HIGHLIGHTED_PLACES",
    "MAX_LOGGED_TABLES",
    "MAX_TABLE_PLACE_DCIDS",
    "HighlightedPlace",
    "LoggedTable",
    "PhaseDuration",
    "PlaceHighlightSource",
    "RefusalStage",
    "TokenCall",
    "TokenTotals",
    "ToolCallCount",
    "TurnOutcome",
    "UsageRecord",
    "build_usage_record",
]

CHAT_TURN_EVENT = "chat_turn"
# `CHAT_TURN_SCHEMA_VERSION` is the version of the `chat_turn` schema. It
# changes when a key is renamed or removed, or when the type or the meaning
# of a key changes. Adding a key does not change it.
CHAT_TURN_SCHEMA_VERSION = 2

MAX_LOGGED_TABLES = 20
# `MAX_TABLE_PLACE_DCIDS` matches `MAX_ENTRIES_PER_SCOPE` in `transcript.py`.
MAX_TABLE_PLACE_DCIDS = 25
MAX_HIGHLIGHTED_PLACES = 25

_FETCHED_TABLE_ID_PATTERN = re.compile(
    rf"{FETCHED_TABLE_PREFIX}{TABLE_ID_NUMBER_PATTERN}"
)
_PLACE_TYPE_PATTERN = re.compile(PLACE_TYPE_PATTERN)


class TurnOutcome(StrEnum):
    """Lists the outcomes that a turn can have."""

    ANSWERED_WITH_DATA = "answered_with_data"
    ANSWERED_WITHOUT_DATA = "answered_without_data"
    CLARIFIED = "clarified"
    REFUSED = "refused"
    ERROR = "error"
    CANCELED = "canceled"


class RefusalStage(StrEnum):
    """Lists the stages where the server can refuse a turn."""

    AVAILABILITY = "availability"
    CLASSIFY = "classify"
    DISCOVERY = "discovery"
    SYNTHESIS = "synthesis"


# `_REFUSAL_STAGE_BY_PHASE` maps each phase where the server can refuse a turn
# to its `RefusalStage`. The phases are ordered from the last one that the
# agent loop runs to the first.
_REFUSAL_STAGE_BY_PHASE: tuple[tuple[TurnPhase, RefusalStage], ...] = (
    ("synthesis", RefusalStage.SYNTHESIS),
    ("discovery", RefusalStage.DISCOVERY),
    ("classify", RefusalStage.CLASSIFY),
)


@dataclass(frozen=True, kw_only=True)
class PhaseDuration:
    """Holds the time that a turn spent in one phase.

    Attributes:
        phase: The name of the phase.
        duration_ms: The total time in the phase, in milliseconds.
        is_nested: Whether the phase runs inside another phase, which means
            that its time is also counted in that phase.
    """

    phase: TurnPhase
    duration_ms: float
    is_nested: bool


@dataclass(frozen=True, kw_only=True)
class TokenTotals:
    """Holds the token counts of a turn, summed over its model calls.

    Attributes:
        prompt_token_count: The number of input tokens.
        candidates_token_count: The number of output tokens.
        thoughts_token_count: The number of reasoning tokens.
        total_token_count: The total that the model reported.
        call_count: The number of model calls that reported token counts.
    """

    prompt_token_count: int
    candidates_token_count: int
    thoughts_token_count: int
    total_token_count: int
    call_count: int


@dataclass(frozen=True, kw_only=True)
class TokenCall:
    """Holds the token counts of one model call.

    Attributes:
        role: The role that the call ran in, such as `discovery`. Each
            caller passes its own role name to the Gemini client.
        model: The configured name of the model that answered the call.
        round_number: The 1-based discovery round of the call, or `None`
            for a call outside the discovery loop.
        prompt_token_count: The number of input tokens.
        candidates_token_count: The number of output tokens.
        thoughts_token_count: The number of reasoning tokens.
        total_token_count: The total that the model reported.
    """

    role: str
    model: str
    round_number: int | None
    prompt_token_count: int
    candidates_token_count: int
    thoughts_token_count: int
    total_token_count: int


@dataclass(frozen=True, kw_only=True)
class ToolCallCount:
    """Holds how many times a turn called one tool.

    Attributes:
        tool: The name of the tool or server function.
        count: The number of calls of that tool.
    """

    tool: str
    count: int


class PlaceHighlightSource(StrEnum):
    """Lists the metric fields that can add a place to `highlighted_places`."""

    RANKED_TOP = "ranked_top"
    RANKED_BOTTOM = "ranked_bottom"
    RANKED_FOCAL = "ranked_focal"
    DISTRIBUTION_MAX = "distribution_max"
    DISTRIBUTION_MIN = "distribution_min"
    DISTRIBUTION_FOCAL = "distribution_focal"
    RELATED_HIGHEST = "related_highest"
    RELATED_LOWEST = "related_lowest"
    TIMESERIES = "timeseries"
    COMPOSITION = "composition"


@dataclass(frozen=True, kw_only=True)
class LoggedTable:
    """Holds the identifiers, scope, and row counts of one fetched table.

    Attributes:
        table_id: The `t<n>` identifier of the fetched table.
        used_in_answer: Whether the turn's answering specification read this
            table.
        variable_dcid: The Data Commons variable identifier of the table.
        facet_id: The facet identifier of the table, or `None` when the table
            does not report a valid facet identifier.
        row_count: The number of observation rows in the table.
        parent_place_dcid: The parent place identifier when the table covers
            a complete child-place cohort, or `None` otherwise.
        child_place_type: The child place type when the table covers a
            complete child-place cohort, or `None` otherwise.
        places_with_data_count: The number of valid place identifiers that
            have rows in the table.
        place_dcids: Up to `MAX_TABLE_PLACE_DCIDS` sorted place identifiers
            when the table does not cover a complete child-place cohort, or
            an empty tuple when it does.
        earliest_date: The earliest valid observation date in the table's
            rows, or `None` when the rows do not have a valid date.
        latest_date: The latest valid observation date in the table's rows,
            or `None` when the rows do not have a valid date.
    """

    table_id: str
    used_in_answer: bool
    variable_dcid: str
    facet_id: str | None
    row_count: int
    parent_place_dcid: str | None
    child_place_type: str | None
    places_with_data_count: int
    place_dcids: tuple[str, ...]
    earliest_date: str | None
    latest_date: str | None


@dataclass(frozen=True, kw_only=True)
class HighlightedPlace:
    """Holds one place that the turn's analysis highlighted and its source.

    Attributes:
        place_dcid: The Data Commons identifier of the place.
        source: The first metric field in the digest that highlighted the
            place.
    """

    place_dcid: str
    source: PlaceHighlightSource


@dataclass(frozen=True, kw_only=True)
class UsageRecord(StructuredRecord):
    """Holds the `chat_turn` record of one turn.

    Every string in the record is a code that the server defines, an
    identifier that the server creates, a model name from the configuration,
    the build SHA, or a verified Data Commons identifier, facet ID, place
    type, or observation date from a fetched table that has rows. The record
    does not have a field for free text. The server writes every field on
    every record, and a value that does not apply is `None`. A caller cannot
    pass `severity` or `message`, because the record derives both from
    `terminal_state`.

    Attributes:
        build_sha: The build or commit SHA of the running image, or `None`
            when the deployment does not set one.
        turn_id: The ID that the server created for the turn.
        conversation_id: The ID of the conversation that the turn belongs
            to, which the server created on the conversation's first turn.
        turn_index: The index that the turn has when it is signed. An
            unsigned turn has the index that it would have had.
        is_signed: Whether the server signed the turn into the conversation.
        was_compacted: Whether signing the turn compacted older turns of the
            conversation into a summary.
        terminal_state: The state that the turn ended in.
        outcome: How the turn ended.
        outcome_reason: The reason code of a refused or failed turn, or
            `None` for any other turn.
        refusal_stage: Where the server refused the turn, or `None` when
            the turn was not refused.
        has_data: Whether the turn's analysis produced data. On a completed
            turn, it is `True` when the server wrote the answer from data.
        is_clarification: Whether the server answered with a clarification
            question.
        is_truncated: Whether the search for data stopped at its round
            limit or time limit.
        title_outcome: Whether the answer has a title.
        pattern: The analytical pattern of the question, or `None` when the
            turn was refused or ended before it was classified.
        duration_ms: The duration of the turn, in milliseconds.
        phase_durations: The time in each phase that ran, in the order of
            `TURN_PHASES`.
        tokens: The token counts of the turn.
        token_calls: The token counts of each model call, in call order.
        mcp_iterations: The number of discovery rounds.
        tool_call_count: The number of tool calls.
        tool_call_counts: The number of calls of each tool, sorted by tool
            name.
        tables_fetched: The number of observation tables that the turn
            fetched.
        total_rows_fetched: The number of observation rows in those tables.
        tables_truncated: Whether qualifying fetched tables were omitted from
            `tables` by the 20-table cap or the line-size limit.
        tables: Up to `MAX_LOGGED_TABLES` fetched tables that returned rows,
            in fetch order.
        highlighted_places: Up to `MAX_HIGHLIGHTED_PLACES` distinct places
            from the steps of the digest that succeeded.
        scripts: The analytical scripts that the turn ran, in step order.
        processing_retries: The number of specifications that the server
            returned to the model for another attempt.
        charts_emitted: The number of charts in the answer.
        charts_rejected: The number of charts that the server dropped.
    """

    severity: Severity = field(init=False)
    message: str = field(init=False)
    event: str = field(default=CHAT_TURN_EVENT, init=False)
    schema_version: int = field(default=CHAT_TURN_SCHEMA_VERSION, init=False)
    build_sha: str | None
    turn_id: str
    conversation_id: str
    turn_index: int
    is_signed: bool
    was_compacted: bool
    terminal_state: TerminalState
    outcome: TurnOutcome
    outcome_reason: ErrorType | RefusedReason | None
    refusal_stage: RefusalStage | None
    has_data: bool
    is_clarification: bool
    is_truncated: bool
    title_outcome: TitleOutcome
    pattern: QueryPattern | None
    duration_ms: float
    # The list has at most one item for each phase in `TURN_PHASES`.
    phase_durations: tuple[PhaseDuration, ...]
    tokens: TokenTotals
    # The list has one item for each model call. A turn makes at most
    # `MAX_ITERATIONS` discovery calls, and one call in each of the other
    # four roles.
    token_calls: tuple[TokenCall, ...]
    mcp_iterations: int
    tool_call_count: int
    # The list has one item for each tool name. A name is a tool or a server
    # function that the discovery loop declares to the model, or one of two
    # labels. The loop records `unknown` for an undeclared tool, and
    # `server_report_unavailable` for a report that the server files itself.
    tool_call_counts: tuple[ToolCallCount, ...]
    tables_fetched: int
    total_rows_fetched: int
    tables_truncated: bool
    tables: tuple[LoggedTable, ...]
    highlighted_places: tuple[HighlightedPlace, ...]
    # The list has one item for each step of the specification, which holds
    # at most six steps.
    scripts: tuple[ScriptName, ...]
    processing_retries: int
    charts_emitted: int
    charts_rejected: int

    def __post_init__(self) -> None:
        """Sets `severity` and `message` from the terminal state."""
        is_error = self.terminal_state == TerminalState.ERROR
        # A frozen dataclass rejects a plain assignment.
        object.__setattr__(self, "severity", "ERROR" if is_error else "INFO")
        object.__setattr__(self, "message", f"chat turn {self.terminal_state}")


def _resolve_outcome(
    state: TerminalState, *, is_clarification: bool, has_data: bool
) -> TurnOutcome:
    """Returns how a turn ended from its terminal state and its answer."""
    match state:
        case TerminalState.REFUSED:
            return TurnOutcome.REFUSED
        case TerminalState.ERROR:
            return TurnOutcome.ERROR
        case TerminalState.CANCELED:
            return TurnOutcome.CANCELED
        case TerminalState.COMPLETE:
            if is_clarification:
                return TurnOutcome.CLARIFIED
            if has_data:
                return TurnOutcome.ANSWERED_WITH_DATA
            return TurnOutcome.ANSWERED_WITHOUT_DATA


def _resolve_refusal_stage(
    state: TerminalState, telemetry: TurnTelemetry
) -> RefusalStage | None:
    """Returns where the server refused a turn, or `None` if it did not.

    `TurnTelemetry.phase` records the duration of a phase when the phase
    ends, including when a refusal ends it. The stage is therefore the last
    phase of `_REFUSAL_STAGE_BY_PHASE` that has a duration. When the server
    refuses a turn before any phase runs, it does so because chat is
    disabled.
    """
    if state != TerminalState.REFUSED:
        return None
    for phase, stage in _REFUSAL_STAGE_BY_PHASE:
        if phase in telemetry.phase_durations_ms:
            return stage
    return RefusalStage.AVAILABILITY


def _build_phase_durations(
    telemetry: TurnTelemetry,
) -> tuple[PhaseDuration, ...]:
    """Returns the duration of each phase that ran, in a fixed order."""
    durations = telemetry.phase_durations_ms
    return tuple(
        PhaseDuration(
            phase=phase,
            duration_ms=durations[phase],
            is_nested=phase in NESTED_PHASES,
        )
        for phase in TURN_PHASES
        if phase in durations
    )


def _build_token_totals(tokens: TokenUsage) -> TokenTotals:
    """Returns the turn's token totals and its number of model calls."""
    return TokenTotals(
        prompt_token_count=tokens.prompt_token_count,
        candidates_token_count=tokens.candidates_token_count,
        thoughts_token_count=tokens.thoughts_token_count,
        total_token_count=tokens.total_token_count,
        call_count=len(tokens.calls),
    )


def _build_token_calls(tokens: TokenUsage) -> tuple[TokenCall, ...]:
    """Returns the token counts of each model call, in call order."""
    return tuple(
        TokenCall(
            role=call.phase,
            model=call.model,
            round_number=call.round_number,
            prompt_token_count=call.counts.prompt,
            candidates_token_count=call.counts.candidates,
            thoughts_token_count=call.counts.thoughts,
            total_token_count=call.counts.total,
        )
        for call in tokens.calls
    )


def _build_tool_call_counts(
    telemetry: TurnTelemetry,
) -> tuple[ToolCallCount, ...]:
    """Returns the number of calls of each tool, sorted by tool name."""
    return tuple(
        ToolCallCount(tool=tool, count=count)
        for tool, count in sorted(telemetry.tool_calls.items())
    )


def _is_valid_place_type(value: str) -> bool:
    """Returns whether `value` is a place type within the length bound."""
    return (
        len(value) <= MAX_PLACE_TYPE_CHARS
        and _PLACE_TYPE_PATTERN.fullmatch(value) is not None
    )


def _build_logged_table(
    entry: CachedTable, used_table_ids: frozenset[str]
) -> tuple[LoggedTable, tuple[str, ...]] | None:
    """Builds one `LoggedTable` and its valid places, or `None` if excluded.

    Empty fetches, table IDs outside `t<n>`, invalid variable DCIDs, and
    tables whose rows do not contain any valid place DCID are excluded.
    """
    table = entry.table
    if (
        not table.rows
        or _FETCHED_TABLE_ID_PATTERN.fullmatch(entry.table_id) is None
        or not is_valid_dcid(table.variable_dcid)
    ):
        return None
    # `table.places_with_data` is already sorted and deduplicated.
    valid_places = tuple(
        place for place in table.places_with_data if is_valid_dcid(place)
    )
    if not valid_places:
        return None
    facet_id = (
        table.facet_id
        if table.facet_id is not None and is_valid_dcid(table.facet_id)
        else None
    )
    parent = table.parent_place_dcid
    child_type = table.child_place_type
    is_cohort = (
        parent is not None
        and is_valid_dcid(parent)
        and child_type is not None
        and _is_valid_place_type(child_type)
    )
    dates = [
        row.date for row in table.rows if is_valid_observation_date(row.date)
    ]
    logged = LoggedTable(
        table_id=entry.table_id,
        used_in_answer=entry.table_id in used_table_ids,
        variable_dcid=table.variable_dcid,
        facet_id=facet_id,
        row_count=len(table.rows),
        parent_place_dcid=parent if is_cohort else None,
        child_place_type=child_type if is_cohort else None,
        places_with_data_count=len(valid_places),
        place_dcids=() if is_cohort else valid_places[:MAX_TABLE_PLACE_DCIDS],
        earliest_date=min(dates) if dates else None,
        latest_date=max(dates) if dates else None,
    )
    return logged, valid_places


def _collect_fetched_tables(
    record: TurnRecord,
) -> tuple[tuple[LoggedTable, ...], bool, set[str]]:
    """Collects up to `MAX_LOGGED_TABLES` tables and all grounded place DCIDs.

    Every qualifying fetched table contributes its valid place DCIDs to the
    grounding set before the `MAX_LOGGED_TABLES` cap is applied, so a place
    from `t21` still counts as grounded in a fetched table.
    """
    qualifying: list[LoggedTable] = []
    grounded_places: set[str] = set()
    for entry in record.cache.list_fetched_tables():
        built = _build_logged_table(entry, record.used_table_ids)
        if built is None:
            continue
        logged, valid_places = built
        qualifying.append(logged)
        grounded_places.update(valid_places)
    is_truncated = len(qualifying) > MAX_LOGGED_TABLES
    return tuple(qualifying[:MAX_LOGGED_TABLES]), is_truncated, grounded_places


def _iter_metric_places(
    metrics: ScriptMetrics,
) -> Iterator[tuple[str, PlaceHighlightSource]]:
    """Yields candidate `(place_dcid, source)` pairs from one step's metrics.

    On ranking and distribution metrics, focal entries come first so that a
    focal place keeps its focal source when it also sits at an extreme.
    """
    match metrics:
        case RankingMetrics():
            for ranked in metrics.focal_entries:
                yield ranked.place_dcid, PlaceHighlightSource.RANKED_FOCAL
            for ranked in metrics.top_n:
                yield ranked.place_dcid, PlaceHighlightSource.RANKED_TOP
            for ranked in metrics.bottom_n:
                yield ranked.place_dcid, PlaceHighlightSource.RANKED_BOTTOM
        case DistributionMetrics():
            for focal in metrics.focal_entries:
                yield (
                    focal.place_dcid,
                    PlaceHighlightSource.DISTRIBUTION_FOCAL,
                )
            yield metrics.max.place_dcid, PlaceHighlightSource.DISTRIBUTION_MAX
            yield metrics.min.place_dcid, PlaceHighlightSource.DISTRIBUTION_MIN
        case RelationMetrics():
            for related in metrics.highest_by:
                yield related.place_dcid, PlaceHighlightSource.RELATED_HIGHEST
            for related in metrics.lowest_by:
                yield related.place_dcid, PlaceHighlightSource.RELATED_LOWEST
        case TimeseriesMetrics():
            for series in metrics.series:
                yield series.place_dcid, PlaceHighlightSource.TIMESERIES
        case CompositionMetrics():
            for place in metrics.places:
                yield place.place_dcid, PlaceHighlightSource.COMPOSITION
        case DerivedMetrics():
            return
        case _ as unreachable:
            assert_never(unreachable)


def _build_highlighted_places(
    digest: AnalysisDigest | None, grounded_places: set[str]
) -> tuple[HighlightedPlace, ...]:
    """Builds up to `MAX_HIGHLIGHTED_PLACES` deduplicated grounded places."""
    if digest is None or not grounded_places:
        return ()
    highlighted: list[HighlightedPlace] = []
    seen: set[str] = set()
    for result in digest.results:
        if result.status != "ok":
            continue
        for place_dcid, source in _iter_metric_places(result.metrics):
            if place_dcid not in grounded_places or place_dcid in seen:
                continue
            seen.add(place_dcid)
            highlighted.append(
                HighlightedPlace(place_dcid=place_dcid, source=source)
            )
            if len(highlighted) == MAX_HIGHLIGHTED_PLACES:
                return tuple(highlighted)
    return tuple(highlighted)


def _measure_record_bytes(record: UsageRecord) -> int:
    """Returns the UTF-8 byte length of `record` serialized as compact JSON."""
    serialized = json.dumps(
        json_safe(record), separators=(",", ":"), allow_nan=False
    )
    return len(serialized.encode("utf-8"))


def _fit_tables_to_line_budget(record: UsageRecord) -> UsageRecord:
    """Drops trailing `tables` entries when `record` exceeds the line limit."""
    while (
        record.tables and _measure_record_bytes(record) > MAX_RECORD_LINE_BYTES
    ):
        record = replace(
            record,
            tables=record.tables[:-1],
            tables_truncated=True,
        )
    return record


def build_usage_record(
    record: TurnRecord, transcript: Transcript, *, build_sha: str | None
) -> UsageRecord:
    """Builds the `chat_turn` record of a turn that has ended.

    Args:
        record: The turn's record, after the agent loop set its terminal
            state and finished its telemetry.
        transcript: The verified transcript that the turn ran with. The
            record takes the conversation ID and the turn's index from it.
        build_sha: The build or commit SHA of the running image, or `None`.

    Returns:
        The record, which `telemetry.write_structured_record` writes.

    Raises:
        ValueError: If the turn does not have a terminal state yet.
    """
    state = record.terminal_state
    if state is None:
        raise ValueError("The turn has not ended.")
    telemetry = record.telemetry
    has_data = record.digest is not None and record.digest.has_data
    tables, is_tables_truncated, grounded_places = _collect_fetched_tables(
        record
    )
    highlighted_places = _build_highlighted_places(
        record.digest, grounded_places
    )
    usage = UsageRecord(
        build_sha=build_sha,
        turn_id=telemetry.turn_id,
        conversation_id=transcript.conversation_id,
        turn_index=transcript.next_turn_index,
        is_signed=record.is_signed,
        was_compacted=record.was_compacted,
        terminal_state=state,
        outcome=_resolve_outcome(
            state,
            is_clarification=record.is_clarification,
            has_data=has_data,
        ),
        outcome_reason=record.terminal_reason,
        refusal_stage=_resolve_refusal_stage(state, telemetry),
        has_data=has_data,
        is_clarification=record.is_clarification,
        is_truncated=record.loop_result.truncated,
        title_outcome=telemetry.title_outcome,
        # The record does not hold the pattern of a turn that the server
        # refused, even when the classifier assigned one before the refusal.
        pattern=None if state == TerminalState.REFUSED else telemetry.pattern,
        duration_ms=telemetry.elapsed_ms(),
        phase_durations=_build_phase_durations(telemetry),
        tokens=_build_token_totals(telemetry.tokens),
        token_calls=_build_token_calls(telemetry.tokens),
        mcp_iterations=telemetry.mcp_iterations,
        tool_call_count=sum(telemetry.tool_calls.values()),
        tool_call_counts=_build_tool_call_counts(telemetry),
        tables_fetched=telemetry.tables_fetched,
        total_rows_fetched=telemetry.total_rows_fetched,
        tables_truncated=is_tables_truncated,
        tables=tables,
        highlighted_places=highlighted_places,
        scripts=tuple(telemetry.scripts),
        processing_retries=telemetry.processing_retries,
        charts_emitted=telemetry.charts_emitted,
        charts_rejected=telemetry.charts_rejected,
    )
    return _fit_tables_to_line_budget(usage)
