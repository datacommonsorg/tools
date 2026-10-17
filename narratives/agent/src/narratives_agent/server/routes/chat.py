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
from fastapi import APIRouter, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, ValidationError
from sse_starlette import ServerSentEvent
from starlette.background import BackgroundTask

from narratives_agent.server.responses import ClosingEventSourceResponse
from narratives_agent.workflows.chat_pipeline import EventName, run_turn
from narratives_agent.workflows.transcript import (
    MAX_QUERY_CHARS,
    IdempotencyKey,
    Transcript,
    TranscriptError,
    load_transcript,
)

router = APIRouter()

HEARTBEAT_INTERVAL_SECONDS = 15

# `TURN_CANCEL_GRACE_SECONDS` bounds how long a canceled turn may spend closing
# model streams and MCP connections before the response stops waiting for it.
TURN_CANCEL_GRACE_SECONDS = 5

# `MAX_REQUEST_BYTES` caps the request body, which is read in full before
# it is parsed. The largest window the agent signs is about 3 MiB: six turns
# of a 4,000-character query, a 32,000-character answer, and eight scopes of
# up to 51 DCID-and-name entries each, with every name in multi-byte UTF-8,
# plus an 8,000-character summary.
MAX_REQUEST_BYTES = 4 * 1024 * 1024


class ChatRequest(BaseModel):
    """The JSON body of a chat request.

    `turns` and `compacted_summary` are the signed transcript window from
    the previous turn's terminal event. They are kept as decoded JSON here
    and validated by `load_transcript`, so that a window that fails its
    schema or caps is rejected with HTTP 400 `transcript_invalid`, which
    the browser recovers from, rather than with HTTP 422.
    """

    message: str = Field(min_length=1, max_length=MAX_QUERY_CHARS)
    turns: list[Any] = Field(default_factory=list)
    compacted_summary: Any = None
    # The browser sends a new key with each chat request, and the server signs
    # it into the completed turn and copies it into the terminal event, where
    # the browser uses it to match the signed window to its turns. A future
    # server-side session store can also use it to detect a request that
    # repeats an earlier one, such as a retry after a dropped connection, and
    # return the stored answer instead of running the turn again.
    idempotency_key: IdempotencyKey = Field(
        default_factory=lambda: uuid.uuid4().hex
    )


def _heartbeat() -> ServerSentEvent:
    """Builds the keepalive frame, which carries no content."""
    return ServerSentEvent(event="heartbeat", data="{}")


async def _turn_events(
    transcript: Transcript,
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
            await run_turn(transcript, emit)
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


def _too_large() -> HTTPException:
    """Returns the error for a request body over `MAX_REQUEST_BYTES`."""
    return HTTPException(
        status_code=413,
        detail={
            "reason": "request_too_large",
            "message": f"The request exceeds {MAX_REQUEST_BYTES} bytes.",
        },
    )


async def _read_body(request: Request) -> bytes:
    """Reads the request body, stopping once it exceeds `MAX_REQUEST_BYTES`.

    A declared `Content-Length` over the cap is rejected before any of the
    body is read, and a body without one, such as a chunked upload, is
    rejected as soon as the bytes read pass the cap.

    Raises:
        HTTPException: The request body exceeds `MAX_REQUEST_BYTES` (HTTP 413).
    """
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_REQUEST_BYTES:
        raise _too_large()
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_REQUEST_BYTES:
            raise _too_large()
    return bytes(body)


@router.post("/chat/stream")
async def chat_stream(request: Request) -> ClosingEventSourceResponse:
    """Streams one chat turn as typed Server-Sent Events.

    The body is read under `MAX_REQUEST_BYTES` and then parsed as a
    `ChatRequest`, rather than declared as a parameter, because FastAPI
    reads a declared body in full before any route code can bound it.

    Request body:
    {
        "message": "user query",
        "turns": [...signed turns from the previous terminal event...],
        "compacted_summary": "summary of compacted turns, or null",
        "idempotency_key": "optional client-generated key"
    }

    Raises:
        HTTPException: The body exceeds `MAX_REQUEST_BYTES` (HTTP 413), or
            the transcript fails its schema or verification (HTTP 400 with
            reason `transcript_invalid`). Both are raised before the stream
            opens, so the browser receives a plain JSON error.
        RequestValidationError: The body is not JSON or the message or
            idempotency key is invalid, which FastAPI reports as HTTP 422.
    """
    raw = await _read_body(request)
    try:
        body = ChatRequest.model_validate_json(raw)
    except ValidationError as error:
        raise RequestValidationError(
            error.errors(include_url=False, include_context=False)
        ) from error
    try:
        transcript = load_transcript(body)
    except TranscriptError as error:
        raise HTTPException(
            status_code=400,
            detail={"reason": "transcript_invalid", "message": str(error)},
        ) from error
    events = _turn_events(transcript)

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
