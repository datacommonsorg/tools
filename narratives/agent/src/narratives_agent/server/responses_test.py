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
"""Tests for `server.responses`.

Verifies that `ClosingStreamingResponse` runs its background task exactly
once when the stream completes, and when the client disconnects under ASGI
spec 2.3 or 2.4.
"""

import asyncio
from collections.abc import AsyncIterator

import pytest
from starlette.background import BackgroundTask
from starlette.requests import ClientDisconnect
from starlette.types import Message, Scope

from narratives_agent.server.responses import ClosingStreamingResponse


def _scope(spec_version: str) -> Scope:
    """Returns a minimal HTTP scope that reports `spec_version`."""
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": spec_version},
        "method": "GET",
        "path": "/",
        "headers": [],
    }


async def _chunks() -> AsyncIterator[bytes]:
    yield b"first"
    yield b"second"


def test_background_runs_once_when_the_stream_completes() -> None:
    # Test: Background task on a stream that runs to completion.
    # Situation: The client stays connected while a two-chunk body is sent.
    # Expectation: Every chunk is sent and the task runs exactly once.
    runs: list[None] = []
    sent: list[bytes] = []
    response = ClosingStreamingResponse(
        _chunks(), background=BackgroundTask(lambda: runs.append(None))
    )

    async def receive() -> Message:
        await asyncio.Event().wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body":
            sent.append(message["body"])

    asyncio.run(response(_scope("2.4"), receive, send))

    assert sent == [b"first", b"second", b""]
    assert runs == [None]


@pytest.mark.parametrize("spec_version", ["2.3", "2.4"])
def test_background_runs_once_when_the_client_disconnects(
    spec_version: str,
) -> None:
    # Test: Background task on a stream the client cuts off.
    # Situation: Under spec 2.3, `receive` answers `http.disconnect` once the
    #   first chunk is sent and `send` then blocks. Under spec 2.4, `send`
    #   raises `OSError` on the first chunk, as Uvicorn's does once the
    #   socket is gone.
    # Expectation: The task runs exactly once, including under spec 2.4,
    #   where the disconnect leaves the response as `ClientDisconnect`.
    runs: list[None] = []
    response = ClosingStreamingResponse(
        _chunks(), background=BackgroundTask(lambda: runs.append(None))
    )

    async def drive() -> None:
        body_sent = asyncio.Event()

        async def receive() -> Message:
            await body_sent.wait()
            return {"type": "http.disconnect"}

        async def send(message: Message) -> None:
            if message["type"] != "http.response.body":
                return
            if spec_version == "2.4":
                raise OSError("connection reset")
            body_sent.set()
            await asyncio.Event().wait()

        try:
            await response(_scope(spec_version), receive, send)
        except ClientDisconnect:
            assert spec_version == "2.4"

    asyncio.run(drive())

    assert runs == [None]
