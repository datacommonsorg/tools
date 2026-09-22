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

"""Chat streaming pipeline phases.

The SSE-emitting phases extracted verbatim from the original inline
``chat_stream`` generator. Each phase is a generator that yields the exact same
SSE strings in the same order and communicates results back to the next phase
through a shared mutable ``ctx`` dict (preserving the threading/queue behavior
of the original inline closures).
"""

import json
import logging
import queue
import threading
import time

import narratives_agent.mcp.client as mcp_client
from narratives_agent.config import (
    apply_query_overrides,
    get_gemini_model,
    load_config,
)
from narratives_agent.gemini.client import gemini_request
from narratives_agent.mcp.client import get_tools
from narratives_agent.mcp.data_utils import (
    annotate_truncation,
    check_data_availability,
    extract_provenance_from_mcp_results,
)
from narratives_agent.workflows.chart_config import (
    get_chart_config,
    validate_data_response,
)
from narratives_agent.workflows.follow_up import generate_follow_up_questions
from narratives_agent.workflows.mcp_loop import execute_mcp_tool_loop

logger = logging.getLogger(__name__)

# How long to wait for the background chart-config thread after synthesis has
# finished streaming. Charts are best-effort: on timeout the turn renders
# without them rather than holding the response open.
CHART_CONFIG_JOIN_TIMEOUT_SECONDS = 5


