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
"""Runs the phases of one chat turn as native asyncio code.

`run_turn` drives a turn through its phases in order: the MCP tool loop,
streamed synthesis, chart configuration, the final event, and follow-up
questions. Each phase reports progress by calling the turn's `emit`
callback with one typed SSE event at a time (an event name from
`EventName` and its JSON payload) and hands its results to the next phase
as typed values rather than through shared mutable state.

Every turn that is not canceled ends in exactly one `terminal` event. An
`error` terminal event carries a user-safe `error` message and a
machine-readable `reason`. Its `hmac`, `state_slots`, and
`compacted_summary` fields are placeholders that transcript signing will
populate; they are sent now so that the event's shape does not change when
transcript signing lands.

Chart configuration runs as an `asyncio.Task` concurrently with synthesis
and is awaited, with a timeout, once synthesis has finished streaming.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from narratives_agent.config import get_gemini_model, load_config
from narratives_agent.gemini.client import (
    GeminiStreamError,
    async_gemini_stream,
)
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
from narratives_agent.workflows.follow_up import generate_follow_up_questions
from narratives_agent.workflows.mcp_loop import (
    McpLoopError,
    execute_mcp_tool_loop,
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

_SYNTHESIS_TEMPERATURE = 0.3

# This source is cited when observation tools ran but reported no
# `sourceMetadata`; see `run_mcp_phase`.
_FALLBACK_SOURCE = {"name": "Data Commons", "url": "https://datacommons.org/"}

_NO_CHARTS: dict[str, Any] = {"should_render": False}

_SYNTHESIS_FAILED = "The response could not be generated. Please try again."
_MCP_UNAVAILABLE = "The data service is unavailable. Please try again."
_MCP_TOOLS_TIMEOUT = "The data service did not respond. Please try again."
_INTERNAL_ERROR = "An internal error occurred. Please try again."

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
    """Holds the inputs and callbacks shared across every phase of a turn."""

    user_message: str
    history: list[dict[str, Any]]
    config: dict[str, Any]
    telemetry: TurnTelemetry
    emit: Emit


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
    """Gathers data through the MCP tool loop during Phase 1.

    Streams the tool calls, the data status, and the provenance sources, and
    starts chart configuration in the background when observations are
    returned.

    Raises:
        TurnAbortedError: If no MCP tools are available or the tool loop
            fails. MCP is a hard dependency: synthesis must not answer from
            general knowledge or run on the empty or partial results left
            behind by a failed loop.
    """
    result = McpPhaseResult()
    if not ctx.config.get("mcp", {}).get("enabled", True):
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
        raise TurnAbortedError("mcp_timeout", _MCP_TOOLS_TIMEOUT) from error
    if not tools:
        logger.warning("MCP unavailable: not connected or no tools available")
        raise TurnAbortedError("mcp_unavailable", _MCP_UNAVAILABLE)

    ctx.emit("status", {"phase": "mcp", "message": "Querying data tools..."})
    try:
        loop_result = await execute_mcp_tool_loop(
            ctx.user_message,
            ctx.config,
            tools,
            ctx.telemetry,
            thought_callback=lambda text: ctx.emit(
                "thought", {"thought": text, "phase": "mcp"}
            ),
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
                result.results, ctx.user_message, ctx.telemetry.tokens
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
    """Streams the narrative answer during Phase 2.

    Returns:
        The complete answer text.

    Raises:
        TurnAbortedError: If the synthesis request fails, its stream breaks
            part-way, or it returns no answer text. A broken or empty stream
            leaves the answer missing or truncated, so chart validation and
            follow-up generation would spend more Gemini calls judging an
            incomplete answer.
    """
    ctx.emit(
        "status", {"phase": "synthesis", "message": "Generating response..."}
    )
    config = ctx.config
    # Conversation history (already in Gemini format from the frontend)
    # comes first, then the current query with the MCP context.
    messages = [
        *ctx.history,
        {
            "role": "user",
            "parts": [{"text": _synthesis_message(ctx.user_message, mcp)}],
        },
    ]
    stream = await async_gemini_stream(
        messages=messages,
        system_instruction=config.get("prompts", {}).get("synthesis", ""),
        model=get_gemini_model(config),
        temperature=_SYNTHESIS_TEMPERATURE,
        thinking_level=config.get("thinking", {}).get("synthesis_level", "low"),
        token_usage=ctx.telemetry.tokens,
        include_thoughts=True,
    )
    if isinstance(stream, dict):
        # The client has already logged the redacted upstream error, so the
        # user receives a fixed message.
        raise TurnAbortedError("synthesis_error", _SYNTHESIS_FAILED)

    full_text = ""
    try:
        async for chunk in stream:
            if isinstance(chunk, str):
                full_text += chunk
                ctx.emit("content", {"text": chunk})
            elif chunk["type"] == "thought":
                ctx.emit(
                    "thought",
                    {"thought": chunk["content"], "phase": "synthesis"},
                )
            else:
                full_text += chunk["content"]
                ctx.emit("content", {"text": chunk["content"]})
    except GeminiStreamError as error:
        raise TurnAbortedError(
            "synthesis_stream_error", _SYNTHESIS_FAILED
        ) from error
    finally:
        await stream.aclose()
    if not full_text.strip():
        logger.warning("Synthesis returned no answer text")
        raise TurnAbortedError("synthesis_empty", _SYNTHESIS_FAILED)
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
        "status", {"phase": "chart_config", "message": "Preparing charts..."}
    )
    show_charts = True
    if full_text:
        try:
            show_charts = await validate_data_response(
                full_text, ctx.user_message, ctx.telemetry.tokens
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
    arrive. It emits nothing when no chart topics are available.
    """
    follow_ups = await generate_follow_up_questions(
        ctx.user_message, _chart_topics(chart_config), ctx.telemetry.tokens
    )
    if follow_ups:
        ctx.emit("follow_ups", {"follow_up_questions": follow_ups})


