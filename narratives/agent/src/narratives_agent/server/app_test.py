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
"""Tests for the application that `create_app` builds.

Verifies that:
1. CORS echoes a configured origin, allows only the local development origins
   when none is configured off Cloud Run, and allows none on Cloud Run.
2. FastAPI's generated API documentation routes are absent.
3. Every data-plane prefix reaches the proxy rather than a static file of the
   same name, at `/<prefix>` and below it.
4. Every GET route also answers HEAD, and a trailing slash returns 404 rather
   than a redirect.
5. Startup writes config.json before it loads branding.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from narratives_agent.mcp.capabilities import Capabilities
from narratives_agent.server import app as server_app
from narratives_agent.server.app import create_app
from narratives_agent.server.routes import brand, dcproxy, system

_ORIGIN = "https://narratives.example.com"
_DATA_PLANE = "http://data-plane.test"


class _RawResponse:
    """Minimal `upstream.raw` stub carrying no headers."""

    def __init__(self) -> None:
        self.headers: dict[str, str] = {}


class _UpstreamResponse:
    """Minimal streaming `requests.Response` stub with a fixed body."""

    status_code = 200

    def __init__(self) -> None:
        self.raw = _RawResponse()

    def iter_content(self, chunk_size: int = 8192) -> Iterator[bytes]:
        yield b"proxied"

    def close(self) -> None:
        """Does nothing: the stub holds no connection to release."""


class _UpstreamRecorder:
    """Stub for `dcproxy._SESSION.request` that records each target URL."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def __call__(
        self, method: str, url: str, **kwargs: object
    ) -> _UpstreamResponse:
        self.urls.append(url)
        return _UpstreamResponse()


@pytest.fixture(autouse=True)
def static_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Points the agent root and the static root at `tmp_path`.

    Returns:
        The static root, which exists and holds no files.
    """
    agent_root = tmp_path / "agent"
    root = agent_root / "static"
    root.mkdir(parents=True)
    monkeypatch.setenv("AGENT_ROOT", str(agent_root))
    monkeypatch.setenv("STATIC_ROOT", str(root))
    return root


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _UpstreamRecorder:
    """Stubs the proxy's upstream session and points it at one test host."""
    rec = _UpstreamRecorder()
    monkeypatch.setattr(dcproxy._SESSION, "request", rec)
    monkeypatch.setenv("DATA_PLANE_URL", _DATA_PLANE)
    monkeypatch.delenv("DATA_PLANE_WEB_URL", raising=False)
    monkeypatch.setenv("DATA_PLANE_AUTH", "off")
    return rec


def test_cors_echoes_a_configured_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: CORS response headers for a configured origin.
    # Situation: `ALLOWED_ORIGIN` lists two origins, separated by a comma and
    #   a space, and a request arrives from the second.
    # Expectation: The response echoes that origin in
    #   `Access-Control-Allow-Origin`.
    monkeypatch.setenv(
        "ALLOWED_ORIGIN", f"https://other.example.com, {_ORIGIN}"
    )
    client = TestClient(create_app())

    response = client.get("/healthz", headers={"Origin": _ORIGIN})

    assert response.headers.get("access-control-allow-origin") == _ORIGIN


