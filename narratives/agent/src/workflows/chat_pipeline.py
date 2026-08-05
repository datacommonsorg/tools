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

import src.mcp.client as mcp_client
from src.config import apply_query_overrides, load_config
from src.gemini.client import gemini_request
from src.mcp.client import get_tools, initialize_mcp
from src.mcp.data_utils import (
    check_data_availability,
    extract_provenance_from_mcp_results,
)
from src.workflows.chart_config import get_chart_config, validate_data_response
from src.workflows.follow_up import generate_follow_up_questions
from src.workflows.kb_search import execute_kb_query
from src.workflows.mcp_loop import execute_mcp_tool_loop

logger = logging.getLogger(__name__)

# How long to wait for the background chart-config thread after synthesis has
# finished streaming. Charts are best-effort: on timeout the turn renders
# without them rather than holding the response open.
CHART_CONFIG_JOIN_TIMEOUT_SECONDS = 5


def run_mcp_phase(ctx):
    """Phase 1: run config/MCP setup then execute the MCP tool loop.

    Reads ``user_message``, ``history``, ``session_logger``, ``query_params``,
    ``demo_mode`` and the chart holders from ``ctx``; writes ``effective_config``,
    ``mcp_results``, ``tool_calls_list``, ``thought_queue`` and
    ``thought_callback`` back into ``ctx`` for later phases. Sets
    ``ctx['aborted']`` if the backend config fails to load."""
    session_logger = ctx['session_logger']
    query_params = ctx['query_params']
    demo_mode = ctx['demo_mode']
    user_message = ctx['user_message']
    history = ctx['history']
    chart_result_holder = ctx['chart_result_holder']
    chart_thread = ctx['chart_thread']

    # Log query params if present
    if query_params:
        session_logger.log("QUERY_PARAMS_OVERRIDE", query_params)

    # Log demo mode if enabled
    if demo_mode:
        session_logger.log("DEMO_MODE_ENABLED", {"using_demo_keys": True})

    # Log user message
    session_logger.log_user_message(user_message, len(history))

    config = load_config()
    if not config:
        session_logger.log_error("CONFIG_ERROR", "Backend config not loaded")
        yield f"data: {json.dumps({'error': 'Backend config not loaded'})}\n\n"
        ctx['aborted'] = True
        return

    # Apply query param overrides to config
    effective_config = apply_query_overrides(config, query_params)
    ctx['effective_config'] = effective_config

    # Ensure MCP is initialized (fix for tool calls not showing)
    mcp_ready = False
    if not mcp_client.session_id:
        logger.info("MCP session not initialized, attempting to connect...")
        session_logger.log("MCP_INIT_ATTEMPT", {"reason": "session_id was None"})
        if initialize_mcp():
            session_logger.log("MCP_INIT_SUCCESS", {"mcp_session_id": mcp_client.session_id})
            mcp_ready = True
        else:
            # Even if init returns False, try to get tools anyway
            # Some MCP servers work without session IDs
            session_logger.log("MCP_INIT_RETURNED_FALSE", {"trying_tools_anyway": True})
    else:
        mcp_ready = True

    # Double-check: if we have tools, MCP is working regardless of session_id
    tools = get_tools()
    if tools:
        mcp_ready = True
        session_logger.log("MCP_TOOLS_AVAILABLE", {"tool_count": len(tools), "tools": [t.get("name") for t in tools]})
    else:
        session_logger.log("MCP_NO_TOOLS", {"session_id": mcp_client.session_id})

    # Create thought queue for streaming thoughts from background threads
    thought_queue = queue.Queue()
    ctx['thought_queue'] = thought_queue

    def thought_callback(thought_text: str, phase: str):
        """Callback to put thoughts into queue for streaming."""
        thought_queue.put({'thought': thought_text, 'phase': phase})
    ctx['thought_callback'] = thought_callback

    # Phase 1: MCP Tools
    mcp_enabled = effective_config.get("mcp", {}).get("enabled", True)
    mcp_results = ""
    tool_calls_list = []

    if mcp_enabled and mcp_ready:
        yield f"data: {json.dumps({'status': 'mcp_start', 'message': 'Querying data tools...'})}\n\n"

        # Run MCP in thread to enable thought streaming
        mcp_result_holder = {'results': '', 'tool_calls': [], 'text': ''}

        def run_mcp():
            try:
                mcp_result_holder['results'], mcp_result_holder['tool_calls'], mcp_result_holder['text'] = execute_mcp_tool_loop(
                    user_message, history, session_logger=session_logger,
                    effective_config=effective_config,
                    thought_callback=lambda t: thought_callback(t, 'mcp'),
                    demo_mode=demo_mode
                )
            except Exception as e:
                logger.error(f"MCP thread error: {e}")
                mcp_result_holder['text'] = f"Error: {e}"

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
        mcp_results = mcp_result_holder['results']
        tool_calls_list = mcp_result_holder['tool_calls']

        # Send each tool call for left sidebar
        for tc in tool_calls_list:
            yield f"data: {json.dumps({'type': 'tool_call', 'name': tc['name'], 'arguments': tc['arguments'], 'result': tc['result'], 'status': tc['status']})}\n\n"

        yield f"data: {json.dumps({'status': 'mcp_complete', 'tool_count': len(tool_calls_list)})}\n\n"

        # Check data availability and send status to frontend
        data_status = check_data_availability(tool_calls_list)
        yield f"data: {json.dumps({'data_status': data_status})}\n\n"

        # Extract and send provenance sources from MCP results
        mcp_sources = extract_provenance_from_mcp_results(tool_calls_list)
        if mcp_sources:
            yield f"data: {json.dumps({'mcp_sources': mcp_sources})}\n\n"

        # Start chart config in background (runs parallel with KB + synthesis)
        if mcp_results:
            def run_chart_config():
                chart_result_holder['config'] = get_chart_config(mcp_results, user_message)
            chart_thread[0] = threading.Thread(target=run_chart_config)
            chart_thread[0].start()

    elif mcp_enabled and not mcp_ready:
        session_logger.log("MCP_SKIPPED", {"reason": "MCP not connected or no tools available"})
        yield f"data: {json.dumps({'status': 'mcp_skipped', 'message': 'MCP server not connected'})}\n\n"

    ctx['mcp_results'] = mcp_results
    ctx['tool_calls_list'] = tool_calls_list


def run_kb_phase(ctx):
    """Phase 2: KB Query (if enabled).

    Reads ``effective_config``, ``user_message``, ``session_logger``,
    ``demo_mode``, ``thought_queue`` and ``thought_callback`` from ``ctx``;
    writes ``kb_response`` and ``kb_sources`` back into ``ctx``."""
    if ctx['aborted']:
        return
    session_logger = ctx['session_logger']
    effective_config = ctx['effective_config']
    user_message = ctx['user_message']
    demo_mode = ctx['demo_mode']
    thought_queue = ctx['thought_queue']
    thought_callback = ctx['thought_callback']

    # Phase 2: KB Query (if enabled)
    kb_response = ""
    kb_sources = []
    kb_enabled = effective_config.get("knowledge_base", {}).get("enabled", False)

    if kb_enabled:
        yield f"data: {json.dumps({'status': 'kb_start', 'message': 'Searching knowledge base...'})}\n\n"

        # Run KB in thread to enable thought streaming
        kb_result_holder = {'response': '', 'sources': []}

        def run_kb():
            try:
                kb_result = execute_kb_query(
                    user_message, session_logger=session_logger,
                    thought_callback=lambda t: thought_callback(t, 'kb'),
                    demo_mode=demo_mode,
                    effective_config=effective_config
                )
                kb_result_holder['response'] = kb_result.get("response", "")
                kb_result_holder['sources'] = kb_result.get("sources", [])
            except Exception as e:
                logger.error(f"KB thread error: {e}")

        kb_thread = threading.Thread(target=run_kb)
        kb_thread.start()

        # Stream thoughts while KB runs
        while kb_thread.is_alive() or not thought_queue.empty():
            try:
                thought_data = thought_queue.get(timeout=0.1)
                yield f"data: {json.dumps(thought_data)}\n\n"
            except queue.Empty:
                continue

        kb_thread.join()

        # Signal KB thinking complete
        yield f"data: {json.dumps({'thinking_complete': 'kb'})}\n\n"

        # Get results from thread
        kb_response = kb_result_holder['response']
        kb_sources = kb_result_holder['sources']

        # Send KB sources to frontend for inline citations
        if kb_sources:
            yield f"data: {json.dumps({'kb_sources': kb_sources})}\n\n"
        yield f"data: {json.dumps({'status': 'kb_complete'})}\n\n"

    ctx['kb_response'] = kb_response
    ctx['kb_sources'] = kb_sources


