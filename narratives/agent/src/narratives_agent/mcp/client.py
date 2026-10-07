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
using `mcp.ClientSession` and `streamable_http_client`. The public entry points
are the asynchronous `async_get_tools` and `async_call_tool`, plus
`cached_tools` for latency-sensitive callers that must not wait on the
network.

Every operation opens its own MCP connection on one shared, connection-pooled
`httpx2.AsyncClient`, so the 5 to 15 tool calls of a chat turn reuse
keep-alive connections instead of each paying a TCP and TLS handshake. The
shared client carries no per-operation state: the headers an operation needs
(authentication and `Mcp-Session-Id`) and the observer that reads its
responses travel in a `ContextVar` that the client's request and response
event hooks read. Concurrent operations therefore never see one another's
credentials or session IDs.

The MCP session persists across operations within the same turn. The
handshake stores the server-issued session ID and the negotiated
`InitializeResult`. Subsequent operations send that session ID in the
`Mcp-Session-Id` header and restore the negotiated protocol state with
`ClientSession.adopt`, avoiding repeated handshakes while preserving the
negotiated protocol version header. Connections are opened with
`terminate_on_close=False` so that closing an individual connection does not
send an `HTTP DELETE` request that would terminate the session on the server.

A turn's session lives in a mutable `_SessionScope` held in a
`contextvars.ContextVar`. `ensure_session_scope` creates the scope in the
parent task, and child tasks spawned afterwards (for example, concurrent tool
calls run in an `asyncio.TaskGroup`) copy a reference to the same scope, so they
share one handshake and see one another's re-initialization. Separate turns
run in separate request contexts and keep separate sessions.

Functions return plain dictionaries matching the MCP wire format expected by
`workflows/` and `mcp/data_utils.py`: `async_get_tools` returns tool
definitions with `"name"`, `"description"`, and `"inputSchema"`, and
`async_call_tool` returns the tool result dictionary (`"content"` and optional
`"structuredContent"`) or `{"error": <message>}` when the tool itself reports
an error. A transport or protocol failure is not a tool result: it raises
`McpTransportError`, whose message carries no endpoint or upstream detail, so
that callers abort the turn instead of passing a transport failure to the
model as a tool result.
"""

import asyncio
import logging
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any
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
# Establishing a TCP and TLS connection gets a much shorter budget than the
# exchange itself: an unreachable server should fail the turn in seconds
# rather than hold it until the request timeout.
_CONNECT_TIMEOUT_SECONDS = 10.0
# `_MAX_IDLE_CONNECTIONS` caps how many idle connections to the MCP server
# are kept open for reuse. Concurrent connections are not capped, matching
# the data-plane proxy client.
_MAX_IDLE_CONNECTIONS = 64

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
# individual session, so it is cached across turns. Expiring the cache after a
# fixed TTL allows the agent to pick up tool changes on the data plane without
# restarting.
_TOOLS_TTL_SECONDS = 600


@dataclass(frozen=True)
class _Session:
    """Holds the state of an established MCP session.

    `session_id` is `None` when the server completes the initialization
    handshake without issuing a session ID, as a stateless MCP server does.
    """

    session_id: str | None
    initialize_result: types.InitializeResult


@dataclass
class _SessionScope:
    """Holds the MCP session shared by every operation of one turn.

    The scope object is shared by reference between a parent task and the
    child tasks it spawns, so assigning `session` here is visible to all of
    them. `lock` serializes handshakes so that concurrent operations that
    find no session, or the same rejected session, perform one handshake
    between them.
    """

    session: _Session | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass
class _ToolCache:
    """Holds the most recently fetched tool list and when it was fetched."""

    tools: list[dict[str, Any]] | None = None
    fetched_at: float = 0.0


class _SessionLostError(Exception):
    """Raised when the MCP server no longer recognizes the current session."""


class McpTransportError(Exception):
    """Raised when an MCP request fails below the tool layer.

    This exception covers connection, HTTP, and protocol failures, including
    a failed handshake. The message is fixed and safe to surface; the
    underlying detail, which names the endpoint, is logged and kept as
    `__cause__`.
    """

    def __init__(self) -> None:
        super().__init__("The MCP server request failed.")


@dataclass
class _ResponseObserver:
    """Captures HTTP response details that `streamable_http_client` hides.

    `streamable_http_client` keeps the `Mcp-Session-Id` response header private
    to its internal transport and converts a bare HTTP 404 response into a
    generic `MCPError`. The shared client's response event hook forwards each
    response of an operation to that operation's observer, which lets the
    client read the server-issued session ID and detect bare HTTP 404
    responses directly.
    """

    session_id: str | None = None
    saw_not_found: bool = False

    def observe(self, response: httpx2.Response) -> None:
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


@dataclass(frozen=True)
class _Operation:
    """Holds per-operation state read by the shared client's event hooks."""

    headers: dict[str, str]
    observer: _ResponseObserver


