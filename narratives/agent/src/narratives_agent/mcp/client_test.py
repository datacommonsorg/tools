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
"""Behavioral test for MCP session handling.

Thread isolation, recovery from a data-plane instance that does not recognize
our session, and tool-cache TTL.

Guards the fix for the module-global session_id, which made N instances
incorrect rather than merely slow. The three behaviors asserted here are the
ones whose absence is silent: a session rejected by a different data-plane
instance must recover, concurrent threads must not share a session, and a
failing tools/list must not blank the tool surface.
"""

import threading
from typing import Any

import pytest

from narratives_agent.mcp import client

_TOOLS = [{"name": "get_observations"}]


class _ScriptedServer:
    """Scripted server: rejects the first tools/list, accepts after re-init."""

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
            # A real server mints one session per caller; the id is carried
            # back on a response header, which this stands in for.
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
    """Every call fails, as during a data-plane outage."""

    def __call__(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        is_notification: bool = False,
    ) -> dict[str, Any]:
        return {"error": {"message": "backend down"}}


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> _ScriptedServer:
    """A scripted transport over freshly isolated client state.

    The session id is thread-local and the tool list is a process-wide cache,
    so both are replaced per test: left shared, a test would be reading state
    another test wrote, which is the very class of bug this file exists for.
    """
    monkeypatch.setattr(client, "_local", threading.local())
    monkeypatch.setattr(
        client, "_TOOLS_CACHE", {"tools": None, "fetched_at": 0.0}
    )
    # The handshake reads mcp.* out of the agent config; an empty document
    # exercises the defaults and keeps the test off the filesystem.
    monkeypatch.setattr(client, "load_config", lambda: {})
    scripted = _ScriptedServer()
    monkeypatch.setattr(client, "mcp_request", scripted)
    return scripted


def test_rejected_session_recovers_and_returns_the_tool_list(
    server: _ScriptedServer,
) -> None:
    # Test: recovery from a session the server does not recognize.
    # Situation: the request lands on a data-plane instance that never minted
    #   our session, so tools/list comes back "Session not found".
    # Expectation: the tool list is still returned. A lost session must be a
    #   recoverable event rather than a permanent one -- nothing used to clear
    #   the value, so the failure stuck until the container restarted.
    assert client.get_tools(force_refresh=True) == _TOOLS


def test_rejected_session_re_initializes_and_retries_exactly_once(
    server: _ScriptedServer,
) -> None:
    # Test: the bound on the recovery path.
    # Situation: as above -- one rejected tools/list, then a working one.
    # Expectation: exactly one re-initialize and exactly one retry. Retrying
    #   once rather than looping matters: a genuine outage should surface as an
    #   error, not as an unbounded retry storm against a struggling backend.
    client.get_tools(force_refresh=True)

    assert server.calls.count("initialize") == 2
    assert server.calls.count("tools/list") == 2


def test_threads_hold_distinct_sessions(server: _ScriptedServer) -> None:
    # Test: session state is per thread.
    # Situation: two worker threads initialize concurrently, as two requests
    #   in one Gunicorn process do.
    # Expectation: each holds its own session id. A module-global was
    #   last-writer-wins, so one thread would send the session another had just
    #   been issued.
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
    # Test: the tool cache actually caches.
    # Situation: the list has been fetched, and two more calls arrive inside
    #   the TTL.
    # Expectation: no further round trips -- tools/list is two extra calls per
    #   chat turn when it is not cached.
    client.get_tools(force_refresh=True)
    before = server.calls.count("tools/list")

    client.get_tools()
    client.get_tools()

    assert server.calls.count("tools/list") == before


def test_a_failing_refresh_serves_the_stale_list_rather_than_nothing(
    server: _ScriptedServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Test: what a failed refresh leaves the model to work with.
    # Situation: the list has been fetched, then the backend goes down and a
    #   forced refresh fails.
    # Expectation: the previously known list is served. An expired-but-known
    #   tool surface is far more useful than an empty one, which would silently
    #   disable every tool the model can call.
    client.get_tools(force_refresh=True)
    monkeypatch.setattr(client, "mcp_request", _DeadServer())

    assert client.get_tools(force_refresh=True) == _TOOLS
