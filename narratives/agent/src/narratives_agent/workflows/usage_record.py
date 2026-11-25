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

from narratives_agent.analytics.digest import (
    AnalysisDigest,
    RefusalReason,
    ResultStatus,
)
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
from narratives_agent.workflows.charts import (
    MAX_CHARTS_PER_TURN,
    ChartKind,
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
from narratives_agent.workflows.classify import RefusedReason
from narratives_agent.workflows.mcp_loop import (
    MAX_PROCESSING_RETRIES,
    RejectedSubmission,
    RejectionReason,
)
from narratives_agent.workflows.processing import (
    StepRefusalDiagnostic,
    TimeoutDiagnostic,
)
from narratives_agent.workflows.transcript import (
    MAX_PLACE_TYPE_CHARS,
    PLACE_TYPE_PATTERN,
    Transcript,
)
from narratives_agent.workflows.turn_cache import (
    DERIVED_TABLE_PREFIX,
    FETCHED_TABLE_PREFIX,
    TABLE_ID_NUMBER_PATTERN,
    CachedTable,
)
from narratives_agent.workflows.turn_record import (
    ChartOrigin,
    SpecificationOrigin,
    TurnRecord,
)

__all__ = [
    "CHAT_TURN_EVENT",
    "CHAT_TURN_SCHEMA_VERSION",
    "MAX_CHART_VARIABLES",
    "MAX_HIGHLIGHTED_PLACES",
    "MAX_LOGGED_CHARTS",
    "MAX_LOGGED_REJECTED_SUBMISSIONS",
    "MAX_LOGGED_TABLES",
    "MAX_TABLE_PLACE_DCIDS",
    "ChartVariable",
    "HighlightedPlace",
    "LoggedChart",
    "LoggedRejectedSubmission",
    "LoggedScriptStep",
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
MAX_TABLE_PLACE_DCIDS = 25
MAX_HIGHLIGHTED_PLACES = 25
# The discovery loop rejects at most this many specifications in a turn: the
# ones that it returns to the model, and the one that ends the loop.
MAX_LOGGED_REJECTED_SUBMISSIONS = MAX_PROCESSING_RETRIES + 1
MAX_LOGGED_CHARTS = MAX_CHARTS_PER_TURN
MAX_CHART_VARIABLES = 10

_FETCHED_TABLE_ID_PATTERN = re.compile(
    rf"{FETCHED_TABLE_PREFIX}{TABLE_ID_NUMBER_PATTERN}"
)
_STEP_ID_PATTERN = re.compile(
    rf"{DERIVED_TABLE_PREFIX}{TABLE_ID_NUMBER_PATTERN}"
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
class LoggedScriptStep:
    """Holds the outcome of one step of a turn's specification.

    Attributes:
        step_index: The 0-based position of the step in the specification.
        step_id: The `s<n>` identifier of the step.
        script: The analytical script that the step ran.
        status: Whether the script produced its output or refused.
        refusal_reason: The reason code of a refused step, or `None` for a
            step that succeeded.
    """

    step_index: int
    step_id: str
    script: ScriptName
    status: ResultStatus
    refusal_reason: RefusalReason | None


@dataclass(frozen=True, kw_only=True)
class LoggedRejectedSubmission:
    """Holds why the server rejected one specification from the model.

    Attributes:
        round_number: The 1-based discovery round of the submission.
        reason: Whether the specification failed schema validation, failed
            the check of its references, or failed when it ran.
        scripts: The scripts of the specification, in step order, or an
            empty tuple when the specification did not parse.
        failed_step_id: The `s<n>` identifier of the step that refused, or
            `None` when the run did not stop at a refused step.
        failed_script: The script of the step that refused, or `None` when
            the run did not stop at a refused step.
        refusal_reason: The reason code of the step that refused, or `None`
            when the run did not stop at a refused step.
        timed_out: Whether the run exceeded its time limit.
    """

    round_number: int
    reason: RejectionReason
    scripts: tuple[ScriptName, ...]
    failed_step_id: str | None
    failed_script: ScriptName | None
    refusal_reason: RefusalReason | None
    timed_out: bool


@dataclass(frozen=True, kw_only=True)
class ChartVariable:
    """Holds one variable of a chart and the facet that the chart pins it to.

    Attributes:
        variable_dcid: The Data Commons identifier of the variable.
        facet_id: The identifier of the facet that the chart draws the
            variable from, or `None` when the chart does not pin the
            variable to one facet.
    """

    variable_dcid: str
    facet_id: str | None


@dataclass(frozen=True, kw_only=True)
class LoggedChart:
    """Holds the kind, origin, variables, and scope of one chart of an answer.

    Attributes:
        index: The 0-based position of the chart among the logged charts.
        kind: The chart kind, such as `line` or `map`.
        origin: Whether the model wrote the chart or the server supplied it
            as a default chart.
        variables: Up to `MAX_CHART_VARIABLES` of the chart's variables that
            a fetched table of the turn holds, in the chart's order, each
            with the facet that the chart pins it to.
        parent_place_dcid: The parent place identifier when the chart draws
            a child-place cohort, or `None` otherwise.
        child_place_type: The child place type when the chart draws a
            child-place cohort, or `None` otherwise.
        place_dcids: Up to `MAX_TABLE_PLACE_DCIDS` place identifiers that
            the chart lists and that have rows in a fetched table of the
            turn, in the chart's order. The tuple is empty for a chart that
            draws a cohort.
        per_capita: Whether the chart divides its values by population.
    """

    index: int
    kind: ChartKind
    origin: ChartOrigin
    variables: tuple[ChartVariable, ...]
    parent_place_dcid: str | None
    child_place_type: str | None
    place_dcids: tuple[str, ...]
    per_capita: bool


@dataclass(frozen=True, kw_only=True)
class UsageRecord(StructuredRecord):
    """Holds the `chat_turn` record of one turn.

    Every string in the record is a code that the server defines, an
    identifier that the server creates, a model name from the configuration,
    the build SHA, the `s<n>` identifier of an analysis step, or a verified
    Data Commons identifier, facet ID, place type, or observation date from
    a fetched table that has rows. The record does not have a field for free
    text. The server writes every field on every record, and a value that
    does not apply is `None`. A caller cannot pass `severity` or `message`,
    because the record derives both from `terminal_state`.

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
        specification_origin: Whether the model or the server wrote the
            turn's specification, or `None` when the turn does not have
            one. A turn that fails after its analysis keeps the origin.
        scripts: The analytical scripts that the turn ran, in step order.
        script_steps: The steps of that specification that ran, in step
            order, each with its outcome.
        processing_retries: The number of specifications that the server
            returned to the model for another attempt.
        rejected_submissions: Up to `MAX_LOGGED_REJECTED_SUBMISSIONS`
            specifications that the server rejected, in submission order.
        charts_emitted: The number of charts in the answer.
        charts_rejected: The number of charts that the server dropped.
        charts: Up to `MAX_LOGGED_CHARTS` charts of the answer, in the
            order in which the server emitted them.
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
    specification_origin: SpecificationOrigin | None
    # The list has one item for each step of the specification, which holds
    # at most six steps.
    scripts: tuple[ScriptName, ...]
    # The list has at most one item for each step of the specification.
    script_steps: tuple[LoggedScriptStep, ...]
    processing_retries: int
    rejected_submissions: tuple[LoggedRejectedSubmission, ...]
    charts_emitted: int
    charts_rejected: int
    charts: tuple[LoggedChart, ...]

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


@dataclass(frozen=True, kw_only=True)
class _FetchedTables:
    """Holds the logged tables of a turn and the identifiers that they ground.

    Every qualifying fetched table contributes to the four identifier sets
    before the `MAX_LOGGED_TABLES` cap is applied, so an identifier from
    `t21` still counts as grounded in a fetched table.

    Attributes:
        tables: Up to `MAX_LOGGED_TABLES` qualifying tables, in fetch order.
        is_truncated: Whether the cap left qualifying tables out of `tables`.
        variable_dcids: The variable DCIDs of the qualifying tables.
        variable_facets: The `(variable DCID, facet ID)` pair of each
            qualifying table that reports a valid facet ID.
        place_dcids: The valid place DCIDs that have rows in a qualifying
            table.
        cohorts: The `(parent place DCID, child place type)` pair of each
            qualifying table that covers a complete child-place cohort. The
            rows of such a table hold the child places and do not hold the
            parent place.
    """

    tables: tuple[LoggedTable, ...]
    is_truncated: bool
    variable_dcids: frozenset[str]
    variable_facets: frozenset[tuple[str, str]]
    place_dcids: frozenset[str]
    cohorts: frozenset[tuple[str, str]]


def _collect_fetched_tables(record: TurnRecord) -> _FetchedTables:
    """Collects the turn's qualifying fetched tables and their identifiers."""
    qualifying: list[LoggedTable] = []
    place_dcids: set[str] = set()
    for entry in record.cache.list_fetched_tables():
        built = _build_logged_table(entry, record.used_table_ids)
        if built is None:
            continue
        logged, valid_places = built
        qualifying.append(logged)
        place_dcids.update(valid_places)
    return _FetchedTables(
        tables=tuple(qualifying[:MAX_LOGGED_TABLES]),
        is_truncated=len(qualifying) > MAX_LOGGED_TABLES,
        variable_dcids=frozenset(table.variable_dcid for table in qualifying),
        variable_facets=frozenset(
            (table.variable_dcid, table.facet_id)
            for table in qualifying
            if table.facet_id is not None
        ),
        place_dcids=frozenset(place_dcids),
        cohorts=frozenset(
            (table.parent_place_dcid, table.child_place_type)
            for table in qualifying
            if table.parent_place_dcid is not None
            and table.child_place_type is not None
        ),
    )


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
    digest: AnalysisDigest | None, grounded_places: frozenset[str]
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


def _is_valid_step_id(value: str) -> bool:
    """Returns whether `value` is a step identifier such as `s1`."""
    return _STEP_ID_PATTERN.fullmatch(value) is not None


def _build_script_steps(record: TurnRecord) -> tuple[LoggedScriptStep, ...]:
    """Returns the steps of the turn's specification that ran, in order.

    `execute_specification` stops at the first step that refuses, so the
    steps after a refused step are left out. The diagnostic of a run that
    exceeded its time limit does not identify the steps that finished, so
    the list is empty for that run. A step whose identifier is not `s<n>`
    is left out.

    Raises:
        ValueError: If the record's diagnostic names a refused step that
            its specification does not hold.
    """
    specification = record.specification
    diagnostic = record.specification_diagnostic
    if specification is None or isinstance(diagnostic, TimeoutDiagnostic):
        return ()
    refused_step_id = diagnostic.step_id if diagnostic is not None else None
    if refused_step_id is not None and all(
        step.step_id != refused_step_id for step in specification.steps
    ):
        raise ValueError("The specification does not hold the refused step.")
    refusal_reason = (
        diagnostic.refusal_reason if diagnostic is not None else None
    )
    steps: list[LoggedScriptStep] = []
    for step_index, step in enumerate(specification.steps):
        is_refused = step.step_id == refused_step_id
        if _is_valid_step_id(step.step_id):
            steps.append(
                LoggedScriptStep(
                    step_index=step_index,
                    step_id=step.step_id,
                    script=step.script,
                    status="refused" if is_refused else "ok",
                    refusal_reason=refusal_reason if is_refused else None,
                )
            )
        if is_refused:
            break
    return tuple(steps)


def _build_rejected_submission(
    submission: RejectedSubmission,
) -> LoggedRejectedSubmission:
    """Builds the logged form of one rejected specification.

    The function reads only codes and identifiers. It does not read the
    error messages of the submission or the message of its diagnostic.
    """
    specification = submission.specification
    diagnostic = submission.diagnostic
    refusal = (
        diagnostic if isinstance(diagnostic, StepRefusalDiagnostic) else None
    )
    return LoggedRejectedSubmission(
        round_number=submission.round_number,
        reason=submission.reason,
        scripts=(
            tuple(specification.list_script_names())
            if specification is not None
            else ()
        ),
        failed_step_id=(
            refusal.step_id
            if refusal is not None and _is_valid_step_id(refusal.step_id)
            else None
        ),
        failed_script=refusal.script if refusal is not None else None,
        refusal_reason=refusal.refusal_reason if refusal is not None else None,
        timed_out=isinstance(diagnostic, TimeoutDiagnostic),
    )


def _read_chart_scope(
    chart: ResolvedChart,
) -> tuple[tuple[str, ...], ChildCohort | None]:
    """Returns the places that a chart lists, or the cohort that it draws."""
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
        case _ as unreachable:
            assert_never(unreachable)


def _build_logged_chart(
    index: int,
    chart: ResolvedChart,
    origin: ChartOrigin,
    fetched: _FetchedTables,
) -> LoggedChart:
    """Builds the logged form of one chart from grounded identifiers.

    A variable or a place is logged only when a qualifying fetched table of
    the turn holds it. A facet is logged only when one such table reports it
    for the same variable, and a cohort only when one such table covers the
    same parent place and child place type. An identifier that the model
    wrote is therefore left out. The function does not read the chart's
    title or unit.
    """
    places, cohort = _read_chart_scope(chart)
    # A chart pins each variable to at most one facet.
    grounded_facets = {
        variable_dcid: facet_id
        for variable_dcid, facet_id in chart.facet_ids
        if (variable_dcid, facet_id) in fetched.variable_facets
    }
    variables = tuple(
        ChartVariable(
            variable_dcid=variable_dcid,
            facet_id=grounded_facets.get(variable_dcid),
        )
        for variable_dcid in chart.variable_dcids
        if variable_dcid in fetched.variable_dcids
    )[:MAX_CHART_VARIABLES]
    grounded_cohort = (
        cohort
        if cohort is not None
        and (cohort.parent_place, cohort.child_place_type) in fetched.cohorts
        else None
    )
    return LoggedChart(
        index=index,
        kind=chart.viz_type,
        origin=origin,
        variables=variables,
        parent_place_dcid=(
            grounded_cohort.parent_place
            if grounded_cohort is not None
            else None
        ),
        child_place_type=(
            grounded_cohort.child_place_type
            if grounded_cohort is not None
            else None
        ),
        place_dcids=tuple(
            place_dcid
            for place_dcid in places
            if place_dcid in fetched.place_dcids
        )[:MAX_TABLE_PLACE_DCIDS],
        per_capita=chart.per_capita,
    )


def _build_logged_charts(
    record: TurnRecord, fetched: _FetchedTables
) -> tuple[LoggedChart, ...]:
    """Builds up to `MAX_LOGGED_CHARTS` charts of the answer, in order."""
    return tuple(
        _build_logged_chart(index, entry.chart, entry.origin, fetched)
        for index, entry in enumerate(record.charts[:MAX_LOGGED_CHARTS])
    )


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
        ValueError: If the turn does not have a terminal state yet, or if
            its diagnostic names a refused step that its specification does
            not hold.
    """
    state = record.terminal_state
    if state is None:
        raise ValueError("The turn has not ended.")
    telemetry = record.telemetry
    has_data = record.digest is not None and record.digest.has_data
    fetched = _collect_fetched_tables(record)
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
        tables_truncated=fetched.is_truncated,
        tables=fetched.tables,
        highlighted_places=_build_highlighted_places(
            record.digest, fetched.place_dcids
        ),
        specification_origin=(
            None
            if record.specification is None
            else record.specification_origin
        ),
        scripts=tuple(telemetry.scripts),
        script_steps=_build_script_steps(record),
        processing_retries=telemetry.processing_retries,
        rejected_submissions=tuple(
            _build_rejected_submission(submission)
            for submission in record.loop_result.rejected_submissions[
                :MAX_LOGGED_REJECTED_SUBMISSIONS
            ]
        ),
        charts_emitted=telemetry.charts_emitted,
        charts_rejected=telemetry.charts_rejected,
        charts=_build_logged_charts(record, fetched),
    )
    return _fit_tables_to_line_budget(usage)
