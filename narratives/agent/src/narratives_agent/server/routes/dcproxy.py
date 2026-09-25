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
"""Same-origin reverse proxy from the app plane to the data plane.

The Data Commons web components fetch their own data from
`window.location.origin` -- that is upstream's design, not ours -- and the two
iframe tools read `contentDocument` to inject CSS, which browsers only permit
same-origin. So the browser's data routes have to appear on the app plane's
origin even though the data plane is a separate service.

Pointing the components at the data plane's own URL instead would be simpler,
and CORS is already permissive on /core/api/ -- but it is ruled out twice over:
IAP would mean a second sign-in session for the second origin, and the iframe
tools would break outright.

So those routes land here and are replayed against DATA_PLANE_URL. When the
data plane is IAM-gated the agent's service-account ID token is attached; when
it is only network-restricted (ingress=internal) the token is harmless surplus.
Either way the browser never needs a Google credential, which it could not
obtain anyway.
"""

import logging
from collections.abc import AsyncIterator
from urllib.parse import urlsplit, urlunsplit

import httpx2
from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from starlette.background import BackgroundTask
from starlette.requests import ClientDisconnect

from narratives_agent.gcp_auth import attach_auth
from narratives_agent.server.responses import ClosingStreamingResponse
from narratives_agent.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Prefixes that must go to the MCP/API host rather than the web host.
#
# Splitting the two upstreams is only correct per-route. /mcp belongs to the API
# host: datacommons.org answers 405 for it, so sending the browser's MCP calls
# to the web host breaks them while the agent -- which dials MCP_SERVER_URL
# directly and never touches this proxy -- keeps working. That asymmetry hides
# the fault from /agent/health and from chat, and it is exactly what happened
# when this split was first added.
_MCP_HOST_PREFIXES = frozenset({"mcp"})


def _upstream_for(prefix: str) -> str:
    """Which host serves this prefix. Identical on cdc and dcp."""
    settings = get_settings()
    return (
        settings.data_plane_url
        if prefix in _MCP_HOST_PREFIXES
        else settings.data_plane_web_url
    )


# Upper bound on each phase of an upstream request: connect, write, read,
# and waiting for a pooled connection.
_UPSTREAM_TIMEOUT_SECONDS = 120.0
# Idle upstream connections kept open for reuse.
_MAX_IDLE_CONNECTIONS = 64


def create_client() -> httpx2.AsyncClient:
    """Builds the client that sends every proxied request.

    The application opens one for its lifetime, for the same reason the MCP
    client has one pooled session: a single page of charts fires many of these
    requests and each would otherwise pay a TLS handshake. Up to
    _MAX_IDLE_CONNECTIONS idle connections stay open for reuse, and concurrent
    requests are not capped. Redirects are returned to the browser rather than
    followed; see _same_origin_location.
    """
    return httpx2.AsyncClient(
        timeout=httpx2.Timeout(_UPSTREAM_TIMEOUT_SECONDS),
        limits=httpx2.Limits(
            max_connections=None,
            max_keepalive_connections=_MAX_IDLE_CONNECTIONS,
        ),
        follow_redirects=False,
    )


# Top-level path segments owned by the data plane. Derived from the route list
# in ui/vite.config.ts, which is the same set the dev proxy has always
# forwarded -- keep the two in sync.
#
# Anything not listed here falls through to the SPA, which is the safe default:
# a missing entry shows up as "Uncaught SyntaxError: Unexpected token '<'"
# inside a tool iframe (index.html served where JavaScript was expected).
DATA_PLANE_PREFIXES = (
    "api",
    "core",
    "mcp",
    "node",
    "browser",
    "tools",
    "explore",
    "disease",
    "nl",
    "admin",
    "place",
    "ranking",
    "topic",
    "custom_dc",
    "datacommons",
    "files",
    "sitemap",
    "css",
    "datacommons.js",
    "queryStore.js",
    "base.js",
    "download.js",
    "stat_var.js",
)

# Headers that must not be forwarded upstream.
#
# The IAP entries are the important ones. With IAP in front, Cloud Run hands
# this container IAP's own Authorization token, whose audience is THIS service.
# Forwarding it alongside our service-account token gives the data plane a
# mixed-identity context and it refuses the request -- which surfaces as a 401
# on every chart *after* the user has already signed in successfully, and reads
# like an authorization bug rather than a header-hygiene one.
_HOP_HEADERS = frozenset(
    {
        "host",
        "authorization",
        "connection",
        "keep-alive",
        "transfer-encoding",
        "te",
        "upgrade",
        "proxy-authorization",
        "proxy-authenticate",
        "trailers",
        "content-length",
        "accept-encoding",
        "x-goog-iap-jwt-assertion",
        "x-goog-authenticated-user-email",
        "x-goog-authenticated-user-id",
        "x-serverless-authorization",
        "cookie",
        # The agent attaches its own key for the host it calls (attach_auth).
        # A caller's key would otherwise be sent alongside it, first.
        "x-api-key",
    }
)

