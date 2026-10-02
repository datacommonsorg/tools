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
"""MCP client built on the official `mcp` Python SDK.

The client communicates with the MCP server over the Streamable HTTP transport
using `mcp.ClientSession` and `streamable_http_client` backed by
`httpx2.AsyncClient`.

Each MCP operation is available in both asynchronous and synchronous forms:

- `async_initialize_mcp`, `async_get_tools`, and `async_call_tool` are
  asynchronous functions for callers running on an event loop.
- `initialize_mcp`, `get_tools`, and `call_tool` are synchronous wrappers for
  the existing blocking callers in `workflows/`. They will be removed in the
  next migration stage when `workflows/` is converted to asynchronous code.

Each operation opens its own HTTP connection, while the MCP session persists
across operations within the same turn. The handshake stores the server-issued
session ID and the negotiated `InitializeResult`. Subsequent operations send
that session ID in the `Mcp-Session-Id` header and restore the negotiated
protocol state with `ClientSession.adopt`, avoiding repeated handshakes while
preserving the negotiated protocol version header. Connections are opened with
`terminate_on_close=False` so that closing an individual HTTP connection does
not send an `HTTP DELETE` request that would terminate the session on the
server.

Session state is stored in a `contextvars.ContextVar` so that concurrent
asyncio tasks and threads maintain separate MCP sessions without overwriting
one another's session IDs.

Functions return plain dictionaries matching the MCP wire format expected by
`workflows/` and `mcp/data_utils.py`: `get_tools` returns tool definitions
with `"name"`, `"description"`, and `"inputSchema"`, and `call_tool` returns
the tool result dictionary (`"content"` and optional `"structuredContent"`) or
`{"error": <message>}` when a call fails.
"""

import asyncio
import contextvars
import logging
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx2
from mcp import ClientSession, MCPError, types
from mcp.client.streamable_http import streamable_http_client

from narratives_agent.config import load_config
from narratives_agent.gcp_auth import attach_auth
from narratives_agent.mcp.schema import fix_tool_arguments
from narratives_agent.settings import get_settings

logger = logging.getLogger(__name__)

# Each HTTP exchange with the MCP server, including streamed tool results,
# times out after 300 seconds.
_REQUEST_TIMEOUT_SECONDS = 300.0

_SESSION_ID_HEADER = "Mcp-Session-Id"
_HTTP_NOT_FOUND = 404

_DEFAULT_CLIENT_NAME = "dc-mcp-proxy"
_DEFAULT_CLIENT_VERSION = "1.0.0"

# The endpoint URL is resolved on first use rather than at import time because
# `load_config()` reads `config.json`, which `bootstrap_config_from_url()`
# writes during application startup. Storing the cached URL in a dictionary
# avoids rebinding a module-level variable with `global`.
_URL_CACHE: dict[str, str] = {}

# Different MCP server versions report an unrecognized or expired session with
# different error text and do not share a standard JSON-RPC error code. We
# match these substrings case-insensitively against the error message to detect
# when a session must be re-initialized.
_SESSION_LOST_MARKERS = (
    "session not found",
    "invalid session",
    "unknown session",
    "session expired",
    "missing session",
)

# The list of available tools is a property of the MCP server rather than an
# individual session, so it is cached across threads and tasks. Expiring the
# cache after a fixed TTL allows the agent to pick up tool changes on the data
# plane without restarting.
_TOOLS_TTL_SECONDS = 600