def run_mcp_phase(ctx):
    """Phase 1: run config/MCP setup then execute the MCP tool loop.

    Reads ``user_message``, ``history``, ``session_logger``, ``query_params``
    and the chart holders from ``ctx``; writes ``effective_config``,
    ``mcp_results``, ``tool_calls_list``, ``mcp_sources``, ``thought_queue``
    and ``thought_callback`` back into ``ctx`` for later phases. Sets
    ``ctx['aborted']`` if the backend config fails to load.

    ``mcp_sources`` is both streamed to the frontend and left on ``ctx``: it is
    the single source of citation numbering, shared by the rendered Sources
    list and the numbered list synthesis is prompted with."""
    session_logger = ctx["session_logger"]
    query_params = ctx["query_params"]
    user_message = ctx["user_message"]
    history = ctx["history"]
    chart_result_holder = ctx["chart_result_holder"]
    chart_thread = ctx["chart_thread"]

    # Log query params if present
    if query_params:
        session_logger.log("QUERY_PARAMS_OVERRIDE", query_params)

    # Log user message
    session_logger.log_user_message(user_message, len(history))

    config = load_config()
    if not config:
        session_logger.log_error("CONFIG_ERROR", "Backend config not loaded")
        yield f"data: {json.dumps({'error': 'Backend config not loaded'})}\n\n"
        ctx["aborted"] = True
        return

    # Apply query param overrides to config
    effective_config = apply_query_overrides(config, query_params)
    ctx["effective_config"] = effective_config

    # Ensure MCP is initialized (fix for tool calls not showing)
    # Readiness is "can we list tools?", not "do we hold a session id?".
    # The session is established on demand and re-established automatically if
    # the data plane instance we land on does not recognise it, so a session id
    # says nothing useful about whether MCP is reachable right now.
    mcp_ready = False
    tools = get_tools()
    if tools:
        mcp_ready = True
        session_logger.log(
            "MCP_TOOLS_AVAILABLE",
            {"tool_count": len(tools), "tools": [t.get("name") for t in tools]},
        )
    else:
        session_logger.log(
            "MCP_NO_TOOLS", {"mcp_session_id": mcp_client.get_session_id()}
        )

    # Create thought queue for streaming thoughts from background threads
    thought_queue = queue.Queue()
    ctx["thought_queue"] = thought_queue

    def thought_callback(thought_text: str, phase: str):
        """Callback to put thoughts into queue for streaming."""
        thought_queue.put({"thought": thought_text, "phase": phase})

    ctx["thought_callback"] = thought_callback

    # Phase 1: MCP Tools
    mcp_enabled = effective_config.get("mcp", {}).get("enabled", True)
    mcp_results = ""
    tool_calls_list = []
    mcp_sources = []

    if mcp_enabled and mcp_ready:
        yield (
            f"data: {
                json.dumps(
                    {
                        'status': 'mcp_start',
                        'message': 'Querying data tools...',
                    }
                )
            }\n\n"
        )

        # Run MCP in thread to enable thought streaming
        # `text` is captured but deliberately unused: the tool loop's own prose
        # ("Max tool iterations reached", "No response from model") is
        # diagnostic, not something to show a user. `truncated` is the part that
        # has to travel -- see the data_status yield below.
        mcp_result_holder = {
            "results": "",
            "tool_calls": [],
            "text": "",
            "truncated": False,
        }

        def run_mcp():
            try:
                (
                    mcp_result_holder["results"],
                    mcp_result_holder["tool_calls"],
                    mcp_result_holder["text"],
                    mcp_result_holder["truncated"],
                ) = execute_mcp_tool_loop(
                    user_message,
                    history,
                    session_logger=session_logger,
                    effective_config=effective_config,
                    thought_callback=lambda t: thought_callback(t, "mcp"),
                )
            except Exception as e:
                logger.error(f"MCP thread error: {e}")
                mcp_result_holder["text"] = f"Error: {e}"

        mcp_thread = threading.Thread(target=run_mcp)
        mcp_thread.start()

        # Stream thoughts while MCP runs
        while mcp_thread.is_alive() or not thought_queue.empty():
            try:
                thought_data = thought_queue.get(timeout=0.1)
                yield f"data: {json.dumps(thought_data)}\n\n"
            except queue.Empty:
                continue

        mcp_thread.join()

        # Signal MCP thinking complete
        yield f"data: {json.dumps({'thinking_complete': 'mcp'})}\n\n"

        # Get results from thread
        mcp_results = mcp_result_holder["results"]
        tool_calls_list = mcp_result_holder["tool_calls"]
        mcp_truncated = mcp_result_holder["truncated"]

        # Send each tool call for left sidebar
        for tc in tool_calls_list:
            yield (
                f"data: {
                    json.dumps(
                        {
                            'type': 'tool_call',
                            'name': tc['name'],
                            'arguments': tc['arguments'],
                            'result': tc['result'],
                            'status': tc['status'],
                        }
                    )
                }\n\n"
            )

        yield (
            f"data: {
                json.dumps(
                    {
                        'status': 'mcp_complete',
                        'tool_count': len(tool_calls_list),
                    }
                )
            }\n\n"
        )

        # Check data availability and send status to frontend.
        # `truncated` rides along here rather than in an event of its own: the
        # frontend already consumes data_status, and truncation is a statement
        # about how complete the data is. Without it a cut-short answer is
        # indistinguishable from a complete one -- it still has citations, a
        # chart and has_data=true.
        data_status = annotate_truncation(
            check_data_availability(tool_calls_list), mcp_truncated
        )
        yield f"data: {json.dumps({'data_status': data_status})}\n\n"

        # Extract and send provenance sources from MCP results.
        #
        # This list is the ONE authority on citation numbering. The frontend
        # numbers the Sources list by position in it, and synthesis is handed
        # the same list already numbered, so the [n] in the prose and the [n]
        # beside the source resolve to the same row. It is therefore stashed on
        # ctx rather than recomputed downstream: two calls that drift apart --
        # because a later phase appended a tool call, say -- would renumber the
        # prose against a list the reader never sees, and nothing would fail
        # loudly.
        mcp_sources = extract_provenance_from_mcp_results(tool_calls_list)
        if not mcp_sources and mcp_results:
            # Observation tools ran but reported no sourceMetadata. Synthesis
            # still has to attribute its figures to something, so fall back to
            # the graph itself -- defined here, once, so the fallback the model
            # cites is the same row the reader sees. Left out entirely when
            # there are no results at all: nothing was fetched, so nothing is
            # attributable.
            mcp_sources = [
                {"name": "Data Commons", "url": "https://datacommons.org/"}
            ]
        if mcp_sources:
            yield f"data: {json.dumps({'mcp_sources': mcp_sources})}\n\n"

        # Start chart config in background (runs parallel with synthesis)
        #
        # Gated on the structural `has_data` check above, not only on the
        # model's later reading of the synthesis prose. A chart is drawn from
        # observations, and check_data_availability already knows whether any
        # landed, so when none did there is nothing to configure and no Gemini
        # call worth spending. The prose check downstream stays as a second net
        # for the case where observations exist but do not answer the question
        # asked; it cannot be the only net, because it is a model judging a
        # wording -- asked about an answer that opened "I don't have this
        # specific data in the current dataset" it still reported data found,
        # and the turn rendered two chart cards whose own fetches then came
        # back empty, under prose saying there was no data.
        if mcp_results and data_status.get("has_data"):

            def run_chart_config():
                chart_result_holder["config"] = get_chart_config(
                    mcp_results, user_message
                )

            chart_thread[0] = threading.Thread(target=run_chart_config)
            chart_thread[0].start()
        elif mcp_results:
            # Left unstarted, so `chart_result_holder` keeps the
            # should_render=False it was created with and the turn renders no
            # charts. Logged because a turn with results but no charts is
            # otherwise indistinguishable from one whose chart config timed out.
            session_logger.log(
                "CHART_CONFIG_SKIPPED",
                {
                    "reason": "no observations in tool results",
                    "no_variables_found": data_status.get("no_variables_found"),
                    "no_observations_found": data_status.get(
                        "no_observations_found"
                    ),
                    "truncated": data_status.get("truncated"),
                },
            )

    elif mcp_enabled and not mcp_ready:
        session_logger.log(
            "MCP_SKIPPED", {"reason": "MCP not connected or no tools available"}
        )
        yield (
            f"data: {
                json.dumps(
                    {
                        'status': 'mcp_skipped',
                        'message': 'MCP server not connected',
                    }
                )
            }\n\n"
        )

    ctx["mcp_results"] = mcp_results
    ctx["tool_calls_list"] = tool_calls_list
    ctx["mcp_sources"] = mcp_sources


