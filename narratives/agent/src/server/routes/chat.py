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

import json
import logging
import time

from flask import Blueprint, jsonify, request, Response, stream_with_context

from src.config import get_query_param_key
from src.session_logger import SessionLogger
from src.workflows.chat_pipeline import (
    run_followups,
    run_kb_phase,
    run_mcp_phase,
    run_synthesis_phase,
)

logger = logging.getLogger(__name__)

chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/api/chat/stream", methods=["POST"])
@chat_bp.route("/chat/stream", methods=["POST"])  # alias for the SPA served under /agent/*
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

        # Shared mutable context threaded through the phase generators so the
        # threading/queue behavior and cross-phase state match the original
        # inline generator exactly.
        ctx = {
            'user_message': user_message,
            'history': history,
            'session_logger': session_logger,
            'query_params': query_params,
            'demo_mode': demo_mode,
            'request_start_time': request_start_time,
            'full_text': full_text,
            'chart_result_holder': chart_result_holder,
            'chart_thread': chart_thread,
            'effective_config': None,
            'mcp_results': "",
            'tool_calls_list': [],
            'kb_response': "",
            'kb_sources': [],
            'thought_queue': None,
            'thought_callback': None,
            'chart_config': None,
            'aborted': False,
        }

        # Send session ID first so frontend can display it
        yield f"data: {json.dumps({'session_id': session_logger.session_id})}\n\n"

        yield from run_mcp_phase(ctx)
        yield from run_kb_phase(ctx)
        yield from run_synthesis_phase(ctx)
        yield from run_followups(ctx)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )
