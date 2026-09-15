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

import json
import logging
import os
import threading
import time
from typing import Any, Optional
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter

from src.config import load_config
from src.gcp_auth import attach_auth
from src.mcp.schema import fix_tool_arguments
from src.session_logger import SessionLogger

logger = logging.getLogger(__name__)

# Configuration
MCP_PORT = int(os.environ.get("MCP_PORT", 3000))

# Resolved on first use, not at import: load_config() reads config.json, which
# _bootstrap_config_from_url() only writes once startup has run. A dict rather
# than a rebound module global so mcp_url() needs no `global` statement.
_URL_CACHE = {}

# One pooled session for every MCP call. Bare requests.post() opened a fresh
# TCP connection per call -- free over localhost, but once the MCP server moves
# out of this container each of the 5-15 tool calls in a single chat turn also
# pays a TLS handshake. Keep-alive turns that into one handshake per worker.
_SESSION = requests.Session()
_SESSION.mount("https://", HTTPAdapter(pool_connections=4, pool_maxsize=32))
_SESSION.mount("http://", HTTPAdapter(pool_connections=4, pool_maxsize=32))

# MCP session state.
#
# This was a module-level `session_id` written from every response header with
# no lock, which was wrong in three separate ways once anything scaled:
#
#   * N threads in one process -- last writer wins, so thread A would send the
#     session that thread B had just been issued.
#   * N data-plane instances -- an MCP streamable-HTTP session belongs to the
#     server process that minted it. Cloud Run has no request affinity, so a
#     session created against instance 1 gets presented to instance 2, which
#     has never heard of it.
#   * No recovery -- nothing cleared the value on a session-not-found reply, so
#     the failure was sticky until the container restarted. Worse, a
#     stale-but-truthy id was used as the "is MCP up?" test, so the agent
#     skipped re-initialising at exactly the moment it needed to.
#
# Thread-local state fixes the first. `_ensure_session` + retry-once fixes the
# second and third, and is the part that actually matters: it makes a lost
# session a recoverable event rather than a permanent one, whichever instance
# the next request happens to land on.
_local = threading.local()

# The tool list is a property of the *server*, not of a session, so it is shared
# across threads -- but it is refreshed on a TTL and negative results are not
# cached, because a permanent None meant every later request retried a failing
# tools/list and added two round trips per turn during an outage.
_TOOLS_LOCK = threading.Lock()
_TOOLS_CACHE = {"tools": None, "fetched_at": 0.0}
_TOOLS_TTL_SECONDS = 600

# Substrings that identify "your session is gone" across MCP server generations.
# Matched case-insensitively against the error payload; the JSON-RPC error code
# for this is not standardised, so the text is what we have.
_SESSION_LOST_MARKERS = (
    "session not found",
    "invalid session",
    "unknown session",
    "session expired",
    "missing session",
)


def get_session_id() -> Optional[str]:
    """This thread's MCP session id, if it has one."""
    return getattr(_local, "session_id", None)


def _set_session_id(value: Optional[str]) -> None:
    _local.session_id = value


def _looks_like_lost_session(result: dict) -> bool:
    """True when the server is telling us our session is no longer valid."""
    error = result.get("error")
    if not error:
        return False
    text = json.dumps(error, default=str).lower()
    return any(marker in text for marker in _SESSION_LOST_MARKERS)


def _normalise_url(url: str) -> str:
    """Append the /mcp path when the configured value is a bare origin.

    Every config we ship writes `mcp.server_url` as an origin
    ("http://127.0.0.1:8082") while the endpoint itself lives at /mcp.
    Accepting both spellings stops a config author from silently producing a
    URL that 404s.
    """
    if urlparse(url).path in ("", "/"):
        return url.rstrip("/") + "/mcp"
    return url


def mcp_url() -> str:
    """The MCP endpoint: MCP_SERVER_URL, then config, then in-container localhost.

    Cached after the first call. The localhost fallback keeps the co-located
    sidecar deployment working unchanged when neither override is set, so this
    is additive rather than a behaviour change for existing instances.
    """
    if "url" in _URL_CACHE:
        return _URL_CACHE["url"]

    configured = os.environ.get("MCP_SERVER_URL", "").strip()
    if not configured:
        mcp_config = load_config().get("mcp", {})
        configured = str(mcp_config.get("server_url") or "").strip()

    resolved = (
        _normalise_url(configured) if configured
        else f"http://localhost:{MCP_PORT}/mcp"
    )
    _URL_CACHE["url"] = resolved
    logger.info("MCP endpoint resolved to %s", resolved)
    return resolved


