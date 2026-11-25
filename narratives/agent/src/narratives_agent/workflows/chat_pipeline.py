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
typed values rather than shared mutable state. Each phase also records what
it did on the turn's `TurnRecord`. The `chat_turn` record that the server
logs for the turn and the debug report are both built from it.

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
from narratives_agent.config import (
    get_chat_config,
    get_current_date,
    get_debug_report_mode,
    load_config,
    pin_current_date,
)
from narratives_agent.config_model import AgentConfig, GeminiRole
from narratives_agent.gemini.client import (
    GeminiBlockedError,
    GeminiError,
    GeminiStreamError,
    async_gemini_stream,
)
from narratives_agent.gemini.response import StreamChunk
from narratives_agent.gemini.schemas import QueryClassification
from narratives_agent.json_value import JsonObject
from narratives_agent.mcp import client as mcp_client
from narratives_agent.mcp.capabilities import (
    Capabilities,
    from_tools,
    warn_on_missing_tools,
)
from narratives_agent.settings import get_settings
from narratives_agent.telemetry import (
    ErrorType,
    TerminalState,
    TitleOutcome,
    TurnTelemetry,
    write_structured_record,
)
from narratives_agent.token_budget import get_daily_token_budget
from narratives_agent.workflows.blocks import BlockSplitter, TextBlock
from narratives_agent.workflows.chart_defaults import build_default_charts
from narratives_agent.workflows.charts import (
    ChartRejection,
    ChartRejectionReason,
    ChartSpecification,
    ResolvedChart,
    get_chart_cohort,
    resolve_chart_specification,
)
from narratives_agent.workflows.classify import (
    Admitted,
    Clarification,
    RefusedReason,
    ScreeningUnavailableError,
    TurnRefusedError,
    classify_query,
)
from narratives_agent.workflows.debug_report import (
    build_debug_report,
    should_emit_debug_report,
)
from narratives_agent.workflows.follow_up import (
    FollowUpTopics,
    generate_follow_up_questions,
)
from narratives_agent.workflows.mcp_loop import (
    DISCOVERY_STATUS,
    PROCESSING_STATUS,
    DiscoveryResult,
    McpLoopError,
    execute_discovery_loop,
)
from narratives_agent.workflows.messages import (
    CLASSIFY_STATUS,
    CONFIG_MISSING,
    INTERNAL_ERROR,
    MCP_TOOLS_TIMEOUT,
    MCP_UNAVAILABLE,
    NO_DATA_MESSAGE,
    SAFETY_REFUSED_MESSAGE,
    SCREENING_UNAVAILABLE,
    SYNTHESIS_FAILED,
    SYNTHESIS_STATUS,
    SYNTHESIS_TRANSIENT_ERROR,
    TRUNCATED_MESSAGE,
)
from narratives_agent.workflows.metadata_backfill import (
    backfill_variable_metadata,
)
from narratives_agent.workflows.processing import (
    ProcessingDiagnostic,
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
    DebugReportFrame,
    FollowUpsFrame,
    SourcesFrame,
    SseFrame,
    StatusFrame,
    StatusPhase,
    TerminalCompleteFrame,
    TerminalErrorFrame,
    TerminalRefusedFrame,
    ThoughtFrame,
    TitleFrame,
    ToolCallFrame,
)
from narratives_agent.workflows.state_slots import build_state_slots
from narratives_agent.workflows.synthesis import (
    SYNTHESIS_CHUNK_TIMEOUT_SECONDS,
    build_synthesis_inputs,
    render_synthesis_message,
)
from narratives_agent.workflows.title import (
    TitleExtractor,
    select_title_addendum,
)
from narratives_agent.workflows.transcript import (
    ConversationStateSlots,
    SignedWindow,
    Transcript,
    finalize_turn,
    transcript_contents,
)
from narratives_agent.workflows.turn_cache import CachedTable, TurnCache
from narratives_agent.workflows.turn_record import (
    SpecificationOrigin,
    TurnChart,
    TurnRecord,
    TurnThought,
)
from narratives_agent.workflows.usage_record import build_usage_record

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

# Pre-turn lockout reasons that end the turn before classification and omit
# debug report emission.
_PRE_TURN_REASONS = frozenset(
    {
        ErrorType.CHAT_DISABLED,
        ErrorType.DAILY_TOKEN_BUDGET_EXHAUSTED,
    }
)

