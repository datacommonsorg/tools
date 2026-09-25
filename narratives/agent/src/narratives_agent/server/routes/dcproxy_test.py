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
test client and a stubbed upstream session:
1. `/mcp` requests are forwarded to `DATA_PLANE_URL`, while website and web
   component routes (`/api`, `/core`, `/place`, `/datacommons.js`) are forwarded
   to `DATA_PLANE_WEB_URL`.
2. Incoming caller identity headers (`Authorization`,
   `X-Goog-Iap-Jwt-Assertion`, `X-Goog-Authenticated-User-Email`,
   `X-Goog-Authenticated-User-Id`) are stripped before forwarding.
3. `X-API-Key` is attached when forwarding to an allowlisted public Data Commons
   host (`api.datacommons.org`) and omitted when forwarding to an unlisted host.
4. Upstream transfer-framing headers (`Content-Encoding`, `Transfer-Encoding`,
   `Content-Length`) are stripped from the proxied response.
5. An unconfigured `DATA_PLANE_URL` returns HTTP 503, and an upstream transport
   exception returns HTTP 502.
6. A query parameter cannot choose the upstream: the query string is forwarded
   unchanged, and the route's own prefix selects the host.
7. Repeated upstream response headers, such as two `Set-Cookie` headers, reach
   the client as separate headers.
"""

from collections.abc import Iterable

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

from narratives_agent import gcp_auth
from narratives_agent.server.routes import dcproxy

_API_HOST = "https://api.datacommons.org"
_WEB_HOST = "https://datacommons.org"
_API_KEY = "test-dc-api-key"


class _RawHeaders:
    """Minimal urllib3 `HTTPHeaderDict` stub exposing `.items()`."""

    def __init__(self, items: list[tuple[str, str]]) -> None:
        self._items = items

    def items(self) -> list[tuple[str, str]]:
        return list(self._items)


class _RawResponse:
    """Minimal `upstream.raw` stub holding raw response headers."""

    def __init__(self, headers: list[tuple[str, str]]) -> None:
        self.headers = _RawHeaders(headers)


class _UpstreamResponse:
    """Minimal streaming `requests.Response` stub for `dcproxy._SESSION`."""

    def __init__(
        self,
        status_code: int = 200,
        body: bytes = b"proxied-payload",
        headers: list[tuple[str, str]] | None = None,
    ) -> None:
        self.status_code = status_code
        self._body = body
        self.raw = _RawResponse(
            headers
            if headers is not None
            else [("Content-Type", "application/json")]
        )

    def iter_content(self, chunk_size: int = 8192) -> Iterable[bytes]:
        yield self._body

    def close(self) -> None:
        """Does nothing: the stub holds no connection to release."""


class _UpstreamRecorder:
    """Stub for `dcproxy._SESSION.request` that records outbound calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, str]]] = []
        self.response = _UpstreamResponse()
        self.error: Exception | None = None

    def __call__(
        self,
        method: str,
        url: str,
        **kwargs: object,
    ) -> _UpstreamResponse:
        raw_headers = kwargs.get("headers")
        headers = (
            {str(k): str(v) for k, v in raw_headers.items()}
            if isinstance(raw_headers, dict)
            else {}
        )
        self.calls.append((method, url, headers))
        if self.error is not None:
            raise self.error
        return self.response


@pytest.fixture
def client() -> TestClient:
    """Returns a test client for an app that serves only `dcproxy.router`."""
    app = FastAPI()
    app.include_router(dcproxy.router)
    return TestClient(app)


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _UpstreamRecorder:
    """Stub `dcproxy._SESSION.request` and configure clean auth defaults."""
    rec = _UpstreamRecorder()
    monkeypatch.setattr(dcproxy._SESSION, "request", rec)
    monkeypatch.delenv("DATA_PLANE_AUTH", raising=False)
    monkeypatch.setenv("DC_API_KEY", _API_KEY)
    monkeypatch.setattr(gcp_auth, "get_id_token", lambda audience: "fake-jwt")
    return rec


