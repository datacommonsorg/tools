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
"""Runs the agent loop, the phases of one chat turn, as native asyncio code.

`run_turn` drives a turn through its phases in order: classification, the
discovery loop and specification processing, streamed synthesis, chart
configuration, turn signing, and follow-up questions. Each phase reports
progress by calling the turn's `emit` callback with one typed SSE frame at a
time (an `SseFrame` from `sse_frames`, which declares each frame's event name
and payload) and hands its results to the next phase as typed values rather
than shared mutable state.

Every turn that is not canceled ends in one `terminal` frame
(`TerminalCompleteFrame`, `TerminalRefusedFrame`, or `TerminalErrorFrame`).
Every phase reads the conversation through the verified `Transcript`, and
completed turns are appended and signed by `finalize_turn` before the
`complete` frame is sent. Chart configuration runs as an `asyncio.Task`
concurrently with synthesis and is awaited, with a timeout, once synthesis
has finished streaming.
"""

import asyncio
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace

from narratives_agent.analytics.digest import AnalysisDigest
from narratives_agent.analytics.provenance import Source
from narratives_agent.config import load_config
from narratives_agent.config_model import AgentConfig, GeminiRole
from narratives_agent.gemini.client import (
    GeminiBlockedError,
    GeminiError,
    GeminiStreamError,
    async_gemini_stream,
)
from narratives_agent.gemini.schemas import QueryClassification, QueryPattern
from narratives_agent.json_value import JsonObject, JsonValue
from narratives_agent.mcp import client as mcp_client
from narratives_agent.mcp.capabilities import warn_on_missing_tools
from narratives_agent.settings import get_settings
from narratives_agent.telemetry import ErrorType, TerminalState, TurnTelemetry
from narratives_agent.workflows.chart_config import (
    get_chart_config,
    validate_data_response,
)
from narratives_agent.workflows.classify import (
    Clarification,
    RefusedReason,
    TurnRefusedError,
    classify_query,
)
from narratives_agent.workflows.follow_up import generate_follow_up_questions
from narratives_agent.workflows.mcp_loop import (
    DISCOVERY_STATUS,
    PROCESSING_STATUS,
    DiscoveryResult,
    McpLoopError,
    execute_discovery_loop,
    format_count,
)
from narratives_agent.workflows.messages import (
    CHART_CONFIG_STATUS,
    CHAT_DISABLED,
    CLASSIFY_STATUS,
    INTERNAL_ERROR,
    MCP_TOOLS_TIMEOUT,
    MCP_UNAVAILABLE,
    NO_DATA_MESSAGE,
    REFUSED_MESSAGE,
    SYNTHESIS_FAILED,
    SYNTHESIS_STATUS,
    TRUNCATED_MESSAGE,
)
from narratives_agent.workflows.pattern_guidance import append_pattern_guidance
from narratives_agent.workflows.processing import (
    StepRefusalDiagnostic,
    execute_specification,
)
from narratives_agent.workflows.specification import (
    AnalysisSpecification,
    ComputeDerivedMetricStep,
    build_default_specification,
    get_step_output_kind,
)
from narratives_agent.workflows.sse_frames import (
    ChartConfigFrame,
    DataStatusFrame,
    FollowUpsFrame,
    SourcesFrame,
    SseFrame,
    StatusFrame,
    StatusPhase,
    TerminalCompleteFrame,
    TerminalErrorFrame,
    TerminalRefusedFrame,
    TextFrame,
    ThoughtFrame,
    ToolCallFrame,
)
from narratives_agent.workflows.state_slots import build_state_slots
from narratives_agent.workflows.transcript import (
    ConversationStateSlots,
    SignedWindow,
    Transcript,
    finalize_turn,
    transcript_contents,
)
from narratives_agent.workflows.turn_cache import CachedTable, TurnCache

logger = logging.getLogger(__name__)

# Maximum seconds to wait for the background chart task after synthesis ends.
_CHART_CONFIG_JOIN_TIMEOUT_SECONDS = 5

# Maximum seconds to wait for the MCP tool list before aborting the turn.
_MCP_TOOLS_TIMEOUT_SECONDS = 20

# Maximum places with data named per table in the synthesis table inventory.
_INVENTORY_PLACE_CAP = 25

# Fallback source cited when the digest has data but no table reported a URL.
_FALLBACK_SOURCE = Source(name="Data Commons", url="https://datacommons.org/")

