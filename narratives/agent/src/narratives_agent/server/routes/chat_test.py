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
"""Tests for the chat streaming route in `chat`.

Verifies that:
1. `/chat/stream` sends each event the turn emits as a typed SSE frame with
   an `id:` counting up from 1, byte for byte, with the streaming headers.
2. The request's message, history, and idempotency key reach the turn; an
   omitted history reaches it as an empty list and an omitted key as a
   server-generated one.
3. Invalid request bodies are rejected with 422 before the turn runs.
4. A heartbeat frame is sent while the turn is idle.
5. A client disconnect cancels the turn before the response ends, under ASGI
   spec 2.3 and 2.4, without relying on the garbage collector.
"""

import asyncio
import gc
import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sse_starlette import ServerSentEvent
from starlette.types import Message

from narratives_agent.server.routes import chat
from narratives_agent.workflows.chat_pipeline import Emit, EventName

_HISTORY = [{"role": "user", "content": "What is the population of France?"}]
_IDEMPOTENCY_KEY = "test-idempotency-key"
# `_CLEANUP_STEPS` sets the number of event-loop iterations a canceled stub
# turn spends in cleanup. Using more than one iteration verifies that a second
# cancellation does not interrupt cleanup mid-way.
_CLEANUP_STEPS = 3
_EVENTS: list[tuple[EventName, dict[str, Any]]] = [
    ("status", {"phase": "mcp"}),
    ("content", {"text": "About 68 million."}),
    ("terminal", {"state": "complete"}),
]