@dataclass
class _HttpClientHolder:
    """Holds the shared HTTP client and the event loop it belongs to."""

    client: httpx2.AsyncClient | None = None
    loop: asyncio.AbstractEventLoop | None = None


_session_scope_var: ContextVar[_SessionScope | None] = ContextVar(
    "mcp_session_scope", default=None
)
# `streamable_http_client` sends requests from tasks it starts in an AnyIO
# task group, and AnyIO starts each task in a copy of the context that
# entered the transport. Setting this variable before entering the transport
# therefore scopes it to exactly one operation's requests.
_operation_var: ContextVar[_Operation | None] = ContextVar(
    "mcp_operation", default=None
)

_HTTP_CLIENT = _HttpClientHolder()

_TOOLS_LOCK = threading.Lock()
_TOOLS_CACHE = _ToolCache()

# `_REFRESH_TASKS` holds strong references to in-flight background tool
# refreshes. The event loop holds only weak references to tasks, so an
# unreferenced task can be garbage-collected before it finishes.
_REFRESH_TASKS: set[asyncio.Task[list[dict[str, Any]]]] = set()


def get_session_id() -> str | None:
    """Returns the MCP session ID for the current context, or `None`."""
    scope = _session_scope_var.get()
    if scope is None or scope.session is None:
        return None
    return scope.session.session_id


def ensure_session_scope() -> None:
    """Opens an MCP session scope in the current context if none is open.

    Call this in the parent task of a turn before spawning concurrent MCP
    operations. Child tasks inherit the scope, so they share one handshake
    and one session; a scope created inside a child task would be invisible
    to its siblings and its parent. Each request runs in its own context, so
    separate turns never share a scope.
    """
    _current_scope()


def reset_client() -> None:
    """Clears the cached URL, tool cache, refresh tasks, and session scope.

    The shared HTTP client is not closed here, because closing requires the
    event loop that owns it; call `aclose` from that loop.
    """
    _URL_CACHE.clear()
    with _TOOLS_LOCK:
        _TOOLS_CACHE.tools = None
        _TOOLS_CACHE.fetched_at = 0.0
    _REFRESH_TASKS.clear()
    _session_scope_var.set(None)


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


async def _apply_operation_headers(request: httpx2.Request) -> None:
    """Adds the current operation's headers to an outgoing request."""
    operation = _operation_var.get()
    if operation is not None:
        request.headers.update(operation.headers)


async def _observe_operation_response(response: httpx2.Response) -> None:
    """Forwards a response to the current operation's observer."""
    operation = _operation_var.get()
    if operation is not None:
        operation.observer.observe(response)


def _http_transport() -> httpx2.AsyncBaseTransport | None:
    """Returns the transport for the shared client.

    `None` selects the default network transport. Tests replace this function
    to route the client to an in-process server.
    """
    return None