_NO_CHARTS: JsonObject = {"should_render": False}

_NO_OBSERVATIONS_NOTE = "No observations were retrieved for the question."

# Default pattern recorded in telemetry when the classifier call failed.
_UNCLASSIFIED_PATTERN: QueryPattern = "exploratory"

type Emit = Callable[[SseFrame], None]


class TurnAbortedError(Exception):
    """Raised when a phase fails and the turn must end in an error.

    `error_type` is a short machine-readable reason for telemetry. The
    message is shown to the user, so it must not carry upstream error text
    that has not been redacted.

    Attributes:
        error_type: Short machine-readable failure category for telemetry.
    """

    def __init__(self, error_type: ErrorType, message: str) -> None:
        super().__init__(message)
        self.error_type = error_type


@dataclass(frozen=True)
class TurnContext:
    """Holds the inputs and callbacks shared across every phase of a turn.

    `classification` is the classify phase's verdict, or `None` when the
    classifier failed and the turn proceeds without a pattern directive.
    `cache` holds the observation tables the turn fetches; it is created
    with the context and discarded with it, so nothing is shared across
    turns or requests.

    Attributes:
        transcript: The verified transcript for the current turn.
        config: The loaded agent configuration.
        telemetry: The turn's telemetry collector.
        emit: Callback invoked with each SSE frame of the turn.
        classification: The classify phase's verdict, or `None` on fallback.
        cache: Per-turn observation table and metadata cache.
    """

    transcript: Transcript
    config: AgentConfig
    telemetry: TurnTelemetry
    emit: Emit
    classification: QueryClassification | None = None
    cache: TurnCache = field(default_factory=TurnCache)


@dataclass
class DiscoveryPhaseResult:
    """Holds the discovery phase outputs passed to later phases.

    `context` is the rendering of the digest and the tables it rests on
    that synthesis and the chart planner read. `sources` is the single
    authority on citation numbering; see `run_discovery_phase`. `tables`
    are the cached tables the specification used, in order of first use,
    from which the state slots are built.

    Attributes:
        context: Rendered digest and table inventory text for synthesis.
        has_data: Whether the resolved digest holds computed data.
        tool_calls: Serialized tool-call records streamed to the client.
        sources: Ordered provenance sources for citation numbering.
        tables: Cached tables used by the specification, in first-use order.
        chart_task: Background task computing chart configuration, if started.
    """

    context: str = ""
    has_data: bool = False
    tool_calls: list[JsonObject] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    tables: tuple[CachedTable, ...] = ()
    chart_task: asyncio.Task[JsonObject] | None = None


def _emit_status(ctx: TurnContext, status: tuple[StatusPhase, str]) -> None:
    """Reports a `(phase, message)` status pair to the browser.

    Args:
        ctx: The turn context holding the `emit` callback.
        status: The `(phase, message)` tuple to emit as a `StatusFrame`.
    """
    phase, message = status
    ctx.emit(StatusFrame(phase=phase, message=message))


async def _run_default_specification(
    ctx: TurnContext,
    specification: AnalysisSpecification,
    notes: list[str],
) -> tuple[AnalysisDigest, AnalysisSpecification]:
    """Runs the default specification and retries without any refused step.

    When a step of the default refuses, the default runs again without that
    step's relation or table so the remaining tables still answer the turn,
    and each refusal is appended to `notes`. When a retry leaves no table,
    or processing times out, the digest holds the results completed before
    the last failure and carries the failure in `notes`.

    Args:
        ctx: The turn context holding the classification, cache, and telemetry.
        specification: The initial default specification built over the cache.
        notes: Mutable list of missing-data notes accumulated before and during
            the default specification run.

    Returns:
        A `(digest, specification)` pair holding the resulting `AnalysisDigest`
        and the final `AnalysisSpecification` that was executed.
    """
    logger.info(
        "Running the default specification %s over the cache",
        specification.list_script_names(),
    )
    _emit_status(ctx, PROCESSING_STATUS)
    with ctx.telemetry.phase("processing"):
        outcome = await execute_specification(specification, ctx.cache)
        relate = True
        excluded: set[str] = set()
        # Each retry drops the relation or the refused step's table, so there
        # is at most one retry per fetched table plus one for the relation; a
        # timeout names no step and is not retried.
        while isinstance(outcome, StepRefusalDiagnostic):
            if outcome.script == "relate_cohorts" and relate:
                relate = False
            elif (
                outcome.input_table_ids
                and (table_id := outcome.input_table_ids[0]) not in excluded
            ):
                excluded.add(table_id)
            else:
                break
            retry = build_default_specification(
                ctx.classification,
                ctx.cache,
                should_relate=relate,
                excluded_table_ids=frozenset(excluded),
            )
            if retry is None:
                break
            notes.append(f"An analysis step failed: {outcome.message}")
            specification = retry
            logger.info(
                "Default specification step %s (%s) refused; running %s",
                outcome.step_id,
                outcome.script,
                specification.list_script_names(),
            )
            outcome = await execute_specification(specification, ctx.cache)
    if isinstance(outcome, AnalysisDigest):
        return (
            replace(outcome, missing_notes=(*outcome.missing_notes, *notes)),
            specification,
        )
    notes.append(f"The default analysis also failed: {outcome.message}")
    return (
        AnalysisDigest.from_results(
            (
                outcome.completed_results
                if isinstance(outcome, StepRefusalDiagnostic)
                else ()
            ),
            missing_notes=tuple(notes),
        ),
        specification,
    )


