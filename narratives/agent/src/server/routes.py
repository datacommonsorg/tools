#!/usr/bin/env python3
# Copyright 2024 Google LLC
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

import json
import logging
import os
import queue
import threading
import time

from flask import jsonify, request, Response, stream_with_context

import src.mcp.client as mcp_client
from src.config import (
    _fetch_gcs_url,
    apply_query_overrides,
    get_query_param_key,
    load_config,
)
from src.mcp.client import call_tool, get_tools, initialize_mcp, MCP_PORT, MCP_URL
from src.mcp.data_utils import (
    check_data_availability,
    extract_provenance_from_mcp_results,
)
from src.mcp.schema import transform_schema_for_gemini
from src.gemini.client import gemini_request
from src.server.app import app, PROXY_PORT
from src.session_logger import SessionLogger
from src.workflows.chart_config import get_chart_config, validate_data_response
from src.workflows.follow_up import generate_follow_up_questions
from src.workflows.kb_search import execute_kb_query
from src.workflows.mcp_loop import execute_mcp_tool_loop

logger = logging.getLogger(__name__)


# Route aliases the React UI expects. The upstream routes (/api/chat/stream,
# /api/config) stay live
# for backward compatibility; these aliases are what the SPA at /agent/* hits
# via the services container's nginx prefix-strip.
# Short-TTL cache for branding.json so we don't hit GCS (and the
# metadata token endpoint) on every page load. Bounds staleness to _BRAND_TTL
# seconds; /brand?refresh=1 forces an immediate refetch after a config sync
# (e.g. `deploy.sh --config-only`).
_BRAND_CACHE: dict = {"ts": 0.0, "payload": None}
_BRAND_TTL_SECONDS = int(os.environ.get("BRAND_CACHE_TTL", "60"))


def _build_brand_payload() -> dict:
    """Assemble the /brand payload: the config bucket URL plus, when available,
    the branding.json contents fetched from the (possibly private) bucket."""
    brand_config_url = os.environ.get("BRAND_CONFIG_URL", "").rstrip("/")
    branding_data = None
    if brand_config_url:
        try:
            r = _fetch_gcs_url(f"{brand_config_url}/branding.json")
            if r.status_code == 200:
                branding_data = r.json()
                logger.info("Successfully fetched branding.json from config bucket")
            else:
                logger.warning(f"Failed to fetch branding.json: HTTP {r.status_code}")
        except Exception as e:
            logger.error(f"Error fetching branding.json from bucket: {e}")

    return {
        "brand_config_url": brand_config_url,
        "instance": os.environ.get("INSTANCE_ID", ""),
        "branding": branding_data,
    }


@app.route("/brand", methods=["GET"])
def brand_alias():
    """Return the per-instance branding bucket URL and branding.json contents.

    Cached in-process for _BRAND_TTL_SECONDS; pass ?refresh=1 to force a fresh
    fetch (e.g. right after uploading a new branding.json to the bucket)."""
    force = request.args.get("refresh") == "1"
    now = time.time()
    cached = _BRAND_CACHE["payload"]
    if not force and cached is not None and now - _BRAND_CACHE["ts"] < _BRAND_TTL_SECONDS:
        payload = cached
    else:
        payload = _build_brand_payload()
        _BRAND_CACHE["payload"] = payload
        _BRAND_CACHE["ts"] = now

    resp = jsonify(payload)
    resp.headers["Cache-Control"] = "no-store"
    return resp


# Flask Routes

@app.route("/health", methods=["GET"])
def health():
    """Health check."""
    return jsonify({"status": "ok", "mcp_url": MCP_URL})


@app.route("/api/tools", methods=["GET"])
def list_tools():
    """List available tools."""
    if not mcp_client.session_id:
        if not initialize_mcp():
            return jsonify({"success": False, "error": "Cannot connect to MCP server. Make sure it's running on port 3000!"}), 503

    tools = get_tools()
    if not tools:
        return jsonify({"success": False, "error": "No tools available"}), 503

    # Convert to Gemini format (transform schema to remove unsupported constructs)
    gemini_tools = [{
        "name": t.get("name", ""),
        "description": t.get("description", ""),
        "parameters": transform_schema_for_gemini(
            t.get("inputSchema", {"type": "object", "properties": {}})
        )
    } for t in tools]

    return jsonify({"success": True, "tools": gemini_tools, "raw_tools": tools})


@app.route("/api/call", methods=["POST"])
def tool_call():
    """Execute a tool call."""
    if not mcp_client.session_id:
        if not initialize_mcp():
            return jsonify({"success": False, "error": "Cannot connect to MCP server"}), 503

    data = request.get_json()
    if not data or not data.get("name"):
        return jsonify({"success": False, "error": "Tool name required"}), 400

    logger.info(f"Calling tool: {data['name']}")
    result = call_tool(data["name"], data.get("arguments", {}))
    return jsonify({"success": True, "result": result})


