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
"""Streams a chat turn to the browser as typed Server-Sent Events.

Each event carries an `event:` name (`status`, `thought`, `content`,
`terminal`, `follow_ups`), a JSON `data:` payload, and an `id:` that counts
up from 1 within the stream. An `event: heartbeat` frame, without an `id:`,
is also sent every `HEARTBEAT_INTERVAL_SECONDS`, so that proxies do not drop
the connection while the turn waits on slow upstream calls.
"""

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import anyio
from fastapi import APIRouter
from pydantic import BaseModel, Field
from sse_starlette import ServerSentEvent
from starlette.background import BackgroundTask

from narratives_agent.server.responses import ClosingEventSourceResponse
from narratives_agent.workflows.chat_pipeline import EventName, run_turn

router = APIRouter()

HEARTBEAT_INTERVAL_SECONDS = 15

# `TURN_CANCEL_GRACE_SECONDS` bounds how long a canceled turn may spend closing
# model streams and MCP connections before the response stops waiting for it.
TURN_CANCEL_GRACE_SECONDS = 5

# `_MAX_IDEMPOTENCY_KEY_LENGTH` bounds the client-supplied key that is echoed
# in the terminal event.
_MAX_IDEMPOTENCY_KEY_LENGTH = 128


class ChatRequest(BaseModel):
    """The JSON body of a chat request."""

    message: str = Field(min_length=1)
    history: list[dict[str, Any]] = Field(default_factory=list)
    # The browser sends a new key with each chat request, and the server copies
    # it unchanged into the terminal event. The server does not otherwise use
    # the key yet. Its purpose is to let a future server-side session store
    # detect a request that repeats an earlier one, such as a retry after a
    # dropped connection, and return the stored answer instead of running the
    # turn again.
    idempotency_key: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        min_length=1,
        max_length=_MAX_IDEMPOTENCY_KEY_LENGTH,
    )


def _heartbeat() -> ServerSentEvent:
    """Builds the keepalive frame, which carries no content."""
    return ServerSentEvent(event="heartbeat", data="{}")


async def _turn_events(
    request: ChatRequest,
) -> AsyncGenerator[ServerSentEvent]:
    """Runs the turn in a task and yields its events as they arrive.

    The turn runs in its own task because the MCP phase reports model
    thoughts through a callback while it awaits the model, so its events
    cannot be yielded from the awaiting code itself. They pass through an
    `asyncio.Queue` that this generator drains. When the generator stops
    early because the client disconnected or the response was closed, the
    turn task is canceled and awaited for at most
    `TURN_CANCEL_GRACE_SECONDS`, which cancels its in-flight model and tool
    calls and records the turn as canceled.
    """
    queue: asyncio.Queue[tuple[EventName, dict[str, Any]] | None] = (
        asyncio.Queue()
    )

    def emit(event: EventName, data: dict[str, Any]) -> None:
        queue.put_nowait((event, data))

    async def produce() -> None:
        try:
            await run_turn(
                request.message, request.history, request.idempotency_key, emit
            )
        finally:
            queue.put_nowait(None)

    task = asyncio.create_task(produce(), name="chat-turn")
    try:
        event_id = 0
        while (item := await queue.get()) is not None:
            event_id += 1
            event, data = item
            yield ServerSentEvent(
                data=json.dumps(data), event=event, id=str(event_id)
            )
    finally:
        task.cancel()
        # The wait is shielded because sse-starlette's AnyIO cancel scope
        # cancels this generator again on every event-loop iteration, and
        # awaiting the task directly would forward each of those to it,
        # interrupting the cleanup the first cancellation started. It is
        # bounded so that a turn stuck in cleanup cannot hold the response.
        with anyio.CancelScope(shield=True):
            await asyncio.wait({task}, timeout=TURN_CANCEL_GRACE_SECONDS)
        if task.done() and not task.cancelled():
            # Re-raise any failure other than cancellation, just as awaiting
            # the task directly would.
            task.result()


@router.post("/chat/stream")
async def chat_stream(body: ChatRequest) -> ClosingEventSourceResponse:
    """Streams one chat turn as typed Server-Sent Events.

    Request body:
    {
        "message": "user query",
        "history": [...optional conversation history...],
        "idempotency_key": "optional client-generated key"
    }
    """
    events = _turn_events(body)

    async def close_events() -> None:
        # `events.aclose` itself cannot be the task: it is a builtin method,
        # not a coroutine function, so `BackgroundTask` would call it in a
        # worker thread and drop the coroutine it returns unawaited.
        await events.aclose()

    return ClosingEventSourceResponse(
        events,
        ping=HEARTBEAT_INTERVAL_SECONDS,
        ping_message_factory=_heartbeat,
        # When the client disconnects -- the UI aborts the request on Stop and
        # when a new turn is sent mid-stream -- the stream stops and this task
        # still runs, whatever ASGI spec version the server reports (see
        # ClosingEventSourceResponse). Closing the generator cancels the turn
        # task at once rather than whenever the garbage collector reaches
        # it. aclose() does nothing on a generator that already finished.
        background=BackgroundTask(close_events),
    )