type Emit = Callable[[SseFrame], None]


class TurnAbortedError(Exception):
    """Raised when a phase fails and the turn must end in an error.

    `error_type` is a short machine-readable reason for telemetry. The
    message is shown to the user, so it must not carry upstream error text
    that has not been redacted.

    Attributes:
        error_type: Short machine-readable failure category for telemetry.
        is_retryable: False only when the failure is identified as
            permanent; every other failure is retryable.
    """

    def __init__(
        self, error_type: ErrorType, message: str, *, is_retryable: bool
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.is_retryable = is_retryable


@dataclass(frozen=True)
class TurnContext:
    """Holds the inputs and callbacks shared across every phase of a turn.

    `classification` is the classify phase's verdict. `run_turn` always
    sets it. Only tests build a context without one.
    `record` is the only holder of the turn's telemetry and of the cache of
    observation tables the turn fetches; `telemetry` and `cache` return the
    record's own objects.

    Attributes:
        transcript: The verified transcript for the current turn.
        config: The loaded agent configuration.
        record: The turn's record, on which the phases record what they did.
        emit: Callback invoked with each SSE frame of the turn.
        classification: The classify phase's verdict, or `None` in a context
            that a test builds without one.
    """

    transcript: Transcript
    config: AgentConfig
    record: TurnRecord
    emit: Emit
    classification: QueryClassification | None = None

    @property
    def telemetry(self) -> TurnTelemetry:
        """The turn's telemetry collector."""
        return self.record.telemetry

    @property
    def cache(self) -> TurnCache:
        """The per-turn observation table and metadata cache."""
        return self.record.cache


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
    lines, with every chart block and the title line left out. `charts` are
    the resolved charts in the order their blocks were emitted.

    Attributes:
        text: The signed prose text with chart blocks and the title line
            excluded.
        charts: Resolved charts in emission order.
        rendered_prompt: The rendered synthesis user prompt.
        raw_output: The raw Gemini output including chart fences.
    """

    text: str
    charts: tuple[ResolvedChart, ...] = ()
    rendered_prompt: str = ""
    raw_output: str = ""


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
    capabilities: Capabilities,
) -> tuple[AnalysisDigest, AnalysisSpecification]:
    """Runs the default specification and retries without any refused step.

    When a step of the default refuses, the default runs again without that
    step's relation or table so the remaining tables still answer the turn,
    and each refusal is appended to `notes`. When a retry leaves no table,
    or processing times out, the digest holds the results completed before
    the last failure and carries the failure in `notes`. The diagnostic of
    each failed run is recorded on the turn's record. When the last run
    fails, this function also sets the record's `specification_diagnostic`
    to the diagnostic of that run.

    Args:
        ctx: The turn context holding the classification, cache, telemetry,
            and record.
        specification: The initial default specification built over the cache.
        notes: Mutable list of missing-data notes accumulated before and during
            the default specification run.
        capabilities: The MCP server's tools; variable metadata is requested
            before the first run only when they include
            `get_variable_metadata`.

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
        # A retry only drops tables from the initial default, so the initial
        # default references every table a retry can read.
        await backfill_variable_metadata(
            specification, ctx.cache, capabilities, ctx.telemetry
        )
        outcome = await execute_specification(specification, ctx.cache)
        if isinstance(outcome, ProcessingDiagnostic):
            ctx.record.default_diagnostics.append(outcome)
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
            if isinstance(outcome, ProcessingDiagnostic):
                ctx.record.default_diagnostics.append(outcome)
    if isinstance(outcome, AnalysisDigest):
        return (
            replace(outcome, missing_notes=(*outcome.missing_notes, *notes)),
            specification,
        )
    ctx.record.specification_diagnostic = outcome
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
    ctx: TurnContext,
    loop: DiscoveryResult,
    capabilities: Capabilities,
) -> tuple[AnalysisDigest, AnalysisSpecification | None]:
    """Returns the digest the turn is answered from, and its specification.

    An accepted specification and a no-data report each settle the digest.
    Otherwise the loop ended at a bound, with a prose reply, or with its
    retries exhausted, and the turn is answered from a default
    specification over the fetched tables rather than from partial raw
    data. When no fetched table has rows, the digest is empty and says so.
    The digest, the specification, and the specification's origin are
    recorded on the turn's record.

    Args:
        ctx: The turn context holding the classification, cache, telemetry,
            and record.
        loop: The completed discovery loop result.
        capabilities: The MCP server's tools, passed to the default
            specification run.

    Returns:
        A `(digest, specification)` pair holding the resolved `AnalysisDigest`
        and the `AnalysisSpecification` that produced it, or `None` when no
        specification ran.
    """
    digest: AnalysisDigest
    specification: AnalysisSpecification | None
    origin: SpecificationOrigin | None
    if loop.digest is not None:
        digest, specification = loop.digest, loop.specification
        origin = "model"
    elif loop.unavailable is not None:
        digest = AnalysisDigest(
            results=(),
            sources=(),
            missing_notes=(loop.unavailable.format_note(),),
        )
        specification = None
        origin = None
    else:
        notes: list[str] = []
        if loop.last_diagnostic is not None:
            notes.append(
                f"{_STEP_FAILED_NOTE_PREFIX}{loop.last_diagnostic.message}"
            )
        default_spec = build_default_specification(
            ctx.classification, ctx.cache
        )
        if default_spec is None:
            notes.append(_NO_OBSERVATIONS_NOTE)
            digest = AnalysisDigest(
                results=(),
                sources=(),
                missing_notes=tuple(notes),
            )
            specification = None
            origin = None
        else:
            digest, specification = await _run_default_specification(
                ctx, default_spec, notes, capabilities
            )
            origin = "default"

    ctx.record.specification = specification
    ctx.record.specification_origin = origin
    ctx.record.digest = digest
    return digest, specification


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
    and records the phase's telemetry counts. The loop's result and the IDs
    of the tables the specification used are recorded on the turn's record.

    Args:
        ctx: The turn context holding the transcript, config, telemetry,
            cache, and record.

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
            ErrorType.MCP_TIMEOUT, MCP_TOOLS_TIMEOUT, is_retryable=True
        ) from error
    if not tools:
        logger.warning("MCP unavailable: not connected or no tools available")
        raise TurnAbortedError(
            ErrorType.MCP_UNAVAILABLE, MCP_UNAVAILABLE, is_retryable=True
        )
    warn_on_missing_tools(tools)

    _emit_status(ctx, DISCOVERY_STATUS)
    loop = ctx.record.loop_result
    try:
        # The loop fills the record's result in place, so the record holds
        # the calls that completed before a loop that fails.
        loop = await execute_discovery_loop(
            ctx.transcript,
            ctx.config,
            tools,
            ctx.telemetry,
            ctx.cache,
            thought_callback=lambda text, round_number: ctx.emit(
                ThoughtFrame(
                    thought=text, phase="discovery", round_number=round_number
                )
            ),
            status_callback=lambda phase, message: ctx.emit(
                StatusFrame(phase=phase, message=message)
            ),
            classification=ctx.classification,
            result=loop,
        )
    except McpLoopError as error:
        if error.result is not loop and error.result != DiscoveryResult():
            loop = error.result
        raise TurnAbortedError(
            error.error_type, str(error), is_retryable=error.is_retryable
        ) from error
    finally:
        ctx.record.loop_result = loop
        ctx.telemetry.tables_fetched = ctx.cache.tables_fetched
        ctx.telemetry.total_rows_fetched = ctx.cache.total_rows_fetched
        ctx.telemetry.processing_retries = loop.processing_retries

    result.tool_calls = loop.tool_calls
    for call in result.tool_calls:
        ctx.emit(ToolCallFrame(tool_call=call))

    digest, specification = await _resolve_digest(ctx, loop, from_tools(tools))
    result.digest = digest
    result.spec = specification
    result.has_data = digest.has_data
    result.tables = _collect_tables_used(specification, ctx.cache)
    ctx.record.used_table_ids = frozenset(t.table_id for t in result.tables)
    ctx.telemetry.scripts = (
        specification.list_script_names() if specification is not None else []
    )

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
    emitted. When the digest has data, the model opens with a title line,
    which is taken off the stream and emitted as a `TitleFrame` before the
    first block; a turn without data gets no title. When the digest has data
    and no chart block was emitted, at most one default chart from the
    primary result is appended. Opening the stream and reading each chunk
    are bounded by `SYNTHESIS_CHUNK_TIMEOUT_SECONDS`, so a stalled stream
    ends the turn rather than holding it open for the whole HTTP timeout.
    The rendered user message, the raw output, the emitted charts with
    their origins, and the chart blocks that closed and were rejected are
    recorded on the turn's record, including when the phase aborts. If the
    stream aborts while a chart fence is still open, that incomplete fence
    is not recorded as a rejection.

    Args:
        ctx: The turn context holding the transcript, config, telemetry, and
            record.
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
    rendered_prompt = render_synthesis_message(inputs)
    ctx.record.synthesis_prompt = rendered_prompt
    # Put the verified window first, then the query with the analysis context.
    messages = transcript_contents(
        ctx.transcript, rendered_prompt, current_date=get_current_date()
    )
    # A `scatter` chart is drawn only across a cohort, so the synthesis
    # directive of a correlation question depends on whether one was fetched.
    has_cohort_table = any(
        get_chart_cohort(entry.table) is not None for entry in discovery.tables
    )
    try:
        async with asyncio.timeout(SYNTHESIS_CHUNK_TIMEOUT_SECONDS):
            stream = await async_gemini_stream(
                messages=messages,
                system_instruction=compose_system_instruction(
                    config.prompts.synthesis,
                    "synthesis",
                    ctx.classification,
                    has_cohort_table=has_cohort_table,
                    addendum=select_title_addendum(discovery.has_data),
                ),
                model=role.model,
                temperature=role.temperature,
                thinking_level=role.thinking_level,
                token_usage=ctx.telemetry.tokens,
                include_thoughts=True,
                token_role=GeminiRole.SYNTHESIS,
            )
    except TimeoutError as error:
        logger.warning(
            "Synthesis stream stalled for %.0f seconds",
            SYNTHESIS_CHUNK_TIMEOUT_SECONDS,
        )
        raise TurnAbortedError(
            ErrorType.SYNTHESIS_STREAM_ERROR,
            SYNTHESIS_TRANSIENT_ERROR,
            is_retryable=True,
        ) from error
    except GeminiBlockedError:
        # Propagates to `run_turn`, which ends the turn as `refused`.
        raise
    except GeminiError as error:
        # The client has already logged the redacted upstream error, so the
        # user receives a fixed message.
        message = (
            SYNTHESIS_TRANSIENT_ERROR
            if error.is_retryable
            else SYNTHESIS_FAILED
        )
        raise TurnAbortedError(
            ErrorType.SYNTHESIS_ERROR, message, is_retryable=error.is_retryable
        ) from error

    raw_chunks: list[str] = []
    splitter = BlockSplitter(
        on_block=lambda block: ctx.emit(BlockContentFrame(block=block)),
        resolve_chart=lambda spec: _resolve_chart_block(
            spec, discovery, ctx.cache
        ),
    )
    extractor = TitleExtractor(
        forward=splitter.feed,
        on_title=lambda title: ctx.emit(TitleFrame(title=title)),
        accept=discovery.has_data,
    )
    # The value stays `None` when the phase exits before the stream has
    # ended, in which case the model wrote every emitted chart.
    model_chart_count: int | None = None
    try:
        await _consume_synthesis_stream(
            ctx, stream, extractor, splitter, raw_chunks
        )
        extractor.finish()
        splitter.finish()
        if not splitter.text:
            logger.warning("Synthesis returned no answer text")
            raise TurnAbortedError(
                ErrorType.SYNTHESIS_EMPTY,
                SYNTHESIS_TRANSIENT_ERROR,
                is_retryable=True,
            )
        model_chart_count = len(splitter.charts)
        if discovery.has_data and not splitter.charts:
            for default in build_default_charts(
                discovery.digest, discovery.spec, ctx.cache
            ):
                splitter.append_chart(default)
    finally:
        ctx.telemetry.charts_emitted = splitter.charts_emitted
        ctx.telemetry.charts_rejected = splitter.charts_rejected
        ctx.telemetry.title_outcome = _resolve_title_outcome(extractor)
        raw_output = "".join(raw_chunks)
        ctx.record.synthesis_raw_output = raw_output
        # The phase appends its default charts after the stream has ended,
        # so they follow every chart block that the model wrote.
        ctx.record.charts = tuple(
            TurnChart(
                chart=chart,
                origin=(
                    "model"
                    if model_chart_count is None or index < model_chart_count
                    else "default"
                ),
            )
            for index, chart in enumerate(splitter.charts)
        )
        ctx.record.chart_rejections = splitter.chart_rejections
    return SynthesisPhaseResult(
        splitter.text,
        tuple(splitter.charts),
        rendered_prompt=rendered_prompt,
        raw_output=raw_output,
    )


