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

Each record describes one turn in identifiers, codes, and counts, so that
operators can measure usage from the logs. By default (`include_content=False`),
`content` is `None` and the record does not contain any text from the
conversation. When `include_content=True` (`telemetry.content` set to
`"included"`), `content` holds the turn's user-visible conversation text,
shortened when needed to stay within `MAX_RECORD_LINE_BYTES`.
`build_usage_record` reads the turn's `TurnRecord`, and the agent loop writes
the result with `telemetry.write_structured_record`.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import StrEnum

from narratives_agent.analytics.metrics import ScriptName
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
from narratives_agent.workflows.transcript import Transcript
from narratives_agent.workflows.turn_record import TurnRecord

__all__ = [
    "CHAT_TURN_EVENT",
    "CHAT_TURN_SCHEMA_VERSION",
    "PhaseDuration",
    "RefusalStage",
    "TokenCall",
    "TokenTotals",
    "ToolCallCount",
    "TurnContent",
    "TurnOutcome",
    "UsageRecord",
    "build_usage_record",
]

CHAT_TURN_EVENT = "chat_turn"
# `CHAT_TURN_SCHEMA_VERSION` is the version of the `chat_turn` schema. It
# changes when a key is renamed or removed, or when the type or the meaning
# of a key changes. Adding a key does not change it.
CHAT_TURN_SCHEMA_VERSION = 2


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


@dataclass(frozen=True, kw_only=True)
class TurnContent:
    """Holds the opt-in conversation text of one turn.

    The server attaches this object to `UsageRecord` only when
    `telemetry.content` is `"included"`. When the serialized `chat_turn` line
    would exceed `MAX_RECORD_LINE_BYTES`, the builder shortens the fields in
    priority order and sets `is_truncated` to `True`.

    Attributes:
        query: The user's query for the current turn.
        answer_text: The clean Markdown answer or clarification question, or
            `None` when the turn did not emit any answer text.
        title: The answer title emitted before the first block, or `None`
            when the turn did not emit a title.
        chart_titles: The titles of the emitted charts, in emission order.
        follow_up_questions: The emitted follow-up questions, in emission
            order.
        is_truncated: Whether any field of `TurnContent` was shortened so the
            serialized `chat_turn` line stays within `MAX_RECORD_LINE_BYTES`.
    """

    query: str
    answer_text: str | None
    title: str | None
    chart_titles: tuple[str, ...]
    follow_up_questions: tuple[str, ...]
    is_truncated: bool


