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
"""End-to-end HTTP proxy tests for `server.routes.dcproxy`.

Verifies the proxy's behavior across the HTTP boundary using the application
test client and an upstream served by `httpx2.MockTransport`:
1. `/mcp` requests are forwarded to `DATA_PLANE_URL`, while website and web
   component routes (`/api`, `/core`, `/place`, `/datacommons.js`) are forwarded
   to `DATA_PLANE_WEB_URL`.
2. Incoming caller identity headers (`Authorization`,
   `X-Goog-Iap-Jwt-Assertion`, `X-Goog-Authenticated-User-Email`,
   `X-Goog-Authenticated-User-Id`) are stripped before forwarding.
3. `X-API-Key` is attached when forwarding to an allowlisted public Data Commons
   host (`api.datacommons.org`) and omitted when forwarding to an unlisted host.
4. Upstream transfer-framing headers (`Content-Encoding`, `Transfer-Encoding`,
   `Content-Length`) are stripped from the proxied response, whose body is
   decoded.
5. An unconfigured `DATA_PLANE_URL` returns HTTP 503, and an upstream transport
   exception returns HTTP 502.
6. A query parameter cannot choose the upstream: the query string is forwarded
   unchanged, and the route's own prefix selects the host.
7. Repeated upstream response headers, such as two `Set-Cookie` headers, reach
   the client as separate headers.
8. A POST body reaches the upstream unchanged with the caller's
   `Content-Length`, and a GET sends no body.
9. The upstream response is closed when the browser disconnects mid-stream,
   under ASGI spec 2.3 and 2.4, and when the upstream fails mid-body, whose
   error propagates.
10. A redirect to the data plane's own host is returned as a path on the app's
    origin that no browser reads as another host, and any other redirect is
    returned unchanged.
11. Upstream header values reach the client byte for byte, a Location on a
    response that is not a redirect is relayed unchanged, and an upstream
    status outside 100-599 returns HTTP 502; the upstream is closed in each
    case.
12. The path is forwarded still percent-encoded, and a path or query string
    that is not ASCII returns HTTP 400.
13. A caller's `X-API-Key` never reaches the upstream, and the upstream's
    `Date` and `Server` headers are not copied.
14. Request header values reach the upstream byte for byte, including bytes
    outside ASCII.
15. A client that disconnects during a streamed upload ends the request
    without an error escaping the application.
16. A proxied request writes no INFO record to the `httpx2` logger.
"""

import asyncio
import gc
import gzip
import logging
from collections.abc import AsyncIterator, Sequence

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import ClientDisconnect
from starlette.types import ASGIApp, Message, Scope

from narratives_agent import gcp_auth
from narratives_agent.server.routes import dcproxy

_API_HOST = "https://api.datacommons.org"
_WEB_HOST = "https://datacommons.org"
_API_KEY = "test-dc-api-key"


class _ClosingStream(httpx2.AsyncByteStream):
    """Upstream response body that records whether it was closed.

    Yields `body` as one chunk, then raises `error` when one is set.
    """

    def __init__(self, body: bytes, error: Exception | None = None) -> None:
        self._body = body
        self._error = error
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self._body
        if self._error is not None:
            raise self._error

    async def aclose(self) -> None:
        self.closed = True


def _http_scope(
    path: str,
    raw_path: bytes,
    *,
    method: str = "GET",
    headers: Sequence[tuple[bytes, bytes]] = (),
    query_string: bytes = b"",
    spec_version: str = "2.3",
) -> Scope:
    """Returns the scope of a request as Uvicorn builds it.

    The scope reports ASGI spec 2.3 unless told otherwise, as Uvicorn does,
    which selects the Starlette code path that watches for a client
    disconnect.
    """
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": spec_version},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": raw_path,
        "root_path": "",
        "query_string": query_string,
        "headers": list(headers),
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 5001),
        "state": {},
    }