async def _resolve_digest(
    ctx: TurnContext, loop: DiscoveryResult
) -> tuple[AnalysisDigest, AnalysisSpecification | None]:
    """Returns the digest the turn is answered from, and its specification.

    An accepted specification and a no-data report each settle the digest.
    Otherwise the loop ended at a bound, with a prose reply, or with its
    retries exhausted, and the turn is answered from a default
    specification over the fetched tables rather than from partial raw
    data. When no fetched table has rows, the digest is empty and says so.

    Args:
        ctx: The turn context holding the classification, cache, and telemetry.
        loop: The completed discovery loop result.

    Returns:
        A `(digest, specification)` pair holding the resolved `AnalysisDigest`
        and the `AnalysisSpecification` that produced it, or `None` when no
        specification ran.
    """
    if loop.digest is not None:
        return loop.digest, loop.specification
    if loop.unavailable is not None:
        return (
            AnalysisDigest(
                results=(),
                sources=(),
                missing_notes=(loop.unavailable.format_note(),),
            ),
            None,
        )
    notes: list[str] = []
    if loop.last_diagnostic is not None:
        notes.append(f"An analysis step failed: {loop.last_diagnostic.message}")
    specification = build_default_specification(ctx.classification, ctx.cache)
    if specification is None:
        notes.append(_NO_OBSERVATIONS_NOTE)
        return (
            AnalysisDigest(
                results=(),
                sources=(),
                missing_notes=tuple(notes),
            ),
            None,
        )
    return await _run_default_specification(ctx, specification, notes)


def _collect_tables_used(
    specification: AnalysisSpecification | None, cache: TurnCache
) -> tuple[CachedTable, ...]:
    """Returns the cached tables a specification used, fetched ones first.

    Only the steps that produce a table are looked up by step id, so a
    result-only step never resolves to a derived table left in the cache by
    an earlier run that happened to use the same id.

    Args:
        specification: The specification that answered the turn, or `None`.
        cache: The turn's table cache.

    Returns:
        A tuple of `CachedTable` entries in first-use order.
    """
    if specification is None:
        return ()
    # list_referenced_table_ids returns only fetched (`t<n>`) table IDs, in
    # first-reference order; the derived (`s<n>`) step IDs follow them.
    table_ids = [
        *specification.list_referenced_table_ids(),
        *(
            step.step_id
            for step in specification.steps
            if get_step_output_kind(step) == "table"
        ),
    ]
    tables = (cache.get(table_id) for table_id in dict.fromkeys(table_ids))
    return tuple(table for table in tables if table is not None)


def _describe_derived_inputs(
    specification: AnalysisSpecification | None,
) -> dict[str, str]:
    """Maps each derived table's step id to a description of its inputs.

    Args:
        specification: The specification that answered the turn, or `None`.

    Returns:
        A dictionary mapping derived step IDs to `"derived from <left> and
        <right>"`.
    """
    if specification is None:
        return {}
    return {
        step.step_id: f"derived from {step.left} and {step.right}"
        for step in specification.steps
        if isinstance(step, ComputeDerivedMetricStep)
    }