def _resolve_title_outcome(extractor: TitleExtractor) -> TitleOutcome:
    """Returns the title outcome of a synthesis phase from its extractor."""
    if not extractor.accept:
        return TitleOutcome.NOT_REQUESTED
    if extractor.title is None:
        return TitleOutcome.OMITTED
    return TitleOutcome.EMITTED


def _resolve_chart_block(
    spec: ChartSpecification,
    discovery: DiscoveryPhaseResult,
    cache: TurnCache,
) -> ResolvedChart | ChartRejection:
    """Resolves a chart block of the answer against the turn's data.

    Args:
        spec: The parsed chart block.
        discovery: The discovery phase result the answer is written from.
        cache: The turn's table cache.

    Returns:
        The resolved chart. Returns a `ChartRejection` when the turn does
        not have data, when the block names a table ID that is not in the
        cache, when it names a cached table that is not among the tables
        the answer used, or when `resolve_chart_specification` rejects the
        block.
    """
    if not discovery.has_data:
        logger.info("Chart block rejected: turn has no data")
        return ChartRejection(ChartRejectionReason.TURN_WITHOUT_DATA, spec.kind)
    allowed_table_ids = {entry.table_id for entry in discovery.tables}
    for table_id in spec.tables:
        if table_id not in allowed_table_ids:
            logger.info(
                "Chart block rejected: %s is not in the table inventory",
                table_id,
            )
            reason = (
                ChartRejectionReason.TABLE_NOT_IN_ANSWER
                if cache.get(table_id) is not None
                else ChartRejectionReason.UNKNOWN_TABLE
            )
            return ChartRejection(reason, spec.kind)
    return resolve_chart_specification(
        spec, cache, discovery.digest, discovery.spec
    )