def terminal_frame(
    state: TerminalState,
    idempotency_key: str,
    error: TurnAbortedError | None = None,
) -> dict[str, Any]:
    """Builds the payload of a `terminal` event.

    An `error` frame adds the user-safe `error` message and the
    machine-readable `reason`. `hmac`, `state_slots`, and
    `compacted_summary` are empty placeholders until transcript signing
    populates them.
    """
    frame: dict[str, Any] = {
        "state": state,
        "idempotency_key": idempotency_key,
        "hmac": "",
        "state_slots": {"scopes": []},
        "compacted_summary": None,
    }
    if error is not None:
        frame["error"] = str(error)
        frame["reason"] = error.error_type
    return frame


async def run_turn(
    user_message: str,
    history: list[dict[str, Any]],
    idempotency_key: str,
    emit: Emit,
) -> None:
    """Runs one chat turn and emits its typed SSE events through `emit`.

    The turn ends in one `terminal` event: `complete` once the answer and
    chart config are delivered, or `error` with a user-safe message. Every
    failure is reported through that event and recorded in telemetry. Only
    `asyncio.CancelledError` is re-raised to the caller; cancellation emits
    no terminal event because the client that would read it has already
    disconnected, and it is recorded as `canceled` unless the turn has
    already completed. Follow-up questions are emitted after the terminal
    event. The background chart task is settled whenever the turn ends, so
    no orphaned task outlives the request.
    """
    telemetry = TurnTelemetry()
    state: TerminalState | None = None
    error_type: str | None = None
    chart_task: asyncio.Task[dict[str, Any]] | None = None
    try:
        config = load_config()
        if not config:
            raise TurnAbortedError(
                "config_missing", "Backend config not loaded"
            )
        ctx = TurnContext(user_message, history, config, telemetry, emit)
        with telemetry.phase("mcp"):
            mcp = await run_mcp_phase(ctx)
        chart_task = mcp.chart_task
        with telemetry.phase("synthesis"):
            full_text = await run_synthesis_phase(ctx, mcp)
        with telemetry.phase("chart_config"):
            chart_config = await resolve_chart_config(ctx, mcp, full_text)
        emit("content", {"chart_config": chart_config})
        state = "complete"
        emit("terminal", terminal_frame(state, idempotency_key))
        with telemetry.phase("follow_ups"):
            await run_followups(ctx, chart_config)
    except TurnAbortedError as error:
        state, error_type = "error", error.error_type
        emit("terminal", terminal_frame(state, idempotency_key, error))
    except asyncio.CancelledError:
        state = state or "canceled"
        raise
    except Exception:
        if state is None:
            logger.exception("Chat turn failed")
            internal = TurnAbortedError("internal_error", _INTERNAL_ERROR)
            state, error_type = "error", internal.error_type
            emit("terminal", terminal_frame(state, idempotency_key, internal))
        else:
            # The answer was already delivered; only the follow-ups failed.
            logger.exception("Follow-up generation failed")
    finally:
        _settle_chart_task(chart_task)
        telemetry.finish(state or "error", error_type)


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