def render_analysis_context(
    digest: AnalysisDigest,
    specification: AnalysisSpecification | None,
    tables: Sequence[CachedTable],
) -> str:
    """Renders the digest and its tables as the text synthesis reads.

    This adapter feeds the existing synthesis prompt and chart planner,
    which read one block of text, a rendering of the digest in place of raw
    tool results. Everything in the text is computed or fetched by the
    server: the digest's results and missing-data notes, then one line per
    table. The specification's `findings` are not included, because they
    are the model's reading of five sample rows and the digest holds the
    computed figures. The chart planner extracts variable DCIDs, place
    DCIDs, parent places, and child place types from the text, so the
    inventory lists each fetched table's identity and places alongside the
    computed figures. A derived table is listed by name only, marked as not
    a Data Commons variable, because its DCID names no series the chart web
    components could fetch.

    Args:
        digest: The computed `AnalysisDigest` for the turn.
        specification: The `AnalysisSpecification` that produced `digest`, or
            `None` when no specification ran.
        tables: The cached tables used by `specification`.

    Returns:
        The formatted digest and table inventory text.
    """
    lines = [digest.format_for_prompt()]
    if tables:
        lines.append("\nTables used:")
    derived_inputs = _describe_derived_inputs(specification)
    for cached in tables:
        table_id = cached.table_id
        table = cached.table
        dates = sorted({row.date for row in table.rows})
        # table.places_with_data is already sorted and deduplicated by
        # ObservationTable.
        places = table.places_with_data
        named = ", ".join(
            f"{table.place_names.get(place, place)} ({place})"
            for place in places[:_INVENTORY_PLACE_CAP]
        )
        if len(places) > _INVENTORY_PLACE_CAP:
            extra = len(places) - _INVENTORY_PLACE_CAP
            named += f", and {format_count(extra, 'other place')}"
        scope = (
            f"every {table.child_place_type} in {table.parent_place_dcid}"
            if table.child_place_type and table.parent_place_dcid
            else format_count(len(places), "place")
        )
        span = f"{dates[0]} to {dates[-1]}" if dates else "no dates"
        if table_id in derived_inputs:
            identity = (
                f"{table_id} ({derived_inputs[table_id]}; not a "
                f"Data Commons variable, do not chart it): "
                f"{table.variable_name}"
            )
        else:
            identity = (
                f"{table_id}: {table.variable_name} ({table.variable_dcid})"
            )
        unit = table.unit or "unknown"
        if table.scaling_factor is not None:
            unit += f" (scaling factor {table.scaling_factor:g})"
        lines.append(
            f"- {identity}; unit: {unit}; {scope}; dates {span}; places with "
            f"data: {named or 'none'}"
        )
    return "\n".join(lines)


