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
1. `/chat/stream` sends the session event and then each phase's events, byte
   for byte, with the three streaming headers.
2. The request's message, history, and session id reach the pipeline, and an
   omitted history reaches it as an empty list.
3. Invalid request bodies, including a session id that could name a file
   outside the logs directory, are rejected with 422 before the pipeline
   runs, while a session id `SessionLogger` issued is accepted.
4. A client disconnect closes the pipeline generator before the response
   ends, under ASGI spec 2.3 and 2.4, without relying on the garbage
   collector.
"""

import asyncio
import gc
import json
import threading
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import ClientDisconnect
from starlette.types import Message

from narratives_agent.server.routes import chat
from narratives_agent.session_logger import SessionLogger

_HISTORY = [{"role": "user", "content": "What is the population of France?"}]


class _SessionLoggerStub:
    """Stands in for `SessionLogger`: writes nothing and fixes new ids."""

    def __init__(self, session_id: str | None = None) -> None:
        self.session_id = session_id or "session-new"


class _Pipeline:
    """Stub phase generators that record the context the route passes in."""

    def __init__(self) -> None:
        self.contexts: list[dict[str, Any]] = []

    def mcp_phase(self, ctx: dict[str, Any]) -> Iterator[str]:
        self.contexts.append(ctx)
        yield 'data: {"type": "mcp_start"}\n\n'

    def synthesis_phase(self, ctx: dict[str, Any]) -> Iterator[str]:
        yield 'data: {"type": "text", "content": "About 68 million."}\n\n'

    def followups(self, ctx: dict[str, Any]) -> Iterator[str]:
        yield 'data: {"type": "done"}\n\n'


@pytest.fixture
def pipeline(monkeypatch: pytest.MonkeyPatch) -> _Pipeline:
    """Replaces the session logger and the three phases with stubs."""
    stub = _Pipeline()
    monkeypatch.setattr(chat, "SessionLogger", _SessionLoggerStub)
    monkeypatch.setattr(chat, "run_mcp_phase", stub.mcp_phase)
    monkeypatch.setattr(chat, "run_synthesis_phase", stub.synthesis_phase)
    monkeypatch.setattr(chat, "run_followups", stub.followups)
    return stub


@pytest.fixture
def client() -> TestClient:
    """Returns a test client for an app that serves only `chat.router`."""
    app = FastAPI()
    app.include_router(chat.router, prefix="/agent")
    return TestClient(app)


def test_stream_sends_session_then_phase_events_byte_for_byte(
    pipeline: _Pipeline,
    client: TestClient,
) -> None:
    # Test: Wire format of `POST /agent/chat/stream`.
    # Situation: Each pipeline phase is stubbed to yield one fixed event, and
    #   a client posts a message with no session id.
    # Expectation: The body is the new session's event followed by the three
    #   phase events, byte for byte, sent as `text/event-stream` with
    #   `Cache-Control: no-cache`, `X-Accel-Buffering: no`, and
    #   `Connection: keep-alive`.
    response = client.post(
        "/agent/chat/stream",
        json={"message": "What is the population of France?"},
    )

    assert response.status_code == 200
    assert response.content == (
        b'data: {"session_id": "session-new"}\n\n'
        b'data: {"type": "mcp_start"}\n\n'
        b'data: {"type": "text", "content": "About 68 million."}\n\n'
        b'data: {"type": "done"}\n\n'
    )
    assert (
        response.headers["content-type"] == "text/event-stream; charset=utf-8"
    )
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["connection"] == "keep-alive"


def test_request_fields_reach_the_pipeline(
    pipeline: _Pipeline,
    client: TestClient,
) -> None:
    # Test: Mapping of the request body onto the pipeline context.
    # Situation: A follow-up request carries a message, a one-turn history,
    #   and the session id of the earlier turn.
    # Expectation: The pipeline receives the message and history unchanged,
    #   and the stream resumes the given session id.
    response = client.post(
        "/agent/chat/stream",
        json={
            "message": "And Spain?",
            "history": _HISTORY,
            "session_id": "session-earlier",
        },
    )

    assert response.status_code == 200
    assert response.content.startswith(
        b'data: {"session_id": "session-earlier"}\n\n'
    )
    [ctx] = pipeline.contexts
    assert ctx["user_message"] == "And Spain?"
    assert ctx["history"] == _HISTORY
    assert ctx["session_logger"].session_id == "session-earlier"


def test_omitted_history_reaches_the_pipeline_empty(
    pipeline: _Pipeline,
    client: TestClient,
) -> None:
    # Test: Default for a request body without `history`.
    # Situation: A client posts only a message.
    # Expectation: The pipeline receives an empty history.
    response = client.post("/agent/chat/stream", json={"message": "Hello"})

    assert response.status_code == 200
    [ctx] = pipeline.contexts
    assert ctx["history"] == []


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
        pytest.param(
            {"json": {"message": "Hello", "session_id": "../../escaped"}},
            id="session-id-path-traversal",
        ),
        pytest.param(
            {"json": {"message": "Hello", "session_id": "logs/other"}},
            id="session-id-separator",
        ),
        pytest.param(
            {"json": {"message": "Hello", "session_id": ""}},
            id="session-id-empty",
        ),
        pytest.param(
            {"json": {"message": "Hello", "session_id": "a" * 65}},
            id="session-id-too-long",
        ),
    ],
)
def test_invalid_request_body_returns_422(
    request_kwargs: dict[str, Any],
    pipeline: _Pipeline,
    client: TestClient,
) -> None:
    # Test: Validation of the chat request body.
    # Situation: A client posts a body with no message, an empty message, a
    #   null history, a history that is not a list, bytes that are not JSON,
    #   or a session id that is empty, longer than 64 characters, or holds a
    #   character other than a letter, digit, or hyphen, such as a path
    #   separator that would place the session log outside `logs/`.
    # Expectation: The route answers 422, and the pipeline never runs.
    response = client.post("/agent/chat/stream", **request_kwargs)

    assert response.status_code == 422
    assert pipeline.contexts == []


def test_a_session_id_the_server_issued_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
    pipeline: _Pipeline,
    client: TestClient,
) -> None:
    # Test: The contract between the session ids the server issues and the
    #   ids the route accepts.
    # Situation: A real `SessionLogger`, with file logging off, issues a new
    #   session id, and a follow-up request sends it back, as the UI does.
    # Expectation: The route accepts the id and resumes that session, rather
    #   than rejecting every follow-up turn with 422.
    monkeypatch.setenv("SESSION_LOG_TO_FILE", "false")
    issued = SessionLogger().session_id

    response = client.post(
        "/agent/chat/stream",
        json={"message": "And Spain?", "session_id": issued},
    )

    assert response.status_code == 200
    [ctx] = pipeline.contexts
    assert ctx["session_logger"].session_id == issued


@pytest.mark.parametrize("spec_version", ["2.3", "2.4"])
def test_client_disconnect_closes_the_pipeline_before_the_response_ends(
    spec_version: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Cleanup of the pipeline when the browser disconnects mid-stream.
    # Situation: The MCP phase yields events without end and records when
    #   its `finally` block runs. The app is driven over ASGI. Under spec
    #   2.3, which Uvicorn reports, `receive` answers `http.disconnect` once
    #   the first phase event has been sent. Under spec 2.4, `send` raises
    #   `OSError` on that event instead, as a server does once the socket is
    #   gone. The garbage collector is disabled, so collection cannot close
    #   the generator.
    # Expectation: The phase's `finally` block has run by the time the
    #   application returns.
    closed = threading.Event()

    def endless_mcp_phase(ctx: dict[str, Any]) -> Iterator[str]:
        try:
            while True:
                yield 'data: {"type": "thought"}\n\n'
        finally:
            closed.set()

    monkeypatch.setattr(chat, "SessionLogger", _SessionLoggerStub)
    monkeypatch.setattr(chat, "run_mcp_phase", endless_mcp_phase)
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
            # The session event comes first; waiting for a phase event
            # guarantees the phase generator has started, so it has a
            # `finally` block to run.
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
        # Read before the event loop runs again, so loop shutdown cannot
        # close the generator first.
        closed_on_return.append(closed.is_set())

    closed_on_return: list[bool] = []
    gc.disable()
    try:
        asyncio.run(drive())
    finally:
        gc.enable()
    assert closed_on_return == [True]
