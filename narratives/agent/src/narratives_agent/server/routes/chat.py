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
import time

from flask import Blueprint, Response, jsonify, request, stream_with_context

from narratives_agent.session_logger import SessionLogger
from narratives_agent.workflows.chat_pipeline import (
    run_followups,
    run_mcp_phase,
    run_synthesis_phase,
)

chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/chat/stream", methods=["POST"])
def chat_stream():
    """Full chat workflow with SSE streaming.

    Phases:
    1. MCP Tools - Execute data queries (send tool call details)
    2. Synthesis - Stream final response with chart config

    Request body:
    {
        "message": "user query",
        "history": [...optional conversation history...],
        "session_id": "optional session ID for follow-up messages"
    }

    Response: Server-Sent Events stream
    """
    data = request.get_json()
    if not data or not data.get("message"):
        return jsonify({"error": "Message required"}), 400

    user_message = data["message"]
    history = data.get("history", [])
    existing_session_id = data.get("session_id")  # From follow-up messages

    # Create or resume session logger
    session_logger = SessionLogger(session_id=existing_session_id)

    def generate():
        nonlocal session_logger
        request_start_time = time.time()
        full_text = ""

        # Chart config runs in parallel with synthesis
        chart_result_holder = {"config": {"should_render": False}}
        chart_thread = [None]  # Use list to avoid nonlocal issues

        # Shared mutable context threaded through the phase generators so the
        # threading/queue behavior and cross-phase state match the original
        # inline generator exactly.
        ctx = {
            "user_message": user_message,
            "history": history,
            "session_logger": session_logger,
            "request_start_time": request_start_time,
            "full_text": full_text,
            "chart_result_holder": chart_result_holder,
            "chart_thread": chart_thread,
            "mcp_results": "",
            "tool_calls_list": [],
            "thought_queue": None,
            "thought_callback": None,
            "chart_config": None,
            "aborted": False,
        }

        # Send session ID first so frontend can display it
        yield (
            f"data: {json.dumps({'session_id': session_logger.session_id})}\n\n"
        )

        yield from run_mcp_phase(ctx)
        yield from run_synthesis_phase(ctx)
        yield from run_followups(ctx)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