def mcp_request(method: str, params: dict = None, is_notification: bool = False) -> dict:
    """Send one JSON-RPC request or notification. No session recovery.

    Prefer `mcp_call` for anything that needs a live session -- this is the raw
    transport, used directly only by the handshake itself (which must not
    recurse into session recovery).

    Args:
        method: The JSON-RPC method name
        params: Optional parameters
        is_notification: If True, sends as notification (no id, no response expected)
    """
    payload = {
        "jsonrpc": "2.0",
        "method": method
    }

    # Notifications don't have an id
    if not is_notification:
        payload["id"] = int(time.time() * 1000)

    if params:
        payload["params"] = params

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }

    current_session = get_session_id()
    if current_session:
        headers["Mcp-Session-Id"] = current_session

    url = mcp_url()
    # No-op while the MCP server is a localhost sidecar; once it is a separate
    # IAM-gated service this is what makes the call succeed.
    attach_auth(headers, url)

    try:
        # For notifications, we send but don't expect a response
        if is_notification:
            _SESSION.post(
                url,
                json=payload,
                headers=headers,
                timeout=5
            )
            return {"result": "notification sent"}

        response = _SESSION.post(
            url,
            json=payload,
            headers=headers,
            timeout=300,
            stream=True
        )

        # Log response details for debugging
        logger.info(f"MCP Response - Status: {response.status_code}, Headers: {dict(response.headers)}")

        # Get session ID from response (try multiple header variations)
        session_header = (
            response.headers.get("Mcp-Session-Id") or
            response.headers.get("mcp-session-id") or
            response.headers.get("MCP-Session-ID")
        )
        if session_header:
            _set_session_id(session_header)
            logger.info("Got MCP session ID from headers: %s", session_header)
        else:
            logger.debug(
                "No session ID in response headers; keeping the current one. "
                "Available headers: %s", list(response.headers.keys())
            )

        content_type = response.headers.get("content-type", "")

        if "text/event-stream" in content_type:
            # Parse SSE response
            result = None
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith("data: "):
                        try:
                            data = json.loads(line_str[6:])
                            if "result" in data:
                                result = data["result"]
                            elif "error" in data:
                                return {"error": data["error"]}
                        except json.JSONDecodeError:
                            continue
            return {"result": result} if result else {"error": "No result"}
        else:
            return response.json()

    except requests.exceptions.ConnectionError:
        return {"error": f"Cannot connect to MCP server at {url}. Make sure it's running!"}
    except Exception as e:
        return {"error": str(e)}


def initialize_mcp() -> bool:
    """Perform the MCP handshake for the calling thread.

    Safe to call repeatedly: it simply mints a fresh session. Uses mcp_request
    directly rather than mcp_call, because the recovery path in mcp_call calls
    this -- routing the handshake through it would recurse.
    """
    logger.info("Initializing MCP session...")

    _set_session_id(None)
    mcp_config = load_config().get("mcp", {})
    result = mcp_request("initialize", {
        "protocolVersion": mcp_config.get("protocol_version", "2024-11-05"),
        "capabilities": {"roots": {"listChanged": True}},
        "clientInfo": {
            "name": mcp_config.get("client_name", "dc-mcp-proxy"),
            "version": mcp_config.get("client_version", "1.0.0"),
        },
    })

    if "error" in result:
        logger.error("Failed to initialize MCP: %s", result["error"])
        _set_session_id(None)
        return False

    logger.info("MCP session initialized: %s", get_session_id())

    # Send initialized notification (no id, no response expected)
    mcp_request("notifications/initialized", {}, is_notification=True)
    return True