def _http_client() -> httpx2.AsyncClient:
    """Returns the shared HTTP client for the running event loop.

    This function creates the client on first use and replaces it if it has
    been closed or if a different event loop is running, such as between
    tests. In production, a single event loop runs for the life of the
    server, so one client is reused across all requests.
    """
    loop = asyncio.get_running_loop()
    holder = _HTTP_CLIENT
    if (
        holder.client is None
        or holder.client.is_closed
        or holder.loop is not loop
    ):
        holder.client = httpx2.AsyncClient(
            transport=_http_transport(),
            timeout=httpx2.Timeout(
                _REQUEST_TIMEOUT_SECONDS, connect=_CONNECT_TIMEOUT_SECONDS
            ),
            limits=httpx2.Limits(
                max_connections=None,
                max_keepalive_connections=_MAX_IDLE_CONNECTIONS,
            ),
            event_hooks={
                "request": [_apply_operation_headers],
                "response": [_observe_operation_response],
            },
        )
        holder.loop = loop
    return holder.client


async def aclose() -> None:
    """Closes the shared HTTP client, if one is open on the running loop.

    Background tool refreshes on this loop are canceled first, so that none
    of them is still using the client when it closes.
    """
    running = asyncio.get_running_loop()
    # The list is a copy because each task removes itself from the set when
    # it finishes.
    pending = [
        task
        for task in _REFRESH_TASKS
        if task.get_loop() is running and not task.done()
    ]
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)

    holder = _HTTP_CLIENT
    client, loop = holder.client, holder.loop
    holder.client = None
    holder.loop = None
    if client is not None and loop is running:
        await client.aclose()


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

    When resuming an existing `session`, the session ID is added to each
    request by the shared client's request hook rather than passed through
    `streamable_http_client`'s transport, and no `notifications/initialized`
    message is sent. Because the transport's internal `session_id` remains
    `None`, the SDK never opens its background `GET` SSE stream on a resumed
    connection. This makes it safe for `_is_session_lost` to treat any
    non-JSON HTTP 404 recorded by `observer` on the connection as a rejected
    session ID on the `POST` request.

    Args:
        session: Existing session to resume on the new connection, or `None`
            when opening a connection for the initial handshake.
        observer: Records the session ID header and any bare HTTP 404
            responses on the connection.
    """
    url = mcp_url()
    headers: dict[str, str] = {}
    if session is not None and session.session_id:
        headers[_SESSION_ID_HEADER] = session.session_id
    # We attach authentication headers on every operation because credentials
    # depend on the target host and Google Cloud ID tokens expire over time.
    # For a localhost sidecar this is a no-op, whereas for a remote IAM-gated
    # MCP service it attaches a fresh bearer token or API key. A cold token
    # cache makes a blocking metadata-server request, so it runs in a worker
    # thread rather than on the event loop.
    await asyncio.to_thread(attach_auth, headers, url)
    token = _operation_var.set(_Operation(headers=headers, observer=observer))
    try:
        async with (
            streamable_http_client(
                url, http_client=_http_client(), terminate_on_close=False
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
    finally:
        _operation_var.reset(token)


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
    """Performs the MCP handshake and returns the new session.

    Raises:
        Exception: Any transport or protocol error from the handshake.
    """
    logger.info("Initializing MCP session...")
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
    logger.info(
        "MCP session initialized (server-issued session ID: %s).",
        "yes" if session.session_id else "no",
    )
    return session


def _current_scope() -> _SessionScope:
    """Returns the current session scope, creating one if none is open."""
    scope = _session_scope_var.get()
    if scope is None:
        scope = _SessionScope()
        _session_scope_var.set(scope)
    return scope


async def _ensure_session(
    scope: _SessionScope, stale: _Session | None
) -> _Session:
    """Returns a usable session for `scope`, performing a handshake if needed.

    A handshake runs only if the scope still holds `stale` (no session, or
    the session the server just rejected). An operation that waited on the
    lock while another performed the handshake reuses its result.

    Raises:
        Exception: Any transport or protocol error from the handshake. The
            scope is then left without a session.
    """
    async with scope.lock:
        if scope.session is not None and scope.session is not stale:
            return scope.session
        scope.session = None
        scope.session = await _initialize()
        return scope.session


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

    If the current scope has no session, this function performs the handshake
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
    scope = _current_scope()
    session = scope.session or await _ensure_session(scope, None)
    try:
        return await _run_once(session, operation)
    except _SessionLostError:
        logger.warning(
            "MCP session rejected by the server (likely a different data-plane "
            "instance); re-initializing and retrying %s once.",
            description,
        )
    session = await _ensure_session(scope, session)
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
    name: str, message: str, level: int = logging.ERROR
) -> dict[str, Any]:
    """Logs a failed tool call and returns its error result dictionary."""
    logger.log(level, "MCP tool %s failed: %s", name, message)
    return {"error": message}


async def async_call_tool(
    name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Calls a tool on the MCP server.

    Args:
        name: Name of the MCP tool to invoke.
        arguments: Tool arguments produced by the model. These are normalized
            with `fix_tool_arguments` before the request is sent.

    Returns:
        The tool result dictionary in its MCP wire format (`"content"` and
        optional `"structuredContent"`), or `{"error": <message>}` if the
        tool returned `isError: true` or the server rejected the call's
        arguments (`INVALID_PARAMS`, which also covers an unknown tool name).
        Those are failures the model can correct on its next iteration.

    Raises:
        McpTransportError: If the request failed for any other reason:
            connection, HTTP, or protocol errors, or a failed handshake.
    """
    fixed_args = fix_tool_arguments(name, arguments)
    if fixed_args != arguments:
        # Argument values can contain text from the user's query, so only the
        # names of the rewritten arguments are logged.
        changed = sorted(
            key
            for key in arguments.keys() | fixed_args.keys()
            if arguments.get(key) != fixed_args.get(key)
        )
        logger.info(
            "Fixed arguments for MCP tool %s: %s", name, ", ".join(changed)
        )

    try:
        result = await _run_with_session(
            f"tools/call {name}",
            lambda client_session: _send_tool_call(
                client_session, name, fixed_args
            ),
        )
    except Exception as error:
        if any(
            isinstance(leaf, MCPError)
            and leaf.error.code == types.INVALID_PARAMS
            for leaf in _leaf_errors(error)
        ):
            return _tool_failure(
                name, _describe_error(error), level=logging.WARNING
            )
        logger.error("MCP tool %s failed: %s", name, _describe_error(error))
        raise McpTransportError() from error

    if result.is_error:
        # When `is_error` is True, the MCP request succeeded at the transport
        # layer, but the tool itself reported an execution error that the model
        # can react to.
        return _tool_failure(
            name, _tool_error_message(result), level=logging.WARNING
        )

    # Pass `exclude_unset=True` and `exclude_none=True` so that Pydantic
    # serializes only the fields returned by the server without injecting
    # default values for omitted fields.
    return result.model_dump(
        mode="json", by_alias=True, exclude_unset=True, exclude_none=True
    )


