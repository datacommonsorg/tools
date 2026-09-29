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
"""Streams a chat turn to the browser as Server-Sent Events."""

import json
import time
from collections.abc import Generator
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from narratives_agent.server.responses import ClosingStreamingResponse
from narratives_agent.session_logger import SESSION_ID_PATTERN, SessionLogger
from narratives_agent.workflows.chat_pipeline import (
    run_followups,
    run_mcp_phase,
    run_synthesis_phase,
)

router = APIRouter()


class ChatRequest(BaseModel):
    """The JSON body of a chat request."""

    message: str = Field(min_length=1)
    history: list[dict[str, Any]] = Field(default_factory=list)
    # SessionLogger names the session's log file after the id; the pattern
    # it owns accepts only characters that cannot leave the logs directory.
    session_id: str | None = Field(default=None, pattern=SESSION_ID_PATTERN)


@router.post("/chat/stream")
def chat_stream(body: ChatRequest) -> ClosingStreamingResponse:
    """Streams the full chat workflow as Server-Sent Events.

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

    Starlette advances the synchronous generator below one `next()` call at a
    time, each on a thread borrowed from AnyIO's worker pool, so one turn's
    events can run on several threads. The MCP session id is thread-local
    (`mcp/client.py`), so a turn can use several MCP sessions, and a later turn
    can reuse a session that an earlier one left on a pool thread. This is
    safe: a pool thread runs one job at a time, so no two requests share a
    session at once; the MCP tool loop runs on one dedicated thread for the
    whole turn; and `mcp_call` opens a session when its thread has none and
    retries once on a new session when the server rejects one.
    """
    user_message = body.message
    history = body.history
    existing_session_id = body.session_id  # From follow-up messages

    # Create or resume session logger
    session_logger = SessionLogger(session_id=existing_session_id)

    def generate() -> Generator[str]:
        nonlocal session_logger
        request_start_time = time.time()
        full_text = ""

        # Chart config runs in parallel with synthesis
        chart_result_holder = {"config": {"should_render": False}}
        chart_thread = [None]  # Use list to avoid nonlocal issues

        # Shared mutable context threaded through the phase generators so the
        # threading/queue behavior and cross-phase state match the original
        # inline generator exactly.
        ctx: dict[str, Any] = {
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

        # The phase generators are unannotated until Branch 5 rewrites the
        # pipeline.
        yield from run_mcp_phase(ctx)  # type: ignore[no-untyped-call]
        yield from run_synthesis_phase(ctx)  # type: ignore[no-untyped-call]
        yield from run_followups(ctx)  # type: ignore[no-untyped-call]

    events = generate()
    return ClosingStreamingResponse(
        events,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
        # When the client disconnects -- the UI aborts the request on Stop and
        # when a new turn is sent mid-stream -- the stream stops and this task
        # still runs, whatever ASGI spec version the server reports (see
        # ClosingStreamingResponse). Closing the generator runs the pipeline's
        # cleanup, which closes the Gemini stream, at once rather than
        # whenever the garbage collector reaches it. close() does nothing on a
        # generator that already finished.
        background=BackgroundTask(events.close),
    )