def mcp_call(method: str, params: dict = None) -> dict:
    """Send a request, establishing or re-establishing the session as needed.

    This is the entry point everything except the handshake should use. It
    makes a lost session a recoverable event: whichever data-plane instance the
    request lands on, if that instance does not recognise our session we mint a
    new one and retry exactly once.

    Retrying once rather than looping matters -- a genuine outage should surface
    as an error, not as an unbounded retry storm against a struggling backend.
    """
    if not get_session_id():
        initialize_mcp()

    result = mcp_request(method, params)

    if _looks_like_lost_session(result):
        logger.warning(
            "MCP session rejected by the server (likely a different data-plane "
            "instance); re-initialising and retrying %s once.", method
        )
        if initialize_mcp():
            result = mcp_request(method, params)

    return result


_REFRESH_LOCK = threading.Lock()
_refresh_in_flight = False


def _refresh_tools_in_background() -> None:
    """Populate the tool cache off the request path, at most one at a time."""
    global _refresh_in_flight
    with _REFRESH_LOCK:
        if _refresh_in_flight:
            return
        _refresh_in_flight = True

    def run():
        global _refresh_in_flight
        try:
            get_tools(force_refresh=True)
        except Exception:
            logger.warning("Background tool refresh failed.", exc_info=True)
        finally:
            with _REFRESH_LOCK:
                _refresh_in_flight = False

    threading.Thread(target=run, name="mcp-tools-refresh", daemon=True).start()


def cached_tools() -> list:
    """Whatever tools we already know about, without blocking on the network.

    For callers that must not block on the data plane -- notably /agent/health,
    which is what Cloud Run's uptime check hits. Calling get_tools() there meant
    a cold cache turned a health check into a live MCP round trip with a 300s
    timeout, so an unreachable backend made the agent look hung rather than
    unhealthy.

    An empty cache additionally kicks off a background refresh. Without that,
    reading the cache alone made health *under-report* rather than hang: if the
    startup probe failed, health kept reporting zero tools indefinitely while a
    live call would have succeeded. That is the normal case on a fresh CDC
    deploy, where the app plane starts before its run.invoker binding on the
    private data plane has propagated -- the probe fails once, and the stack
    then looks broken long after it is fine.
    """
    with _TOOLS_LOCK:
        tools = _TOOLS_CACHE["tools"] or []
    if not tools:
        _refresh_tools_in_background()
    return tools


def get_tools(force_refresh: bool = False) -> list:
    """Available tools, cached with a TTL and a lock.

    The previous cache was permanent-on-success and absent-on-failure, which
    meant (a) a tool-surface change on the data plane needed an agent restart,
    and (b) during an outage every request retried tools/list, adding two
    failing round trips per chat turn on top of the failure already happening.
    """
    now = time.time()
    with _TOOLS_LOCK:
        fresh = (now - _TOOLS_CACHE["fetched_at"]) < _TOOLS_TTL_SECONDS
        if _TOOLS_CACHE["tools"] and fresh and not force_refresh:
            return _TOOLS_CACHE["tools"]

    result = mcp_call("tools/list", {})
    tools = (result.get("result") or {}).get("tools")

    if tools:
        with _TOOLS_LOCK:
            _TOOLS_CACHE["tools"] = tools
            _TOOLS_CACHE["fetched_at"] = now
        return tools

    # Serve a stale list rather than nothing: an expired-but-known tool surface
    # is far more useful than an empty one, which would silently disable every
    # tool the model can call.
    with _TOOLS_LOCK:
        return _TOOLS_CACHE["tools"] or []


def call_tool(name: str, arguments: dict, session_logger: Optional[SessionLogger] = None) -> Any:
    """Call a tool on the MCP server with optional logging."""
    # Fix common parameter mistakes
    fixed_args = fix_tool_arguments(name, arguments)
    if fixed_args != arguments:
        logger.info(f"Fixed arguments: {arguments} -> {fixed_args}")

    # Log tool call request
    if session_logger:
        session_logger.log_mcp_tool_call(name, fixed_args)

    start_time = time.time()

    result = mcp_call("tools/call", {
        "name": name,
        "arguments": fixed_args
    })

    duration_ms = (time.time() - start_time) * 1000

    if "result" in result:
        # Log successful result
        if session_logger:
            session_logger.log_mcp_tool_result(name, result["result"], duration_ms, "success")
        return result["result"]

    # Log error result
    error_result = {"error": result.get("error", "Unknown error")}
    if session_logger:
        session_logger.log_mcp_tool_result(name, error_result, duration_ms, "error")
    return error_result