async def run_discovery_phase(ctx: TurnContext) -> DiscoveryPhaseResult:
    """Finds and analyzes the data, the discovery and processing phases.

    Runs the discovery loop, resolves the digest the turn is answered from,
    streams the tool calls, the data status, and the provenance sources,
    records the phase's telemetry counts, and starts chart configuration in
    the background when the digest has data.

    Args:
        ctx: The turn context holding the transcript, config, telemetry, and
            cache.

    Returns:
        The populated `DiscoveryPhaseResult` for synthesis and chart planning.

    Raises:
        TurnAbortedError: If no MCP tools are available or the loop fails.
            MCP is a hard dependency: synthesis must not answer from
            general knowledge or run on the empty or partial tables left
            behind by a failed loop.
        GeminiBlockedError: If Gemini blocks the prompt or the candidate of
            a loop iteration.
    """
    result = DiscoveryPhaseResult()
    if not ctx.config.mcp.enabled:
        return result
    mcp_client.ensure_session_scope()
    try:
        async with asyncio.timeout(_MCP_TOOLS_TIMEOUT_SECONDS):
            tools = await mcp_client.async_get_tools()
    except TimeoutError as error:
        logger.warning(
            "MCP tool list did not arrive within %d seconds",
            _MCP_TOOLS_TIMEOUT_SECONDS,
        )
        raise TurnAbortedError(
            ErrorType.MCP_TIMEOUT, MCP_TOOLS_TIMEOUT
        ) from error
    if not tools:
        logger.warning("MCP unavailable: not connected or no tools available")
        raise TurnAbortedError(ErrorType.MCP_UNAVAILABLE, MCP_UNAVAILABLE)
    warn_on_missing_tools(tools)

    _emit_status(ctx, DISCOVERY_STATUS)
    try:
        loop = await execute_discovery_loop(
            ctx.transcript,
            ctx.config,
            tools,
            ctx.telemetry,
            ctx.cache,
            thought_callback=lambda text: ctx.emit(
                ThoughtFrame(thought=text, phase="discovery")
            ),
            status_callback=lambda phase, message: ctx.emit(
                StatusFrame(phase=phase, message=message)
            ),
            classification=ctx.classification,
        )
    except McpLoopError as error:
        raise TurnAbortedError(error.error_type, str(error)) from error

    result.tool_calls = loop.tool_calls
    for call in result.tool_calls:
        ctx.emit(ToolCallFrame(tool_call=call))

    digest, specification = await _resolve_digest(ctx, loop)
    result.has_data = digest.has_data
    result.tables = _collect_tables_used(specification, ctx.cache)
    ctx.telemetry.scripts = (
        specification.list_script_names() if specification is not None else []
    )
    ctx.telemetry.tables_fetched = ctx.cache.tables_fetched
    ctx.telemetry.total_rows_fetched = ctx.cache.total_rows_fetched
    ctx.telemetry.processing_retries = loop.processing_retries

    # Include `truncated` on `data_status` so the UI knows when data was cut.
    message: str | None = None
    if not result.has_data:
        message = TRUNCATED_MESSAGE if loop.truncated else NO_DATA_MESSAGE
    ctx.emit(
        DataStatusFrame(
            data_status={
                "has_data": result.has_data,
                "truncated": loop.truncated,
                "message": message,
            }
        )
    )

    # digest.sources is already deduplicated in first-use order by
    # execute_specification; use it as the single authority on citation numbers.
    result.sources = list(digest.sources)
    if result.has_data and not result.sources:
        # Cite Data Commons when the tables that answered carried no source URL.
        result.sources = [_FALLBACK_SOURCE]
    if result.sources:
        ctx.emit(SourcesFrame(sources=result.sources))

    result.context = render_analysis_context(
        digest, specification, result.tables
    )
    # Only generate charts when the digest holds computed figures.
    if result.has_data:
        result.chart_task = asyncio.create_task(
            get_chart_config(
                result.context,
                ctx.transcript.current_query,
                ctx.config,
                ctx.telemetry.tokens,
            ),
            name="chart-config",
        )
    else:
        logger.info(
            "Chart config skipped: the digest has no data (truncated=%s, "
            "unavailable=%s)",
            loop.truncated,
            loop.unavailable is not None,
        )
    return result


def _build_synthesis_message(
    user_message: str, discovery: DiscoveryPhaseResult
) -> str:
    """Builds the final user message that carries the analysis.

    Args:
        user_message: The user's current query text.
        discovery: The completed discovery phase result.

    Returns:
        The formatted user prompt combining numbered sources and data results.
    """
    context_parts = []
    if discovery.context:
        # Number sources 1..N in the order streamed to the UI as `sources`.
        if discovery.sources:
            numbered_sources = "\n".join(
                f"[{number}] {source.name or source.url} - {source.url}"
                for number, source in enumerate(discovery.sources, start=1)
            )
            context_parts.append(
                "**NUMBERED SOURCES - cite these numbers, exactly as given:**\n"
                f"{numbered_sources}"
            )
        context_parts.append(f"**DATA RESULTS:**\n{discovery.context}")
    context = (
        "\n".join(context_parts)
        if context_parts
        else "No additional context available."
    )
    return (
        f"User Query: {user_message}\n\n{context}\n\n"
        "Please provide a comprehensive response combining all available "
        "information."
    )


