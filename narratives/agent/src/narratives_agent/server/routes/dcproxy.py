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
from collections.abc import Iterator
from typing import Annotated

import requests
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from narratives_agent.gcp_auth import attach_auth
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


# One pooled session, for the same reason the MCP client has one: a single page
# of charts fires many of these and each would otherwise pay a TLS handshake.
_SESSION = requests.Session()
_SESSION.mount(
    "https://",
    requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=64),
)
_SESSION.mount(
    "http://",
    requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=64),
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
    }
)

_RESPONSE_HEADER_BLOCKLIST = frozenset(
    {"content-encoding", "transfer-encoding", "connection", "content-length"}
)


async def _read_body(request: Request) -> bytes | None:
    """Returns the request body for methods that carry one, or else None.

    Runs as a dependency on the event loop, so the synchronous handler
    receives the body already read and a GET never reads one at all.
    """
    if request.method in ("POST", "PUT", "PATCH"):
        return await request.body()
    return None


def _forward(
    request: Request, body: bytes | None, subpath: str, prefix: str
) -> Response:
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

    target = f"{upstream_url}/{subpath}"
    query_string: bytes = request.scope["query_string"]
    if query_string:
        target = f"{target}?{query_string.decode('utf-8', 'ignore')}"

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
    # Auth is chosen by the host actually being called, not by a single
    # global -- the two hosts differ on the "none" backend, and attaching a
    # credential scoped to the wrong host is how the API key would leak
    # somewhere it does not belong.
    attach_auth(headers, upstream_url)

    # TODO(juliawu): stream the body once this service is on FastAPI (see
    # comment in PR 472)
    try:
        upstream = _SESSION.request(
            request.method,
            target,
            data=body,
            headers=headers,
            stream=True,
            timeout=120,
        )
    except requests.RequestException as e:
        logger.error("dcproxy: %s %s failed: %s", request.method, target, e)
        return JSONResponse(
            {"error": f"Data plane unreachable: {e}"}, status_code=502
        )

    # Surface upstream failures in the log -- this is the first place to look
    # when charts or tools do not render. 401/403 = IAM or ingress, 404 = the
    # path is not served by the data plane, 5xx = the backend itself.
    if upstream.status_code >= 400:
        logger.warning(
            "dcproxy: %s /%s -> HTTP %d from data plane",
            request.method,
            subpath,
            upstream.status_code,
        )

    response = StreamingResponse(
        _stream_upstream(upstream), status_code=upstream.status_code
    )
    # Appended one at a time, so a repeated header such as Set-Cookie keeps
    # every value instead of the last one replacing the others.
    for k, v in upstream.raw.headers.items():
        if k.lower() not in _RESPONSE_HEADER_BLOCKLIST:
            response.headers.append(k, v)
    return response


def _stream_upstream(upstream: requests.Response) -> Iterator[bytes]:
    """Yields the upstream body in chunks, then closes the upstream response.

    The `finally` block returns the connection to the pool however the stream
    ends: completed, failed, or closed early when the client disconnects.
    """
    try:
        yield from upstream.iter_content(chunk_size=8192)
    finally:
        upstream.close()


def _register_prefix(prefix: str) -> None:
    """Routes both `/<prefix>` and `/<prefix>/<anything>` to the data plane.

    Registered as two explicit routes rather than one catch-all so that unknown
    paths still fall through to the SPA. The closure binds the prefix: FastAPI
    fills a handler parameter that is not in the path from the query string,
    so a prefix parameter would let `?prefix=mcp` choose the upstream.
    """
    methods = ["GET", "POST", "OPTIONS", "HEAD"]

    def forward_root(
        request: Request, body: Annotated[bytes | None, Depends(_read_body)]
    ) -> Response:
        return _forward(request, body, prefix, prefix)

    def forward_subpath(
        subpath: str,
        request: Request,
        body: Annotated[bytes | None, Depends(_read_body)],
    ) -> Response:
        return _forward(request, body, f"{prefix}/{subpath}", prefix)

    router.api_route(f"/{prefix}", methods=methods)(forward_root)
    router.api_route(f"/{prefix}/{{subpath:path}}", methods=methods)(
        forward_subpath
    )


for _prefix in DATA_PLANE_PREFIXES:
    _register_prefix(_prefix)
