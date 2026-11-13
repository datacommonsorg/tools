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
6. Every response, including a 404, a CORS preflight, and the streamed chat
   response, carries the security headers, with or without `BASE_PATH`, and
   the chat response still streams each frame as the turn emits it.
"""

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.types import Message

from narratives_agent import model_armor, telemetry
from narratives_agent.mcp.capabilities import Capabilities
from narratives_agent.server import app as server_app
from narratives_agent.server.app import create_app
from narratives_agent.server.routes import chat, system
from narratives_agent.server.security_headers import SECURITY_HEADERS
from narratives_agent.workflows.chat_pipeline import Emit
from narratives_agent.workflows.messages import DISCOVERY_STATUS
from narratives_agent.workflows.sse_frames import (
    StatusFrame,
    TerminalCompleteFrame,
)
from narratives_agent.workflows.transcript import Transcript

_ORIGIN = "https://narratives.example.com"

# The stubbed chat turn waits at most this long for its first frame to reach
# the client, so that a buffered response fails the test instead of hanging
# it.
_STREAM_TIMEOUT_SECONDS = 1


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


def test_startup_fails_with_a_malformed_model_armor_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Startup validation of `MODEL_ARMOR_TEMPLATE`.
    # Situation: `MODEL_ARMOR_TEMPLATE` is set to a malformed resource path and
    #   the application lifespan starts.
    # Expectation: Entering the `TestClient` context raises `RuntimeError`
    #   before the server accepts requests.
    monkeypatch.setenv("MODEL_ARMOR_TEMPLATE", "invalid-template-path")

    with (
        pytest.raises(RuntimeError, match="MODEL_ARMOR_TEMPLATE"),
        TestClient(create_app()),
    ):
        pass


def test_lifespan_flushes_telemetry_at_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Pooled clients are closed and buffered telemetry is written when
    #   the application stops.
    # Situation: The config bootstrap is stubbed, `model_armor.aclose` and
    #   `flush_telemetry` are stubbed to record their calls, and the
    #   application starts and then shuts down.
    # Expectation: Neither shutdown callback runs while the application
    #   serves requests, and both run at shutdown.
    shutdown_events: list[str] = []

    async def _close_model_armor() -> None:
        shutdown_events.append("model_armor")

    monkeypatch.setattr(server_app, "bootstrap_config_from_url", lambda: None)
    monkeypatch.setattr(model_armor, "aclose", _close_model_armor)
    monkeypatch.setattr(
        telemetry,
        "flush_telemetry",
        lambda: shutdown_events.append("telemetry"),
    )

    with TestClient(create_app()):
        assert shutdown_events == []

    assert shutdown_events == ["model_armor", "telemetry"]


@pytest.mark.parametrize("base_path", ["/narratives", "/labs/discover"])
@pytest.mark.parametrize(
    "route",
    [
        "/healthz",
        "{base_path}/healthz",
        "{base_path}/agent/health",
    ],
)
def test_base_path_mounts_api_and_health_routes_under_subpath(
    base_path: str,
    route: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: API and health routes when `BASE_PATH` is set.
    # Situation: `BASE_PATH` is a single- or multi-segment subpath and a client
    #   sends GET and HEAD requests to `/healthz`, `<base_path>/healthz`, and
    #   `<base_path>/agent/health`.
    # Expectation: Each route answers 200 on both GET and HEAD, while the
    #   unprefixed `/agent/health` route answers 404.
    monkeypatch.setenv("BASE_PATH", base_path)
    monkeypatch.setattr(system, "mcp_url", lambda: "http://mcp.test/mcp")
    monkeypatch.setattr(system, "mcp_capabilities", lambda: Capabilities())
    client = TestClient(create_app())

    path = route.format(base_path=base_path)
    get_response = client.get(path)
    head_response = client.head(path)

    assert get_response.status_code == 200
    assert head_response.status_code == 200
    assert head_response.content == b""
    assert client.get("/agent/health").status_code == 404


@pytest.mark.parametrize(
    ("base_path", "request_path", "expected_location"),
    [
        ("/narratives", "/narratives", "/narratives/"),
        (
            "/narratives",
            "/narratives?q=india&tab=metrics",
            "/narratives/?q=india&tab=metrics",
        ),
        ("/labs/discover", "/labs/discover", "/labs/discover/"),
        (
            "/labs/discover",
            "/labs/discover?q=india&tab=metrics",
            "/labs/discover/?q=india&tab=metrics",
        ),
    ],
)
def test_base_path_without_trailing_slash_redirects_relatively(
    base_path: str,
    request_path: str,
    expected_location: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Redirect from `BASE_PATH` without a trailing slash.
    # Situation: `BASE_PATH` is a single- or multi-segment subpath and a client
    #   requests `<base_path>` (with or without a query string) via GET or HEAD.
    # Expectation: The server answers 307 with a root-relative `Location`
    #   header pointing to `<base_path>/` (preserving any query string) rather
    #   than an absolute `http://` URL.
    monkeypatch.setenv("BASE_PATH", base_path)
    client = TestClient(create_app())

    get_response = client.get(request_path, follow_redirects=False)
    head_response = client.head(request_path, follow_redirects=False)

    assert get_response.status_code == 307
    assert get_response.headers["location"] == expected_location
    assert head_response.status_code == 307
    assert head_response.headers["location"] == expected_location
    assert head_response.content == b""


def _assert_has_security_headers(headers: Mapping[str, str]) -> None:
    """Asserts that `headers` carries every header in `SECURITY_HEADERS`.

    Args:
        headers: The response headers, as a case-insensitive mapping or a
            mapping keyed by lower-case name.
    """
    for name, value in SECURITY_HEADERS:
        assert headers[name.lower()] == value


@pytest.mark.parametrize("base_path", ["", "/labs/discover"])
@pytest.mark.parametrize(
    ("route", "status_code"),
    [
        ("/healthz", 200),
        ("{base_path}/agent/health", 200),
        ("{base_path}/missing.png", 404),
    ],
)
def test_every_response_carries_the_security_headers(
    base_path: str,
    route: str,
    status_code: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Security headers on routes outside the static files.
    # Situation: `BASE_PATH` is unset or a subpath, and a client requests the
    #   liveness route, the health report, and a file that does not exist.
    #   The MCP lookups are stubbed.
    # Expectation: Each response, the 404 included, carries every header in
    #   `SECURITY_HEADERS`.
    if base_path:
        monkeypatch.setenv("BASE_PATH", base_path)
    monkeypatch.setattr(system, "mcp_url", lambda: "http://mcp.test/mcp")
    monkeypatch.setattr(system, "mcp_capabilities", lambda: Capabilities())
    client = TestClient(create_app())

    response = client.get(route.format(base_path=base_path))

    assert response.status_code == status_code
    _assert_has_security_headers(response.headers)


@pytest.mark.parametrize("base_path", ["", "/labs/discover"])
def test_a_cors_preflight_carries_the_security_headers(
    base_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Security headers on a response that `CORSMiddleware` answers.
    # Situation: `BASE_PATH` is unset or a subpath, `ALLOWED_ORIGIN` is
    #   unset, as in local development, and the Vite dev server origin sends
    #   a CORS preflight for the chat route.
    # Expectation: The preflight succeeds and carries every header in
    #   `SECURITY_HEADERS`.
    if base_path:
        monkeypatch.setenv("BASE_PATH", base_path)
    monkeypatch.delenv("ALLOWED_ORIGIN", raising=False)
    client = TestClient(create_app())

    response = client.options(
        f"{base_path}/agent/chat/stream",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert (
        response.headers["access-control-allow-origin"]
        == "http://localhost:3000"
    )
    _assert_has_security_headers(response.headers)


@pytest.mark.parametrize("base_path", ["", "/labs/discover"])
def test_the_chat_stream_carries_the_headers_and_streams_each_frame(
    base_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Security headers and incremental delivery on the chat stream.
    # Situation: `BASE_PATH` is unset or a subpath, and the application is
    #   driven over ASGI. The stubbed turn emits a status frame, waits until
    #   the client has received it, and then emits the terminal frame.
    # Expectation: The response carries every header in `SECURITY_HEADERS`,
    #   the status frame reaches the client before the terminal frame is
    #   emitted, and the client receives both frames.
    if base_path:
        monkeypatch.setenv("BASE_PATH", base_path)
    status_frame_received = asyncio.Event()
    response_finished = asyncio.Event()
    delivery_before_terminal: list[bool] = []
    sent: list[Message] = []

    async def wait_for_delivery_turn(
        transcript: Transcript,
        emit: Emit,
        *,
        request_debug: bool = False,
    ) -> None:
        emit(StatusFrame(phase="discovery", message=DISCOVERY_STATUS))
        try:
            async with asyncio.timeout(_STREAM_TIMEOUT_SECONDS):
                await status_frame_received.wait()
        except TimeoutError:
            delivery_before_terminal.append(False)
        else:
            delivery_before_terminal.append(True)
        emit(
            TerminalCompleteFrame(
                idempotency_key=transcript.current_idempotency_key,
                window=None,
            )
        )

    monkeypatch.setattr(chat, "run_turn", wait_for_delivery_turn)
    application = create_app()
    body = json.dumps({"message": "Hello"}).encode()
    path = f"{base_path}/agent/chat/stream"
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 5001),
        "state": {},
    }
    is_request_delivered = False

    async def receive() -> Message:
        nonlocal is_request_delivered
        if not is_request_delivered:
            is_request_delivered = True
            return {"type": "http.request", "body": body}
        await response_finished.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)
        if message["type"] != "http.response.body":
            return
        if b"event: status" in message.get("body", b""):
            status_frame_received.set()
        if not message.get("more_body", False):
            response_finished.set()

    asyncio.run(application(scope, receive, send))

    start = sent[0]
    assert start["type"] == "http.response.start"
    assert start["status"] == 200
    _assert_has_security_headers(
        {
            name.decode("latin-1"): value.decode("latin-1")
            for name, value in start["headers"]
        }
    )
    assert delivery_before_terminal == [True]
    stream = b"".join(message.get("body", b"") for message in sent[1:])
    assert b"event: status" in stream
    assert b"event: terminal" in stream