async def run_synthesis_phase(
    ctx: TurnContext, discovery: DiscoveryPhaseResult
) -> str:
    """Streams the narrative answer, the synthesis phase.

    Args:
        ctx: The turn context holding the transcript, config, and telemetry.
        discovery: The discovery phase result to synthesize into prose.

    Returns:
        The complete answer text.

    Raises:
        TurnAbortedError: If the synthesis request fails, its stream breaks
            part-way, or it returns no answer text.
        GeminiBlockedError: If Gemini blocks the synthesis prompt or the
            candidate before any answer text has streamed.
    """
    ctx.emit(StatusFrame(phase="synthesis", message=SYNTHESIS_STATUS))
    config = ctx.config
    role = config.resolve_role_config(GeminiRole.SYNTHESIS)
    # Put the verified window first, then the query with the analysis context.
    messages = transcript_contents(
        ctx.transcript,
        _build_synthesis_message(ctx.transcript.current_query, discovery),
    )
    try:
        stream = await async_gemini_stream(
            messages=messages,
            system_instruction=append_pattern_guidance(
                config.prompts.synthesis, ctx.classification, "synthesis"
            ),
            model=role.model,
            temperature=role.temperature,
            thinking_level=role.thinking_level,
            token_usage=ctx.telemetry.tokens,
            include_thoughts=True,
        )
    except GeminiBlockedError:
        # Propagates to `run_turn`, which ends the turn as `refused`.
        raise
    except GeminiError as error:
        # The client has already logged the redacted upstream error, so the
        # user receives a fixed message.
        raise TurnAbortedError(
            ErrorType.SYNTHESIS_ERROR, SYNTHESIS_FAILED
        ) from error

    full_text = ""
    try:
        async for chunk in stream:
            if chunk.kind == "thought":
                ctx.emit(ThoughtFrame(thought=chunk.text, phase="synthesis"))
            else:
                full_text += chunk.text
                ctx.emit(TextFrame(text=chunk.text))
    except GeminiBlockedError as error:
        if not full_text.strip():
            raise
        # Once answer text has streamed to the client, a mid-stream block
        # leaves the response truncated and is reported as a stream error.
        raise TurnAbortedError(
            ErrorType.SYNTHESIS_STREAM_ERROR, SYNTHESIS_FAILED
        ) from error
    except GeminiStreamError as error:
        raise TurnAbortedError(
            ErrorType.SYNTHESIS_STREAM_ERROR, SYNTHESIS_FAILED
        ) from error
    finally:
        await stream.aclose()
    if not full_text.strip():
        logger.warning("Synthesis returned no answer text")
        raise TurnAbortedError(ErrorType.SYNTHESIS_EMPTY, SYNTHESIS_FAILED)
    return full_text


async def resolve_chart_config(
    ctx: TurnContext, discovery: DiscoveryPhaseResult, full_text: str
) -> JsonObject:
    """Determines whether to display charts and returns their configuration.

    Charts are best-effort because the answer has already streamed when this
    phase runs. They are hidden when a second model call finds that the
    answer does not contain data or when that call fails, and they are
    omitted when chart configuration fails or does not finish within
    `_CHART_CONFIG_JOIN_TIMEOUT_SECONDS`.

    Args:
        ctx: The turn context holding the transcript, config, and telemetry.
        discovery: The discovery phase result holding the background chart task.
        full_text: The complete synthesized answer text.

    Returns:
        The resolved chart configuration JSON object.
    """
    if discovery.chart_task is None:
        return dict(_NO_CHARTS)
    ctx.emit(StatusFrame(phase="chart_config", message=CHART_CONFIG_STATUS))
    show_charts = True
    if full_text:
        try:
            show_charts = await validate_data_response(
                full_text,
                ctx.transcript.current_query,
                ctx.config,
                ctx.telemetry.tokens,
            )
        except Exception as error:
            logger.warning(
                "Chart validation failed with %s; hiding charts",
                type(error).__name__,
            )
            show_charts = False
        else:
            if not show_charts:
                logger.info("Chart validation found no data; hiding charts")
    try:
        # `wait_for` cancels the task when the timeout expires.
        chart_config = await asyncio.wait_for(
            discovery.chart_task, _CHART_CONFIG_JOIN_TIMEOUT_SECONDS
        )
    except TimeoutError:
        logger.warning(
            "Chart config did not finish within %d seconds; rendering "
            "without charts",
            _CHART_CONFIG_JOIN_TIMEOUT_SECONDS,
        )
        chart_config = dict(_NO_CHARTS)
    except Exception:
        # `_settle_chart_task` logs the task exception when the turn ends.
        chart_config = dict(_NO_CHARTS)
    if not show_charts:
        chart_config["hide_charts"] = True
    return chart_config


def _collect_chart_topics(chart_config: Mapping[str, JsonValue]) -> list[str]:
    """Returns the chart titles that ground the follow-up questions.

    Args:
        chart_config: The resolved chart configuration dictionary.

    Returns:
        A list of non-empty chart title strings.
    """
    charts = chart_config.get("charts")
    topics: list[str] = []
    if isinstance(charts, list):
        for chart in charts:
            if isinstance(chart, dict):
                chart_title = chart.get("title")
                if isinstance(chart_title, str) and chart_title:
                    topics.append(chart_title)
    title = chart_config.get("title")
    if not topics and isinstance(title, str) and title:
        # Legacy single-chart shape.
        topics.append(title)
    return topics


