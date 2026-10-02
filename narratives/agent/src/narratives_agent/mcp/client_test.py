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
"""Tests for the MCP client in `narratives_agent.mcp.client`.

Every test drives the real `mcp.ClientSession` and `streamable_http_client`
against `_FakeMcpServer`, an in-memory MCP Streamable HTTP server installed
through `httpx2.MockTransport`, so no network socket is opened. The tests
cover:
1. Session establishment, reuse, and retry-once recovery when the server
   rejects a session with a JSON-RPC error or HTTP 404.
2. Isolation of the session across asyncio tasks and OS threads, and its
   propagation out of the blocking entry points.
3. Tool-list caching, forced refresh, stale fallback, and the non-blocking
   `cached_tools` read.
4. Tool calls: argument normalization, credentials, result unpacking, error
   reporting, and session logging.
5. Endpoint URL normalization and resolution.
"""

import asyncio
import json
import logging
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx2
import pytest
from mcp import MCPError, types

from narratives_agent.mcp import client
from narratives_agent.settings import Settings

_URL = "http://mcp.test/mcp"
_PROTOCOL_VERSION = "2025-06-18"
_TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_observations",
        "description": "Fetches observations.",
        "inputSchema": {"type": "object", "properties": {}},
    }
]
_REFRESH_JOIN_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class _Request:
    """Records a single HTTP request received by `_FakeMcpServer`."""

    http_method: str
    rpc_method: str | None
    session_id: str | None
    headers: dict[str, str]
    params: dict[str, Any]


@dataclass
class _FakeMcpServer:
    """An in-memory MCP Streamable HTTP server for `httpx2.MockTransport`.

    Issues a new session ID on every `initialize` call and rejects messages
    that carry an unknown session ID, matching the behavior of a stateful MCP
    server instance.
    """

    # Controls how the server rejects a request with an unknown session ID:
    # "rpc" returns a JSON-RPC "Session not found" error, "http" returns a bare
    # HTTP 404 response, and "http-json" returns an HTTP 404 response carrying
    # an unrelated JSON-RPC error body.
    rejection: str = "rpc"
    # When True, the server discards every session ID immediately after issuing
    # it so that every subsequent request fails session validation.
    forget_every_session: bool = False
    # When True, the server omits `mcp-session-id` during initialization and
    # accepts every request without checking for a session ID.
    stateless: bool = False
    fail_initialize: bool = False
    reject_ping: bool = False
    down: bool = False
    tools: list[dict[str, Any]] = field(default_factory=lambda: list(_TOOLS))
    received: list[_Request] = field(default_factory=list)
    sessions: set[str] = field(default_factory=set)
    issued: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def count(self, rpc_method: str) -> int:
        """Returns how many messages for `rpc_method` the server received."""
        with self.lock:
            return sum(
                1
                for request in self.received
                if request.rpc_method == rpc_method
            )

    def received_for(self, rpc_method: str) -> list[_Request]:
        """Returns the messages for `rpc_method` in arrival order."""
        with self.lock:
            return [
                request
                for request in self.received
                if request.rpc_method == rpc_method
            ]

    def forget_sessions(self) -> None:
        """Clears active sessions to simulate routing to a new server."""
        with self.lock:
            self.sessions.clear()

    async def handle(self, request: httpx2.Request) -> httpx2.Response:
        """Handles a single HTTP request from the MCP client."""
        if self.down:
            raise httpx2.ConnectError("Connection refused", request=request)
        body = json.loads(request.content) if request.content else {}
        session_id = request.headers.get("mcp-session-id")
        with self.lock:
            self.received.append(
                _Request(
                    http_method=request.method,
                    rpc_method=body.get("method"),
                    session_id=session_id,
                    headers=dict(request.headers),
                    params=body.get("params") or {},
                )
            )
        if request.method != "POST":
            return httpx2.Response(405)
        if "id" not in body:
            return httpx2.Response(202)
        method = body["method"]
        if method == "initialize":
            return self._initialize(body["id"])
        with self.lock:
            known = self.stateless or session_id in self.sessions
        if not known:
            if self.rejection == "http":
                return httpx2.Response(404)
            if self.rejection == "http-json":
                error = {"code": -32600, "message": "Invalid request"}
                return httpx2.Response(
                    404,
                    json={"jsonrpc": "2.0", "id": body["id"], "error": error},
                )
            return _rpc_error(body["id"], -32600, "Session not found")
        if method == "ping":
            if self.reject_ping:
                return _rpc_error(body["id"], -32601, "Method not found: ping")
            return _rpc_result(body["id"], {})
        if method == "tools/list":
            return _rpc_result(body["id"], {"tools": self.tools})
        if method == "tools/call":
            return self._call_tool(body["id"], body["params"])
        return _rpc_error(body["id"], -32601, f"Method not found: {method}")

    def _initialize(self, request_id: int) -> httpx2.Response:
        if self.fail_initialize:
            return httpx2.Response(500)
        with self.lock:
            self.issued += 1
            session_id = f"session-{self.issued}"
            if not self.forget_every_session:
                self.sessions.add(session_id)
        result = {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "fake-mcp", "version": "1.0.0"},
        }
        response = _rpc_result(request_id, result)
        if not self.stateless:
            response.headers["mcp-session-id"] = session_id
        return response

    def _call_tool(
        self, request_id: int, params: dict[str, Any]
    ) -> httpx2.Response:
        name = params["name"]
        if name == "unknown_tool":
            return _rpc_error(request_id, -32602, f"Unknown tool: {name}")
        if name == "failing_tool":
            result: dict[str, Any] = {
                "content": [{"type": "text", "text": "No such place."}],
                "isError": True,
            }
        else:
            echo = json.dumps({"arguments": params.get("arguments")})
            result = {"content": [{"type": "text", "text": echo}]}
        # Return tool results as an SSE stream to match the Data Commons MCP
        # server.
        message = {"jsonrpc": "2.0", "id": request_id, "result": result}
        return httpx2.Response(
            200,
            content=f"event: message\ndata: {json.dumps(message)}\n\n".encode(),
            headers={"content-type": "text/event-stream"},
        )