@pytest.mark.parametrize("origin", ["http://localhost:3000", _ORIGIN])
def test_cors_allows_no_origin_on_cloud_run_without_configuration(
    origin: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: CORS behavior in a deployed environment with no allow-list.
    # Situation: `K_SERVICE` is set, as on Cloud Run, `ALLOWED_ORIGIN` is
    #   unset, and a request arrives from a local development origin or from
    #   a deployed one.
    # Expectation: The response carries no `Access-Control-Allow-Origin`, so
    #   CORS fails closed instead of falling back to the local origins.
    monkeypatch.setenv("K_SERVICE", "narratives-app")
    monkeypatch.delenv("ALLOWED_ORIGIN", raising=False)
    client = TestClient(create_app())

    response = client.get("/healthz", headers={"Origin": origin})

    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize(
    "origin", ["http://localhost:3000", "http://127.0.0.1:3000"]
)
def test_cors_allows_only_local_development_origins_by_default(
    origin: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: CORS defaults on a developer machine.
    # Situation: Neither `K_SERVICE` nor `ALLOWED_ORIGIN` is set, and requests
    #   arrive from a Vite dev server origin and from a deployed origin.
    # Expectation: The response echoes the dev server origin and carries no
    #   `Access-Control-Allow-Origin` for the deployed one.
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("ALLOWED_ORIGIN", raising=False)
    client = TestClient(create_app())

    local = client.get("/healthz", headers={"Origin": origin})
    foreign = client.get("/healthz", headers={"Origin": _ORIGIN})

    assert local.headers.get("access-control-allow-origin") == origin
    assert "access-control-allow-origin" not in foreign.headers


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_api_documentation_routes_are_absent(path: str) -> None:
    # Test: Exposure of FastAPI's generated API documentation.
    # Situation: A client requests one of the paths where FastAPI serves its
    #   documentation by default.
    # Expectation: The application answers 404.
    response = TestClient(create_app()).get(path)

    assert response.status_code == 404


@pytest.mark.parametrize("prefix", dcproxy.DATA_PLANE_PREFIXES)
def test_data_plane_prefix_reaches_the_proxy_before_a_static_file(
    prefix: str,
    static_root: Path,
    recorder: _UpstreamRecorder,
) -> None:
    # Test: Route precedence between a proxy root route and the static mount.
    # Situation: The static root holds a file named after the prefix, which
    #   the static mount would serve at `/<prefix>`.
    # Expectation: `GET /<prefix>` reaches the proxy, which forwards it to the
    #   data plane and returns the upstream body.
    (static_root / prefix).write_bytes(b"static")
    client = TestClient(create_app())

    response = client.get(f"/{prefix}")

    assert response.content == b"proxied"
    assert recorder.urls == [f"{_DATA_PLANE}/{prefix}"]


@pytest.mark.parametrize("prefix", dcproxy.DATA_PLANE_PREFIXES)
def test_data_plane_subpath_reaches_the_proxy_before_a_static_file(
    prefix: str,
    static_root: Path,
    recorder: _UpstreamRecorder,
) -> None:
    # Test: Route precedence between a proxy subpath route and the static
    #   mount.
    # Situation: The static root holds `<prefix>/page.js`, which the static
    #   mount would serve at `/<prefix>/page.js`.
    # Expectation: `GET /<prefix>/page.js` reaches the proxy, which forwards
    #   it to the data plane and returns the upstream body.
    (static_root / prefix).mkdir()
    (static_root / prefix / "page.js").write_bytes(b"static")
    client = TestClient(create_app())

    response = client.get(f"/{prefix}/page.js")

    assert response.content == b"proxied"
    assert recorder.urls == [f"{_DATA_PLANE}/{prefix}/page.js"]


@pytest.mark.parametrize(
    "path",
    [
        "/healthz",
        "/agent/health",
        "/agent/brand",
        "/agent/brand.css",
        "/agent/brand.js",
        "/agent/brand/assets/logo-a1b2c3d4.svg",
        "/api",
        "/api/observations",
    ],
)
def test_every_get_route_also_answers_head(
    path: str,
    monkeypatch: pytest.MonkeyPatch,
    recorder: _UpstreamRecorder,
) -> None:
    # Test: HEAD support on each GET route of the application.
    # Situation: A client sends HEAD to one path per GET handler: the liveness
    #   route, the health report, the four branding routes, and a proxy prefix
    #   with and without a subpath. The MCP lookups, a mirrored logo, and the
    #   upstream are stubbed.
    # Expectation: Each answers 200 with an empty body. A route without HEAD
    #   would fall through to the static mount and answer 404 instead.
    monkeypatch.setattr(system, "mcp_url", lambda: "http://mcp.test/mcp")
    monkeypatch.setattr(system, "mcp_capabilities", lambda: Capabilities())
    monkeypatch.setitem(
        brand._BRAND_STATE, "assets", {"logo-a1b2c3d4.svg": b"<svg/>"}
    )
    client = TestClient(create_app())

    response = client.head(path)

    assert response.status_code == 200
    assert response.content == b""


@pytest.mark.parametrize(
    "path", ["/healthz/", "/agent/health/", "/agent/brand/"]
)
def test_a_trailing_slash_returns_404(path: str) -> None:
    # Test: Handling of a trailing slash on a route declared without one.
    # Situation: A client requests a route's path with a trailing slash.
    # Expectation: The application answers 404 rather than redirecting to the
    #   path without the slash.
    client = TestClient(create_app())

    response = client.get(path, follow_redirects=False)

    assert response.status_code == 404


def test_startup_writes_config_before_loading_branding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: The startup work the lifespan runs, and its order.
    # Situation: The config bootstrap and the branding load are stubbed to
    #   record their calls, and the application starts.
    # Expectation: Both run before the first request, the config bootstrap
    #   first, because it writes the config.json that later reads depend on.
    calls: list[str] = []
    monkeypatch.setattr(
        server_app, "bootstrap_config_from_url", lambda: calls.append("config")
    )
    monkeypatch.setattr(
        brand, "load_branding", lambda: calls.append("branding")
    )

    with TestClient(create_app()) as client:
        assert calls == ["config", "branding"]
        assert client.get("/healthz").status_code == 200