async def run_followups(
    ctx: TurnContext, chart_config: Mapping[str, JsonValue]
) -> None:
    """Emits follow-up questions grounded in the chart topics.

    This phase runs after the terminal event so the UI can display the
    answer and charts immediately and show the follow-up questions when they
    arrive. If there are no chart topics or generation fails, nothing is
    emitted.

    Args:
        ctx: The turn context holding the transcript, config, and telemetry.
        chart_config: The resolved chart configuration dictionary.
    """
    try:
        follow_ups = await generate_follow_up_questions(
            ctx.transcript.current_query,
            _collect_chart_topics(chart_config),
            ctx.config,
            ctx.telemetry.tokens,
        )
        if follow_ups:
            ctx.emit(FollowUpsFrame(follow_up_questions=follow_ups))
    except Exception as error:
        logger.warning("Follow-up generation failed: %s", type(error).__name__)


def _load_turn_config() -> AgentConfig:
    """Returns the agent configuration, or raises `TurnAbortedError`.

    Returns:
        The loaded `AgentConfig`.

    Raises:
        TurnAbortedError: With reason `config_missing` if no configuration
            is loaded.
    """
    config = load_config()
    if config is None:
        raise TurnAbortedError(
            ErrorType.CONFIG_MISSING, "Backend config not loaded"
        )
    return config


async def run_turn(transcript: Transcript, emit: Emit) -> None:
    """Runs one chat turn and emits its typed SSE frames through `emit`.

    Runs classification first: refuses adversarial or off-domain queries,
    streams and signs a clarification question when disambiguation is
    required, or admits the query into the discovery loop, synthesis, chart
    configuration, and turn signing. A model call that Gemini blocks in any
    of those phases ends the turn as `refused` with reason `safety_blocked`;
    the phases let `GeminiBlockedError` propagate here rather than each
    translating it. Every non-canceled turn ends in one `terminal` frame
    (`complete`, `refused`, or `error`) and records its outcome and
    classified pattern in telemetry. Only `asyncio.CancelledError` is
    re-raised to the caller; cancellation emits no terminal frame because the
    client has already disconnected, and it is recorded as `canceled` unless
    the turn has already completed. Follow-up questions are emitted after the
    terminal frame, and the background chart task is settled whenever the
    turn ends so no orphaned task outlives the request.

    Args:
        transcript: The verified transcript holding the current query,
            idempotency key, and prior turns.
        emit: The callback invoked with each SSE frame of the turn.
    """
    idempotency_key = transcript.current_idempotency_key
    telemetry = TurnTelemetry()
    state: TerminalState | None = None
    error_type: ErrorType | RefusedReason | None = None
    chart_task: asyncio.Task[JsonObject] | None = None
    try:
        if not get_settings().enable_chat:
            state, error_type = TerminalState.REFUSED, ErrorType.CHAT_DISABLED
            emit(
                TerminalErrorFrame(
                    idempotency_key=idempotency_key,
                    error=CHAT_DISABLED,
                    reason=ErrorType.CHAT_DISABLED,
                )
            )
            return
        config = _load_turn_config()
        emit(StatusFrame(phase="classify", message=CLASSIFY_STATUS))
        with telemetry.phase("classify"):
            admission = await classify_query(transcript, config, telemetry)
        telemetry.pattern = (
            admission.classification.pattern
            if admission.classification is not None
            else _UNCLASSIFIED_PATTERN
        )
        ctx = TurnContext(
            transcript, config, telemetry, emit, admission.classification
        )
        if isinstance(admission, Clarification):
            window = await run_clarification(ctx, admission.question)
            state = TerminalState.COMPLETE
            emit(
                TerminalCompleteFrame(
                    idempotency_key=idempotency_key, window=window
                )
            )
            return
        # Processing runs inside discovery are also timed under their own phase.
        with telemetry.phase("discovery"):
            discovery = await run_discovery_phase(ctx)
        chart_task = discovery.chart_task
        with telemetry.phase("synthesis"):
            full_text = await run_synthesis_phase(ctx, discovery)
        with telemetry.phase("chart_config"):
            chart_config = await resolve_chart_config(ctx, discovery, full_text)
        emit(ChartConfigFrame(chart_config=chart_config))
        with telemetry.phase("finalize"):
            window = await _sign_turn(
                ctx,
                full_text,
                lambda: build_state_slots(discovery.tables, chart_config),
            )
        state = TerminalState.COMPLETE
        emit(
            TerminalCompleteFrame(
                idempotency_key=idempotency_key, window=window
            )
        )
        with telemetry.phase("follow_ups"):
            await run_followups(ctx, chart_config)
    except TurnRefusedError as refusal:
        state, error_type = TerminalState.REFUSED, refusal.reason
        emit(
            TerminalRefusedFrame(
                idempotency_key=idempotency_key,
                reason=refusal.reason,
                message=str(refusal),
            )
        )
    except GeminiBlockedError:
        state, error_type = TerminalState.REFUSED, RefusedReason.SAFETY_BLOCKED
        emit(
            TerminalRefusedFrame(
                idempotency_key=idempotency_key,
                reason=RefusedReason.SAFETY_BLOCKED,
                message=REFUSED_MESSAGE,
            )
        )
    except TurnAbortedError as error:
        state, error_type = TerminalState.ERROR, error.error_type
        emit(
            TerminalErrorFrame(
                idempotency_key=idempotency_key,
                error=str(error),
                reason=error.error_type,
            )
        )
    except asyncio.CancelledError:
        state = state or TerminalState.CANCELED
        raise
    except Exception:
        logger.exception("Chat turn failed")
        state, error_type = TerminalState.ERROR, ErrorType.INTERNAL_ERROR
        emit(
            TerminalErrorFrame(
                idempotency_key=idempotency_key,
                error=INTERNAL_ERROR,
                reason=ErrorType.INTERNAL_ERROR,
            )
        )
    finally:
        _settle_chart_task(chart_task)
        telemetry.finish(state or TerminalState.ERROR, error_type)