def _rpc_result(request_id: int, result: dict[str, Any]) -> httpx2.Response:
    return httpx2.Response(
        200, json={"jsonrpc": "2.0", "id": request_id, "result": result}
    )


def _rpc_error(request_id: int, code: int, message: str) -> httpx2.Response:
    error = {"code": code, "message": message}
    return httpx2.Response(
        200, json={"jsonrpc": "2.0", "id": request_id, "error": error}
    )


@dataclass
class _RecordingSessionLogger:
    """Records the calls the MCP client makes on a session logger."""

    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    results: list[tuple[str, Any, str]] = field(default_factory=list)

    def log_mcp_tool_call(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> None:
        self.calls.append((tool_name, arguments))

    def log_mcp_tool_result(
        self, tool_name: str, result: Any, duration_ms: float, status: str
    ) -> None:
        self.results.append((tool_name, result, status))


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> Iterator[_FakeMcpServer]:
    """Installs a `_FakeMcpServer` behind the client and resets client state.

    Clears the cached URL, tool cache, and session before and after each test
    so that state does not leak between test cases. Stubs `load_config` so the
    handshake uses the default client name without reading from disk.
    """
    fake = _FakeMcpServer()
    client.reset_client()
    monkeypatch.setitem(client._URL_CACHE, "url", _URL)
    monkeypatch.setattr(client, "load_config", lambda: {})
    monkeypatch.setattr(
        client,
        "_create_http_client",
        lambda headers: httpx2.AsyncClient(
            headers=headers, transport=httpx2.MockTransport(fake.handle)
        ),
    )
    yield fake
    client.reset_client()


def _join_background_refresh() -> None:
    """Waits for any background refresh thread started by `cached_tools`."""
    for thread in threading.enumerate():
        if thread.name == "mcp-tools-refresh":
            thread.join(timeout=_REFRESH_JOIN_TIMEOUT_SECONDS)


@pytest.mark.parametrize("reject_ping", [False, True])
def test_initialize_stores_the_server_issued_session(
    server: _FakeMcpServer, reject_ping: bool
) -> None:
    # Test: `initialize_mcp` completes the handshake and stores the session ID
    #   whether or not the server supports `ping`.
    # Situation: `initialize_mcp` runs against a server that returns
    #   "session-1" in the `mcp-session-id` response header and either answers
    #   or rejects the post-handshake `ping`.
    # Expectation: It returns True, stores "session-1" in the caller's context,
    #   and flushes `notifications/initialized` before closing the connection.
    server.reject_ping = reject_ping

    assert client.initialize_mcp() is True

    assert client.get_session_id() == "session-1"
    assert server.count("notifications/initialized") == 1


def test_operations_reuse_the_session_without_a_new_handshake(
    server: _FakeMcpServer, caplog: pytest.LogCaptureFixture
) -> None:
    # Test: Subsequent MCP operations reuse the established session without
    #   repeating the handshake.
    # Situation: Two forced `get_tools` refreshes and one `call_tool` request
    #   run sequentially in the same context without a prior `initialize_mcp`
    #   call.
    # Expectation: Only one `initialize` handshake is sent, the handshake start
    #   and completion are logged at INFO, every subsequent request carries the
    #   session ID and negotiated protocol version, and no HTTP DELETE request
    #   is sent when connections close.
    with caplog.at_level(logging.INFO, logger=client.logger.name):
        client.get_tools(force_refresh=True)
        client.get_tools(force_refresh=True)
        client.call_tool("get_observations", {})

    assert server.count("initialize") == 1
    assert caplog.text.count("Initializing MCP session...") == 1
    assert (
        "MCP session initialized (server-issued session ID: yes)."
        in caplog.text
    )
    for request in server.received_for("tools/list") + server.received_for(
        "tools/call"
    ):
        assert request.session_id == "session-1"
        assert request.headers["mcp-protocol-version"] == _PROTOCOL_VERSION
    assert not [r for r in server.received if r.http_method == "DELETE"]


def test_a_stateless_server_is_used_without_a_session_id(
    server: _FakeMcpServer,
) -> None:
    # Test: The client operates against a stateless MCP server that does not
    #   issue a session ID.
    # Situation: The server's `initialize` response omits the `mcp-session-id`
    #   header and accepts every request without a session ID.
    # Expectation: A single handshake serves both `get_tools` calls, no
    #   request includes an `mcp-session-id` header, and `get_session_id()`
    #   returns None.
    server.stateless = True

    assert client.get_tools(force_refresh=True) == _TOOLS
    assert client.get_tools(force_refresh=True) == _TOOLS

    assert server.count("initialize") == 1
    assert all(request.session_id is None for request in server.received)
    assert client.get_session_id() is None


@pytest.mark.parametrize("rejection", ["rpc", "http"])
def test_a_rejected_session_re_initializes_and_retries_once(
    server: _FakeMcpServer, rejection: str
) -> None:
    # Test: The client re-initializes the session and retries once when the
    #   server rejects an existing session ID.
    # Situation: After a session is established, the server forgets the session
    #   and rejects the next request with either a JSON-RPC "Session not found"
    #   error or a bare HTTP 404 response.
    # Expectation: `get_tools` performs a new handshake, retries `tools/list`
    #   once with the new session ID, and returns the tool list.
    server.rejection = rejection
    client.initialize_mcp()
    server.forget_sessions()

    assert client.get_tools(force_refresh=True) == _TOOLS
    assert server.count("initialize") == 2
    assert [r.session_id for r in server.received_for("tools/list")] == [
        "session-1",
        "session-2",
    ]
    assert client.get_session_id() == "session-2"


@pytest.mark.parametrize("rejection", ["rpc", "http"])
def test_session_recovery_retries_exactly_once(
    server: _FakeMcpServer, rejection: str
) -> None:
    # Test: Session recovery retries a rejected operation at most once.
    # Situation: The server forgets every session immediately after issuing it,
    #   so both the initial request and the retry after re-initialization are
    #   rejected.
    # Expectation: `call_tool` performs one re-initialization and one retry
    #   (two handshakes and two `tools/call` messages in total), and then
    #   returns an error dictionary.
    server.rejection = rejection
    server.forget_every_session = True

    result = client.call_tool("get_observations", {})

    assert server.count("initialize") == 2
    assert server.count("tools/call") == 2
    assert "error" in result


def test_a_404_with_an_unrelated_rpc_error_is_not_retried(
    server: _FakeMcpServer,
) -> None:
    # Test: An HTTP 404 response with an unrelated JSON-RPC error body does not
    #   trigger session recovery.
    # Situation: The server responds to `tools/call` with HTTP 404 and a
    #   JSON-RPC error whose message does not indicate a lost session.
    # Expectation: The client does not re-initialize or retry the call, and
    #   returns the error immediately after a single handshake and tool call.
    server.rejection = "http-json"
    server.forget_every_session = True

    result = client.call_tool("get_observations", {})

    assert server.count("initialize") == 1
    assert server.count("tools/call") == 1
    assert "error" in result


@pytest.mark.asyncio
async def test_async_tool_call_recovers_a_rejected_session(
    server: _FakeMcpServer,
) -> None:
    # Test: `async_call_tool` recovers when the server rejects the current
    #   session.
    # Situation: `async_initialize_mcp` establishes a session, and the server
    #   forgets that session before `async_call_tool` is awaited.
    # Expectation: `async_call_tool` re-initializes the session once and
    #   returns the tool result without error.
    assert await client.async_initialize_mcp() is True
    server.forget_sessions()

    result = await client.async_call_tool("get_observations", {})

    assert "error" not in result
    assert server.count("initialize") == 2


def test_a_failed_handshake_fails_closed(server: _FakeMcpServer) -> None:
    # Test: Operations fail closed without sending an uninitialized request
    #   when the handshake fails.
    # Situation: The server responds to `initialize` with HTTP 500.
    # Expectation: `initialize_mcp` returns False, `get_tools` returns `[]`,
    #   `call_tool` returns an error dictionary, and no `tools/list` or
    #   `tools/call` request is sent to the server.
    server.fail_initialize = True

    assert client.initialize_mcp() is False
    assert client.get_tools(force_refresh=True) == []
    assert "error" in client.call_tool("get_observations", {})
    assert server.count("tools/list") == 0
    assert server.count("tools/call") == 0
    assert client.get_session_id() is None


def test_a_failed_re_initialization_clears_the_previous_session(
    server: _FakeMcpServer,
) -> None:
    # Test: A failed `initialize_mcp` call clears any previously stored session
    #   in the current context.
    # Situation: A session is established, and a subsequent `initialize_mcp`
    #   call fails because the server is unreachable.
    # Expectation: `initialize_mcp` returns False, and `get_session_id()`
    #   returns None instead of the stale session ID.
    client.initialize_mcp()
    server.down = True

    assert client.initialize_mcp() is False
    assert client.get_session_id() is None


@pytest.mark.asyncio
async def test_concurrent_tasks_hold_distinct_sessions(
    server: _FakeMcpServer,
) -> None:
    # Test: Concurrent asyncio tasks maintain separate MCP sessions.
    # Situation: Two asyncio tasks run concurrently via `asyncio.gather`; each
    #   initializes a session and fetches the tool list.
    # Expectation: Each task receives and sends its own distinct session ID,
    #   and neither task's session leaks into the parent context.
    async def turn() -> str | None:
        await client.async_initialize_mcp()
        await client.async_get_tools(force_refresh=True)
        return client.get_session_id()

    first, second = await asyncio.gather(turn(), turn())

    assert first and second and first != second
    sent = {r.session_id for r in server.received_for("tools/list")}
    assert sent == {first, second}
    assert client.get_session_id() is None


def test_threads_hold_distinct_sessions(server: _FakeMcpServer) -> None:
    # Test: Concurrent OS threads maintain separate MCP sessions.
    # Situation: Two threads concurrently call `initialize_mcp` and
    #   `call_tool`.
    # Expectation: Each thread receives and sends its own distinct session ID,
    #   and the main thread's context remains without a session.
    seen: dict[str, str | None] = {}

    def worker() -> None:
        client.initialize_mcp()
        seen[threading.current_thread().name] = client.get_session_id()
        client.call_tool("get_observations", {})

    threads = [threading.Thread(target=worker, name=n) for n in ("A", "B")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert seen["A"] and seen["B"] and seen["A"] != seen["B"]
    sent = {r.session_id for r in server.received_for("tools/call")}
    assert sent == {seen["A"], seen["B"]}
    assert client.get_session_id() is None


def test_a_blocking_call_propagates_a_session_even_when_it_raises(
    server: _FakeMcpServer,
) -> None:
    # Test: `_run_sync` copies the updated session back to the caller's
    #   context even when the coroutine raises an exception.
    # Situation: An async operation establishes a session and then raises a
    #   `RuntimeError`.
    # Expectation: The `RuntimeError` propagates to the caller, and the
    #   caller's context retains the newly established session ID.
    async def initialize_then_fail() -> None:
        await client.async_initialize_mcp()
        raise RuntimeError("downstream failure")

    with pytest.raises(RuntimeError, match="downstream failure"):
        client._run_sync(initialize_then_fail)

    assert client.get_session_id() == "session-1"


def test_tool_list_is_served_from_cache_within_the_ttl(
    server: _FakeMcpServer,
) -> None:
    # Test: `get_tools` serves the cached tool list when the cache has not
    #   expired.
    # Situation: A forced refresh populates the tool cache, followed by two
    #   unforced `get_tools` calls within the TTL window.
    # Expectation: Both unforced calls return the cached tool list without
    #   sending another `tools/list` request.
    assert client.get_tools(force_refresh=True) == _TOOLS

    assert client.get_tools() == _TOOLS
    assert client.get_tools() == _TOOLS
    assert server.count("tools/list") == 1


def test_an_expired_cache_and_force_refresh_fetch_again(
    server: _FakeMcpServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Test: `get_tools` fetches a fresh tool list when `force_refresh=True` is
    #   passed or when the cache TTL has expired.
    # Situation: Two forced refreshes run within the TTL, and then an unforced
    #   `get_tools` call runs after `_TOOLS_TTL_SECONDS` is set to zero.
    # Expectation: All three calls send a `tools/list` request to the server.
    client.get_tools(force_refresh=True)
    client.get_tools(force_refresh=True)
    monkeypatch.setattr(client, "_TOOLS_TTL_SECONDS", 0)

    client.get_tools()

    assert server.count("tools/list") == 3


@pytest.mark.asyncio
async def test_a_failing_refresh_serves_the_stale_list(
    server: _FakeMcpServer,
) -> None:
    # Test: `async_get_tools` falls back to the stale cached list when a
    #   refresh fails.
    # Situation: `async_get_tools` populates the cache, the server becomes
    #   unreachable, and a forced refresh is awaited.
    # Expectation: The forced refresh returns the previously cached tool list
    #   instead of an empty list.
    await client.async_get_tools(force_refresh=True)
    server.down = True

    assert await client.async_get_tools(force_refresh=True) == _TOOLS


def test_an_empty_tool_list_is_cached(server: _FakeMcpServer) -> None:
    # Test: Caching of a successful `tools/list` response that lists no tools.
    # Situation: The cache holds the server's tools. The server then lists no
    #   tools, a forced refresh runs, and `get_tools` and `cached_tools` are
    #   called within the TTL.
    # Expectation: The empty list replaces the previous list, later calls
    #   return it without another `tools/list` request, and `cached_tools`
    #   starts no background refresh.
    client.get_tools(force_refresh=True)
    server.tools = []

    assert client.get_tools(force_refresh=True) == []
    assert client.get_tools() == []
    assert client.cached_tools() == []
    _join_background_refresh()
    assert server.count("tools/list") == 2


def test_tool_definitions_keep_the_wire_key_names(
    server: _FakeMcpServer,
) -> None:
    # Test: `get_tools` preserves the MCP wire key names and defaults missing
    #   descriptions to an empty string.
    # Situation: The server returns one tool with a description and one tool
    #   that omits the `description` field.
    # Expectation: Each returned dictionary contains `"name"`, `"inputSchema"`,
    #   and `"description"`, with `"description"` set to `""` when omitted by
    #   the server.
    server.tools = [
        *_TOOLS,
        {"name": "bare", "inputSchema": {"type": "object"}},
    ]

    tools = client.get_tools(force_refresh=True)

    assert tools[1] == {
        "name": "bare",
        "description": "",
        "inputSchema": {"type": "object"},
    }


def test_cached_tools_on_a_cold_cache_returns_at_once_and_refreshes(
    server: _FakeMcpServer,
) -> None:
    # Test: `cached_tools` returns immediately on a cold cache and populates
    #   the cache in the background.
    # Situation: `cached_tools` is called when the tool cache is empty.
    # Expectation: The first call immediately returns `[]` without blocking,
    #   and once the background refresh thread completes, a subsequent
    #   `cached_tools` call returns the server's tool list.
    assert client.cached_tools() == []

    _join_background_refresh()

    assert client.cached_tools() == _TOOLS


def test_cached_tools_on_a_warm_cache_sends_nothing(
    server: _FakeMcpServer,
) -> None:
    # Test: `cached_tools` returns the cached list without network traffic
    #   when the cache is already populated.
    # Situation: `get_tools` populates the tool cache before `cached_tools` is
    #   called.
    # Expectation: `cached_tools` returns the cached list and sends no
    #   request to the server.
    client.get_tools(force_refresh=True)
    before = len(server.received)

    assert client.cached_tools() == _TOOLS
    assert len(server.received) == before


def test_call_tool_sends_normalized_arguments(server: _FakeMcpServer) -> None:
    # Test: `call_tool` normalizes tool arguments before sending them to the
    #   server.
    # Situation: The caller passes `date_range_start` without `date="range"`
    #   and includes a `None`-valued argument.
    # Expectation: The server receives `date="range"` and the `None`-valued
    #   argument is omitted.
    client.call_tool(
        "get_observations",
        {
            "date_range_start": "2020",
            "variable_dcid": "Count_Person",
            "x": None,
        },
    )

    sent = server.received_for("tools/call")[0].params["arguments"]
    assert sent == {
        "date_range_start": "2020",
        "variable_dcid": "Count_Person",
        "date": "range",
    }


def test_call_tool_attaches_credentials_for_the_endpoint(
    server: _FakeMcpServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Test: `call_tool` attaches authentication headers for the resolved MCP
    #   endpoint URL on every request.
    # Situation: `attach_auth` is stubbed to add a bearer token header for the
    #   target URL.
    # Expectation: `attach_auth` is called with the MCP endpoint URL, and
    #   every request received by the server includes the `Authorization`
    #   header.
    targets: list[str] = []

    def fake_attach_auth(headers: dict[str, str], target_url: str) -> None:
        targets.append(target_url)
        headers["Authorization"] = "Bearer test-token"

    monkeypatch.setattr(client, "attach_auth", fake_attach_auth)

    client.call_tool("get_observations", {})

    assert set(targets) == {_URL}
    assert all(
        r.headers.get("authorization") == "Bearer test-token"
        for r in server.received
    )


@pytest.mark.asyncio
async def test_call_tool_returns_the_result_in_wire_shape(
    server: _FakeMcpServer,
) -> None:
    # Test: `async_call_tool` returns a successful tool result using the MCP
    #   wire format without injecting unset default fields.
    # Situation: The server streams a `CallToolResult` containing a single
    #   text content block.
    # Expectation: `async_call_tool` returns `{"content": [{"type": "text",
    #   "text": ...}]}` with no extra default fields added by Pydantic.
    result = await client.async_call_tool(
        "get_observations", {"date": "latest"}
    )

    text = json.dumps({"arguments": {"date": "latest"}})
    assert result == {"content": [{"type": "text", "text": text}]}


@pytest.mark.parametrize(
    ("tool", "expected"),
    [
        ("failing_tool", "No such place."),
        ("unknown_tool", "Unknown tool: unknown_tool"),
    ],
    ids=["tool reports an error", "server rejects the call"],
)
def test_call_tool_reports_tool_and_protocol_errors(
    server: _FakeMcpServer, tool: str, expected: str
) -> None:
    # Test: `call_tool` returns an error dictionary when a tool reports
    #   `isError: true` or the server returns a JSON-RPC error.
    # Situation: `call_tool` is invoked once for a tool that sets `isError` on
    #   its result and once for a tool that fails with a JSON-RPC error.
    # Expectation: Both calls return `{"error": <message>}` without retrying.
    assert client.call_tool(tool, {}) == {"error": expected}
    assert server.count("tools/call") == 1


def test_call_tool_reports_an_unreachable_server(
    server: _FakeMcpServer,
) -> None:
    # Test: `call_tool` returns a connection error message when the MCP server
    #   is unreachable.
    # Situation: Every connection attempt to the MCP server fails with
    #   `httpx2.ConnectError`.
    # Expectation: `call_tool` returns `{"error": "Cannot connect to MCP
    #   server at <url>. Make sure it's running!"}`.
    server.down = True

    assert client.call_tool("get_observations", {}) == {
        "error": f"Cannot connect to MCP server at {_URL}. Make sure it's "
        "running!"
    }


@pytest.mark.parametrize(
    ("underlying", "expected"),
    [
        (
            httpx2.ConnectError("Connection refused"),
            f"Cannot connect to MCP server at {_URL}. Make sure it's running!",
        ),
        (
            MCPError(code=-32603, message="Upstream gateway timeout"),
            "Upstream gateway timeout",
        ),
    ],
    ids=[
        "connect error after connection closed",
        "rpc error after connection closed",
    ],
)
def test_describe_error_prefers_the_underlying_failure_over_connection_closed(
    server: _FakeMcpServer, underlying: Exception, expected: str
) -> None:
    # Test: `_describe_error` selects the underlying transport or protocol
    #   error from an `ExceptionGroup` rather than a secondary
    #   `CONNECTION_CLOSED` error.
    # Situation: An `ExceptionGroup` contains a `CONNECTION_CLOSED` `MCPError`
    #   followed by either an `httpx2.ConnectError` or an upstream `MCPError`.
    # Expectation: `_describe_error` returns the message for the `ConnectError`
    #   or upstream `MCPError` instead of `"Connection closed"`.
    connection_closed = MCPError(
        code=types.CONNECTION_CLOSED, message="Connection closed"
    )
    group = ExceptionGroup("unhandled errors", [connection_closed, underlying])

    assert client._describe_error(group) == expected


def test_call_tool_records_calls_and_results_in_the_session_logger(
    server: _FakeMcpServer,
) -> None:
    # Test: `call_tool` logs tool invocations and their outcomes to the
    #   provided `session_logger`.
    # Situation: One succeeding tool call and one failing tool call are made
    #   with a `session_logger` instance.
    # Expectation: The session logger records the normalized arguments for
    #   each call and records `"success"` and `"error"` statuses for the
    #   respective results.
    session_logger = _RecordingSessionLogger()

    client.call_tool("get_observations", {}, session_logger)
    client.call_tool("failing_tool", {}, session_logger)

    assert session_logger.calls == [
        ("get_observations", {"date": "latest"}),
        ("failing_tool", {}),
    ]
    assert [status for _, _, status in session_logger.results] == [
        "success",
        "error",
    ]
    assert session_logger.results[1][1] == {"error": "No such place."}


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("http://127.0.0.1:8082", "http://127.0.0.1:8082/mcp"),
        ("http://127.0.0.1:8082/", "http://127.0.0.1:8082/mcp"),
        ("https://api.datacommons.org/mcp", "https://api.datacommons.org/mcp"),
        (
            "https://host.example/custom/path",
            "https://host.example/custom/path",
        ),
    ],
    ids=["bare origin", "origin with slash", "explicit /mcp", "custom path"],
)
def test_normalize_url_appends_mcp_only_to_bare_origins(
    configured: str, expected: str
) -> None:
    # Test: `_normalize_url` appends `/mcp` only when the configured URL has
    #   no path component.
    # Situation: `_normalize_url` is called with a bare origin, an origin with
    #   a trailing slash, a URL ending in `/mcp`, and a URL with a custom
    #   path.
    # Expectation: Bare origins gain `/mcp`, while URLs that already contain a
    #   path are returned unchanged.
    assert client._normalize_url(configured) == expected


@pytest.mark.parametrize(
    ("env_url", "config_url", "expected"),
    [
        (
            "https://env.example",
            "https://config.example",
            "https://env.example/mcp",
        ),
        ("", "https://config.example", "https://config.example/mcp"),
        ("", "", "http://localhost:4321/mcp"),
    ],
    ids=["MCP_SERVER_URL wins", "config next", "localhost fallback"],
)
def test_mcp_url_resolution_order(
    monkeypatch: pytest.MonkeyPatch,
    env_url: str,
    config_url: str,
    expected: str,
) -> None:
    # Test: `mcp_url` resolves the endpoint from `MCP_SERVER_URL`, then
    #   `config.json`, and finally the localhost fallback, caching the result.
    # Situation: `mcp_url` is called with `MCP_SERVER_URL` and `mcp.server_url`
    #   configured in each precedence combination.
    # Expectation: `MCP_SERVER_URL` takes precedence over `mcp.server_url`,
    #   which takes precedence over `http://localhost:<mcp_port>/mcp`, and
    #   subsequent calls return the cached URL.
    monkeypatch.setattr(client, "_URL_CACHE", {})
    settings = Settings(mcp_server_url=env_url, mcp_port=4321)
    monkeypatch.setattr(client, "get_settings", lambda: settings)
    monkeypatch.setattr(
        client, "load_config", lambda: {"mcp": {"server_url": config_url}}
    )

    assert client.mcp_url() == expected
    monkeypatch.setattr(client, "load_config", lambda: {})
    assert client.mcp_url() == expected


@pytest.mark.asyncio
async def test_sync_wrapper_raises_when_called_inside_running_loop() -> None:
    # Test: Calling a synchronous MCP wrapper from a thread with a running
    #   event loop raises `RuntimeError`.
    # Situation: `client.get_tools()` is called directly inside an `async def`
    #   function where an event loop is already running on the current thread.
    # Expectation: `get_tools()` raises `RuntimeError` without leaving an
    #   unawaited coroutine warning.
    with pytest.raises(RuntimeError):
        client.get_tools()