def _refresh_tools_in_background() -> None:
    """Schedules a tool-cache refresh on the running event loop.

    At most one refresh is in flight at a time. If no event loop is running
    (for example, when called from synchronous code outside the server), no
    task is scheduled and the next asynchronous caller refreshes the cache
    instead.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.debug("No running event loop; skipping tool refresh.")
        return
    if any(not task.done() for task in _REFRESH_TASKS):
        return
    _REFRESH_TASKS.clear()
    task = loop.create_task(
        async_get_tools(force_refresh=True), name="mcp-tools-refresh"
    )
    _REFRESH_TASKS.add(task)
    task.add_done_callback(_REFRESH_TASKS.discard)


def cached_tools() -> list[dict[str, Any]]:
    """Returns the currently cached tool list without blocking on the network.

    This function is used by latency-sensitive endpoints such as `/agent/health`
    that are polled by Cloud Run uptime checks. Fetching tools on a cold cache
    would block the health check on an MCP network round trip with a
    300-second timeout, causing an unreachable data plane to make the agent
    appear hung rather than unhealthy.

    When no tool list has been fetched yet, this function schedules a
    background refresh and immediately returns `[]`. Without the background
    refresh, a failed startup probe would leave `/agent/health` reporting zero
    tools indefinitely if no chat traffic arrived. This commonly occurs on a
    fresh Custom Data Commons deployment when the app container starts before
    its `roles/run.invoker` IAM binding on the private data plane has finished
    propagating.
    """
    with _TOOLS_LOCK:
        tools = _TOOLS_CACHE.tools
    if tools is None:
        _refresh_tools_in_background()
        return []
    return tools
