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
1. `/chat/stream` sends each payload the turn emits as an SSE frame, byte
   for byte, with the three streaming headers.
2. The request's message and history reach the turn, and an omitted history
   reaches it as an empty list.
3. Invalid request bodies are rejected with 422 before the turn runs.
4. A client disconnect cancels the turn before the response ends, under ASGI
   spec 2.3 and 2.4, without relying on the garbage collector.
"""

import asyncio
import gc
import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import ClientDisconnect
from starlette.types import Message

from narratives_agent.server.routes import chat
from narratives_agent.workflows.chat_pipeline import Emit

_HISTORY = [{"role": "user", "content": "What is the population of France?"}]
_PAYLOADS: list[dict[str, Any]] = [
    {"status": "mcp_start"},
    {"text": "About 68 million."},
    {"done": True},
]


class _Turn:
    """Stubs `run_turn` by recording its inputs and emitting fixed payloads."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[dict[str, Any]]]] = []

    async def __call__(
        self, user_message: str, history: list[dict[str, Any]], emit: Emit
    ) -> None:
        self.calls.append((user_message, history))
        for payload in _PAYLOADS:
            emit(payload)


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


def test_stream_sends_each_payload_as_a_frame_byte_for_byte(
    turn: _Turn,
    client: TestClient,
) -> None:
    # Test: Wire format of `POST /agent/chat/stream`.
    # Situation: The turn is stubbed to emit three fixed payloads, and a
    #   client posts a message.
    # Expectation: The body is one `data:` frame per payload, in order, byte
    #   for byte, sent as `text/event-stream` with `Cache-Control: no-cache`,
    #   `X-Accel-Buffering: no`, and `Connection: keep-alive`.
    response = client.post(
        "/agent/chat/stream",
        json={"message": "What is the population of France?"},
    )

    assert response.status_code == 200
    assert response.content == (
        b'data: {"status": "mcp_start"}\n\n'
        b'data: {"text": "About 68 million."}\n\n'
        b'data: {"done": true}\n\n'
    )
    assert (
        response.headers["content-type"] == "text/event-stream; charset=utf-8"
    )
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["connection"] == "keep-alive"


def test_request_fields_reach_the_turn(
    turn: _Turn,
    client: TestClient,
) -> None:
    # Test: Mapping of the request body onto the turn's inputs.
    # Situation: A follow-up request carries a message and a one-turn
    #   history.
    # Expectation: The turn receives the message and history unchanged.
    response = client.post(
        "/agent/chat/stream",
        json={"message": "And Spain?", "history": _HISTORY},
    )

    assert response.status_code == 200
    assert turn.calls == [("And Spain?", _HISTORY)]


def test_omitted_history_reaches_the_turn_empty(
    turn: _Turn,
    client: TestClient,
) -> None:
    # Test: Default for a request body without `history`.
    # Situation: A client posts only a message.
    # Expectation: The turn receives an empty history.
    response = client.post("/agent/chat/stream", json={"message": "Hello"})

    assert response.status_code == 200
    assert turn.calls == [("Hello", [])]


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
    #   null history, a history that is not a list, or bytes that are not
    #   JSON.
    # Expectation: The route answers 422, and the turn never runs.
    response = client.post("/agent/chat/stream", **request_kwargs)

    assert response.status_code == 422
    assert turn.calls == []


@pytest.mark.parametrize("spec_version", ["2.3", "2.4"])
def test_client_disconnect_cancels_the_turn_before_the_response_ends(
    spec_version: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Cancellation of the turn when the browser disconnects mid-stream.
    # Situation: The turn emits one payload, then awaits an event that never
    #   fires, and records whether it was canceled. The app is
    #   driven over ASGI. Under spec 2.3, which Uvicorn reports, `receive`
    #   answers `http.disconnect` once the payload has been sent. Under spec
    #   2.4, `send` raises `OSError` on that payload instead, as a server
    #   does once the socket is gone. The garbage collector is disabled, so
    #   collection cannot close the generator.
    # Expectation: The turn has been canceled by the time the application
    #   returns.
    canceled = asyncio.Event()

    async def blocked_turn(
        user_message: str, history: list[dict[str, Any]], emit: Emit
    ) -> None:
        emit({"thought": "..."})
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            canceled.set()
            raise

    monkeypatch.setattr(chat, "run_turn", blocked_turn)
    app = FastAPI()
    app.include_router(chat.router, prefix="/agent")
    body = json.dumps({"message": "Hello"}).encode()
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": spec_version},
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
        phase_chunk_sent = asyncio.Event()
        request_delivered = False

        async def receive() -> Message:
            nonlocal request_delivered
            if not request_delivered:
                request_delivered = True
                return {"type": "http.request", "body": body}
            await phase_chunk_sent.wait()
            return {"type": "http.disconnect"}

        async def send(message: Message) -> None:
            # Waiting for a payload guarantees the turn task has started.
            if message["type"] == "http.response.body" and (
                b"thought" in message.get("body", b"")
            ):
                if spec_version == "2.4":
                    raise OSError("connection reset")
                phase_chunk_sent.set()

        try:
            await app(scope, receive, send)
        except ClientDisconnect:
            # Under spec 2.4 the disconnect leaves the application as this
            # error, which the server discards.
            assert spec_version == "2.4"
        # Record the state before the event loop runs again, so loop
        # shutdown cannot cancel the turn first.
        canceled_on_return.append(canceled.is_set())

    canceled_on_return: list[bool] = []
    gc.disable()
    try:
        asyncio.run(drive())
    finally:
        gc.enable()
    assert canceled_on_return == [True]
