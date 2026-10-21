#!/usr/bin/env python3
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
MCP tool loop, streamed synthesis, chart configuration, turn signing, and
follow-up questions. Each phase reports progress by calling the turn's `emit`
callback with one typed SSE event at a time (`EventName` and its JSON payload)
and hands its results to the next phase as typed values rather than shared
mutable state.

Every turn that is not canceled ends in one `terminal` event (`complete`,
`refused`, or `error`) built by `terminal_frame`. Every phase reads the
conversation through the verified `Transcript`, and completed turns are
appended and signed by `finalize_turn` before the `complete` event is sent.
Chart configuration runs as an `asyncio.Task` concurrently with synthesis and
is awaited, with a timeout, once synthesis has finished streaming.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from narratives_agent.config import load_config
from narratives_agent.config_model import AgentConfig, GeminiRole
from narratives_agent.gemini.client import (
    GeminiBlockedError,
    GeminiError,
    GeminiStreamError,
    async_gemini_stream,
)
from narratives_agent.gemini.schemas import QueryClassification, QueryPattern
from narratives_agent.mcp import client as mcp_client
from narratives_agent.mcp.data_utils import (
    annotate_truncation,
    check_data_availability,
    extract_provenance_from_mcp_results,
)
from narratives_agent.telemetry import TerminalState, TurnTelemetry
from narratives_agent.workflows.chart_config import (
    get_chart_config,
    validate_data_response,
)
from narratives_agent.workflows.classify import (
    Clarification,
    TurnRefusedError,
    classify_query,
)
from narratives_agent.workflows.follow_up import generate_follow_up_questions
from narratives_agent.workflows.mcp_loop import (
    McpLoopError,
    execute_mcp_tool_loop,
)
from narratives_agent.workflows.messages import (
    CHART_CONFIG_STATUS,
    CLASSIFY_STATUS,
    INTERNAL_ERROR,
    MCP_STATUS,
    MCP_TOOLS_TIMEOUT,
    MCP_UNAVAILABLE,
    REFUSED_MESSAGE,
    SYNTHESIS_FAILED,
    SYNTHESIS_STATUS,
)
from narratives_agent.workflows.pattern_guidance import with_pattern_guidance
from narratives_agent.workflows.state_slots import extract_state_slots
from narratives_agent.workflows.transcript import (
    ConversationStateSlots,
    SignedWindow,
    Transcript,
    finalize_turn,
    transcript_contents,
)

logger = logging.getLogger(__name__)

# Maximum time in seconds to wait for the background chart-config task after
# synthesis has finished streaming. Charts are best-effort: if the timeout
# expires, the turn completes without charts rather than holding the response
# open.
CHART_CONFIG_JOIN_TIMEOUT_SECONDS = 5

# Maximum time in seconds to wait for the MCP tool list. A warm cache returns
# the list immediately, whereas a cold cache performs the handshake and
# `tools/list` request, which must not hold the turn for the MCP client's full
# request timeout.
MCP_TOOLS_TIMEOUT_SECONDS = 20

# This source is cited when observation tools ran but reported no
# `sourceMetadata`; see `run_mcp_phase`.
_FALLBACK_SOURCE = {"name": "Data Commons", "url": "https://datacommons.org/"}

_NO_CHARTS: dict[str, Any] = {"should_render": False}

# Default pattern recorded in telemetry when the classifier call failed.
_UNCLASSIFIED_PATTERN: QueryPattern = "exploratory"

type EventName = Literal[
    "status", "thought", "content", "terminal", "follow_ups"
]
type Emit = Callable[[EventName, dict[str, Any]], None]


class TurnAbortedError(Exception):
    """Raised when a phase fails and the turn must end in an error.

    `error_type` is a short machine-readable reason for telemetry. The
    message is shown to the user, so it must not carry upstream error text
    that has not been redacted.
    """

    def __init__(self, error_type: str, message: str) -> None:
        super().__init__(message)
        self.error_type = error_type


@dataclass(frozen=True)
class TurnContext:
    """Holds the inputs and callbacks shared across every phase of a turn.

    `classification` is the classify phase verdict, or `None` when the
    classifier call failed and the turn proceeds without a pattern directive.
    """

    transcript: Transcript
    config: AgentConfig
    telemetry: TurnTelemetry
    emit: Emit
    classification: QueryClassification | None = None