class SessionLoggerLike(Protocol):
    """Defines the `SessionLogger` methods used by the MCP client.

    `SessionLogger` is not yet type-annotated, so the client depends on this
    protocol instead of importing the untyped class directly.
    """

    def log_mcp_tool_call(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> None: ...

    def log_mcp_tool_result(
        self, tool_name: str, result: Any, duration_ms: float, status: str
    ) -> None: ...


@dataclass(frozen=True)
class _Session:
    """Holds the state of an established MCP session.

    `session_id` is `None` when the server completes the initialization
    handshake without issuing a session ID, as a stateless MCP server does.
    """

    session_id: str | None
    initialize_result: types.InitializeResult


@dataclass
class _ToolCache:
    """Holds the most recently fetched tool list and when it was fetched."""

    tools: list[dict[str, Any]] | None = None
    fetched_at: float = 0.0


class _SessionLostError(Exception):
    """Raised when the MCP server no longer recognizes the current session."""


@dataclass
class _ResponseObserver:
    """Captures HTTP response details that `streamable_http_client` hides.

    `streamable_http_client` keeps the `Mcp-Session-Id` response header private
    to its internal transport and converts a bare HTTP 404 response into a
    generic `MCPError`. Attaching this observer as an `httpx2` response event
    hook on each connection lets the client read the server-issued session ID
    and detect bare HTTP 404 responses directly.
    """

    session_id: str | None = None
    saw_not_found: bool = False

    async def __call__(self, response: httpx2.Response) -> None:
        """Records `Mcp-Session-Id` and whether a bare HTTP 404 occurred.

        An HTTP 404 response with a JSON body is ignored here because the SDK
        parses and raises the JSON-RPC error, which `_is_session_lost` inspects
        by message.
        """
        session_id = response.headers.get(_SESSION_ID_HEADER)
        if session_id and self.session_id is None:
            self.session_id = session_id
        content_type = response.headers.get("content-type", "").lower()
        if response.status_code == _HTTP_NOT_FOUND and not (
            content_type.startswith("application/json")
        ):
            self.saw_not_found = True


# The MCP session of the current thread or asyncio task.
_session_var: ContextVar[_Session | None] = ContextVar(
    "mcp_session", default=None
)

# The tool list shared by all threads and tasks, and the lock that guards it.
_TOOLS_LOCK = threading.Lock()
_TOOLS_CACHE = _ToolCache()


def get_session_id() -> str | None:
    """Returns the MCP session ID for the current context, or `None`."""
    session = _session_var.get()
    return session.session_id if session else None


def reset_client() -> None:
    """Clears the cached URL, the tool cache, and the current session."""
    _URL_CACHE.clear()
    with _TOOLS_LOCK:
        _TOOLS_CACHE.tools = None
        _TOOLS_CACHE.fetched_at = 0.0
    _session_var.set(None)


def _normalize_url(url: str) -> str:
    """Appends `/mcp` when the configured URL is a bare origin with no path.

    Configuration files often specify `mcp.server_url` as a bare origin such as
    `http://127.0.0.1:8082`, while the MCP endpoint is served at `/mcp`.
    Normalizing bare origins prevents configuration values without a path from
    failing with HTTP 404.
    """
    if urlparse(url).path in ("", "/"):
        return url.rstrip("/") + "/mcp"
    return url


def mcp_url() -> str:
    """Resolves and caches the MCP server endpoint URL.

    Checks `MCP_SERVER_URL` first, then `mcp.server_url` in the agent
    configuration, and finally falls back to `http://localhost:<mcp_port>/mcp`
    for co-located sidecar deployments. The resolved URL is cached after the
    first call.
    """
    if "url" in _URL_CACHE:
        return _URL_CACHE["url"]

    settings = get_settings()
    configured = settings.mcp_server_url
    if not configured:
        mcp_config = load_config().get("mcp", {})
        configured = str(mcp_config.get("server_url") or "").strip()

    resolved = (
        _normalize_url(configured)
        if configured
        else f"http://localhost:{settings.mcp_port}/mcp"
    )
    _URL_CACHE["url"] = resolved
    logger.info("MCP endpoint resolved to %s", resolved)
    return resolved


def _create_http_client(headers: dict[str, str]) -> httpx2.AsyncClient:
    """Returns an `httpx2.AsyncClient` configured for a single MCP operation.

    Each operation opens its own client, so each of the 5 to 15 tool calls in a
    chat turn opens its own connection and, when the MCP server runs outside
    this container, performs its own TLS handshake. A shared keep-alive pool
    will be introduced once the synchronous wrappers (which create a fresh
    event loop per call) are removed.
    """
    return httpx2.AsyncClient(
        headers=headers, timeout=httpx2.Timeout(_REQUEST_TIMEOUT_SECONDS)
    )


def _client_info() -> types.Implementation:
    """Returns the client name and version sent during the MCP handshake."""
    mcp_config = load_config().get("mcp", {})
    return types.Implementation(
        name=mcp_config.get("client_name", _DEFAULT_CLIENT_NAME),
        version=mcp_config.get("client_version", _DEFAULT_CLIENT_VERSION),
    )


@asynccontextmanager
async def _connect(
    session: _Session | None, observer: _ResponseObserver
) -> AsyncIterator[ClientSession]:
    """Opens a Streamable HTTP connection and yields a `ClientSession`.

    When resuming an existing `session`, the session ID is sent via the
    `AsyncClient` default headers rather than `streamable_http_client`'s
    `session_id` parameter, and no `notifications/initialized` message is sent.
    Because the transport's internal `session_id` remains `None`, the SDK never
    opens its background `GET` SSE stream on a resumed connection. This makes
    it safe for `_is_session_lost` to treat any non-JSON HTTP 404 recorded by
    `observer` on the connection as a rejected session ID on the `POST`
    request.

    Args:
        session: Existing session to resume on the new connection, or `None`
            when opening a connection for the initial handshake.
        observer: Response event hook that records the session ID header and
            any bare HTTP 404 responses on the connection.
    """
    url = mcp_url()
    headers: dict[str, str] = {}
    if session is not None and session.session_id:
        headers[_SESSION_ID_HEADER] = session.session_id
    # We attach authentication headers on every operation because credentials
    # depend on the target host and Google Cloud ID tokens expire over time.
    # For a localhost sidecar this is a no-op, whereas for a remote IAM-gated
    # MCP service it attaches a fresh bearer token or API key.
    attach_auth(headers, url)
    http_client = _create_http_client(headers)
    http_client.event_hooks["response"].append(observer)
    async with (
        http_client,
        streamable_http_client(
            url, http_client=http_client, terminate_on_close=False
        ) as (read_stream, write_stream),
        ClientSession(
            read_stream,
            write_stream,
            client_info=_client_info() if session is None else None,
        ) as client_session,
    ):
        if session is not None:
            client_session.adopt(session.initialize_result)
        yield client_session


def _leaf_errors(error: BaseException) -> list[BaseException]:
    """Flattens `error` and any nested exception groups into leaf exceptions.

    The MCP SDK runs transport tasks inside AnyIO task groups, which wrap
    exceptions in one `ExceptionGroup` per nesting level.
    """
    if isinstance(error, BaseExceptionGroup):
        return [
            leaf for inner in error.exceptions for leaf in _leaf_errors(inner)
        ]
    return [error]


def _describe_error(error: BaseException) -> str:
    """Returns a human-readable error message for a failed MCP operation."""
    leaves = _leaf_errors(error)
    if any(isinstance(leaf, httpx2.ConnectError) for leaf in leaves):
        return (
            f"Cannot connect to MCP server at {mcp_url()}. Make sure it's "
            "running!"
        )
    # When the HTTP writer task fails, closing its stream causes
    # `ClientSession` to fail any pending request with `CONNECTION_CLOSED`.
    # Prefer the underlying transport or protocol exception over that
    # secondary stream-closure error.
    leaf = next(
        (
            item
            for item in leaves
            if not (
                isinstance(item, MCPError)
                and item.error.code == types.CONNECTION_CLOSED
            )
        ),
        leaves[0],
    )
    return str(leaf) or type(leaf).__name__


def _is_session_lost(
    error: BaseException, observer: _ResponseObserver, session: _Session
) -> bool:
    """Returns whether `error` means the server does not recognize `session`.

    Some MCP server versions return a JSON-RPC error message stating that the
    session was not found, whereas the MCP Streamable HTTP specification allows
    a server to respond with a bare HTTP 404 when given an unknown session ID.
    """
    if session.session_id is not None and observer.saw_not_found:
        return True
    return any(
        marker in str(leaf).lower()
        for leaf in _leaf_errors(error)
        for marker in _SESSION_LOST_MARKERS
    )


async def _initialize() -> _Session:
    """Performs the MCP handshake and stores the new session in the context.

    Raises:
        Exception: Any transport or protocol error from the handshake. When an
            error occurs, the current context is left without a session.
    """
    logger.info("Initializing MCP session...")
    _session_var.set(None)
    observer = _ResponseObserver()
    async with _connect(None, observer) as client_session:
        result = await client_session.initialize()
        # `ClientSession.initialize()` returns as soon as the
        # `notifications/initialized` message is queued to the internal memory
        # stream, before the HTTP writer task finishes sending the POST
        # request. Sending a ping waits for the writer to flush that
        # notification before `_connect` closes the HTTP connection. If the
        # server rejects `ping`, we log and ignore the error because the
        # handshake itself has already completed.
        try:
            await client_session.send_ping()
        except MCPError as error:
            logger.debug("MCP ping after the handshake failed: %s", error)
    session = _Session(session_id=observer.session_id, initialize_result=result)
    _session_var.set(session)
    logger.info(
        "MCP session initialized (server-issued session ID: %s).",
        "yes" if session.session_id else "no",
    )
    return session


async def _run_once[T](
    session: _Session, operation: Callable[[ClientSession], Awaitable[T]]
) -> T:
    """Runs `operation` on a new connection that resumes `session`.

    Raises:
        _SessionLostError: If the server no longer recognizes `session`.
    """
    observer = _ResponseObserver()
    try:
        async with _connect(session, observer) as client_session:
            return await operation(client_session)
    except Exception as error:
        if _is_session_lost(error, observer, session):
            raise _SessionLostError(_describe_error(error)) from error
        raise


# An MCP Streamable HTTP session is held in memory on the server instance that
# created it. Because Cloud Run does not guarantee request affinity, a later
# request in the same turn can reach a different data-plane instance that does
# not recognize the session ID. `_run_with_session` recovers from this by
# initializing a new session and retrying the operation once.
async def _run_with_session[T](
    description: str, operation: Callable[[ClientSession], Awaitable[T]]
) -> T:
    """Runs `operation`, initializing or recovering the MCP session if needed.

    If the current context has no session, this function performs the handshake
    first; if the handshake fails, the error is raised without sending
    `operation`. If the server rejects an existing session as unknown, this
    function initializes a fresh session and retries `operation` once. Retrying
    at most once ensures that a persistent backend failure surfaces immediately
    instead of looping indefinitely.

    Args:
        description: Human-readable name of the operation for log messages.
        operation: Async callable that performs the MCP request on a connected
            `ClientSession`.

    Raises:
        Exception: Any transport or protocol error, including a second session
            rejection after retrying.
    """
    session = _session_var.get()
    if session is None:
        session = await _initialize()
    try:
        return await _run_once(session, operation)
    except _SessionLostError:
        logger.warning(
            "MCP session rejected by the server (likely a different data-plane "
            "instance); re-initializing and retrying %s once.",
            description,
        )
    session = await _initialize()
    return await _run_once(session, operation)


def _tool_dict(tool: types.Tool) -> dict[str, Any]:
    """Converts an `mcp.types.Tool` model into a wire-format dictionary."""
    definition = tool.model_dump(
        mode="json", by_alias=True, exclude_unset=True, exclude_none=True
    )
    definition.setdefault("description", "")
    return definition


async def _send_tool_call(
    client_session: ClientSession, name: str, arguments: dict[str, Any]
) -> types.CallToolResult:
    """Sends a `tools/call` request on `client_session`.

    `ClientSession.call_tool` validates structured tool output against the
    tool's schema, which triggers an extra `tools/list` request whenever the
    `ClientSession` instance has not cached the tool list. Because each
    operation creates a new `ClientSession`, calling `client_session.call_tool`
    would add an extra `tools/list` round trip to every tool call. Sending
    `CallToolRequest` directly via `send_request` avoids that extra request.
    """
    return await client_session.send_request(
        types.CallToolRequest(
            params=types.CallToolRequestParams(name=name, arguments=arguments)
        ),
        types.CallToolResult,
    )


def _tool_error_message(result: types.CallToolResult) -> str:
    """Extracts the error message text from a failed `CallToolResult`."""
    texts = [
        block.text
        for block in result.content
        if isinstance(block, types.TextContent)
    ]
    return "\n".join(texts) or "Tool call failed"


def _elapsed_ms(start: float) -> float:
    """Returns the time elapsed since `start` in milliseconds."""
    return (time.monotonic() - start) * 1000


async def async_initialize_mcp() -> bool:
    """Performs the MCP initialization handshake for the current context.

    Calling this function when a session already exists replaces it with a new
    session.

    Returns:
        `True` if the handshake succeeded, or `False` if it failed. On failure,
        the error is logged and the current context is left without a session.
    """
    try:
        await _initialize()
    except Exception as error:
        logger.error("Failed to initialize MCP: %s", _describe_error(error))
        _session_var.set(None)
        return False
    return True


async def async_get_tools(
    force_refresh: bool = False,
) -> list[dict[str, Any]]:
    """Returns the server's tool definitions, cached for `_TOOLS_TTL_SECONDS`.

    Args:
        force_refresh: If `True`, fetches the tool list from the server even
            when the cached list has not expired.

    Returns:
        A list of tool definition dictionaries containing `"name"`,
        `"description"`, and `"inputSchema"`. A successful response is cached
        even when it lists no tools. If the fetch fails, returns the most
        recently cached tool list, or `[]` if no list has been fetched yet.
    """
    now = time.monotonic()
    with _TOOLS_LOCK:
        fresh = (now - _TOOLS_CACHE.fetched_at) < _TOOLS_TTL_SECONDS
        if _TOOLS_CACHE.tools is not None and fresh and not force_refresh:
            return _TOOLS_CACHE.tools

    try:
        result = await _run_with_session(
            "tools/list", lambda client_session: client_session.list_tools()
        )
    except Exception as error:
        logger.error("MCP tools/list failed: %s", _describe_error(error))
        # Return the previously cached list rather than an empty list so that
        # a transient failure does not disable all tools for later turns.
        with _TOOLS_LOCK:
            return _TOOLS_CACHE.tools or []

    tools = [_tool_dict(tool) for tool in result.tools]
    with _TOOLS_LOCK:
        _TOOLS_CACHE.tools = tools
        _TOOLS_CACHE.fetched_at = now
    return tools


def _tool_failure(
    name: str,
    message: str,
    start: float,
    session_logger: SessionLoggerLike | None,
    level: int = logging.ERROR,
) -> dict[str, Any]:
    """Logs a failed tool call and returns its error result dictionary."""
    logger.log(level, "MCP tool %s failed: %s", name, message)
    error_result = {"error": message}
    if session_logger:
        session_logger.log_mcp_tool_result(
            name, error_result, _elapsed_ms(start), "error"
        )
    return error_result


async def async_call_tool(
    name: str,
    arguments: dict[str, Any],
    session_logger: SessionLoggerLike | None = None,
) -> dict[str, Any]:
    """Calls a tool on the MCP server.

    Args:
        name: Name of the MCP tool to invoke.
        arguments: Tool arguments produced by the model. These are normalized
            with `fix_tool_arguments` before the request is sent.
        session_logger: Optional logger that records the tool call and its
            result.

    Returns:
        The tool result dictionary in its MCP wire format (`"content"` and
        optional `"structuredContent"`), or `{"error": <message>}` if the
        request failed or the tool returned `isError: true`.
    """
    fixed_args = fix_tool_arguments(name, arguments)
    if fixed_args != arguments:
        logger.info("Fixed arguments: %s -> %s", arguments, fixed_args)

    if session_logger:
        session_logger.log_mcp_tool_call(name, fixed_args)

    start = time.monotonic()
    try:
        result = await _run_with_session(
            f"tools/call {name}",
            lambda client_session: _send_tool_call(
                client_session, name, fixed_args
            ),
        )
    except Exception as error:
        return _tool_failure(
            name, _describe_error(error), start, session_logger
        )

    if result.is_error:
        # When `is_error` is True, the MCP request succeeded at the transport
        # layer, but the tool itself reported an execution error that the model
        # can react to.
        return _tool_failure(
            name,
            _tool_error_message(result),
            start,
            session_logger,
            level=logging.WARNING,
        )

    # Pass `exclude_unset=True` and `exclude_none=True` so that Pydantic
    # serializes only the fields returned by the server without injecting
    # default values for omitted fields.
    payload = result.model_dump(
        mode="json", by_alias=True, exclude_unset=True, exclude_none=True
    )
    if session_logger:
        session_logger.log_mcp_tool_result(
            name, payload, _elapsed_ms(start), "success"
        )
    return payload


def _run_sync[T](operation: Callable[[], Coroutine[Any, Any, T]]) -> T:
    """Runs an async MCP operation to completion from synchronous code.

    `asyncio.Runner.run` executes the coroutine inside a task using the
    provided `context`. Copying the context before running and restoring
    `_session_var` in the `finally` block ensures that any session created or
    cleared inside the coroutine is preserved in the calling thread's context,
    both when the coroutine returns normally and when it raises an exception.

    Raises:
        RuntimeError: If called from a thread that already has a running event
            loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError(
            "Synchronous MCP functions cannot be called from a running event "
            "loop; await the async_* function instead."
        )
    context = contextvars.copy_context()
    try:
        with asyncio.Runner() as runner:
            return runner.run(operation(), context=context)
    finally:
        _session_var.set(context.get(_session_var))


def initialize_mcp() -> bool:
    """Synchronously performs the MCP handshake for the calling thread.

    See `async_initialize_mcp` for details.
    """
    return _run_sync(async_initialize_mcp)


def get_tools(force_refresh: bool = False) -> list[dict[str, Any]]:
    """Synchronously returns the MCP server's tool definitions.

    See `async_get_tools` for details.
    """
    return _run_sync(lambda: async_get_tools(force_refresh))


def call_tool(
    name: str,
    arguments: dict[str, Any],
    session_logger: SessionLoggerLike | None = None,
) -> dict[str, Any]:
    """Synchronously calls a tool on the MCP server.

    See `async_call_tool` for details.
    """
    return _run_sync(lambda: async_call_tool(name, arguments, session_logger))


_REFRESH_LOCK = threading.Lock()
_refresh_in_flight = False


def _refresh_tools_in_background() -> None:
    """Starts a background thread to refresh the tool cache if needed."""
    global _refresh_in_flight
    with _REFRESH_LOCK:
        if _refresh_in_flight:
            return
        _refresh_in_flight = True

    def run() -> None:
        global _refresh_in_flight
        try:
            get_tools(force_refresh=True)
        except Exception:
            logger.warning("Background tool refresh failed.", exc_info=True)
        finally:
            with _REFRESH_LOCK:
                _refresh_in_flight = False

    threading.Thread(target=run, name="mcp-tools-refresh", daemon=True).start()


def cached_tools() -> list[dict[str, Any]]:
    """Returns the currently cached tool list without blocking on the network.

    This function is used by latency-sensitive endpoints such as `/agent/health`
    that are polled by Cloud Run uptime checks. Fetching tools synchronously on
    a cold cache would block the health check on an MCP network round trip with
    a 300-second timeout, causing an unreachable data plane to make the agent
    appear hung rather than unhealthy.

    When no tool list has been fetched yet, this function starts a background
    refresh and immediately returns `[]`. Without the background refresh, a
    failed startup probe would leave `/agent/health` reporting zero tools
    indefinitely if no chat traffic arrived. This commonly occurs on a fresh
    Custom Data Commons deployment when the app container starts before its
    `roles/run.invoker` IAM binding on the private data plane has finished
    propagating.
    """
    with _TOOLS_LOCK:
        tools = _TOOLS_CACHE.tools
    if tools is None:
        _refresh_tools_in_background()
        return []
    return tools
