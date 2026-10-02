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

import asyncio
import contextlib
import json
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from narratives_agent.server.responses import ClosingStreamingResponse
from narratives_agent.workflows.chat_pipeline import run_turn

router = APIRouter()


class ChatRequest(BaseModel):
    """The JSON body of a chat request."""

    message: str = Field(min_length=1)
    history: list[dict[str, Any]] = Field(default_factory=list)


async def _turn_events(
    user_message: str, history: list[dict[str, Any]]
) -> AsyncGenerator[str]:
    """Runs the turn in a task and yields its payloads as SSE frames.

    The turn runs in its own task because the MCP phase reports model
    thoughts through a callback while it awaits the model, so its payloads
    cannot be yielded from the awaiting code itself. They pass through an
    `asyncio.Queue` that this generator drains as they arrive. When the
    generator stops early because the client disconnected or the response
    was closed, the turn task is canceled and awaited, which cancels its
    in-flight model and tool calls and records the turn as canceled.
    """
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def produce() -> None:
        try:
            await run_turn(user_message, history, queue.put_nowait)
        finally:
            queue.put_nowait(None)

    task = asyncio.create_task(produce(), name="chat-turn")
    try:
        while (payload := await queue.get()) is not None:
            yield f"data: {json.dumps(payload)}\n\n"
    finally:
        if not task.done():
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


@router.post("/chat/stream")
async def chat_stream(body: ChatRequest) -> ClosingStreamingResponse:
    """Streams the full chat workflow as Server-Sent Events.

    Phases:
    1. MCP Tools - Execute data queries (send tool call details)
    2. Synthesis - Stream final response with chart config

    Request body:
    {
        "message": "user query",
        "history": [...optional conversation history...]
    }

    Response: Server-Sent Events stream
    """
    events = _turn_events(body.message, body.history)

    async def close_events() -> None:
        # `events.aclose` itself cannot be the task: it is a builtin method,
        # not a coroutine function, so `BackgroundTask` would call it in a
        # worker thread and drop the coroutine it returns unawaited.
        await events.aclose()

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
        # ClosingStreamingResponse). Closing the generator cancels the turn
        # task at once rather than whenever the garbage collector reaches
        # it. aclose() does nothing on a generator that already finished.
        background=BackgroundTask(close_events),
    )