async def run_clarification(
    ctx: TurnContext, question: str
) -> SignedWindow | None:
    """Streams `question` as the turn response and signs it with empty slots.

    No `data_status`, `sources`, `chart_config`, or `follow_ups` events are
    emitted because no observations were retrieved.

    Args:
        ctx: The turn context holding the transcript, config, and telemetry.
        question: The clarification question to stream to the user.

    Returns:
        The signed conversation window, or `None` if signing failed.
    """
    ctx.emit(TextFrame(text=question))
    with ctx.telemetry.phase("finalize"):
        return await _sign_turn(ctx, question, ConversationStateSlots)


async def _sign_turn(
    ctx: TurnContext,
    full_text: str,
    state_slots: Callable[[], ConversationStateSlots],
) -> SignedWindow | None:
    """Builds the turn's state slots and signs the turn into the window.

    Because the answer has already been delivered, a failure here is logged
    and the turn completes unsigned, as an answer too long to sign does: the
    browser leaves it out of later context and keeps the window it holds.

    Args:
        ctx: The turn context holding the transcript, config, and telemetry.
        full_text: The complete model response text for the turn.
        state_slots: Zero-argument callable that builds the turn's state slots.

    Returns:
        The signed conversation window, or `None` if signing failed or the
        response exceeded the signing length limit.
    """
    try:
        return await finalize_turn(
            ctx.transcript,
            full_text,
            state_slots(),
            ctx.config,
            ctx.telemetry.tokens,
        )
    except Exception as error:
        logger.error(
            "Signing the turn failed with %s; completing it unsigned",
            type(error).__name__,
        )
        return None


def _settle_chart_task(task: asyncio.Task[JsonObject] | None) -> None:
    """Cancels the chart task if it is still running, or logs its error.

    This is the one place a chart task failure is logged, whether
    `resolve_chart_config` contained it or synthesis failed before the task
    was awaited. Retrieving the exception also prevents the "exception was
    never retrieved" warning that asyncio logs when a failed task that no
    one awaited is garbage collected.

    Args:
        task: The background chart configuration task, or `None`.
    """
    if task is None:
        return
    if not task.done():
        task.cancel()
    elif not task.cancelled() and (error := task.exception()) is not None:
        logger.warning("Chart config failed: %s", type(error).__name__)


__all__ = [
    "DiscoveryPhaseResult",
    "Emit",
    "TurnAbortedError",
    "TurnContext",
    "render_analysis_context",
    "resolve_chart_config",
    "run_clarification",
    "run_discovery_phase",
    "run_followups",
    "run_synthesis_phase",
    "run_turn",
]