class _Turn:
    """Stubs `run_turn` by recording its inputs and emitting fixed events."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[dict[str, Any]], str]] = []

    async def __call__(
        self,
        user_message: str,
        history: list[dict[str, Any]],
        idempotency_key: str,
        emit: Emit,
    ) -> None:
        self.calls.append((user_message, history, idempotency_key))
        for event, data in _EVENTS:
            emit(event, data)


@pytest.fixture
def turn(monkeypatch: pytest.MonkeyPatch) -> _Turn:
    """Replaces the chat pipeline with a stub."""
    stub = _Turn()
    monkeypatch.setattr(chat, "run_turn", stub)
    return stub


@pytest.fixture
def client() -> TestClient:
    """Returns a test client for an app that serves only `chat.router`."""
    app = FastAPI()
    app.include_router(chat.router, prefix="/agent")
    return TestClient(app)


@pytest.mark.usefixtures("turn")
def test_stream_sends_each_event_as_a_typed_frame_byte_for_byte(
    client: TestClient,
) -> None:
    # Test: Wire format of `POST /agent/chat/stream`.
    # Situation: The turn is stubbed to emit three fixed events, and a
    #   client posts a message.
    # Expectation: The body is one frame per event, in order, byte for byte,
    #   each with an `id:` counting up from 1, its `event:` name, and its
    #   JSON `data:`; it is sent as `text/event-stream` with
    #   `Cache-Control: no-store` and `X-Accel-Buffering: no`.
    response = client.post(
        "/agent/chat/stream",
        json={"message": "What is the population of France?"},
    )

    assert response.status_code == 200
    assert response.content == (
        b'id: 1\r\nevent: status\r\ndata: {"phase": "mcp"}\r\n\r\n'
        b"id: 2\r\nevent: content\r\n"
        b'data: {"text": "About 68 million."}\r\n\r\n'
        b'id: 3\r\nevent: terminal\r\ndata: {"state": "complete"}\r\n\r\n'
    )
    assert (
        response.headers["content-type"] == "text/event-stream; charset=utf-8"
    )
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-accel-buffering"] == "no"


def test_request_fields_reach_the_turn(
    turn: _Turn,
    client: TestClient,
) -> None:
    # Test: Mapping of the request body onto the turn's inputs.
    # Situation: A follow-up request carries a message, a one-turn history,
    #   and an idempotency key.
    # Expectation: The turn receives all three unchanged.
    response = client.post(
        "/agent/chat/stream",
        json={
            "message": "And Spain?",
            "history": _HISTORY,
            "idempotency_key": _IDEMPOTENCY_KEY,
        },
    )

    assert response.status_code == 200
    assert turn.calls == [("And Spain?", _HISTORY, _IDEMPOTENCY_KEY)]


def test_omitted_optional_fields_reach_the_turn_defaulted(
    turn: _Turn,
    client: TestClient,
) -> None:
    # Test: Defaults for a request body with only a message.
    # Situation: A client posts only a message, twice.
    # Expectation: The turn receives an empty history and a server-generated
    #   idempotency key that differs between the two requests.
    client.post("/agent/chat/stream", json={"message": "Hello"})
    response = client.post("/agent/chat/stream", json={"message": "Hello"})

    assert response.status_code == 200
    (_, first_history, first_key), (_, _, second_key) = turn.calls
    assert first_history == []
    assert first_key
    assert first_key != second_key


@pytest.mark.parametrize(
    "request_kwargs",
    [
        pytest.param({"json": {"history": []}}, id="missing-message"),
        pytest.param({"json": {"message": ""}}, id="empty-message"),
        pytest.param(
            {"json": {"message": "Hello", "history": None}},
            id="null-history",
        ),
        pytest.param(
            {"json": {"message": "Hello", "history": "Hello"}},
            id="history-not-a-list",
        ),
        pytest.param(
            {"json": {"message": "Hello", "idempotency_key": ""}},
            id="empty-idempotency-key",
        ),
        pytest.param(
            {
                "json": {
                    "message": "Hello",
                    "idempotency_key": "k"
                    * (chat._MAX_IDEMPOTENCY_KEY_LENGTH + 1),
                }
            },
            id="overlong-idempotency-key",
        ),
        pytest.param(
            {
                "content": b"not json",
                "headers": {"Content-Type": "application/json"},
            },
            id="non-json-body",
        ),
    ],
)
def test_invalid_request_body_returns_422(
    request_kwargs: dict[str, Any],
    turn: _Turn,
    client: TestClient,
) -> None:
    # Test: Validation of the chat request body.
    # Situation: A client posts a body with no message, an empty message, a
    #   null history, a history that is not a list, an empty or overlong
    #   idempotency key, or bytes that are not JSON.
    # Expectation: The route answers 422, and the turn never runs.
    response = client.post("/agent/chat/stream", **request_kwargs)

    assert response.status_code == 422
    assert turn.calls == []


@pytest.mark.parametrize("disconnect", ["message", "send-error"])
def test_client_disconnect_cancels_the_turn_before_the_response_ends(
    disconnect: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Cancellation of the turn when the browser disconnects mid-stream.
    # Situation: The turn emits one event, then awaits an event that never
    #   fires, and records whether it was canceled. The app is driven over
    #   ASGI. The disconnect surfaces either as `receive` answering
    #   `http.disconnect` once the event has been sent, or as `send` raising
    #   `OSError` on that event, as a server does once the socket is gone.
    #   The garbage collector is disabled, so collection cannot close the
    #   generator. The turn's cancellation handler yields to the event loop
    #   across multiple steps, as closing a model stream does, before it
    #   finishes.
    # Expectation: The turn has been canceled, and its cleanup has run to
    #   completion, by the time the application returns.
    canceled = asyncio.Event()
    cleaned_up = asyncio.Event()

    async def blocked_turn(
        user_message: str,
        history: list[dict[str, Any]],
        idempotency_key: str,
        emit: Emit,
    ) -> None:
        emit("thought", {"thought": "..."})
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            canceled.set()
            for _ in range(_CLEANUP_STEPS):
                await asyncio.sleep(0)
            cleaned_up.set()
            raise

    monkeypatch.setattr(chat, "run_turn", blocked_turn)
    app = FastAPI()
    app.include_router(chat.router, prefix="/agent")
    body = json.dumps({"message": "Hello"}).encode()
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/agent/chat/stream",
        "raw_path": b"/agent/chat/stream",
        "root_path": "",
        "query_string": b"",
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 5001),
        "state": {},
    }

    async def drive() -> None:
        event_sent = asyncio.Event()
        request_delivered = False

        async def receive() -> Message:
            nonlocal request_delivered
            if not request_delivered:
                request_delivered = True
                return {"type": "http.request", "body": body}
            await event_sent.wait()
            return {"type": "http.disconnect"}

        async def send(message: Message) -> None:
            # Waiting for an event guarantees the turn task has started.
            if message["type"] == "http.response.body" and (
                b"thought" in message.get("body", b"")
            ):
                if disconnect == "send-error":
                    raise OSError("connection reset")
                event_sent.set()

        try:
            await app(scope, receive, send)
        except OSError:
            # The send error leaves the application, and the server
            # discards it.
            assert disconnect == "send-error"
        # Record the state before the event loop runs again, so loop
        # shutdown cannot cancel the turn first.
        canceled_on_return.append((canceled.is_set(), cleaned_up.is_set()))

    canceled_on_return: list[tuple[bool, bool]] = []
    gc.disable()
    try:
        asyncio.run(drive())
    finally:
        gc.enable()
    assert canceled_on_return == [(True, True)]


def test_heartbeat_frames_are_sent_while_the_turn_is_idle(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    # Test: Keepalive frames during a slow upstream wait.
    # Situation: The heartbeat interval is shortened to 1 ms, and the turn
    #   waits between its two events until a heartbeat has been built.
    # Expectation: The body carries an `event: heartbeat` frame with an
    #   empty JSON object and no `id:`, and the turn's two events keep the
    #   ids 1 and 2, so heartbeats do not advance the event sequence.
    heartbeat_built = asyncio.Event()

    def heartbeat() -> ServerSentEvent:
        heartbeat_built.set()
        return original_heartbeat()

    async def slow_turn(
        user_message: str,
        history: list[dict[str, Any]],
        idempotency_key: str,
        emit: Emit,
    ) -> None:
        emit("status", {"phase": "mcp"})
        async with asyncio.timeout(1):
            await heartbeat_built.wait()
        emit("terminal", {"state": "complete"})

    original_heartbeat = chat._heartbeat
    monkeypatch.setattr(chat, "_heartbeat", heartbeat)
    monkeypatch.setattr(chat, "run_turn", slow_turn)
    monkeypatch.setattr(chat, "HEARTBEAT_INTERVAL_SECONDS", 0.001)

    response = client.post("/agent/chat/stream", json={"message": "Hello"})

    frames = [f for f in response.content.split(b"\r\n\r\n") if f]
    assert b"event: heartbeat\r\ndata: {}" in frames
    assert [f.split(b"\r\n")[0] for f in frames if b"heartbeat" not in f] == [
        b"id: 1",
        b"id: 2",
    ]