def _asgi_get(
    app: ASGIApp,
    path: str,
    raw_path: bytes,
    headers: Sequence[tuple[bytes, bytes]] = (),
    query_string: bytes = b"",
) -> Message:
    """Sends `GET` to `app` over ASGI and returns its response start message.

    The test client encodes request header values as UTF-8 and decodes
    response header values as UTF-8 before re-encoding them as ASCII, so it
    can neither send nor read an arbitrary header byte; this carries the
    headers exactly as given and as the application sent them. It likewise
    percent-encodes the query string, which this passes through raw.
    """
    starts: list[Message] = []
    request_delivered = False

    async def receive() -> Message:
        nonlocal request_delivered
        if not request_delivered:
            request_delivered = True
            return {"type": "http.request", "body": b""}
        # The client stays connected; the response finishing ends the wait.
        await asyncio.Event().wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.start":
            starts.append(message)

    scope = _http_scope(
        path, raw_path, headers=headers, query_string=query_string
    )
    asyncio.run(app(scope, receive, send))
    return starts[0]


class _Upstream:
    """`MockTransport` handler that records each request the proxy sends.

    Every call answers with a new response built from `status_code`,
    `headers`, and `body`, or raises `error` when one is set.
    """

    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []
        self.status_code = 200
        self.headers: list[tuple[str, str]] | list[tuple[bytes, bytes]] = [
            ("Content-Type", "application/json")
        ]
        self.body: bytes | httpx2.AsyncByteStream = b"proxied-payload"
        self.error: Exception | None = None

    @property
    def calls(self) -> list[tuple[str, str, httpx2.Headers]]:
        """Each forwarded request as its method, URL, and headers."""
        return [(r.method, str(r.url), r.headers) for r in self.requests]

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if isinstance(self.body, bytes):
            return httpx2.Response(
                self.status_code, headers=self.headers, content=self.body
            )
        return httpx2.Response(
            self.status_code, headers=self.headers, stream=self.body
        )


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Upstream:
    """Returns the stub upstream, with clean auth defaults configured."""
    monkeypatch.delenv("DATA_PLANE_AUTH", raising=False)
    monkeypatch.setenv("DC_API_KEY", _API_KEY)
    monkeypatch.setattr(gcp_auth, "get_id_token", lambda audience: "fake-jwt")
    return _Upstream()


@pytest.fixture
def client(recorder: _Upstream) -> TestClient:
    """Returns a test client for an app that serves only `dcproxy.router`.

    The app's data-plane client sends every request to `recorder`.
    """
    app = FastAPI()
    app.include_router(dcproxy.router)
    app.state.data_plane_client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(recorder)
    )
    return TestClient(app)


