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
import os

import requests
from flask import Blueprint, Response, jsonify, request, stream_with_context

from src.gcp_auth import attach_auth

logger = logging.getLogger(__name__)

dcproxy_bp = Blueprint("dcproxy", __name__)

# Base URL of the data-plane service. Empty means "not split yet" -- the routes
# below then report a clear 503 instead of proxying to nowhere.
DATA_PLANE_URL = os.environ.get("DATA_PLANE_URL", "").rstrip("/")

# Where the browser's data routes go, which is not always where MCP goes.
#
# On dcp one container serves both, so this is unset. On "none" they are two
# hosts: api.datacommons.org serves the REST API and /mcp, while the routes the
# chart components call (/api/observations/series, /api/place/name,
# /core/api/...) exist only on datacommons.org. Send chart traffic to the API
# host and Cloud Endpoints 404s every chart, with nothing looking wrong
# server-side. Falls back to DATA_PLANE_URL.
DATA_PLANE_WEB_URL = os.environ.get("DATA_PLANE_WEB_URL", "").rstrip("/") or DATA_PLANE_URL

# Prefixes that must go to the API host rather than the web host. /mcp is one:
# datacommons.org answers 405 for it. Getting this wrong breaks only the
# browser's MCP calls -- the agent dials MCP_SERVER_URL directly and never
# touches this proxy -- so chat and /agent/health both stay green.
_MCP_HOST_PREFIXES = frozenset({"mcp"})


def _upstream_for(prefix: str) -> str:
    """Which host serves this prefix. Identical on cdc and dcp."""
    return DATA_PLANE_URL if prefix in _MCP_HOST_PREFIXES else DATA_PLANE_WEB_URL

# One pooled session, for the same reason the MCP client has one: a single page
# of charts fires many of these and each would otherwise pay a TLS handshake.
_SESSION = requests.Session()
_SESSION.mount("https://", requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=64))
_SESSION.mount("http://", requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=64))

# Top-level path segments owned by the data plane. Derived from the route list
# in ui/vite.config.ts, which is the same set the dev proxy has always
# forwarded -- keep the two in sync.
#
# Anything not listed here falls through to the SPA, which is the safe default:
# a missing entry shows up as "Uncaught SyntaxError: Unexpected token '<'"
# inside a tool iframe (index.html served where JavaScript was expected).
DATA_PLANE_PREFIXES = (
    "api", "core", "mcp", "node", "browser", "tools", "explore", "disease",
    "nl", "admin", "place", "ranking", "topic", "custom_dc", "datacommons",
    "files", "sitemap", "css",
    "datacommons.js", "queryStore.js", "base.js", "download.js", "stat_var.js",
)

# Headers that must not be forwarded upstream.
#
# The IAP entries are the important ones. With IAP in front, Cloud Run hands
# this container IAP's own Authorization token, whose audience is THIS service.
# Forwarding it alongside our service-account token gives the data plane a
# mixed-identity context and it refuses the request -- which surfaces as a 401
# on every chart *after* the user has already signed in successfully, and reads
# like an authorisation bug rather than a header-hygiene one.
_HOP_HEADERS = frozenset(
    {
        "host", "authorization", "connection", "keep-alive",
        "transfer-encoding", "te", "upgrade", "proxy-authorization",
        "proxy-authenticate", "trailers", "content-length", "accept-encoding",
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


def _forward(subpath: str, prefix: str) -> Response:
    """Replay the current request against the data plane and stream it back."""
    # Named upstream_url, not upstream: the response object below is called
    # `upstream`, and letting a URL and a Response share a name is how a later
    # edit reaches for the wrong one.
    upstream_url = _upstream_for(prefix)
    if not upstream_url:
        return jsonify({"error": "DATA_PLANE_URL is not configured on the agent"}), 503

    target = f"{upstream_url}/{subpath}"
    if request.query_string:
        target = f"{target}?{request.query_string.decode('utf-8', 'ignore')}"

    headers = {
        k: v for k, v in request.headers.items() if k.lower() not in _HOP_HEADERS
    }
    # Auth is chosen by the host actually being called, not by a single global --
    # the two hosts differ on the "none" backend, and attaching a credential
    # scoped to the wrong host is how the API key would leak somewhere it does
    # not belong.
    attach_auth(headers, upstream_url)

    # TODO(juliawu): stream the body once this service is on FastAPI (see comment
    # in PR 472)
    try:
        upstream = _SESSION.request(
            request.method,
            target,
            data=request.get_data() if request.method in ("POST", "PUT", "PATCH") else None,
            headers=headers,
            stream=True,
            timeout=120,
        )
    except Exception as e:  # pylint: disable=broad-except
        logger.error("dcproxy: %s %s failed: %s", request.method, target, e)
        return jsonify({"error": f"Data plane unreachable: {e}"}), 502

    # Surface upstream failures in the log -- this is the first place to look
    # when charts or tools do not render. 401/403 = IAM or ingress, 404 = the
    # path is not served by the data plane, 5xx = the backend itself.
    if upstream.status_code >= 400:
        logger.warning(
            "dcproxy: %s /%s -> HTTP %d from data plane",
            request.method, subpath, upstream.status_code,
        )

    return Response(
        stream_with_context(upstream.iter_content(chunk_size=8192)),
        status=upstream.status_code,
        headers=[
            (k, v) for k, v in upstream.raw.headers.items()
            if k.lower() not in _RESPONSE_HEADER_BLOCKLIST
        ],
    )


def _register_prefix(prefix: str) -> None:
    """Route both `/<prefix>` and `/<prefix>/<anything>` to the data plane.

    Registered as explicit rules rather than one catch-all so that unknown
    paths still fall through to the SPA, and so these take precedence over
    spa.py's single-segment `/<name>` root-asset rule (Werkzeug prefers a
    static rule part over a converter).
    """
    methods = ["GET", "POST", "OPTIONS", "HEAD"]
    # Flask forbids "." in an endpoint name (it separates blueprint from
    # endpoint), and several prefixes are filenames -- datacommons.js,
    # queryStore.js. The URL rule keeps the dot; only the name is sanitised.
    name = prefix.replace(".", "_")

    dcproxy_bp.add_url_rule(
        f"/{prefix}",
        endpoint=f"{name}_root",
        view_func=lambda p=prefix: _forward(p, p),
        methods=methods,
    )
    dcproxy_bp.add_url_rule(
        f"/{prefix}/<path:subpath>",
        endpoint=name,
        view_func=lambda subpath, p=prefix: _forward(f"{p}/{subpath}", p),
        methods=methods,
    )


for _prefix in DATA_PLANE_PREFIXES:
    _register_prefix(_prefix)