@dataclass
class McpPhaseResult:
    """Holds the MCP phase outputs passed to later phases.

    `sources` is the single authority on citation numbering; see
    `run_mcp_phase`.
    """

    results: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    chart_task: asyncio.Task[dict[str, Any]] | None = None


async def run_mcp_phase(ctx: TurnContext) -> McpPhaseResult:
    """Gathers data through the MCP tool loop during the discovery phase.

    Streams the tool calls, the data status, and the provenance sources, and
    starts chart configuration in the background when observations are
    returned.

    Raises:
        TurnAbortedError: If no MCP tools are available or the tool loop
            fails. MCP is a hard dependency: synthesis must not answer from
            general knowledge or run on the empty or partial results left
            behind by a failed loop.
        GeminiBlockedError: If Gemini blocks the prompt or the candidate of a
            loop iteration.
    """
    result = McpPhaseResult()
    if not ctx.config.mcp.enabled:
        return result
    # Readiness is "can we list tools?", not "do we hold a session id?".
    # The session is established on demand and re-established automatically
    # if the data plane instance we land on does not recognize it, so a
    # session id says nothing useful about whether MCP is reachable right
    # now.
    mcp_client.ensure_session_scope()
    try:
        async with asyncio.timeout(MCP_TOOLS_TIMEOUT_SECONDS):
            tools = await mcp_client.async_get_tools()
    except TimeoutError as error:
        logger.warning(
            "MCP tool list did not arrive within %d seconds",
            MCP_TOOLS_TIMEOUT_SECONDS,
        )
        raise TurnAbortedError("mcp_timeout", MCP_TOOLS_TIMEOUT) from error
    if not tools:
        logger.warning("MCP unavailable: not connected or no tools available")
        raise TurnAbortedError("mcp_unavailable", MCP_UNAVAILABLE)

    ctx.emit("status", {"phase": "mcp", "message": MCP_STATUS})
    try:
        loop_result = await execute_mcp_tool_loop(
            ctx.transcript,
            ctx.config,
            tools,
            ctx.telemetry,
            thought_callback=lambda text: ctx.emit(
                "thought", {"thought": text, "phase": "mcp"}
            ),
            classification=ctx.classification,
        )
    except McpLoopError as error:
        raise TurnAbortedError(error.error_type, str(error)) from error

    result.results = loop_result.results_text
    result.tool_calls = loop_result.tool_calls
    for call in result.tool_calls:
        ctx.emit("content", {"tool_call": call})

    # `truncated` rides along in data_status rather than in a frame of its
    # own: the frontend already consumes data_status, and truncation is a
    # statement about how complete the data is. Without it, a cut-short
    # answer is indistinguishable from a complete one because it still has
    # citations, a chart, and has_data=true.
    data_status = annotate_truncation(
        check_data_availability(result.tool_calls), loop_result.truncated
    )
    ctx.emit("content", {"data_status": data_status})

    # This list is the ONE authority on citation numbering. The frontend
    # numbers the Sources list by position in it, and synthesis is handed
    # the same list already numbered, so the [n] in the prose and the [n]
    # beside the source resolve to the same row. It is therefore carried in
    # the phase result rather than recomputed downstream: two calls that
    # drift apart (because a later phase appended a tool call, for example)
    # would renumber the prose against a list the reader never sees, and
    # nothing would fail loudly.
    result.sources = extract_provenance_from_mcp_results(result.tool_calls)
    if not result.sources and result.results:
        # Observation tools ran but reported no sourceMetadata. Synthesis
        # still has to attribute its figures to something, so fall back to
        # the graph itself, defined here once so the fallback the model
        # cites is the same row the reader sees. Left out entirely when
        # there are no results at all: nothing was fetched, so nothing is
        # attributable.
        result.sources = [dict(_FALLBACK_SOURCE)]
    if result.sources:
        ctx.emit("content", {"sources": result.sources})

    # Only generate charts when the tool results contain observations.
    # Without observations there is nothing to plot, so skipping chart
    # generation here avoids an unnecessary model call and prevents empty
    # charts from being rendered.
    if result.results and data_status.get("has_data"):
        result.chart_task = asyncio.create_task(
            get_chart_config(
                result.results,
                ctx.transcript.current_query,
                ctx.config,
                ctx.telemetry.tokens,
            ),
            name="chart-config",
        )
    elif result.results:
        # Log this skip because a turn with results but no charts is otherwise
        # indistinguishable from a turn whose chart config timed out.
        logger.info(
            "Chart config skipped: no observations in tool results "
            "(no_variables_found=%s, no_observations_found=%s, truncated=%s)",
            data_status.get("no_variables_found"),
            data_status.get("no_observations_found"),
            data_status.get("truncated"),
        )
    return result