@app.route("/", methods=["GET"])
def index():
    return f"""
    <html>
    <head><title>MCP Proxy</title></head>
    <body>
    <h1>Data Commons MCP Proxy Server (Proxy-Only Mode)</h1>
    <p>MCP Server: {MCP_URL}</p>
    <p>Proxy Server: http://localhost:{PROXY_PORT}</p>
    <ul>
        <li><a href="/health">/health</a> - Health check</li>
        <li><a href="/api/tools">/api/tools</a> - List tools</li>
        <li>POST /api/call - Execute tool</li>
        <li><a href="/api/config">/api/config</a> - Get backend config (no API key)</li>
        <li>POST /api/chat/stream - Full chat with streaming</li>
        <li><a href="/logs?key=">/logs</a> - Query Analytics Dashboard (requires ?key=SECRET)</li>
    </ul>
    <h3>Prerequisite</h3>
    <p>Make sure the MCP server is running:</p>
    <code>python3 -m uv tool run datacommons-mcp serve http --port {MCP_PORT}</code>
    </body>
    </html>
    """


# ============================================================
# NEW BACKEND API ENDPOINTS FOR GEMINI CALLS
# ============================================================

@app.route("/api/config", methods=["GET"])
def get_config_endpoint():
    """Return sanitized config (without API key) for frontend."""
    config = load_config()
    if not config:
        return jsonify({"success": False, "error": "Config not loaded"}), 500

    # Return config without sensitive data
    safe_config = {
        "proxy_url": config.get("proxy_url", f"http://localhost:{PROXY_PORT}"),
        "gemini": {
            "api_base": config.get("gemini", {}).get("api_base", ""),
            "mcp_model": config.get("gemini", {}).get("mcp_model", "gemini-3-flash-preview"),
            "kb_model": config.get("gemini", {}).get("kb_model", "gemini-3-flash-preview"),
        },
        "mcp": config.get("mcp", {}),
        "knowledge_base": config.get("knowledge_base", {}),
        "thinking": config.get("thinking", {}),
        "has_api_key": bool(config.get("gemini", {}).get("api_key")),
    }
    return jsonify({"success": True, "config": safe_config})


@app.route("/api/chat/stream", methods=["POST"])
@app.route("/chat/stream", methods=["POST"])  # alias for the SPA served under /agent/*
def chat_stream():
    """Full chat workflow with SSE streaming.

    Phases:
    1. MCP Tools - Execute data queries (send tool call details)
    2. KB Query - Search knowledge base (if enabled)
    3. Synthesis - Stream final response with chart config

    Request body:
    {
        "message": "user query",
        "history": [...optional conversation history...],
        "session_id": "optional session ID for follow-up messages"
    }

    Query params (optional, requires valid key):
    - key: Secret key for config overrides (must match query_param_key in config)
    - model: Override mcp_model and kb_model
    - kb: "true" or "false" to toggle knowledge base
    - mcp_thinking: Override MCP thinking level
    - synthesis_thinking: Override synthesis thinking level

    Response: Server-Sent Events stream
    """
    data = request.get_json()
    if not data or not data.get("message"):
        return jsonify({"error": "Message required"}), 400

    user_message = data["message"]
    history = data.get("history", [])
    existing_session_id = data.get("session_id")  # From follow-up messages

    # Parse query parameters for config overrides
    query_params = {}
    secret_key = request.args.get("key", "")
    expected_key = get_query_param_key()
    demo_mode = False

    if secret_key == expected_key:
        # Valid key - extract override params
        query_params = {
            "model": request.args.get("model"),  # e.g., "gemini-2.0-flash"
            "kb_enabled": request.args.get("kb"),  # "true" or "false"
            "mcp_thinking": request.args.get("mcp_thinking"),  # "low", "medium", "high", or budget number
            "synthesis_thinking": request.args.get("synthesis_thinking"),  # same options
        }
        # Remove None values
        query_params = {k: v for k, v in query_params.items() if v is not None}
        if query_params:
            logger.info(f"Query params override applied: {query_params}")

        # Check for demo mode - uses reserved API keys for internal demos
        if request.args.get("demo", "").lower() == "true":
            demo_mode = True
            logger.info("Demo mode ENABLED - using reserved demo API keys")
    elif secret_key:
        # Invalid key provided - log warning but continue with defaults
        logger.warning(f"Invalid query param key provided, ignoring overrides")

    # Create or resume session logger
    session_logger = SessionLogger(session_id=existing_session_id)

    def generate():
        nonlocal session_logger
        request_start_time = time.time()
        full_text = ""

        # Chart config runs in parallel with KB + synthesis
        chart_result_holder = {'config': {"should_render": False}}
        chart_thread = [None]  # Use list to avoid nonlocal issues

        # Send session ID first so frontend can display it
        yield f"data: {json.dumps({'session_id': session_logger.session_id})}\n\n"

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
            return

        # Apply query param overrides to config
        effective_config = apply_query_overrides(config, query_params)

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

        def thought_callback(thought_text: str, phase: str):
            """Callback to put thoughts into queue for streaming."""
            thought_queue.put({'thought': thought_text, 'phase': phase})

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

        # Quick validation: should we show charts based on synthesis response?
        show_charts = True
        if full_text and chart_thread[0]:
            show_charts = validate_data_response(full_text, user_message)
            if not show_charts:
                session_logger.log("CHART_VALIDATION", {"data_found": False, "action": "hide_charts"})

        # Wait for chart config thread (started after MCP, runs parallel with KB + synthesis)
        if chart_thread[0]:
            chart_thread[0].join(timeout=5)
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

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )
