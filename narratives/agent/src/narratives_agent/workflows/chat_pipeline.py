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
discovery loop and specification processing, streamed synthesis with
interleaved text and chart blocks, turn signing, and follow-up questions. Each
phase reports progress by calling the turn's `emit` callback with one typed
SSE frame at a time (an `SseFrame` from `sse_frames`, which declares each
frame's event name and payload) and hands its results to the next phase as
typed values rather than shared mutable state.

Every turn that is not canceled ends in one `terminal` frame
(`TerminalCompleteFrame`, `TerminalRefusedFrame`, or `TerminalErrorFrame`).
Every phase reads the conversation through the verified `Transcript`, and
completed turns are appended and signed by `finalize_turn` before the
`complete` frame is sent.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator, Callable, Sequence
from dataclasses import dataclass, field, replace

from narratives_agent.analytics.digest import AnalysisDigest
from narratives_agent.analytics.provenance import Source
from narratives_agent.analytics.tables import ObservationTable
from narratives_agent.config import load_config
from narratives_agent.config_model import AgentConfig, GeminiRole
from narratives_agent.gemini.client import (
    GeminiBlockedError,
    GeminiError,
    GeminiStreamError,
    async_gemini_stream,
)
from narratives_agent.gemini.response import StreamChunk
from narratives_agent.gemini.schemas import QueryClassification, QueryPattern
from narratives_agent.json_value import JsonObject
from narratives_agent.mcp import client as mcp_client
from narratives_agent.mcp.capabilities import warn_on_missing_tools
from narratives_agent.settings import get_settings
from narratives_agent.telemetry import ErrorType, TerminalState, TurnTelemetry
from narratives_agent.workflows.blocks import BlockSplitter, TextBlock
from narratives_agent.workflows.chart_defaults import build_default_charts
from narratives_agent.workflows.charts import (
    ChartSpecification,
    ResolvedChart,
    resolve_chart_specification,
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
)
from narratives_agent.workflows.messages import (
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
from narratives_agent.workflows.processing import (
    StepRefusalDiagnostic,
    execute_specification,
)
from narratives_agent.workflows.prompt_contracts import (
    compose_system_instruction,
)
from narratives_agent.workflows.specification import (
    AnalysisSpecification,
    build_default_specification,
    get_step_output_kind,
)
from narratives_agent.workflows.sse_frames import (
    BlockContentFrame,
    DataStatusFrame,
    FollowUpsFrame,
    SourcesFrame,
    SseFrame,
    StatusFrame,
    StatusPhase,
    TerminalCompleteFrame,
    TerminalErrorFrame,
    TerminalRefusedFrame,
    ThoughtFrame,
    ToolCallFrame,
)
from narratives_agent.workflows.state_slots import build_state_slots
from narratives_agent.workflows.synthesis import (
    SYNTHESIS_CHUNK_TIMEOUT_SECONDS,
    build_synthesis_inputs,
    render_synthesis_message,
)
from narratives_agent.workflows.transcript import (
    ConversationStateSlots,
    SignedWindow,
    Transcript,
    finalize_turn,
    transcript_contents,
)
from narratives_agent.workflows.turn_cache import CachedTable, TurnCache

logger = logging.getLogger(__name__)

# Maximum seconds to wait for the MCP tool list before aborting the turn.
_MCP_TOOLS_TIMEOUT_SECONDS = 20

# Maximum places named in a follow-up topic before keeping the variable alone.
_FOLLOW_UP_PLACE_CAP = 3

# Fallback source cited when the digest has data but no table reported a URL.
_FALLBACK_SOURCE = Source(name="Data Commons", url="https://datacommons.org/")

# Generic fallback note when the discovery loop ends without tables or an
# unavailable report; passed to synthesis and excluded from follow-up topics.
_NO_OBSERVATIONS_NOTE = "No observations were retrieved for the question."

# Prefixes of missing-data notes that report a processing failure rather than a
# data gap, excluded from follow-up topics.
_STEP_FAILED_NOTE_PREFIX = "An analysis step failed: "
_DEFAULT_FAILED_NOTE_PREFIX = "The default analysis also failed: "
_DIAGNOSTIC_NOTE_PREFIXES = (
    _STEP_FAILED_NOTE_PREFIX,
    _DEFAULT_FAILED_NOTE_PREFIX,
)

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


def _build_empty_digest() -> AnalysisDigest:
    """Returns the digest of a turn that computed nothing."""
    return AnalysisDigest(results=(), sources=())


@dataclass
class DiscoveryPhaseResult:
    """Holds the discovery phase outputs passed to later phases.

    `digest` is the analysis the turn is answered from and `spec` is the
    specification that produced it, or `None` when the turn has none.
    `sources` is the single authority on citation numbering; see
    `run_discovery_phase`. `tables` are the cached tables the specification
    used, in order of first use, from which the table inventory and the
    state slots are built.

    Attributes:
        digest: The resolved `AnalysisDigest` for the turn.
        spec: The `AnalysisSpecification` that produced `digest`, or `None`
            when no specification ran.
        has_data: Whether the resolved digest holds computed data.
        tool_calls: Serialized tool-call records streamed to the client.
        sources: Ordered provenance sources for citation numbering.
        tables: Cached tables used by the specification, in first-use order.
    """

    digest: AnalysisDigest = field(default_factory=_build_empty_digest)
    spec: AnalysisSpecification | None = None
    has_data: bool = False
    tool_calls: list[JsonObject] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    tables: tuple[CachedTable, ...] = ()


@dataclass(frozen=True)
class SynthesisPhaseResult:
    """Holds what the synthesis phase streamed.

    `text` is the answer that is signed: the text blocks joined by blank
    lines, with every chart block left out. `charts` are the resolved
    charts in the order their blocks were emitted.

    Attributes:
        text: The signed prose text with chart blocks excluded.
        charts: Resolved charts in emission order.
    """

    text: str
    charts: tuple[ResolvedChart, ...] = ()


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
            notes.append(f"{_STEP_FAILED_NOTE_PREFIX}{outcome.message}")
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
    notes.append(f"{_DEFAULT_FAILED_NOTE_PREFIX}{outcome.message}")
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
        notes.append(
            f"{_STEP_FAILED_NOTE_PREFIX}{loop.last_diagnostic.message}"
        )
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


async def run_discovery_phase(ctx: TurnContext) -> DiscoveryPhaseResult:
    """Finds and analyzes the data, the discovery and processing phases.

    Runs the discovery loop, resolves the digest the turn is answered from,
    streams the tool calls, the data status, and the provenance sources,
    and records the phase's telemetry counts.

    Args:
        ctx: The turn context holding the transcript, config, telemetry, and
            cache.

    Returns:
        The populated `DiscoveryPhaseResult` for synthesis, state slots, and
        follow-up generation.

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
    result.digest = digest
    result.spec = specification
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
    return result


async def run_synthesis_phase(
    ctx: TurnContext, discovery: DiscoveryPhaseResult
) -> SynthesisPhaseResult:
    """Streams the answer as text and chart blocks, the synthesis phase.

    The user message is rendered from the typed inputs at the last moment,
    the stream is split into blocks as it arrives, and every chart block is
    resolved against the turn's table inventory and cache before it is
    emitted. When the digest has data and no chart block was emitted, at
    most one default chart from the primary result is appended. Opening the
    stream and reading each chunk are bounded by
    `SYNTHESIS_CHUNK_TIMEOUT_SECONDS`, so a stalled stream ends the turn
    rather than holding it open for the whole HTTP timeout.

    Args:
        ctx: The turn context holding the transcript, config, and telemetry.
        discovery: The discovery phase result to synthesize into prose.

    Returns:
        The signed text and the resolved charts.

    Raises:
        TurnAbortedError: If the synthesis request fails, its stream breaks
            or stalls part-way, or it returns no prose.
        GeminiBlockedError: If Gemini blocks the synthesis prompt or the
            candidate before any answer block has been emitted.
    """
    ctx.emit(StatusFrame(phase="synthesis", message=SYNTHESIS_STATUS))
    config = ctx.config
    role = config.resolve_role_config(GeminiRole.SYNTHESIS)
    inputs = build_synthesis_inputs(
        ctx.transcript.current_query,
        discovery.digest,
        discovery.spec,
        discovery.tables,
        discovery.sources,
    )
    # Put the verified window first, then the query with the analysis context.
    messages = transcript_contents(
        ctx.transcript, render_synthesis_message(inputs)
    )
    try:
        async with asyncio.timeout(SYNTHESIS_CHUNK_TIMEOUT_SECONDS):
            stream = await async_gemini_stream(
                messages=messages,
                system_instruction=compose_system_instruction(
                    config.prompts.synthesis, "synthesis", ctx.classification
                ),
                model=role.model,
                temperature=role.temperature,
                thinking_level=role.thinking_level,
                token_usage=ctx.telemetry.tokens,
                include_thoughts=True,
            )
    except TimeoutError as error:
        logger.warning(
            "Synthesis stream stalled for %.0f seconds",
            SYNTHESIS_CHUNK_TIMEOUT_SECONDS,
        )
        raise TurnAbortedError(
            ErrorType.SYNTHESIS_STREAM_ERROR, SYNTHESIS_FAILED
        ) from error
    except GeminiBlockedError:
        # Propagates to `run_turn`, which ends the turn as `refused`.
        raise
    except GeminiError as error:
        # The client has already logged the redacted upstream error, so the
        # user receives a fixed message.
        raise TurnAbortedError(
            ErrorType.SYNTHESIS_ERROR, SYNTHESIS_FAILED
        ) from error

    allowed_table_ids = {entry.table_id for entry in discovery.tables}

    def resolve(spec: ChartSpecification) -> ResolvedChart | None:
        if not discovery.has_data:
            logger.info("Chart block rejected: turn has no data")
            return None
        for table_id in spec.tables:
            if table_id not in allowed_table_ids:
                logger.info(
                    "Chart block rejected: %s is not in the table inventory",
                    table_id,
                )
                return None
        return resolve_chart_specification(
            spec, ctx.cache, discovery.digest, discovery.spec
        )

    splitter = BlockSplitter(
        on_block=lambda block: ctx.emit(BlockContentFrame(block=block)),
        resolve_chart=resolve,
    )
    try:
        await _consume_synthesis_stream(ctx, stream, splitter)
        splitter.finish()
        if not splitter.text:
            logger.warning("Synthesis returned no answer text")
            raise TurnAbortedError(ErrorType.SYNTHESIS_EMPTY, SYNTHESIS_FAILED)
        if discovery.has_data and not splitter.charts:
            for default in build_default_charts(
                discovery.digest, discovery.spec, ctx.cache
            ):
                splitter.append_chart(default)
    finally:
        ctx.telemetry.charts_emitted = splitter.charts_emitted
        ctx.telemetry.charts_rejected = splitter.charts_rejected
    return SynthesisPhaseResult(splitter.text, tuple(splitter.charts))


async def _consume_synthesis_stream(
    ctx: TurnContext,
    stream: AsyncGenerator[StreamChunk],
    splitter: BlockSplitter,
) -> None:
    """Feeds the synthesis stream to the splitter and relays its thoughts.

    Args:
        ctx: The turn context holding the `emit` callback.
        stream: The open Gemini synthesis stream yielding thought and text
            chunks.
        splitter: The block splitter that buffers paragraphs and chart blocks
            and emits each completed block.

    Raises:
        TurnAbortedError: If the stream breaks part-way, a chunk does not
            arrive within `SYNTHESIS_CHUNK_TIMEOUT_SECONDS`, or Gemini blocks
            the candidate after at least one answer block has been emitted.
        GeminiBlockedError: If Gemini blocks the candidate before any answer
            block has been emitted.
    """
    try:
        while True:
            try:
                async with asyncio.timeout(SYNTHESIS_CHUNK_TIMEOUT_SECONDS):
                    chunk = await anext(stream)
            except StopAsyncIteration:
                return
            except TimeoutError as error:
                logger.warning(
                    "Synthesis stream stalled for %.0f seconds",
                    SYNTHESIS_CHUNK_TIMEOUT_SECONDS,
                )
                raise TurnAbortedError(
                    ErrorType.SYNTHESIS_STREAM_ERROR, SYNTHESIS_FAILED
                ) from error
            if chunk.kind == "thought":
                ctx.emit(ThoughtFrame(thought=chunk.text, phase="synthesis"))
            else:
                splitter.feed(chunk.text)
    except GeminiBlockedError as error:
        if not splitter.text_blocks and not splitter.charts:
            raise
        # Once an answer block has streamed to the client, a mid-stream block
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


def _format_topic_scope(table: ObservationTable | None) -> str:
    """Formats where a variable was measured as a suffix for a follow-up topic.

    Args:
        table: The observation table for the variable, or `None` when none is
            cached.

    Returns:
        A suffix such as `" by County"` or `" in California, Texas"`, or `""`
        when no place scope applies.
    """
    if table is None:
        return ""
    if table.child_place_type and table.parent_place_dcid:
        return f" by {table.child_place_type}"
    names = [
        table.place_names.get(place, place)
        for place in table.places_with_data[:_FOLLOW_UP_PLACE_CAP]
    ]
    return f" in {', '.join(names)}" if names else ""


def collect_follow_up_topics(
    discovery: DiscoveryPhaseResult, charts: Sequence[ResolvedChart]
) -> list[str]:
    """Returns the topics that ground the follow-up questions.

    The topics are the variables the digest's results computed figures
    for, each with the places or the child place type it was measured
    over, then the titles of the charts shown, then the missing-data notes
    that name a data gap (excluding processing diagnostics and the generic
    no-observations fallback note). Duplicates are dropped in order of
    first appearance.

    Args:
        discovery: The completed discovery phase result.
        charts: The resolved charts emitted during synthesis.

    Returns:
        Deduplicated follow-up topic strings in first-appearance order.
    """
    tables_by_variable: dict[str, ObservationTable] = {}
    for cached in discovery.tables:
        tables_by_variable.setdefault(cached.table.variable_dcid, cached.table)
    topics: list[str] = []
    for result in discovery.digest.results:
        if result.status != "ok":
            continue
        for dcid in result.variables:
            name = result.variable_names.get(dcid, dcid)
            scope = _format_topic_scope(tables_by_variable.get(dcid))
            topics.append(f"{name}{scope}")
    topics.extend(chart.title for chart in charts if chart.title)
    topics.extend(
        note
        for note in discovery.digest.missing_notes
        if note != _NO_OBSERVATIONS_NOTE
        and not note.startswith(_DIAGNOSTIC_NOTE_PREFIXES)
    )
    return list(dict.fromkeys(topics))


async def run_followups(
    ctx: TurnContext,
    discovery: DiscoveryPhaseResult,
    charts: Sequence[ResolvedChart],
) -> None:
    """Emits follow-up questions grounded in the digest and the charts.

    This phase runs after the terminal event so the UI can display the
    answer and charts immediately and show the follow-up questions when they
    arrive. If there are no topics or generation fails, nothing is emitted.

    Args:
        ctx: The turn context holding the transcript, config, and telemetry.
        discovery: The completed discovery phase result.
        charts: The resolved charts emitted during synthesis.
    """
    try:
        follow_ups = await generate_follow_up_questions(
            ctx.transcript.current_query,
            collect_follow_up_topics(discovery, charts),
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
    required, or admits the query into the discovery loop, synthesis, and
    turn signing. A model call that Gemini blocks in any of those phases
    ends the turn as `refused` with reason `safety_blocked`; the phases let
    `GeminiBlockedError` propagate here rather than each translating it.
    Every non-canceled turn ends in one `terminal` frame (`complete`,
    `refused`, or `error`) and records its outcome and classified pattern
    in telemetry. Only `asyncio.CancelledError` is re-raised to the caller;
    cancellation emits no terminal frame because the client has already
    disconnected, and it is recorded as `canceled` unless the turn has
    already completed. Follow-up questions are emitted after the terminal
    frame.

    Args:
        transcript: The verified transcript holding the current query,
            idempotency key, and prior turns.
        emit: The callback invoked with each SSE frame of the turn.
    """
    idempotency_key = transcript.current_idempotency_key
    telemetry = TurnTelemetry()
    state: TerminalState | None = None
    error_type: ErrorType | RefusedReason | None = None
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
        with telemetry.phase("synthesis"):
            synthesis = await run_synthesis_phase(ctx, discovery)
        with telemetry.phase("finalize"):
            window = await _sign_turn(
                ctx,
                synthesis.text,
                lambda: build_state_slots(discovery.tables, synthesis.charts),
            )
        state = TerminalState.COMPLETE
        emit(
            TerminalCompleteFrame(
                idempotency_key=idempotency_key, window=window
            )
        )
        with telemetry.phase("follow_ups"):
            await run_followups(ctx, discovery, synthesis.charts)
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
        telemetry.finish(state or TerminalState.ERROR, error_type)


async def run_clarification(
    ctx: TurnContext, question: str
) -> SignedWindow | None:
    """Answers the turn with the classifier's clarification question.

    The question is emitted as the one text block of the answer and the
    turn is signed with empty state slots, so that the user's reply arrives
    with this exchange as context. No data, sources, charts, or follow-ups
    are emitted, because nothing was retrieved.

    Args:
        ctx: The turn context holding the transcript, config, and telemetry.
        question: The clarification question to stream to the user.

    Returns:
        The signed window, or `None` when the turn could not be signed.
    """
    ctx.emit(BlockContentFrame(block=TextBlock(index=0, markdown=question)))
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


__all__ = [
    "DiscoveryPhaseResult",
    "Emit",
    "SynthesisPhaseResult",
    "TurnAbortedError",
    "TurnContext",
    "collect_follow_up_topics",
    "run_clarification",
    "run_discovery_phase",
    "run_followups",
    "run_synthesis_phase",
    "run_turn",
]