async def _consume_synthesis_stream(
    ctx: TurnContext,
    stream: AsyncGenerator[StreamChunk],
    extractor: TitleExtractor,
    splitter: BlockSplitter,
    raw_chunks: list[str],
) -> None:
    """Feeds the synthesis stream to the splitter and relays its thoughts.

    Args:
        ctx: The turn context holding the `emit` callback.
        stream: The open Gemini synthesis stream yielding thought and text
            chunks.
        extractor: The title extractor that takes the title line off the
            stream and forwards the rest to `splitter`.
        splitter: The block splitter that buffers paragraphs and chart blocks
            and emits each completed block.
        raw_chunks: Mutable list collecting raw non-thought chunk texts.

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
                    ErrorType.SYNTHESIS_STREAM_ERROR,
                    SYNTHESIS_TRANSIENT_ERROR,
                    is_retryable=True,
                ) from error
            if chunk.kind == "thought":
                ctx.emit(ThoughtFrame(thought=chunk.text, phase="synthesis"))
            else:
                raw_chunks.append(chunk.text)
                extractor.feed(chunk.text)
    except GeminiBlockedError as error:
        if not splitter.text_blocks and not splitter.charts:
            raise
        # Once an answer block has streamed to the client, a mid-stream block
        # leaves the response truncated and is reported as a stream error.
        raise TurnAbortedError(
            ErrorType.SYNTHESIS_STREAM_ERROR,
            SYNTHESIS_FAILED,
            is_retryable=False,
        ) from error
    except GeminiStreamError as error:
        message = (
            SYNTHESIS_TRANSIENT_ERROR
            if error.is_retryable
            else SYNTHESIS_FAILED
        )
        raise TurnAbortedError(
            ErrorType.SYNTHESIS_STREAM_ERROR,
            message,
            is_retryable=error.is_retryable,
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
) -> FollowUpTopics:
    """Returns the topics that ground the follow-up questions.

    `unused` holds the related indicators the specification left aside
    (`related`), which the answer did not report. `reported` holds the
    variables the digest's results computed figures for, each with the
    places or the child place type it was measured over, and the titles of
    the charts shown. A related indicator that the answer reported is kept
    only in `reported`. The missing-data notes name data the service does
    not have, so they become topics only on a turn that reported nothing,
    where they are all there is; processing diagnostics and the generic
    no-observations note are never topics. Duplicates are dropped in order
    of first appearance.

    Args:
        discovery: The completed discovery phase result.
        charts: The resolved charts emitted during synthesis.

    Returns:
        The two deduplicated topic lists, in first-appearance order.
    """
    tables_by_variable: dict[str, ObservationTable] = {}
    for cached in discovery.tables:
        tables_by_variable.setdefault(cached.table.variable_dcid, cached.table)
    reported: list[str] = []
    for result in discovery.digest.results:
        if result.status != "ok":
            continue
        for dcid in result.variables:
            name = result.variable_names.get(dcid, dcid)
            scope = _format_topic_scope(tables_by_variable.get(dcid))
            reported.append(f"{name}{scope}")
    reported.extend(chart.title for chart in charts if chart.title)
    reported = list(dict.fromkeys(reported))
    related = (
        [topic.strip() for topic in discovery.spec.related if topic.strip()]
        if discovery.spec is not None
        else []
    )
    unused = [topic for topic in related if topic not in reported]
    if not (reported or unused):
        unused = [
            note
            for note in discovery.digest.missing_notes
            if note != _NO_OBSERVATIONS_NOTE
            and not note.startswith(_DIAGNOSTIC_NOTE_PREFIXES)
        ]
    return FollowUpTopics(
        unused=tuple(dict.fromkeys(unused)), reported=tuple(reported)
    )


async def run_followups(
    ctx: TurnContext,
    discovery: DiscoveryPhaseResult,
    charts: Sequence[ResolvedChart],
) -> None:
    """Emits follow-up questions grounded in the digest and the charts.

    This phase runs after the terminal event so the UI can display the
    answer and charts immediately and show the follow-up questions when they
    arrive. If there are no topics or generation fails, nothing is emitted.
    The questions emitted in `FollowUpsFrame` are recorded on the turn's
    record, and so is a cancellation of the turn task while the phase runs.

    Args:
        ctx: The turn context holding the transcript, config, telemetry, and
            record.
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
            ctx.record.follow_up_questions = tuple(follow_ups)
    except asyncio.CancelledError:
        ctx.record.has_canceled_follow_ups = True
        raise
    except Exception as error:
        logger.warning("Follow-up generation failed: %s", type(error).__name__)