def run_synthesis_phase(ctx):
    """Phase 3: Synthesis with streaming, chart validation and the done event.

    Reads the MCP/KB results, chart holders and ``request_start_time`` from
    ``ctx``; writes ``full_text`` and ``chart_config`` back into ``ctx``. Sets
    ``ctx['aborted']`` if the synthesis request returns an error dict or the
    stream breaks part-way, so chart validation, the ``done`` event and
    follow-ups are skipped for a response that was never completed."""
    if ctx['aborted']:
        return
    session_logger = ctx['session_logger']
    effective_config = ctx['effective_config']
    user_message = ctx['user_message']
    history = ctx['history']
    demo_mode = ctx['demo_mode']
    mcp_results = ctx['mcp_results']
    tool_calls_list = ctx['tool_calls_list']
    kb_response = ctx['kb_response']
    kb_sources = ctx['kb_sources']
    chart_result_holder = ctx['chart_result_holder']
    chart_thread = ctx['chart_thread']
    request_start_time = ctx['request_start_time']
    full_text = ctx['full_text']

    # Phase 3: Synthesis with streaming
    yield f"data: {json.dumps({'status': 'synthesis_start', 'message': 'Generating response...'})}\n\n"

    synthesis_prompt = effective_config.get("prompts", {}).get("synthesis", "")
    synthesis_model = effective_config.get("gemini", {}).get("mcp_model", "gemini-3-flash-preview")
    thinking_level = effective_config.get("thinking", {}).get("synthesis_level", "low")

    # Build synthesis context with source labels for citations
    context_parts = []
    if mcp_results:
        # Format extracted sources as markdown links for synthesis
        mcp_sources = extract_provenance_from_mcp_results(tool_calls_list)
        if mcp_sources:
            source_links = ", ".join([f"[{s['name']}]({s['url']})" for s in mcp_sources])
        else:
            source_links = "Data Commons"
        context_parts.append(f"**DATA RESULTS [Sources: {source_links}]:**\n{mcp_results}")
    if kb_response:
        # Include document names from kb_sources for proper citation
        kb_source_names = ", ".join([s['title'] for s in kb_sources]) if kb_sources else "Knowledge Base"
        context_parts.append(f"**POLICY INFORMATION [Sources: {kb_source_names}]:**\n{kb_response}")

    # Log synthesis start
    session_logger.log_synthesis_start(["MCP" if mcp_results else None, "KB" if kb_response else None])

    synthesis_message = f"""User Query: {user_message}

{chr(10).join(context_parts) if context_parts else 'No additional context available.'}

Please provide a comprehensive response combining all available information."""

    # Stream the synthesis response with thought streaming
    try:
        # Build messages with conversation history for context
        synthesis_messages = []

        # Add conversation history first (already in Gemini format from frontend)
        for msg in history:
            synthesis_messages.append(msg)

        # Add current query with MCP/KB context as final user message
        synthesis_messages.append({"role": "user", "parts": [{"text": synthesis_message}]})

        stream_gen = gemini_request(
            messages=synthesis_messages,
            system_instruction=synthesis_prompt,
            model=synthesis_model,
            temperature=0.3,
            thinking_level=thinking_level,
            stream=True,
            session_logger=session_logger,
            include_thoughts=True,  # Enable thought streaming
            demo_mode=demo_mode
        )

        if isinstance(stream_gen, dict) and "error" in stream_gen:
            session_logger.log_error("SYNTHESIS_ERROR", stream_gen['error'])
            yield f"data: {json.dumps({'error': stream_gen['error']})}\n\n"
            ctx['aborted'] = True
            return

        for chunk in stream_gen:
            # Handle dict format with 'type' and 'content' keys
            if isinstance(chunk, dict):
                if chunk.get('type') == 'thought':
                    yield f"data: {json.dumps({'thought': chunk['content'], 'phase': 'synthesis'})}\n\n"
                elif chunk.get('type') == 'text':
                    full_text += chunk['content']
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
        ctx['full_text'] = full_text
        ctx['aborted'] = True
        return

    # Quick validation: should we show charts based on synthesis response?
    show_charts = True
    if full_text and chart_thread[0]:
        show_charts = validate_data_response(full_text, user_message)
        if not show_charts:
            session_logger.log("CHART_VALIDATION", {"data_found": False, "action": "hide_charts"})

    # Wait for chart config thread (started after MCP, runs parallel with KB + synthesis)
    if chart_thread[0]:
        chart_thread[0].join(timeout=CHART_CONFIG_JOIN_TIMEOUT_SECONDS)
    chart_config = chart_result_holder['config']

    # Add hide_charts flag if validation determined no data was found
    if not show_charts:
        chart_config['hide_charts'] = True

    # Log final response
    total_duration_ms = (time.time() - request_start_time) * 1000
    session_logger.log_final_response(full_text, chart_config, total_duration_ms)

    # Temporary cost instrumentation: report accumulated Gemini token usage
    # for this query (MCP + KB + synthesis + chart config). Emitted before
    # `done`; the UI shows it only when opened with ?debug=tokens. Follow-up
    # question generation happens after this and is intentionally excluded.
    session_logger.log("TOKEN_USAGE", session_logger.token_usage)
    yield f"data: {json.dumps({'usage': session_logger.token_usage})}\n\n"

    # Send final event with timing info
    yield f"data: {json.dumps({'chart_config': chart_config, 'done': True, 'duration_ms': round(total_duration_ms, 0)})}\n\n"

    ctx['full_text'] = full_text
    ctx['chart_config'] = chart_config


def run_followups(ctx):
    """Emit follow-up questions grounded in the resolved chart topics.

    Reads ``chart_config`` and ``user_message`` from ``ctx``. Runs after the
    ``done`` event, matching the original order."""
    if ctx['aborted']:
        return
    user_message = ctx['user_message']
    chart_config = ctx['chart_config']

    # Follow-up questions — grounded in the resolved chart topics. Emitted
    # AFTER `done` so the answer/charts render immediately; the UI shows
    # them when they arrive. Returns nothing when no topics resolved.
    try:
        topics = []
        for c in (chart_config.get('charts') or []):
            title = c.get('title')
            if title:
                topics.append(title)
        if not topics and chart_config.get('title'):  # legacy single-chart shape
            topics.append(chart_config['title'])
        follow_ups = generate_follow_up_questions(user_message, topics)
        if follow_ups:
            yield f"data: {json.dumps({'follow_up_questions': follow_ups})}\n\n"
    except Exception as e:
        logger.error(f"Follow-up emit error: {e}")
