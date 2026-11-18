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
"""Tests for `SecurityHeadersMiddleware`, driven directly over ASGI.

Verifies that the middleware:
1. Adds every header in `SECURITY_HEADERS` to an HTTP response.
2. Keeps a header the response already carries, and adds no
   `Content-Security-Policy` of its own.
3. Forwards each body chunk of a streamed response as it is sent.
4. Passes scopes other than HTTP through unchanged.
"""

import asyncio

from starlette.types import Message, Receive, Scope, Send

from narratives_agent.server.security_headers import (
    SECURITY_HEADERS,
    SecurityHeadersMiddleware,
)

# Each wait in the streaming test lasts at most this long, so that a
# middleware that buffers the body fails the test instead of hanging it.
_STREAM_TIMEOUT_SECONDS = 1

_HTTP_SCOPE: Scope = {"type": "http", "method": "GET", "path": "/"}


async def _receive_nothing() -> Message:
    """Returns an empty request body."""
    return {"type": "http.request", "body": b""}


def _send_response_through_middleware(
    response_headers: list[tuple[bytes, bytes]],
) -> list[tuple[str, str]]:
    """Returns the headers of a 200 response sent through the middleware.

    Args:
        response_headers: The raw headers the wrapped application sends.

    Returns:
        The headers the client receives, in order, as lower-case name and
        value pairs.
    """
    sent: list[Message] = []

    async def send_ok_response(
        scope: Scope, receive: Receive, send: Send
    ) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": response_headers,
            }
        )
        await send({"type": "http.response.body", "body": b"ok"})

    async def record(message: Message) -> None:
        sent.append(message)

    asyncio.run(
        SecurityHeadersMiddleware(send_ok_response)(
            _HTTP_SCOPE, _receive_nothing, record
        )
    )
    return [
        (name.decode("latin-1"), value.decode("latin-1"))
        for name, value in sent[0]["headers"]
    ]


def test_every_security_header_is_added() -> None:
    # Test: Headers added to a response that sets none of them.
    # Situation: The wrapped application sends a response with only a
    #   `Content-Type` header.
    # Expectation: The client receives every header in `SECURITY_HEADERS`
    #   with its value, and the `Content-Type` header unchanged.
    headers = dict(
        _send_response_through_middleware([(b"content-type", b"text/plain")])
    )

    assert headers["content-type"] == "text/plain"
    for name, value in SECURITY_HEADERS:
        assert headers[name.lower()] == value


def test_an_existing_header_is_not_overwritten() -> None:
    # Test: A response that already sets one of the headers.
    # Situation: The wrapped application sends `X-Frame-Options: DENY` and
    #   `Content-Security-Policy: sandbox`.
    # Expectation: Both headers keep their values and appear once, and the
    #   middleware still adds the other security headers.
    sent_headers = [
        (b"x-frame-options", b"DENY"),
        (b"content-security-policy", b"sandbox"),
    ]

    received = _send_response_through_middleware(sent_headers)

    names = [name for name, _ in received]
    assert names.count("x-frame-options") == 1
    assert names.count("content-security-policy") == 1
    headers = dict(received)
    assert headers["x-frame-options"] == "DENY"
    assert headers["content-security-policy"] == "sandbox"
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert headers["cross-origin-opener-policy"] == "same-origin-allow-popups"


def test_no_content_security_policy_is_added() -> None:
    # Test: A response without a `Content-Security-Policy`.
    # Situation: The wrapped application sends a response with no headers.
    # Expectation: The client receives no `Content-Security-Policy`, because
    #   each route sets its own policy.
    headers = dict(_send_response_through_middleware([]))

    assert "content-security-policy" not in headers


def test_streamed_body_chunks_are_forwarded_as_they_are_sent() -> None:
    # Test: Streaming through the middleware.
    # Situation: The wrapped application sends the first body chunk with
    #   `more_body` set, then waits until the client has received that chunk
    #   before it sends the last one.
    # Expectation: The first chunk reaches the client before the last chunk
    #   is sent, and the client receives both chunks in order as separate
    #   messages.
    first_chunk_received = asyncio.Event()
    received: list[Message] = []
    delivery_before_last_chunk: list[bool] = []

    async def send_two_chunks(
        scope: Scope, receive: Receive, send: Send
    ) -> None:
        await send({"type": "http.response.start", "status": 200})
        await send(
            {"type": "http.response.body", "body": b"one", "more_body": True}
        )
        try:
            async with asyncio.timeout(_STREAM_TIMEOUT_SECONDS):
                await first_chunk_received.wait()
        except TimeoutError:
            delivery_before_last_chunk.append(False)
        else:
            delivery_before_last_chunk.append(True)
        await send({"type": "http.response.body", "body": b"two"})

    async def receive_message(message: Message) -> None:
        received.append(message)
        if message.get("body") == b"one":
            first_chunk_received.set()

    asyncio.run(
        SecurityHeadersMiddleware(send_two_chunks)(
            _HTTP_SCOPE, _receive_nothing, receive_message
        )
    )

    assert delivery_before_last_chunk == [True]
    assert [message.get("body") for message in received] == [
        None,
        b"one",
        b"two",
    ]


def test_a_lifespan_scope_passes_through_unchanged() -> None:
    # Test: A scope other than HTTP.
    # Situation: The middleware receives a `lifespan` scope.
    # Expectation: The wrapped application receives the same scope and the
    #   server's own `send`, so lifespan messages are not edited.
    calls: list[tuple[Scope, Send]] = []

    async def record_scope(scope: Scope, receive: Receive, send: Send) -> None:
        calls.append((scope, send))

    async def send_to_server(message: Message) -> None:
        pass

    lifespan_scope: Scope = {"type": "lifespan"}
    asyncio.run(
        SecurityHeadersMiddleware(record_scope)(
            lifespan_scope, _receive_nothing, send_to_server
        )
    )

    assert calls == [(lifespan_scope, send_to_server)]