def _require_turn_config(config: AgentConfig | None) -> AgentConfig:
    """Returns `config`, or raises `TurnAbortedError` when it is `None`.

    Args:
        config: The configuration `load_config` returned for the turn.

    Returns:
        The loaded `AgentConfig`.

    Raises:
        TurnAbortedError: With reason `config_missing` if no configuration
            is loaded.
    """
    if config is None:
        raise TurnAbortedError(
            ErrorType.CONFIG_MISSING, CONFIG_MISSING, is_retryable=False
        )
    return config


async def _run_classify_phase(
    transcript: Transcript,
    config: AgentConfig,
    telemetry: TurnTelemetry,
    unavailable_message: str,
) -> Clarification | Admitted:
    """Runs the classify phase and converts its screening failure.

    Args:
        transcript: The verified transcript holding the current query.
        config: The loaded agent configuration.
        telemetry: The turn's telemetry collector.
        unavailable_message: The effective `chat.unavailable_message`, sent
            to the user when the failure is permanent.

    Returns:
        The classify phase's outcome: a clarification or an admitted query.

    Raises:
        TurnAbortedError: If Model Armor or the classifier could not screen
            the query. A retryable failure carries `SCREENING_UNAVAILABLE`
            and a permanent failure carries `unavailable_message`.
        TurnRefusedError: If the classify phase refuses the query.
        GeminiBlockedError: If Gemini blocks the classification call.
    """
    try:
        return await classify_query(transcript, config, telemetry)
    except ScreeningUnavailableError as error:
        message = (
            SCREENING_UNAVAILABLE if error.is_retryable else unavailable_message
        )
        raise TurnAbortedError(
            error.error_type, message, is_retryable=error.is_retryable
        ) from error