def run_synthesis_phase(ctx):
    """Phase 2: Synthesis with streaming, chart validation and the done event.

    Reads the MCP results, chart holders and ``request_start_time`` from
    ``ctx`` -- including ``mcp_sources``, which it numbers for the synthesis
    prompt rather than deriving its own -- and writes ``full_text`` and
    ``chart_config`` back into ``ctx``. Sets
    ``ctx['aborted']`` if the synthesis request returns an error dict or the
    stream breaks part-way, so chart validation, the ``done`` event and
    follow-ups are skipped for a response that was never completed."""
    if ctx["aborted"]:
        return
    session_logger = ctx["session_logger"]
    effective_config = ctx["effective_config"]
    user_message = ctx["user_message"]
    history = ctx["history"]
    mcp_results = ctx["mcp_results"]
    mcp_sources = ctx["mcp_sources"]
    chart_result_holder = ctx["chart_result_holder"]
    chart_thread = ctx["chart_thread"]
    request_start_time = ctx["request_start_time"]
    full_text = ctx["full_text"]

    # Phase 2: Synthesis with streaming
    yield (
        f"data: {
            json.dumps(
                {
                    'status': 'synthesis_start',
                    'message': 'Generating response...',
                }
            )
        }\n\n"
    )

    synthesis_prompt = effective_config.get("prompts", {}).get("synthesis", "")
    synthesis_model = get_gemini_model(effective_config)
    thinking_level = effective_config.get("thinking", {}).get(
        "synthesis_level", "low"
    )

    # Build synthesis context with source labels for citations
    context_parts = []
    if mcp_results:
        # Number sources 1..N in the order streamed to the frontend as
        # mcp_sources so inline [n] citations resolve to the matching entry in
        # the rendered Sources list. Any additional source list must be
        # normalized to {name, url} and appended to mcp_sources before
        # numbering, because the frontend provenance reducer drops entries
        # without a `url` field.
        if mcp_sources:
            numbered_sources = "\n".join(
                f"[{n}] {src.get('name') or src.get('url')} - {src.get('url')}"
                for n, src in enumerate(mcp_sources, start=1)
            )
            context_parts.append(
                "**NUMBERED SOURCES - cite these numbers, exactly as given:**\n"
                f"{numbered_sources}"
            )
        context_parts.append(f"**DATA RESULTS:**\n{mcp_results}")

    # Log synthesis start
    session_logger.log_synthesis_start(["MCP" if mcp_results else None])

    synthesis_message = f"""User Query: {user_message}

{
        chr(10).join(context_parts)
        if context_parts
        else "No additional context available."
    }

Please provide a comprehensive response combining all available information."""

    # Stream the synthesis response with thought streaming
    try:
        # Build messages with conversation history for context
        synthesis_messages = []

        # Add conversation history first (already in Gemini format from
        # frontend)
        for msg in history:
            synthesis_messages.append(msg)

        # Add current query with MCP context as final user message
        synthesis_messages.append(
            {"role": "user", "parts": [{"text": synthesis_message}]}
        )

        stream_gen = gemini_request(
            messages=synthesis_messages,
            system_instruction=synthesis_prompt,
            model=synthesis_model,
            temperature=0.3,
            thinking_level=thinking_level,
            stream=True,
            session_logger=session_logger,
            include_thoughts=True,  # Enable thought streaming
        )

        if isinstance(stream_gen, dict) and "error" in stream_gen:
            session_logger.log_error("SYNTHESIS_ERROR", stream_gen["error"])
            yield f"data: {json.dumps({'error': stream_gen['error']})}\n\n"
            ctx["aborted"] = True
            return

        for chunk in stream_gen:
            # Handle dict format with 'type' and 'content' keys
            if isinstance(chunk, dict):
                if chunk.get("type") == "thought":
                    yield (
                        f"data: {
                            json.dumps(
                                {
                                    'thought': chunk['content'],
                                    'phase': 'synthesis',
                                }
                            )
                        }\n\n"
                    )
                elif chunk.get("type") == "text":
                    full_text += chunk["content"]
                    yield f"data: {json.dumps({'text': chunk['content']})}\n\n"
            else:
                # Backward compatibility: plain text string
                full_text += chunk
                yield f"data: {json.dumps({'text': chunk})}\n\n"

        # Signal synthesis thinking complete
        yield f"data: {json.dumps({'thinking_complete': 'synthesis'})}\n\n"

    except Exception as e:
        logger.error(f"Synthesis streaming error: {e}")
        session_logger.log_error("SYNTHESIS_STREAM_ERROR", str(e))
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
        # A broken stream leaves `full_text` empty or truncated, so chart
        # validation and follow-up generation would spend two more Gemini
        # calls judging a partial answer. Abort instead; the frontend treats
        # `error` as a terminal status, so it does not need the `done` event.
        ctx["full_text"] = full_text
        ctx["aborted"] = True
        return

    # Quick validation: should we show charts based on synthesis response?
    show_charts = True
    if full_text and chart_thread[0]:
        show_charts = validate_data_response(full_text, user_message)
        if not show_charts:
            session_logger.log(
                "CHART_VALIDATION",
                {"data_found": False, "action": "hide_charts"},
            )

    # Wait for chart config thread (started after MCP, runs parallel with
    # synthesis)
    if chart_thread[0]:
        chart_thread[0].join(timeout=CHART_CONFIG_JOIN_TIMEOUT_SECONDS)
    chart_config = chart_result_holder["config"]

    # Add hide_charts flag if validation determined no data was found
    if not show_charts:
        chart_config["hide_charts"] = True

    # Log final response
    total_duration_ms = (time.time() - request_start_time) * 1000
    session_logger.log_final_response(
        full_text, chart_config, total_duration_ms
    )

    # Temporary cost instrumentation: report accumulated Gemini token usage
    # for this query (MCP + synthesis + chart config). Emitted before
    # `done`; the UI shows it only when opened with ?debug=tokens. Follow-up
    # question generation happens after this and is intentionally excluded.
    session_logger.log("TOKEN_USAGE", session_logger.token_usage)
    yield f"data: {json.dumps({'usage': session_logger.token_usage})}\n\n"

    # Send final event with timing info
    yield (
        f"data: {
            json.dumps(
                {
                    'chart_config': chart_config,
                    'done': True,
                    'duration_ms': round(total_duration_ms, 0),
                }
            )
        }\n\n"
    )

    ctx["full_text"] = full_text
    ctx["chart_config"] = chart_config


def run_followups(ctx):
    """Emit follow-up questions grounded in the resolved chart topics.

    Reads ``chart_config`` and ``user_message`` from ``ctx``. Runs after the
    ``done`` event, matching the original order."""
    if ctx["aborted"]:
        return
    user_message = ctx["user_message"]
    chart_config = ctx["chart_config"]

    # Follow-up questions — grounded in the resolved chart topics. Emitted
    # AFTER `done` so the answer/charts render immediately; the UI shows
    # them when they arrive. Returns nothing when no topics resolved.
    try:
        topics = []
        for c in chart_config.get("charts") or []:
            title = c.get("title")
            if title:
                topics.append(title)
        if not topics and chart_config.get(
            "title"
        ):  # legacy single-chart shape
            topics.append(chart_config["title"])
        follow_ups = generate_follow_up_questions(user_message, topics)
        if follow_ups:
            yield f"data: {json.dumps({'follow_up_questions': follow_ups})}\n\n"
    except Exception as e:
        logger.error(f"Follow-up emit error: {e}")