# Upstream response headers that are not copied to the browser, as lowercase
# bytes. Uvicorn writes its own Date and Server, so copying the upstream's
# would send each twice.
_RESPONSE_HEADER_BLOCKLIST = frozenset(
    {
        b"content-encoding",
        b"transfer-encoding",
        b"connection",
        b"content-length",
        b"date",
        b"server",
    }
)

# The status codes Uvicorn can send (RFC 9110 section 15).
_MIN_STATUS = 100
_MAX_STATUS = 599


async def _forward(request: Request, subpath: str, prefix: str) -> Response:
    """Replays `request` on the data plane and streams the response back."""
    # Named upstream_url, not upstream: the response object below is called
    # `upstream`, and letting a URL and a Response share a name is how a later
    # edit reaches for the wrong one.
    upstream_url = _upstream_for(prefix)
    if not upstream_url:
        return JSONResponse(
            {"error": "DATA_PLANE_URL is not configured on the agent"},
            status_code=503,
        )

    # A header sent on several lines is forwarded as one, its values joined
    # with ", " (RFC 9110 section 5.3), so no value is lost. Cookie, whose
    # values join with "; " instead, never reaches the join: it is in
    # _HOP_HEADERS.
    headers: dict[str, str] = {}
    for k, v in request.headers.items():
        name = k.lower()
        if name in _HOP_HEADERS:
            continue
        headers[name] = f"{headers[name]}, {v}" if name in headers else v

    body: AsyncIterator[bytes] | None = None
    if request.method in ("POST", "PUT", "PATCH"):
        body = request.stream()
        # The body is relayed byte for byte, so the caller's Content-Length
        # still describes it, even though content-length is in _HOP_HEADERS.
        # Without it the client would send the body chunked.
        if "content-length" in request.headers:
            headers["content-length"] = request.headers["content-length"]

    # Auth is chosen by the host actually being called, not by a single
    # global -- the two hosts differ on the "none" backend, and attaching a
    # credential scoped to the wrong host is how the API key would leak
    # somewhere it does not belong.
    #
    # attach_auth runs in a worker thread: on a token-cache miss it blocks on
    # the metadata server for up to 5 seconds, which would stall every
    # request on the event loop.
    await run_in_threadpool(attach_auth, headers, upstream_url)
    # Sent as bytes, which httpx2 does not re-encode. The server decoded each
    # header as Latin-1, so encoding it back yields the bytes the caller sent;
    # httpx2 would encode a str as ASCII and raise on any byte above 0x7F.
    raw_headers = [
        (name.encode("latin-1"), value.encode("latin-1"))
        for name, value in headers.items()
    ]

    client: httpx2.AsyncClient = request.app.state.data_plane_client
    try:
        upstream_request = client.build_request(
            request.method,
            _target_url(request, upstream_url),
            content=body,
            headers=raw_headers,
        )
    except (httpx2.InvalidURL, UnicodeDecodeError) as e:
        logger.warning(
            "dcproxy: %s /%s rejected: invalid URL: %s",
            request.method,
            subpath,
            e,
        )
        return JSONResponse({"error": "Invalid request URL"}, status_code=400)
    try:
        upstream = await client.send(upstream_request, stream=True)
    except httpx2.RequestError as e:
        logger.error(
            "dcproxy: %s %s failed: %s", request.method, upstream_request.url, e
        )
        return JSONResponse(
            {"error": f"Data plane unreachable: {e}"}, status_code=502
        )
    except ClientDisconnect:
        # The browser went away while its body was being relayed. Nothing
        # reads this response; returning it only ends the request.
        logger.info(
            "dcproxy: %s /%s canceled: client disconnected during upload",
            request.method,
            subpath,
        )
        return Response(status_code=400)

    # From here on the upstream response is open, and only the response
    # returned below will close it. Anything that fails before then closes it
    # here, or its connection would stay checked out until shutdown.
    try:
        return await _relay(upstream, upstream_url, request.method, subpath)
    except BaseException:
        await upstream.aclose()
        raise


def _target_url(request: Request, upstream_url: str) -> str:
    """Returns the data-plane URL for `request`.

    The path is taken still percent-encoded from `raw_path`, so it reaches the
    data plane as the browser sent it: a decoded `%23` or `%3F` would become a
    fragment or query delimiter, and a decoded control character would make
    the URL invalid.

    Raises:
        UnicodeDecodeError: `raw_path` holds a byte outside ASCII.
    """
    raw_path: bytes = request.scope["raw_path"]
    target = f"{upstream_url}{raw_path.decode('ascii')}"
    query_string: bytes = request.scope["query_string"]
    if query_string:
        target = f"{target}?{query_string.decode('utf-8', 'ignore')}"
    return target