async def run_turn(
    transcript: Transcript,
    emit: Emit,
    *,
    request_debug: bool = False,
) -> None:
    """Runs one chat turn and emits its typed SSE frames through `emit`.

    Ends the turn at once with reason `chat_disabled` and the configured
    unavailable message when chat is disabled, or with reason
    `daily_token_budget_exhausted` and the same unavailable message when this
    instance's daily Gemini token budget has been exhausted. Otherwise runs
    classification first: refuses adversarial or off-domain queries, streams
    and signs a clarification question when disambiguation is required, or
    admits the query into the discovery loop, synthesis, and turn signing. A
    model call that Gemini blocks in any of those phases ends the turn as
    `refused` with reason `safety_blocked`; the phases let
    `GeminiBlockedError` propagate here rather than each translating it.
    A query that Model Armor or the classifier cannot screen ends the turn
    as `error` with reason `model_armor_unavailable` or
    `classifier_unavailable` before the discovery loop runs.
    Every non-canceled turn ends in one `terminal` frame (`complete`,
    `refused`, or `error`) and records its outcome and classified pattern
    in telemetry. Only `asyncio.CancelledError` is re-raised to the caller;
    cancellation emits no terminal frame because the client has already
    disconnected, and it is recorded as `canceled` unless the turn has
    already completed. Follow-up questions are emitted after the terminal
    frame. The agent loop writes one `chat_turn` record when a turn ends,
    including a turn that the client cancels.

    Args:
        transcript: The verified transcript holding the current query,
            idempotency key, and prior turns.
        emit: The callback invoked with each SSE frame of the turn.
        request_debug: Whether the client requested turn debug reporting.
    """
    settings = get_settings()
    budget = get_daily_token_budget()
    idempotency_key = transcript.current_idempotency_key
    record = TurnRecord(telemetry=TurnTelemetry())
    telemetry = record.telemetry
    state: TerminalState | None = None
    error_type: ErrorType | RefusedReason | None = None

    def tracking_emit(frame: SseFrame) -> None:
        if isinstance(frame, ThoughtFrame):
            record.thoughts.append(
                TurnThought(
                    phase=frame.phase,
                    text=frame.thought,
                    round_number=frame.round_number,
                )
            )
        emit(frame)

    config: AgentConfig | None = None
    canceled = False
    try:
        # Chat availability and daily token budget are checked before the
        # configuration is required, so `ENABLE_CHAT=false` or an exhausted
        # budget ends the turn even when no configuration is loaded.
        chat = get_chat_config()
        pre_turn_reason: ErrorType | None = None
        if not chat.enabled:
            pre_turn_reason = ErrorType.CHAT_DISABLED
        elif budget is not None and budget.is_exhausted():
            pre_turn_reason = ErrorType.DAILY_TOKEN_BUDGET_EXHAUSTED
        if pre_turn_reason is not None:
            state, error_type = TerminalState.REFUSED, pre_turn_reason
            emit(
                TerminalErrorFrame(
                    idempotency_key=idempotency_key,
                    error=chat.unavailable_message,
                    reason=pre_turn_reason,
                    is_retryable=False,
                )
            )
            return
        config = _require_turn_config(load_config())
        # The classify, discovery, and synthesis requests of the turn carry
        # one current date, isolated from concurrent turns.
        with pin_current_date():
            tracking_emit(
                StatusFrame(phase="classify", message=CLASSIFY_STATUS)
            )
            with telemetry.phase("classify"):
                admission = await _run_classify_phase(
                    transcript, config, telemetry, chat.unavailable_message
                )
            telemetry.pattern = admission.classification.pattern
            ctx = TurnContext(
                transcript,
                config,
                record,
                tracking_emit,
                admission.classification,
            )
            if isinstance(admission, Clarification):
                window = await run_clarification(ctx, admission.question)
                record.is_clarification = True
                state = TerminalState.COMPLETE
                tracking_emit(
                    TerminalCompleteFrame(
                        idempotency_key=idempotency_key, window=window
                    )
                )
            else:
                # Processing runs inside discovery are also timed under their
                # own phase.
                with telemetry.phase("discovery"):
                    discovery = await run_discovery_phase(ctx)
                with telemetry.phase("synthesis"):
                    synthesis = await run_synthesis_phase(ctx, discovery)
                with telemetry.phase("finalize"):
                    window = await _sign_turn(
                        ctx,
                        synthesis.text,
                        lambda: build_state_slots(
                            discovery.tables, synthesis.charts
                        ),
                    )
                state = TerminalState.COMPLETE
                tracking_emit(
                    TerminalCompleteFrame(
                        idempotency_key=idempotency_key, window=window
                    )
                )
                with telemetry.phase("follow_ups"):
                    await run_followups(ctx, discovery, synthesis.charts)
    except TurnRefusedError as refusal:
        state, error_type = TerminalState.REFUSED, refusal.reason
        tracking_emit(
            TerminalRefusedFrame(
                idempotency_key=idempotency_key,
                reason=refusal.reason,
                message=str(refusal),
            )
        )
    except GeminiBlockedError:
        state, error_type = TerminalState.REFUSED, RefusedReason.SAFETY_BLOCKED
        tracking_emit(
            TerminalRefusedFrame(
                idempotency_key=idempotency_key,
                reason=RefusedReason.SAFETY_BLOCKED,
                message=SAFETY_REFUSED_MESSAGE,
            )
        )
    except TurnAbortedError as error:
        state, error_type = TerminalState.ERROR, error.error_type
        tracking_emit(
            TerminalErrorFrame(
                idempotency_key=idempotency_key,
                error=str(error),
                reason=error.error_type,
                is_retryable=error.is_retryable,
            )
        )
    except asyncio.CancelledError:
        state = state or TerminalState.CANCELED
        canceled = True
        raise
    except Exception:
        logger.exception("Chat turn failed")
        state, error_type = TerminalState.ERROR, ErrorType.INTERNAL_ERROR
        tracking_emit(
            TerminalErrorFrame(
                idempotency_key=idempotency_key,
                error=INTERNAL_ERROR,
                reason=ErrorType.INTERNAL_ERROR,
                # The cause is unknown, so the turn defaults to retryable.
                is_retryable=True,
            )
        )
    finally:
        final_state = state or TerminalState.ERROR
        record.terminal_state = final_state
        record.terminal_reason = error_type
        telemetry.finish(final_state, error_type)
        _write_usage_record(record, transcript, settings.build_sha)
        if budget is not None:
            # Counts only Gemini calls that returned `usage_metadata`; streams
            # canceled before their final chunk and timed-out calls are omitted
            # by the SDK even though Gemini may bill them.
            budget.record(telemetry.tokens.total_token_count)
        if (
            not canceled
            and error_type not in _PRE_TURN_REASONS
            and should_emit_debug_report(
                get_debug_report_mode(), request_debug=request_debug
            )
        ):
            report = build_debug_report(
                record, config=config, build_sha=settings.build_sha
            )
            emit(DebugReportFrame(report=report))


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
    The turn's record stores whether the server signed the turn and whether
    signing compacted older turns into a summary.

    Args:
        ctx: The turn context holding the transcript, config, and telemetry.
        full_text: The complete model response text for the turn.
        state_slots: Zero-argument callable that builds the turn's state slots.

    Returns:
        The signed conversation window, or `None` if signing failed or the
        response exceeded the signing length limit.
    """
    try:
        window = await finalize_turn(
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
    ctx.record.is_signed = window is not None
    ctx.record.was_compacted = window is not None and window.was_compacted
    return window


def _write_usage_record(
    record: TurnRecord, transcript: Transcript, build_sha: str | None
) -> None:
    """Writes the `chat_turn` record of a turn that has ended.

    The agent loop calls this function after it has decided the turn's
    result, so a failure to build or write the record does not fail the
    turn. The function logs only the type of the exception, because the
    turn's record holds text from the conversation.

    Args:
        record: The turn's record, with its terminal state set.
        transcript: The verified transcript that the turn ran with.
        build_sha: The build or commit SHA of the running image, or `None`.
    """
    try:
        write_structured_record(
            build_usage_record(record, transcript, build_sha=build_sha)
        )
    except Exception as error:
        logger.error(
            "Writing the chat_turn record failed with %s",
            type(error).__name__,
        )


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