@dataclass(frozen=True, kw_only=True)
class UsageRecord(StructuredRecord):
    """Holds the `chat_turn` record of one turn.

    Outside `content`, every string in the record is a code that the server
    defines, an identifier that the server creates, a model name from the
    configuration, or the build SHA. `content` is `None` by default, and
    holds a `TurnContent` only when `telemetry.content` is `"included"`. The
    server writes every field on every record, and a value that does not
    apply is `None`. A caller cannot pass `severity` or `message`, because
    the record derives both from `terminal_state`.

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
        scripts: The analytical scripts that the turn ran, in step order.
        processing_retries: The number of specifications that the server
            returned to the model for another attempt.
        charts_emitted: The number of charts in the answer.
        charts_rejected: The number of charts that the server dropped.
        content: The user-visible conversation text of the turn when
            `telemetry.content` is `"included"`, or `None` when excluded.
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
    # The list has one item for each step of the specification, which holds
    # at most six steps.
    scripts: tuple[ScriptName, ...]
    processing_retries: int
    charts_emitted: int
    charts_rejected: int
    content: TurnContent | None

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


# UTF-8 byte length of the `"null"` placeholder that `content=None` writes.
_NULL_JSON_BYTES = len(b"null")


def _measure_json_bytes(value: object) -> int:
    """Returns the UTF-8 byte length of `value` serialized as compact JSON."""
    return len(
        json.dumps(
            json_safe(value), separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    )


def _truncate_text_value(
    value: str,
    apply: Callable[[str], TurnContent],
    *,
    max_bytes: int,
) -> TurnContent:
    """Shortens `value` to the longest prefix whose content fits `max_bytes`."""
    empty = apply("")
    if _measure_json_bytes(empty) > max_bytes:
        return empty
    low = 0
    high = len(value) - 1
    while low < high:
        mid = (low + high + 1) // 2
        if _measure_json_bytes(apply(value[:mid])) <= max_bytes:
            low = mid
        else:
            high = mid - 1
    return apply(value[:low])


def _truncate_tuple_values(
    values: tuple[str, ...],
    apply: Callable[[tuple[str, ...]], TurnContent],
    *,
    max_bytes: int,
) -> TurnContent:
    """Drops or shortens trailing items of `values` to fit in `max_bytes`."""
    empty = apply(())
    if _measure_json_bytes(empty) > max_bytes:
        return empty
    low = 0
    high = len(values) - 1
    while low < high:
        mid = (low + high + 1) // 2
        if _measure_json_bytes(apply(values[:mid])) <= max_bytes:
            low = mid
        else:
            high = mid - 1
    kept = values[:low]
    trailing = values[low]
    if (
        len(trailing) >= 2
        and _measure_json_bytes(apply((*kept, trailing[:1]))) <= max_bytes
    ):
        return _truncate_text_value(
            trailing,
            lambda prefix: apply((*kept, prefix)),
            max_bytes=max_bytes,
        )
    return apply(kept)


def _build_turn_content(
    record: TurnRecord, transcript: Transcript, *, max_bytes: int
) -> TurnContent:
    """Builds `TurnContent` and shortens its fields to stay in `max_bytes`."""
    content = TurnContent(
        query=transcript.current_query,
        answer_text=record.answer_text,
        title=record.title,
        chart_titles=tuple(chart.title for chart in record.charts),
        follow_up_questions=record.follow_up_questions,
        is_truncated=False,
    )
    if _measure_json_bytes(content) <= max_bytes:
        return content

    current = replace(content, is_truncated=True)
    has_shortened = False
    if answer_text := current.answer_text:
        base = current
        current = _truncate_text_value(
            answer_text,
            lambda text: replace(base, answer_text=text),
            max_bytes=max_bytes,
        )
        has_shortened = True
    if (not has_shortened or _measure_json_bytes(current) > max_bytes) and (
        current.follow_up_questions
    ):
        base = current
        current = _truncate_tuple_values(
            base.follow_up_questions,
            lambda items: replace(base, follow_up_questions=items),
            max_bytes=max_bytes,
        )
        has_shortened = True
    if (not has_shortened or _measure_json_bytes(current) > max_bytes) and (
        current.chart_titles
    ):
        base = current
        current = _truncate_tuple_values(
            base.chart_titles,
            lambda items: replace(base, chart_titles=items),
            max_bytes=max_bytes,
        )
        has_shortened = True
    if (not has_shortened or _measure_json_bytes(current) > max_bytes) and (
        title := current.title
    ):
        base = current
        current = _truncate_text_value(
            title,
            lambda text: replace(base, title=text),
            max_bytes=max_bytes,
        )
        has_shortened = True
    if (not has_shortened or _measure_json_bytes(current) > max_bytes) and (
        current.query
    ):
        base = current
        current = _truncate_text_value(
            base.query,
            lambda text: replace(base, query=text),
            max_bytes=max_bytes,
        )
        has_shortened = True
    return current if has_shortened else content


def build_usage_record(
    record: TurnRecord,
    transcript: Transcript,
    *,
    build_sha: str | None,
    include_content: bool = False,
) -> UsageRecord:
    """Builds the `chat_turn` record of a turn that has ended.

    Args:
        record: The turn's record, after the agent loop set its terminal
            state and finished its telemetry.
        transcript: The verified transcript that the turn ran with. The
            record takes the conversation ID and the turn's index from it,
            and reads `current_query` only when `include_content` is `True`.
        build_sha: The build or commit SHA of the running image, or `None`.
        include_content: Whether to populate `content` with the turn's
            user-visible conversation text, shortened when needed so the
            serialized line stays within `MAX_RECORD_LINE_BYTES`.

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
        scripts=tuple(telemetry.scripts),
        processing_retries=telemetry.processing_retries,
        charts_emitted=telemetry.charts_emitted,
        charts_rejected=telemetry.charts_rejected,
        content=None,
    )
    if not include_content:
        return usage
    envelope_bytes = _measure_json_bytes(usage) - _NULL_JSON_BYTES
    content = _build_turn_content(
        record, transcript, max_bytes=MAX_RECORD_LINE_BYTES - envelope_bytes
    )
    return replace(usage, content=content)