@pytest.fixture
def split_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure distinct API and website hosts for public Data Commons."""
    monkeypatch.setenv("DATA_PLANE_URL", _API_HOST)
    monkeypatch.setenv("DATA_PLANE_WEB_URL", _WEB_HOST)


@pytest.mark.usefixtures("split_hosts")
def test_mcp_route_forwards_to_api_host(
    client: TestClient,
    recorder: _Upstream,
) -> None:
    # Test: Upstream target URL when proxying `/mcp`.
    # Situation: `DATA_PLANE_URL` and `DATA_PLANE_WEB_URL` point to distinct
    #   hosts (`api.datacommons.org` and `datacommons.org`), and a client sends
    #   `GET /mcp`.
    # Expectation: The proxy forwards the request to `DATA_PLANE_URL/mcp` and
    #   returns the upstream HTTP 200 payload.
    response = client.get("/mcp")
    assert response.status_code == 200
    assert response.content == b"proxied-payload"
    assert len(recorder.calls) == 1
    _, target_url, _ = recorder.calls[0]
    assert target_url == f"{_API_HOST}/mcp"


@pytest.mark.parametrize(
    "path",
    [
        "/api/observations/series?entities=geoId/06",
        "/core/api/v2/node",
        "/place/geoId/06",
        "/datacommons.js",
    ],
)
@pytest.mark.usefixtures("split_hosts")
def test_website_routes_forward_to_web_host(
    path: str,
    client: TestClient,
    recorder: _Upstream,
) -> None:
    # Test: Upstream target URL for non-MCP data-plane routes.
    # Situation: `DATA_PLANE_URL` and `DATA_PLANE_WEB_URL` point to distinct
    #   hosts, and a client requests a website or chart component route.
    # Expectation: The proxy forwards the request (including any query string)
    #   to `DATA_PLANE_WEB_URL`.
    response = client.get(path)
    assert response.status_code == 200
    assert len(recorder.calls) == 1
    _, target_url, _ = recorder.calls[0]
    assert target_url == f"{_WEB_HOST}{path}"


@pytest.mark.parametrize("path", ["/mcp", "/api/place/name", "/core/api/node"])
def test_single_host_deployment_forwards_all_routes_to_same_host(
    path: str,
    client: TestClient,
    recorder: _Upstream,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Upstream target URL when a single service hosts both API and web
    #   routes.
    # Situation: Both `DATA_PLANE_URL` and `DATA_PLANE_WEB_URL` resolve to the
    #   same Cloud Run service URL.
    # Expectation: Every proxied path is forwarded to that single host.
    one_host = "https://data-plane-uc.a.run.app"
    monkeypatch.setenv("DATA_PLANE_URL", one_host)
    monkeypatch.setenv("DATA_PLANE_WEB_URL", one_host)

    response = client.get(path)
    assert response.status_code == 200
    _, target_url, _ = recorder.calls[0]
    assert target_url == f"{one_host}{path}"


def test_incoming_caller_identity_headers_are_stripped(
    client: TestClient,
    recorder: _Upstream,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Stripping of incoming IAP and caller authorization headers.
    # Situation: An incoming request carries `Authorization`,
    #   `X-Goog-Iap-Jwt-Assertion`, `X-Goog-Authenticated-User-Email`, and
    #   `X-Goog-Authenticated-User-Id` alongside an application header
    #   (`X-Request-Id`), and `DATA_PLANE_AUTH` is `"off"` so the agent adds no
    #   outbound auth header of its own.
    # Expectation: None of the caller identity headers reach the upstream
    #   request, while `X-Request-Id` is preserved.
    monkeypatch.setenv("DATA_PLANE_URL", "http://localhost:8082")
    monkeypatch.setenv("DATA_PLANE_AUTH", "off")

    response = client.get(
        "/mcp",
        headers={
            "Authorization": "Bearer caller-iap-token",
            "X-Goog-Iap-Jwt-Assertion": "iap-jwt-assertion",
            "X-Goog-Authenticated-User-Email": "user@example.com",
            "X-Goog-Authenticated-User-Id": "12345",
            "X-Request-Id": "trace-abc",
        },
    )
    assert response.status_code == 200
    _, _, forwarded_headers = recorder.calls[0]
    lowered = {k.lower(): v for k, v in forwarded_headers.items()}
    assert lowered.get("x-request-id") == "trace-abc"
    assert "authorization" not in lowered
    assert "x-goog-iap-jwt-assertion" not in lowered
    assert "x-goog-authenticated-user-email" not in lowered
    assert "x-goog-authenticated-user-id" not in lowered


@pytest.mark.usefixtures("split_hosts")
def test_repeated_request_headers_are_joined(
    client: TestClient,
    recorder: _Upstream,
) -> None:
    # Test: Forwarding of a request header sent on more than one line.
    # Situation: A client sends two `Accept` header lines on `GET /mcp`.
    # Expectation: The upstream request carries one `Accept` header whose
    #   value joins both values with ", ", in the order they arrived.
    response = client.get(
        "/mcp",
        headers=[("Accept", "text/html"), ("Accept", "application/json")],
    )
    assert response.status_code == 200
    _, _, forwarded_headers = recorder.calls[0]
    assert forwarded_headers["accept"] == "text/html, application/json"


def test_api_key_is_attached_for_public_dc_and_omitted_for_unlisted_host(
    client: TestClient,
    recorder: _Upstream,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Host-scoped credential attachment during proxying.
    # Situation: `DATA_PLANE_URL` points to `https://api.datacommons.org` while
    #   `DATA_PLANE_WEB_URL` points to an unlisted external host
    #   (`https://unlisted.example.com`).
    # Expectation: Forwarding `/mcp` attaches `X-API-Key`, whereas forwarding
    #   `/api/observations` to the unlisted host does not attach `X-API-Key`.
    monkeypatch.setenv("DATA_PLANE_URL", _API_HOST)
    monkeypatch.setenv("DATA_PLANE_WEB_URL", "https://unlisted.example.com")

    client.get("/mcp")
    client.get("/api/observations")

    assert len(recorder.calls) == 2
    _, _, mcp_headers = recorder.calls[0]
    _, _, web_headers = recorder.calls[1]
    assert mcp_headers.get("X-API-Key") == _API_KEY
    assert "X-API-Key" not in web_headers


def test_unconfigured_data_plane_url_returns_503(
    client: TestClient,
    recorder: _Upstream,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Proxy response when `DATA_PLANE_URL` is unconfigured.
    # Situation: Both `DATA_PLANE_URL` and `DATA_PLANE_WEB_URL` are empty.
    # Expectation: `GET /api/observations` returns HTTP 503 without sending
    #   anything upstream.
    monkeypatch.setenv("DATA_PLANE_URL", "")
    monkeypatch.setenv("DATA_PLANE_WEB_URL", "")

    response = client.get("/api/observations")
    assert response.status_code == 503
    assert recorder.calls == []


@pytest.mark.usefixtures("split_hosts")
def test_upstream_request_exception_returns_502(
    client: TestClient,
    recorder: _Upstream,
) -> None:
    # Test: Error handling when the upstream request fails.
    # Situation: The upstream transport raises `httpx2.ConnectError`.
    # Expectation: The proxy catches the exception and returns HTTP 502.
    recorder.error = httpx2.ConnectError("upstream connection refused")

    response = client.get("/api/observations")
    assert response.status_code == 502
    assert "Data plane unreachable" in response.json()["error"]


@pytest.mark.usefixtures("split_hosts")
def test_upstream_framing_headers_are_not_copied_to_response(
    client: TestClient,
    recorder: _Upstream,
) -> None:
    # Test: Filtering of upstream framing headers on proxied responses.
    # Situation: The upstream response has a gzip-compressed body and includes
    #   `Content-Encoding: gzip`, `Transfer-Encoding: chunked`, and
    #   `Content-Length: 999` alongside `X-Upstream-Status: ok`.
    # Expectation: The client receives the decompressed body without
    #   `Content-Encoding`, `Transfer-Encoding`, or the upstream
    #   `Content-Length`, while `X-Upstream-Status` is preserved.
    recorder.body = gzip.compress(b"decoded-body")
    recorder.headers = [
        ("Content-Encoding", "gzip"),
        ("Transfer-Encoding", "chunked"),
        ("Content-Length", "999"),
        ("X-Upstream-Status", "ok"),
    ]

    response = client.get("/mcp")
    assert response.status_code == 200
    assert response.content == b"decoded-body"
    assert response.headers.get("X-Upstream-Status") == "ok"
    assert "Content-Encoding" not in response.headers
    assert "Transfer-Encoding" not in response.headers
    assert response.headers.get("Content-Length") != "999"


@pytest.mark.parametrize("name", ["p", "prefix"])
@pytest.mark.usefixtures("split_hosts")
def test_a_query_parameter_cannot_redirect_the_root_route(
    name: str,
    client: TestClient,
    recorder: _Upstream,
) -> None:
    # Test: Upstream selection for a prefix root route when the query string
    #   names another prefix.
    # Situation: `DATA_PLANE_URL` and `DATA_PLANE_WEB_URL` point to distinct
    #   hosts, and a client requests `/api` with a query parameter whose value
    #   is the `mcp` prefix.
    # Expectation: The proxy forwards the request to `DATA_PLANE_WEB_URL/api`
    #   with the query string unchanged, so the parameter selects neither the
    #   host nor the path.
    response = client.get(f"/api?{name}=mcp")
    assert response.status_code == 200
    assert len(recorder.calls) == 1
    _, target_url, _ = recorder.calls[0]
    assert target_url == f"{_WEB_HOST}/api?{name}=mcp"


@pytest.mark.parametrize("name", ["p", "prefix"])
@pytest.mark.usefixtures("split_hosts")
def test_a_query_parameter_cannot_redirect_a_subpath_route(
    name: str,
    client: TestClient,
    recorder: _Upstream,
) -> None:
    # Test: Upstream selection for a prefix subpath route when the query
    #   string names another prefix.
    # Situation: `DATA_PLANE_URL` and `DATA_PLANE_WEB_URL` point to distinct
    #   hosts, and a client requests `/api/observations` with a query
    #   parameter whose value is the `mcp` prefix.
    # Expectation: The proxy forwards the request to
    #   `DATA_PLANE_WEB_URL/api/observations` with the query string unchanged,
    #   so the parameter selects neither the host nor the path.
    response = client.get(f"/api/observations?{name}=mcp")
    assert response.status_code == 200
    assert len(recorder.calls) == 1
    _, target_url, _ = recorder.calls[0]
    assert target_url == f"{_WEB_HOST}/api/observations?{name}=mcp"


@pytest.mark.usefixtures("split_hosts")
def test_repeated_response_headers_are_not_collapsed(
    client: TestClient,
    recorder: _Upstream,
) -> None:
    # Test: Preservation of repeated upstream response headers.
    # Situation: The upstream response carries two `Set-Cookie` headers and
    #   two `Vary` headers.
    # Expectation: The proxied response carries all four as separate headers,
    #   in upstream order, rather than keeping one value per name.
    recorder.headers = [
        ("Set-Cookie", "a=1"),
        ("Set-Cookie", "b=2"),
        ("Vary", "Accept"),
        ("Vary", "Origin"),
    ]

    response = client.get("/mcp")
    assert response.status_code == 200
    repeated = [
        (key, value)
        for key, value in response.headers.multi_items()
        if key in ("set-cookie", "vary")
    ]
    assert repeated == [
        ("set-cookie", "a=1"),
        ("set-cookie", "b=2"),
        ("vary", "Accept"),
        ("vary", "Origin"),
    ]


@pytest.mark.usefixtures("split_hosts")
def test_post_body_reaches_upstream_with_the_callers_content_length(
    client: TestClient,
    recorder: _Upstream,
) -> None:
    # Test: Forwarding of a request body.
    # Situation: A client posts a JSON body to `/api/observations`.
    # Expectation: The upstream request carries the same bytes with the
    #   caller's `Content-Length`, and is not sent chunked.
    body = b'{"entities": ["geoId/06"], "variables": ["Count_Person"]}'

    response = client.post(
        "/api/observations",
        content=body,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 200
    sent = recorder.requests[0]
    assert sent.method == "POST"
    assert sent.content == body
    assert sent.headers["content-length"] == str(len(body))
    assert "transfer-encoding" not in sent.headers


@pytest.mark.usefixtures("split_hosts")
def test_get_sends_no_body(
    client: TestClient,
    recorder: _Upstream,
) -> None:
    # Test: Forwarding of a request without a body.
    # Situation: A client sends `GET /api/observations`.
    # Expectation: The upstream request has an empty body and neither
    #   `Content-Length` nor `Transfer-Encoding`.
    response = client.get("/api/observations")

    assert response.status_code == 200
    sent = recorder.requests[0]
    assert sent.content == b""
    assert "content-length" not in sent.headers
    assert "transfer-encoding" not in sent.headers


@pytest.mark.parametrize("spec_version", ["2.3", "2.4"])
@pytest.mark.usefixtures("split_hosts")
def test_client_disconnect_closes_the_upstream_before_the_response_ends(
    spec_version: str,
    client: TestClient,
    recorder: _Upstream,
) -> None:
    # Test: Release of the upstream response when the browser disconnects.
    # Situation: The upstream body is a stream that records when it is
    #   closed. The app is driven over ASGI with `GET /mcp`. Under spec 2.3,
    #   which Uvicorn reports, `send` blocks on the first body chunk, as a
    #   stalled socket write does, and `receive` then answers
    #   `http.disconnect`. Under spec 2.4, `send` raises `OSError` on that
    #   chunk instead, as a server does once the socket is gone. The garbage
    #   collector is disabled, so collection cannot close the stream.
    # Expectation: The upstream stream has been closed by the time the
    #   application returns.
    stream = _ClosingStream(b"streamed-payload")
    recorder.body = stream

    async def drive() -> None:
        body_sent = asyncio.Event()
        request_delivered = False

        async def receive() -> Message:
            nonlocal request_delivered
            if not request_delivered:
                request_delivered = True
                return {"type": "http.request", "body": b""}
            await body_sent.wait()
            return {"type": "http.disconnect"}

        async def send(message: Message) -> None:
            if message["type"] == "http.response.body" and message["body"]:
                if spec_version == "2.4":
                    raise OSError("connection reset")
                body_sent.set()
                # Never returns; the disconnect cancels it.
                await asyncio.Event().wait()

        scope = _http_scope("/mcp", b"/mcp", spec_version=spec_version)
        try:
            await client.app(scope, receive, send)
        except ClientDisconnect:
            # Under spec 2.4 the disconnect leaves the application as this
            # error, which the server discards.
            assert spec_version == "2.4"
        # Read before the event loop runs again: asyncio finalizes an
        # abandoned async generator on a later loop iteration, and at the
        # latest when asyncio.run shuts the loop down, which would close the
        # stream whether or not the application did.
        closed_on_return.append(stream.closed)

    closed_on_return: list[bool] = []
    gc.disable()
    try:
        asyncio.run(drive())
    finally:
        gc.enable()
    assert closed_on_return == [True]


@pytest.mark.usefixtures("split_hosts")
def test_an_upstream_failure_mid_body_closes_the_upstream_and_propagates(
    client: TestClient,
    recorder: _Upstream,
) -> None:
    # Test: An upstream connection that fails after part of the body.
    # Situation: The upstream stream yields one chunk and then raises
    #   `httpx2.ReadError`, and a client sends `GET /mcp`.
    # Expectation: The error propagates out of the application, so the server
    #   ends the connection without the terminating chunk and the browser sees
    #   a truncated response, and the upstream stream is closed.
    stream = _ClosingStream(b"partial", error=httpx2.ReadError("reset"))
    recorder.body = stream

    with pytest.raises(httpx2.ReadError):
        client.get("/mcp")

    assert stream.closed


@pytest.mark.parametrize(
    ("name", "value"),
    [
        pytest.param(
            b"content-disposition",
            'attachment; filename="中.csv"'.encode(),
            id="utf-8",
        ),
        pytest.param(b"x-label", "café".encode(), id="latin-1-range"),
    ],
)
@pytest.mark.usefixtures("split_hosts")
def test_upstream_header_bytes_reach_the_client_unchanged(
    name: bytes,
    value: bytes,
    client: TestClient,
    recorder: _Upstream,
) -> None:
    # Test: Relay of upstream header values that are not ASCII.
    # Situation: The upstream answers `GET /mcp` with a header whose value is
    #   UTF-8: a CJK filename in `Content-Disposition`, or `é`, which falls in
    #   the Latin-1 range once decoded. The app is driven over ASGI, because
    #   the test client cannot carry such a header.
    # Expectation: The response carries the header with exactly the bytes the
    #   upstream sent, and the upstream stream is closed.
    stream = _ClosingStream(b"body")
    recorder.body = stream
    recorder.headers = [(name, value)]

    start = _asgi_get(client.app, "/mcp", b"/mcp")

    assert start["status"] == 200
    assert (name, value) in start["headers"]
    assert stream.closed


@pytest.mark.usefixtures("split_hosts")
def test_a_malformed_location_on_a_non_redirect_is_relayed_unchanged(
    client: TestClient,
    recorder: _Upstream,
) -> None:
    # Test: A Location header on a response that is not a redirect.
    # Situation: The upstream answers `POST /api/observations` with HTTP 201
    #   and `Location: http://[bad/x`, which does not parse as a URL.
    # Expectation: The client receives the 201 with the Location exactly as
    #   sent, and the upstream stream is closed.
    stream = _ClosingStream(b"created")
    recorder.body = stream
    recorder.status_code = 201
    recorder.headers = [("Location", "http://[bad/x")]

    response = client.post("/api/observations", content=b"{}")

    assert response.status_code == 201
    assert response.headers["location"] == "http://[bad/x"
    assert stream.closed


@pytest.mark.parametrize("status", [99, 600, 999])
@pytest.mark.usefixtures("split_hosts")
def test_an_out_of_range_upstream_status_returns_502(
    status: int,
    client: TestClient,
    recorder: _Upstream,
) -> None:
    # Test: An upstream status that no HTTP server can send.
    # Situation: The upstream answers `GET /mcp` with a status outside
    #   100-599.
    # Expectation: The proxy returns HTTP 502 instead of relaying the status,
    #   and the upstream stream is closed.
    stream = _ClosingStream(b"body")
    recorder.body = stream
    recorder.status_code = status

    response = client.get("/mcp")

    assert response.status_code == 502
    assert stream.closed


@pytest.mark.parametrize("path", ["/api/%00", "/api/%09", "/api/a%7Fb"])
@pytest.mark.usefixtures("split_hosts")
def test_an_encoded_control_character_is_forwarded_encoded(
    path: str,
    client: TestClient,
    recorder: _Upstream,
) -> None:
    # Test: A path that percent-encodes a control character.
    # Situation: A client requests a data-plane path containing `%00`, `%09`,
    #   or `%7F`.
    # Expectation: The upstream receives the path still percent-encoded, and
    #   the client receives the upstream's HTTP 200 rather than a 500.
    response = client.get(path)

    assert response.status_code == 200
    assert recorder.requests[0].url.raw_path == path.encode()


@pytest.mark.usefixtures("split_hosts")
def test_encoded_delimiters_in_the_path_stay_in_the_path(
    client: TestClient,
    recorder: _Upstream,
) -> None:
    # Test: A path that percent-encodes a URL delimiter.
    # Situation: A client requests `/api/foo%23frag?b=2`, where `%23` encodes
    #   `#`.
    # Expectation: The upstream receives path `/api/foo%23frag` and query
    #   `b=2`; the encoded `#` does not start a fragment that swallows the
    #   query.
    response = client.get("/api/foo%23frag?b=2")

    assert response.status_code == 200
    sent = recorder.requests[0].url
    assert sent.raw_path == b"/api/foo%23frag?b=2"
    assert sent.query == b"b=2"
    assert sent.fragment == ""


@pytest.mark.usefixtures("split_hosts")
def test_a_path_that_is_not_ascii_returns_400(
    client: TestClient,
    recorder: _Upstream,
) -> None:
    # Test: A request line whose path holds a byte outside ASCII.
    # Situation: The app is driven over ASGI with `raw_path` `/api/\xff`,
    #   which a browser never sends but a raw client can.
    # Expectation: The proxy returns HTTP 400 without calling the upstream.
    start = _asgi_get(client.app, "/api/\xff", b"/api/\xff")

    assert start["status"] == 400
    assert recorder.requests == []


@pytest.mark.parametrize(
    "query_string",
    [
        pytest.param(b"q=\xe9", id="latin-1"),
        pytest.param(b"q=\xc3\xa9", id="utf-8"),
        pytest.param(b"q=\xff", id="invalid-utf-8"),
    ],
)
@pytest.mark.usefixtures("split_hosts")
def test_a_query_that_is_not_ascii_returns_400(
    query_string: bytes,
    client: TestClient,
    recorder: _Upstream,
) -> None:
    # Test: A request line whose query string holds a byte outside ASCII.
    # Situation: The app is driven over ASGI with an ASCII path and a raw
    #   query holding `\xe9`, the UTF-8 bytes of `é`, or `\xff`. A browser
    #   percent-encodes these; only a raw client sends them.
    # Expectation: The proxy returns HTTP 400 without calling the upstream,
    #   rather than dropping the bytes or re-encoding them.
    start = _asgi_get(
        client.app, "/api/x", b"/api/x", query_string=query_string
    )

    assert start["status"] == 400
    assert recorder.requests == []


@pytest.mark.usefixtures("split_hosts")
def test_a_proxied_request_logs_nothing_from_httpx2_at_info(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Test: Log volume of a successful proxied request.
    # Situation: Logging is captured at INFO, as `config.py` configures the
    #   root logger, and a client sends `GET /api/x?q=1`, which the upstream
    #   answers with HTTP 200.
    # Expectation: No record comes from the `httpx2` logger, which would
    #   otherwise log the upstream URL of every proxied request.
    caplog.set_level(logging.INFO)

    response = client.get("/api/x?q=1")

    assert response.status_code == 200
    assert [r for r in caplog.records if r.name == "httpx2"] == []


@pytest.mark.usefixtures("split_hosts")
def test_a_callers_api_key_never_reaches_the_upstream(
    client: TestClient,
    recorder: _Upstream,
) -> None:
    # Test: A caller-supplied `X-API-Key` on a route whose host gets the
    #   agent's key.
    # Situation: `DATA_PLANE_URL` is `https://api.datacommons.org`, which is
    #   allowlisted for the configured key, and a client sends `GET /mcp` with
    #   its own `X-API-Key`.
    # Expectation: The upstream request carries exactly one `X-API-Key` line,
    #   holding the configured key.
    response = client.get("/mcp", headers={"X-API-Key": "caller-supplied"})

    assert response.status_code == 200
    keys = [
        value
        for name, value in recorder.requests[0].headers.raw
        if name.lower() == b"x-api-key"
    ]
    assert keys == [_API_KEY.encode()]


@pytest.mark.usefixtures("split_hosts")
def test_upstream_date_and_server_headers_are_not_copied(
    client: TestClient,
    recorder: _Upstream,
) -> None:
    # Test: The upstream's `Date` and `Server` headers.
    # Situation: The upstream answers `GET /mcp` with `Date` and `Server`.
    #   Uvicorn adds its own `Date` and `Server` to every response; the test
    #   client adds neither.
    # Expectation: The proxied response carries no `Date` or `Server` line
    #   from the upstream, so Uvicorn's is the only one of each.
    recorder.headers = [
        ("Date", "Mon, 01 Jan 2024 00:00:00 GMT"),
        ("Server", "upstream-server"),
    ]

    response = client.get("/mcp")

    assert response.status_code == 200
    names = [name for name, _ in response.headers.raw]
    assert b"date" not in names
    assert b"server" not in names


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("http://datacommons.org/browser/", "/browser/"),
        (
            "https://datacommons.org/place?dcid=geoId/06#map",
            "/place?dcid=geoId/06#map",
        ),
        ("/tools/map", "/tools/map"),
        (
            "https://accounts.example.com/login",
            "https://accounts.example.com/login",
        ),
        ("https://datacommons.org//evil.example/x", "/evil.example/x"),
        ("https://datacommons.org/\\evil.example/x", "/evil.example/x"),
        ("//datacommons.org//evil.example/x", "/evil.example/x"),
    ],
)
@pytest.mark.usefixtures("split_hosts")
def test_a_redirect_to_the_data_plane_host_stays_on_this_origin(
    location: str,
    expected: str,
    client: TestClient,
    recorder: _Upstream,
) -> None:
    # Test: The Location header of an upstream redirect.
    # Situation: `DATA_PLANE_WEB_URL` is `https://datacommons.org`, and the
    #   upstream answers `GET /browser` with HTTP 308 and a Location that names
    #   that host (over http, https, or scheme-relative, including paths that
    #   start with `//` or `/\`), a bare path, or another host.
    # Expectation: The proxy returns the redirect without following it. A
    #   Location on the data plane's host becomes a path on this origin that
    #   starts with exactly one slash, so a browser cannot read it as naming
    #   another host; any other Location is unchanged.
    recorder.status_code = 308
    recorder.headers = [("Location", location)]

    response = client.get("/browser", follow_redirects=False)

    assert response.status_code == 308
    rewritten = response.headers["location"]
    assert rewritten == expected
    if rewritten.startswith("/"):
        assert rewritten[1:2] not in ("/", "\\")
    assert len(recorder.requests) == 1


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("café".encode(), id="utf-8"),
        pytest.param("café".encode("latin-1"), id="latin-1"),
    ],
)
@pytest.mark.usefixtures("split_hosts")
def test_request_header_bytes_reach_the_upstream_unchanged(
    value: bytes,
    client: TestClient,
    recorder: _Upstream,
) -> None:
    # Test: Forwarding of a request header value that is not ASCII.
    # Situation: A client sends `GET /mcp` with an `X-Label` header whose
    #   value is `café` encoded as UTF-8 or as Latin-1. The app is driven
    #   over ASGI, because the test client cannot send arbitrary header
    #   bytes.
    # Expectation: The proxy answers 200, and the upstream request carries
    #   the header with exactly the bytes the client sent.
    start = _asgi_get(
        client.app, "/mcp", b"/mcp", headers=[(b"x-label", value)]
    )

    assert start["status"] == 200
    [sent] = recorder.requests
    assert (b"x-label", value) in sent.headers.raw


@pytest.mark.usefixtures("split_hosts")
def test_a_client_disconnect_during_upload_ends_the_request_quietly(
    client: TestClient,
    recorder: _Upstream,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Test: A browser that disconnects while its request body is relayed.
    # Situation: A client posts to `/api/observations`, declaring a 10-byte
    #   body, sends the first 4 bytes, and disconnects.
    # Expectation: No error escapes the application, the upstream never
    #   answers a request, and the disconnect is logged at INFO.
    messages: list[Message] = [
        {"type": "http.request", "body": b"part", "more_body": True},
        {"type": "http.disconnect"},
    ]

    async def receive() -> Message:
        return messages.pop(0)

    async def send(message: Message) -> None:
        pass

    scope = _http_scope(
        "/api/observations",
        b"/api/observations",
        method="POST",
        headers=[(b"content-length", b"10")],
    )
    with caplog.at_level(logging.INFO, logger=dcproxy.__name__):
        asyncio.run(client.app(scope, receive, send))

    assert recorder.requests == []
    [record] = [r for r in caplog.records if r.name == dcproxy.__name__]
    assert record.levelno == logging.INFO
    assert "client disconnected during upload" in record.getMessage()