async def _relay(
    upstream: httpx2.Response, upstream_url: str, method: str, subpath: str
) -> Response:
    """Returns the response that streams `upstream` back to the browser."""
    status = upstream.status_code
    # Surface upstream failures in the log -- this is the first place to look
    # when charts or tools do not render. 401/403 = IAM or ingress, 404 = the
    # path is not served by the data plane, 5xx = the backend itself.
    if status >= 400:
        logger.warning(
            "dcproxy: %s /%s -> HTTP %d from data plane",
            method,
            subpath,
            status,
        )
    # Uvicorn cannot send a status line outside this range, and would fail
    # after the response had already been handed over.
    if not _MIN_STATUS <= status <= _MAX_STATUS:
        await upstream.aclose()
        logger.error(
            "dcproxy: %s /%s -> invalid status %d from data plane",
            method,
            subpath,
            status,
        )
        return JSONResponse(
            {"error": "Invalid response from data plane"}, status_code=502
        )

    response = ClosingStreamingResponse(
        _stream_upstream(upstream),
        status_code=status,
        # Also closes the upstream response when streaming stops before the
        # generator's `finally` can run, as it does when the client
        # disconnects, whatever ASGI spec version the server reports (see
        # ClosingStreamingResponse). aclose() does nothing on a closed
        # response.
        background=BackgroundTask(upstream.aclose),
    )
    # Copied as the bytes the data plane sent. Decoding and re-encoding would
    # raise on a UTF-8 value, such as a non-ASCII filename in
    # Content-Disposition, and would silently change one in the Latin-1 range.
    # Appended one at a time, so a repeated header such as Set-Cookie keeps
    # every value instead of the last one replacing the others.
    for raw_name, raw_value in upstream.headers.raw:
        name = raw_name.lower()
        if name in _RESPONSE_HEADER_BLOCKLIST:
            continue
        value = raw_value
        if name == b"location" and 300 <= status < 400:
            value = _same_origin_location(
                raw_value.decode("latin-1"), upstream_url
            ).encode("latin-1")
        response.raw_headers.append((name, value))
    return response


def _same_origin_location(location: str, upstream_url: str) -> str:
    """Points a redirect to the data plane's own host back through the proxy.

    The client does not follow redirects; the browser does. A Location that
    names the data plane's host would take the browser off this origin, and
    datacommons.org answers `/browser` with `http://datacommons.org/browser/`.
    Such a Location becomes a path on this origin, which the proxy serves.
    Any other Location, including one that does not parse, is returned
    unchanged.
    """
    try:
        target = urlsplit(location)
        upstream_netloc = urlsplit(upstream_url).netloc
    except ValueError:
        return location
    if target.netloc.lower() != upstream_netloc.lower():
        return location
    # Browsers read a path that starts with "//" or "/\" as a scheme-relative
    # URL naming another host, so `https://<data plane>//evil.example/x`
    # would otherwise become a redirect to evil.example. One leading slash is
    # kept and the rest are dropped.
    path = "/" + target.path.lstrip("/\\")
    return urlunsplit(("", "", path, target.query, target.fragment))


async def _stream_upstream(upstream: httpx2.Response) -> AsyncIterator[bytes]:
    """Yields the upstream body in chunks.

    aiter_bytes() decodes any Content-Encoding, which is why content-encoding
    is in _RESPONSE_HEADER_BLOCKLIST. httpx2 closes the upstream response
    itself when iteration completes or raises. When the client disconnects,
    streaming stops while this generator is suspended, so neither httpx2 nor
    the `finally` block runs; the response's background task closes the
    upstream instead. The `finally` block closes it when the generator
    itself is closed early. A response closed before its body is fully read
    closes its connection rather than returning it to the pool.
    """
    try:
        async for chunk in upstream.aiter_bytes():
            yield chunk
    finally:
        await upstream.aclose()


def _register_prefix(prefix: str) -> None:
    """Routes both `/<prefix>` and `/<prefix>/<anything>` to the data plane.

    Registered as two explicit routes rather than one catch-all so that unknown
    paths still fall through to the SPA. The closure binds the prefix: FastAPI
    fills a handler parameter that is not in the path from the query string,
    so a prefix parameter would let `?prefix=mcp` choose the upstream.
    """
    methods = ["GET", "POST", "OPTIONS", "HEAD"]

    async def forward_root(request: Request) -> Response:
        return await _forward(request, prefix, prefix)

    async def forward_subpath(subpath: str, request: Request) -> Response:
        return await _forward(request, f"{prefix}/{subpath}", prefix)

    router.api_route(f"/{prefix}", methods=methods)(forward_root)
    router.api_route(f"/{prefix}/{{subpath:path}}", methods=methods)(
        forward_subpath
    )


for _prefix in DATA_PLANE_PREFIXES:
    _register_prefix(_prefix)