def _synthesis_message(user_message: str, mcp: McpPhaseResult) -> str:
    """Builds the final user message that carries the gathered data."""
    context_parts = []
    if mcp.results:
        # Number sources 1..N in the order streamed to the frontend as
        # `sources` so inline [n] citations resolve to the matching entry
        # in the rendered Sources list. Any additional source list must be
        # normalized to {name, url} and appended to the sources before
        # numbering, because the frontend provenance reducer drops entries
        # without a `url` field.
        if mcp.sources:
            numbered_sources = "\n".join(
                f"[{n}] {src.get('name') or src.get('url')} - {src.get('url')}"
                for n, src in enumerate(mcp.sources, start=1)
            )
            context_parts.append(
                "**NUMBERED SOURCES - cite these numbers, exactly as given:**\n"
                f"{numbered_sources}"
            )
        context_parts.append(f"**DATA RESULTS:**\n{mcp.results}")
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


async def run_synthesis_phase(ctx: TurnContext, mcp: McpPhaseResult) -> str:
    """Streams the narrative answer during the synthesis phase.

    Returns:
        The complete answer text.

    Raises:
        TurnAbortedError: If the synthesis request fails, its stream breaks
            part-way, or it returns no answer text. A broken or empty stream
            leaves the answer missing or truncated, so chart validation and
            follow-up generation would spend more Gemini calls judging an
            incomplete answer.
        GeminiBlockedError: If Gemini blocks the prompt or the candidate
            before any text chunk is yielded.
    """
    ctx.emit("status", {"phase": "synthesis", "message": SYNTHESIS_STATUS})
    config = ctx.config
    role = config.resolve_role_config(GeminiRole.SYNTHESIS)
    # The verified window comes first, with earlier answers in full, then
    # the current query with the MCP context.
    messages = transcript_contents(
        ctx.transcript,
        _synthesis_message(ctx.transcript.current_query, mcp),
    )
    try:
        stream = await async_gemini_stream(
            messages=messages,
            system_instruction=with_pattern_guidance(
                config.prompts.synthesis, ctx.classification
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
        raise TurnAbortedError("synthesis_error", SYNTHESIS_FAILED) from error

    full_text = ""
    try:
        async for chunk in stream:
            if chunk.kind == "thought":
                ctx.emit(
                    "thought",
                    {"thought": chunk.text, "phase": "synthesis"},
                )
            else:
                full_text += chunk.text
                ctx.emit("content", {"text": chunk.text})
    except GeminiBlockedError as error:
        if not full_text.strip():
            raise
        # Once answer text has streamed to the client, a mid-stream block
        # leaves the response truncated and is reported as a stream error.
        raise TurnAbortedError(
            "synthesis_stream_error", SYNTHESIS_FAILED
        ) from error
    except GeminiStreamError as error:
        raise TurnAbortedError(
            "synthesis_stream_error", SYNTHESIS_FAILED
        ) from error
    finally:
        await stream.aclose()
    if not full_text.strip():
        logger.warning("Synthesis returned no answer text")
        raise TurnAbortedError("synthesis_empty", SYNTHESIS_FAILED)
    return full_text


async def resolve_chart_config(
    ctx: TurnContext, mcp: McpPhaseResult, full_text: str
) -> dict[str, Any]:
    """Determines whether to display charts and returns their configuration.

    Charts are best-effort because the answer has already streamed when this
    phase runs. They are hidden when a second model call finds that the
    answer does not contain data or when that call fails, and they are
    omitted when chart configuration fails or does not finish within
    `CHART_CONFIG_JOIN_TIMEOUT_SECONDS`.
    """
    if mcp.chart_task is None:
        return dict(_NO_CHARTS)
    ctx.emit(
        "status", {"phase": "chart_config", "message": CHART_CONFIG_STATUS}
    )
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
            mcp.chart_task, CHART_CONFIG_JOIN_TIMEOUT_SECONDS
        )
    except TimeoutError:
        logger.warning(
            "Chart config did not finish within %d seconds; rendering "
            "without charts",
            CHART_CONFIG_JOIN_TIMEOUT_SECONDS,
        )
        chart_config = dict(_NO_CHARTS)
    except Exception:
        # `wait_for` re-raises any exception the chart task raised.
        # `_settle_chart_task` logs it when the turn ends.
        chart_config = dict(_NO_CHARTS)
    if not show_charts:
        chart_config["hide_charts"] = True
    return chart_config


def _chart_topics(chart_config: dict[str, Any]) -> list[str]:
    """Returns the chart titles that ground the follow-up questions."""
    charts = chart_config.get("charts")
    topics = [
        chart["title"]
        for chart in (charts if isinstance(charts, list) else [])
        if isinstance(chart, dict)
        and isinstance(chart.get("title"), str)
        and chart["title"]
    ]
    title = chart_config.get("title")
    if not topics and isinstance(title, str) and title:
        # Legacy single-chart shape.
        topics.append(title)
    return topics


async def run_followups(ctx: TurnContext, chart_config: dict[str, Any]) -> None:
    """Emits follow-up questions grounded in the chart topics.

    This phase runs after the terminal event so the UI can display the
    answer and charts immediately and show the follow-up questions when they
    arrive. If there are no chart topics or generation fails, nothing is
    emitted.
    """
    try:
        follow_ups = await generate_follow_up_questions(
            ctx.transcript.current_query,
            _chart_topics(chart_config),
            ctx.config,
            ctx.telemetry.tokens,
        )
        if follow_ups:
            ctx.emit("follow_ups", {"follow_up_questions": follow_ups})
    except Exception:
        logger.exception("Follow-up generation failed")


def _load_turn_config() -> AgentConfig:
    """Returns the agent configuration, or raises `TurnAbortedError`.

    Raises:
        TurnAbortedError: With reason `config_missing` if no configuration
            is loaded.
    """
    config = load_config()
    if config is None:
        raise TurnAbortedError("config_missing", "Backend config not loaded")
    return config


def terminal_frame(
    state: TerminalState,
    idempotency_key: str,
    *,
    error: TurnAbortedError | None = None,
    refusal: TurnRefusedError | None = None,
    window: SignedWindow | None = None,
) -> dict[str, Any]:
    """Builds the payload of a `terminal` event.

    An `error` frame adds the user-safe `error` message and the
    machine-readable `reason`. A `refused` frame adds the machine-readable
    `reason` and user-safe `message` without an `error` key. A frame with a
    signed `window` adds the completed turn's `turn_index`, `hmac`, and
    `state_slots`, the window's `compacted_summary`, and `window`: the
    `turn_index`, `idempotency_key`, and `hmac` of every turn the browser
    must send next, oldest first. Compaction re-signs the whole window, so
    the browser replaces the signatures it holds with these and drops any
    turn that `window` does not list. A `complete` frame without a window
    marks a turn that was not signed, which the browser leaves out of later
    requests.

    Args:
        state: The terminal state of the turn (`"complete"`, `"error"`,
            `"refused"`, or `"canceled"`).
        idempotency_key: The request's idempotency key echoed back to the
            client.
        error: The optional `TurnAbortedError` when `state == "error"`.
        refusal: The optional `TurnRefusedError` when `state == "refused"`.
        window: The optional `SignedWindow` when the completed turn was signed.

    Returns:
        The JSON-serializable payload dict for the `terminal` SSE frame.
    """
    frame: dict[str, Any] = {"state": state, "idempotency_key": idempotency_key}
    if error is not None:
        frame["error"] = str(error)
        frame["reason"] = error.error_type
    if refusal is not None:
        frame["reason"] = refusal.reason
        frame["message"] = str(refusal)
    if window is not None:
        turn = window.turn
        frame.update(
            turn_index=turn.turn_index,
            hmac=turn.hmac,
            state_slots=turn.state_slots.model_dump(mode="json"),
            compacted_summary=window.compacted_summary,
            window=[
                {
                    "turn_index": signed.turn_index,
                    "idempotency_key": signed.idempotency_key,
                    "hmac": signed.hmac,
                }
                for signed in window.turns
            ],
        )
    return frame


async def run_turn(transcript: Transcript, emit: Emit) -> None:
    """Runs one chat turn and emits its typed SSE events through `emit`.

    Runs classification first: refuses adversarial or off-domain queries,
    streams and signs a clarification question when disambiguation is
    required, or admits the query into the MCP tool loop, synthesis, chart
    configuration, and turn signing. A model call that Gemini blocks in any
    of those phases ends the turn as `refused` with reason `safety_blocked`;
    the phases let `GeminiBlockedError` propagate here rather than each
    translating it. Every non-canceled turn ends in one `terminal` event
    (`complete`, `refused`, or `error`) and records its outcome and
    classified pattern in telemetry. Only `asyncio.CancelledError` is
    re-raised to the caller; cancellation emits no terminal event because the
    client has already disconnected, and it is recorded as `canceled` unless
    the turn has already completed. Follow-up questions are emitted after the
    terminal event, and the background chart task is settled whenever the
    turn ends so no orphaned task outlives the request.

    Args:
        transcript: The verified transcript holding the current query,
            idempotency key, and prior turns.
        emit: The callback invoked with each typed SSE event name and payload.
    """
    idempotency_key = transcript.current_idempotency_key
    telemetry = TurnTelemetry()
    state: TerminalState | None = None
    error_type: str | None = None
    chart_task: asyncio.Task[dict[str, Any]] | None = None
    try:
        config = _load_turn_config()
        emit("status", {"phase": "classify", "message": CLASSIFY_STATUS})
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
            state = "complete"
            emit(
                "terminal",
                terminal_frame(state, idempotency_key, window=window),
            )
            return
        with telemetry.phase("mcp"):
            mcp = await run_mcp_phase(ctx)
        chart_task = mcp.chart_task
        with telemetry.phase("synthesis"):
            full_text = await run_synthesis_phase(ctx, mcp)
        with telemetry.phase("chart_config"):
            chart_config = await resolve_chart_config(ctx, mcp, full_text)
        emit("content", {"chart_config": chart_config})
        with telemetry.phase("finalize"):
            window = await _sign_turn(
                ctx,
                full_text,
                lambda: extract_state_slots(mcp.tool_calls, chart_config),
            )
        state = "complete"
        emit("terminal", terminal_frame(state, idempotency_key, window=window))
        with telemetry.phase("follow_ups"):
            await run_followups(ctx, chart_config)
    except TurnRefusedError as refusal:
        state, error_type = "refused", refusal.reason
        emit(
            "terminal", terminal_frame(state, idempotency_key, refusal=refusal)
        )
    except GeminiBlockedError:
        # The Gemini client has already logged the block reason.
        blocked = TurnRefusedError("safety_blocked", REFUSED_MESSAGE)
        state, error_type = "refused", blocked.reason
        emit(
            "terminal", terminal_frame(state, idempotency_key, refusal=blocked)
        )
    except TurnAbortedError as error:
        state, error_type = "error", error.error_type
        emit("terminal", terminal_frame(state, idempotency_key, error=error))
    except asyncio.CancelledError:
        state = state or "canceled"
        raise
    except Exception:
        logger.exception("Chat turn failed")
        internal = TurnAbortedError("internal_error", INTERNAL_ERROR)
        state, error_type = "error", internal.error_type
        emit("terminal", terminal_frame(state, idempotency_key, error=internal))
    finally:
        _settle_chart_task(chart_task)
        telemetry.finish(state or "error", error_type)


async def run_clarification(
    ctx: TurnContext, question: str
) -> SignedWindow | None:
    """Streams `question` as the turn response and signs it with empty slots.

    No `data_status`, `sources`, `chart_config`, or `follow_ups` events are
    emitted because no observations were retrieved.
    """
    ctx.emit("content", {"text": question})
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


def _settle_chart_task(task: asyncio.Task[dict[str, Any]] | None) -> None:
    """Cancels the chart task if it is still running, or logs its error.

    This is the one place a chart task failure is logged, whether
    `resolve_chart_config` contained it or synthesis failed before the task
    was awaited. Retrieving the exception also prevents the "exception was
    never retrieved" warning that asyncio logs when a failed task that no
    one awaited is garbage collected.
    """
    if task is None:
        return
    if not task.done():
        task.cancel()
    elif not task.cancelled() and (error := task.exception()) is not None:
        logger.warning("Chart config failed: %s", type(error).__name__)
