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
   when none is configured in local development, and allows none on Cloud Run
   or Kubernetes.
2. FastAPI's generated API documentation routes are absent.
3. Every GET route also answers HEAD, and a trailing slash returns 404 rather
   than a redirect.
4. Startup initializes the transcript signing key and bootstraps the config
   before the first request, and fails fast on Kubernetes when
   `TRANSCRIPT_HMAC_SECRET` is unset.
5. The lifespan writes buffered telemetry at shutdown.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from narratives_agent import telemetry
from narratives_agent.mcp.capabilities import Capabilities
from narratives_agent.server import app as server_app
from narratives_agent.server.app import create_app
from narratives_agent.server.routes import system

_ORIGIN = "https://narratives.example.com"


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


@pytest.mark.parametrize(
    ("env_var", "value"),
    [
        ("K_SERVICE", "narratives-app"),
        ("KUBERNETES_SERVICE_HOST", "10.0.0.1"),
    ],
)
@pytest.mark.parametrize("origin", ["http://localhost:3000", _ORIGIN])
def test_cors_allows_no_origin_on_cloud_run_without_configuration(
    env_var: str,
    value: str,
    origin: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: CORS behavior in a deployed environment with no allow-list.
    # Situation: `K_SERVICE` (Cloud Run) or `KUBERNETES_SERVICE_HOST` (GKE) is
    #   set, `ALLOWED_ORIGIN` is unset, and a request arrives from a local
    #   development origin or from a deployed one.
    # Expectation: The response carries no `Access-Control-Allow-Origin`, so
    #   CORS fails closed instead of falling back to the local origins.
    monkeypatch.setenv(env_var, value)
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


@pytest.mark.parametrize(
    "path",
    [
        "/healthz",
        "/agent/health",
    ],
)
def test_every_get_route_also_answers_head(
    path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: HEAD support on each GET route of the application.
    # Situation: A client sends HEAD to one path per GET handler: the liveness
    #   route and the health report. The MCP lookups are stubbed.
    # Expectation: Each answers 200 with an empty body. A route without HEAD
    #   would fall through to the static mount and answer 404 instead.
    monkeypatch.setattr(system, "mcp_url", lambda: "http://mcp.test/mcp")
    monkeypatch.setattr(system, "mcp_capabilities", lambda: Capabilities())
    client = TestClient(create_app())

    response = client.head(path)

    assert response.status_code == 200
    assert response.content == b""


@pytest.mark.parametrize("path", ["/healthz/", "/agent/health/"])
def test_a_trailing_slash_returns_404(path: str) -> None:
    # Test: Handling of a trailing slash on a route declared without one.
    # Situation: A client requests a route's path with a trailing slash.
    # Expectation: The application answers 404 rather than redirecting to the
    #   path without the slash.
    client = TestClient(create_app())

    response = client.get(path, follow_redirects=False)

    assert response.status_code == 404


def test_startup_bootstraps_the_config_before_serving_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Startup config and signing-key bootstrap in the application
    #   lifespan.
    # Situation: `bootstrap_config_from_url` and `init_signing_key` are stubbed
    #   to record calls, and the application starts and serves a request.
    # Expectation: Both run once at startup and are not called again on
    #   subsequent requests.
    calls: list[str] = []
    monkeypatch.setattr(
        server_app,
        "bootstrap_config_from_url",
        lambda: calls.append("config"),
    )
    monkeypatch.setattr(
        server_app,
        "init_signing_key",
        lambda: calls.append("signing_key"),
    )

    with TestClient(create_app()) as client:
        assert calls == ["signing_key", "config"]
        assert client.get("/healthz").status_code == 200
        assert calls == ["signing_key", "config"]


def test_startup_fails_on_kubernetes_without_a_signing_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Startup enforcement of `TRANSCRIPT_HMAC_SECRET` on Kubernetes.
    # Situation: `KUBERNETES_SERVICE_HOST` is set, `TRANSCRIPT_HMAC_SECRET`
    #   is unset, and the application lifespan starts.
    # Expectation: Entering the `TestClient` context raises `RuntimeError`
    #   before the server accepts requests.
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.0.0.1")
    monkeypatch.delenv("TRANSCRIPT_HMAC_SECRET", raising=False)

    with (
        pytest.raises(RuntimeError, match="TRANSCRIPT_HMAC_SECRET"),
        TestClient(create_app()),
    ):
        pass


def test_lifespan_flushes_telemetry_at_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Buffered telemetry is written when the application stops.
    # Situation: The config bootstrap is stubbed, `flush_telemetry` is stubbed
    #   to record its calls, and the application starts and then shuts down.
    # Expectation: `flush_telemetry` is not called while the application
    #   runs and is called once at shutdown.
    flushes: list[None] = []
    monkeypatch.setattr(server_app, "bootstrap_config_from_url", lambda: None)
    monkeypatch.setattr(
        telemetry, "flush_telemetry", lambda: flushes.append(None)
    )

    with TestClient(create_app()):
        assert flushes == []

    assert flushes == [None]


@pytest.mark.parametrize(
    "path",
    [
        "/healthz",
        "/narratives/healthz",
        "/narratives/agent/health",
    ],
)
def test_base_path_mounts_api_and_health_routes_under_subpath(
    path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: API and health routes when `BASE_PATH` is set.
    # Situation: `BASE_PATH` is `/narratives` and a client sends GET and HEAD
    #   requests to `/healthz`, `/narratives/healthz`, and
    #   `/narratives/agent/health`.
    # Expectation: Each route answers 200 on both GET and HEAD, while the
    #   unprefixed `/agent/health` route answers 404.
    monkeypatch.setenv("BASE_PATH", "/narratives")
    monkeypatch.setattr(system, "mcp_url", lambda: "http://mcp.test/mcp")
    monkeypatch.setattr(system, "mcp_capabilities", lambda: Capabilities())
    client = TestClient(create_app())

    get_response = client.get(path)
    head_response = client.head(path)

    assert get_response.status_code == 200
    assert head_response.status_code == 200
    assert head_response.content == b""
    assert client.get("/agent/health").status_code == 404


@pytest.mark.parametrize(
    ("request_path", "expected_location"),
    [
        ("/narratives", "/narratives/"),
        ("/narratives?q=india&tab=metrics", "/narratives/?q=india&tab=metrics"),
    ],
)
def test_base_path_without_trailing_slash_redirects_relatively(
    request_path: str,
    expected_location: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Redirect from `BASE_PATH` without a trailing slash.
    # Situation: `BASE_PATH` is `/narratives` and a client requests
    #   `/narratives` (with or without a query string) via GET and HEAD.
    # Expectation: The server answers 307 with a root-relative `Location`
    #   header pointing to `/narratives/` (preserving any query string) rather
    #   than an absolute `http://` URL.
    monkeypatch.setenv("BASE_PATH", "/narratives")
    client = TestClient(create_app())

    get_response = client.get(request_path, follow_redirects=False)
    head_response = client.head(request_path, follow_redirects=False)

    assert get_response.status_code == 307
    assert get_response.headers["location"] == expected_location
    assert head_response.status_code == 307
    assert head_response.headers["location"] == expected_location
    assert head_response.content == b""