@pytest.fixture
def split_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure distinct API and website hosts for public Data Commons."""
    monkeypatch.setenv("DATA_PLANE_URL", _API_HOST)
    monkeypatch.setenv("DATA_PLANE_WEB_URL", _WEB_HOST)


@pytest.mark.usefixtures("split_hosts")
def test_mcp_route_forwards_to_api_host(
    client: TestClient,
    recorder: _UpstreamRecorder,
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
    recorder: _UpstreamRecorder,
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
    recorder: _UpstreamRecorder,
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
    recorder: _UpstreamRecorder,
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
    recorder: _UpstreamRecorder,
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
    recorder: _UpstreamRecorder,
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
    recorder: _UpstreamRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Proxy response when `DATA_PLANE_URL` is unconfigured.
    # Situation: Both `DATA_PLANE_URL` and `DATA_PLANE_WEB_URL` are empty.
    # Expectation: `GET /api/observations` returns HTTP 503 without invoking
    #   the upstream session.
    monkeypatch.setenv("DATA_PLANE_URL", "")
    monkeypatch.setenv("DATA_PLANE_WEB_URL", "")

    response = client.get("/api/observations")
    assert response.status_code == 503
    assert recorder.calls == []


@pytest.mark.usefixtures("split_hosts")
def test_upstream_request_exception_returns_502(
    client: TestClient,
    recorder: _UpstreamRecorder,
) -> None:
    # Test: Error handling when the upstream request fails.
    # Situation: `dcproxy._SESSION.request` raises a
    #   `requests.ConnectionError`.
    # Expectation: The proxy catches the exception and returns HTTP 502.
    recorder.error = requests.ConnectionError("upstream connection refused")

    response = client.get("/api/observations")
    assert response.status_code == 502
    assert "Data plane unreachable" in response.json()["error"]


@pytest.mark.usefixtures("split_hosts")
def test_upstream_framing_headers_are_not_copied_to_response(
    client: TestClient,
    recorder: _UpstreamRecorder,
) -> None:
    # Test: Filtering of upstream framing headers on proxied responses.
    # Situation: The upstream response includes `Content-Encoding: gzip`,
    #   `Transfer-Encoding: chunked`, and `Content-Length: 999` alongside
    #   `X-Upstream-Status: ok`.
    # Expectation: `Content-Encoding` and `Transfer-Encoding` from the upstream
    #   raw headers are stripped while `X-Upstream-Status` is preserved.
    recorder.response = _UpstreamResponse(
        body=b"decoded-body",
        headers=[
            ("Content-Encoding", "gzip"),
            ("Transfer-Encoding", "chunked"),
            ("Content-Length", "999"),
            ("X-Upstream-Status", "ok"),
        ],
    )

    response = client.get("/mcp")
    assert response.status_code == 200
    assert response.headers.get("X-Upstream-Status") == "ok"
    assert "Content-Encoding" not in response.headers
    assert "Transfer-Encoding" not in response.headers
    assert response.headers.get("Content-Length") != "999"


@pytest.mark.parametrize("name", ["p", "prefix"])
@pytest.mark.usefixtures("split_hosts")
def test_a_query_parameter_cannot_redirect_the_root_route(
    name: str,
    client: TestClient,
    recorder: _UpstreamRecorder,
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
    recorder: _UpstreamRecorder,
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
    recorder: _UpstreamRecorder,
) -> None:
    # Test: Preservation of repeated upstream response headers.
    # Situation: The upstream response carries two `Set-Cookie` headers and
    #   two `Vary` headers.
    # Expectation: The proxied response carries all four as separate headers,
    #   in upstream order, rather than keeping one value per name.
    recorder.response = _UpstreamResponse(
        headers=[
            ("Set-Cookie", "a=1"),
            ("Set-Cookie", "b=2"),
            ("Vary", "Accept"),
            ("Vary", "Origin"),
        ],
    )

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
