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
"""Tests for MCP session management, thread isolation, and tool-list caching.

Verifies three behaviors in `narratives_agent.mcp.client`:
1. Session recovery: when an MCP server rejects a stale or unrecognized session
   ID (`Session not found`), the client re-initializes the session and retries
   the request once.
2. Thread isolation: concurrent worker threads store independent session IDs in
   thread-local storage rather than overwriting a shared module global.
3. Tool caching and fallback: `get_tools` serves cached tool definitions within
   the TTL and falls back to the last known tool list if a refresh fails.
"""

import threading
from typing import Any

import pytest

from narratives_agent.mcp import client

_TOOLS = [{"name": "get_observations"}]


class _ScriptedServer:
    """Fake MCP transport that rejects the first `tools/list` call and succeeds
    after re-initialization.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.reject_next_tools_list = True

    def __call__(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        is_notification: bool = False,
    ) -> dict[str, Any]:
        self.calls.append(method)
        if method == "initialize":
            # Assign a thread-specific session ID to simulate the MCP session
            # header returned by the server during initialization.
            client._set_session_id("sess-" + threading.current_thread().name)
            return {"result": {"ok": True}}
        if method == "notifications/initialized":
            return {"result": "notification sent"}
        if method == "tools/list":
            if self.reject_next_tools_list:
                self.reject_next_tools_list = False
                return {
                    "error": {"code": -32000, "message": "Session not found"}
                }
            return {"result": {"tools": _TOOLS}}
        return {"result": {}}


class _DeadServer:
    """Fake MCP transport that returns an error for every request."""

    def __call__(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        is_notification: bool = False,
    ) -> dict[str, Any]:
        return {"error": {"message": "backend down"}}


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> _ScriptedServer:
    """Provide a `_ScriptedServer` with isolated thread-local and cache state.

    Replaces `client._local` and `client._TOOLS_CACHE` before each test so that
    session IDs and cached tools do not leak across test cases.
    """
    monkeypatch.setattr(client, "_local", threading.local())
    monkeypatch.setattr(
        client, "_TOOLS_CACHE", {"tools": None, "fetched_at": 0.0}
    )
    # Stub `load_config` with an empty dictionary so initialization uses default
    # MCP settings without reading from disk.
    monkeypatch.setattr(client, "load_config", lambda: {})
    scripted = _ScriptedServer()
    monkeypatch.setattr(client, "mcp_request", scripted)
    return scripted


def test_rejected_session_recovers_and_returns_the_tool_list(
    server: _ScriptedServer,
) -> None:
    # Test: Session recovery when `tools/list` returns a session-not-found
    #   error.
    # Situation: The first `tools/list` request is rejected with code -32000
    #   ("Session not found"), simulating a request routed to a new backend
    #   instance.
    # Expectation: `get_tools` clears the stale session, re-runs MCP
    #   initialization, and returns the tool list from the retry.
    assert client.get_tools(force_refresh=True) == _TOOLS


def test_rejected_session_re_initializes_and_retries_exactly_once(
    server: _ScriptedServer,
) -> None:
    # Test: Retry bound during MCP session recovery.
    # Situation: The initial `tools/list` call fails with "Session not found"
    #   and succeeds after a single re-initialization.
    # Expectation: The client performs exactly one re-initialization and one
    #   retry (`initialize` and `tools/list` are each called twice in total).
    client.get_tools(force_refresh=True)

    assert server.calls.count("initialize") == 2
    assert server.calls.count("tools/list") == 2


def test_threads_hold_distinct_sessions(server: _ScriptedServer) -> None:
    # Test: Thread-local isolation of MCP session IDs.
    # Situation: Two worker threads concurrently call `initialize_mcp()`.
    # Expectation: Each thread stores and retrieves its own distinct session ID
    #   without overwriting the other thread's session.
    seen: dict[str, str | None] = {}

    def worker() -> None:
        client.initialize_mcp()
        seen[threading.current_thread().name] = client.get_session_id()

    first = threading.Thread(target=worker, name="A")
    second = threading.Thread(target=worker, name="B")
    first.start()
    second.start()
    first.join()
    second.join()

    assert all(seen.values())
    assert seen["A"] != seen["B"]


def test_tool_list_is_served_from_cache_within_the_ttl(
    server: _ScriptedServer,
) -> None:
    # Test: Caching of `tools/list` responses within the cache TTL.
    # Situation: `get_tools(force_refresh=True)` populates the cache, followed
    #   immediately by two unforced `get_tools()` calls.
    # Expectation: The subsequent `get_tools()` calls return the cached tool
    #   list without issuing additional `tools/list` network requests.
    client.get_tools(force_refresh=True)
    before = server.calls.count("tools/list")

    client.get_tools()
    client.get_tools()

    assert server.calls.count("tools/list") == before


def test_a_failing_refresh_serves_the_stale_list_rather_than_nothing(
    server: _ScriptedServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Test: Fallback to the last cached tool list when a refresh fails.
    # Situation: The tool cache is populated, the MCP backend becomes
    #   unavailable, and `get_tools(force_refresh=True)` is called.
    # Expectation: `get_tools` returns the previously cached tool list rather
    #   than an empty list.
    client.get_tools(force_refresh=True)
    monkeypatch.setattr(client, "mcp_request", _DeadServer())

    assert client.get_tools(force_refresh=True) == _TOOLS
