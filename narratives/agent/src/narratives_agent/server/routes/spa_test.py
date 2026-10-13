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
"""Tests for the static UI mount and the liveness route in `spa`.

The tests serve the app that `create_app` builds, since that is where the
static mount's options are set.

Verifies that:
1. `SpaStaticFiles` sets `Cache-Control` by kind of file: immutable for files
   under `assets/` and `theme/`, and `no-cache` for every other file.
2. Every static response carries `X-Content-Type-Options: nosniff`, and every
   SVG, and only an SVG, carries `Content-Security-Policy: sandbox`.
3. A revalidation that returns 304 carries the same cache and security headers.
4. HEAD returns the headers and an empty body.
5. Percent-encoded `..` segments cannot reach files outside the static root,
   and an unknown file or a missing static root returns 404.
6. `/healthz` answers `ok`.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from narratives_agent.server.app import create_app

_INDEX = b"<!doctype html><title>Narratives</title>"
_BUNDLE = b"console.log('narratives');"
_LOGO = b"\x89PNG\r\n\x1a\n"
_SVG = b"<svg xmlns='http://www.w3.org/2000/svg'/>"
_CONFIG = b'{"mcp": {"server_url": "http://mcp.test/mcp"}}'

_IMMUTABLE = "public, max-age=31536000, immutable"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Returns a test client for the app over a UI build under `tmp_path`.

    The agent root holds `config.json` beside the static root, as in the
    container, so the traversal tests aim at a file that exists.
    """
    agent_root = tmp_path / "agent"
    static_root = agent_root / "static"
    (static_root / "assets").mkdir(parents=True)
    (static_root / "theme").mkdir()
    (static_root / "index.html").write_bytes(_INDEX)
    (static_root / "assets" / "index-a1b2c3d4.js").write_bytes(_BUNDLE)
    (static_root / "theme" / "logo-e5f6a7b8.svg").write_bytes(_SVG)
    (static_root / "logo.png").write_bytes(_LOGO)
    (static_root / "dc-logo.svg").write_bytes(_SVG)
    (agent_root / "config.json").write_bytes(_CONFIG)
    monkeypatch.setenv("AGENT_ROOT", str(agent_root))
    monkeypatch.setenv("STATIC_ROOT", str(static_root))
    return TestClient(create_app())


@pytest.mark.parametrize(
    ("path", "body", "cache_control"),
    [
        ("/", _INDEX, "no-cache"),
        ("/index.html", _INDEX, "no-cache"),
        ("/assets/index-a1b2c3d4.js", _BUNDLE, _IMMUTABLE),
        ("/theme/logo-e5f6a7b8.svg", _SVG, _IMMUTABLE),
        ("/logo.png", _LOGO, "no-cache"),
        ("/dc-logo.svg", _SVG, "no-cache"),
    ],
)
def test_cache_control_follows_the_kind_of_file(
    path: str,
    body: bytes,
    cache_control: str,
    client: TestClient,
) -> None:
    # Test: `Cache-Control` header values across static file paths.
    # Situation: A client requests `/`, `/index.html`, content-hashed files
    #   under `assets/` and `theme/`, and unhashed files at the root.
    # Expectation: Files under `assets/` and `theme/` receive an immutable
    #   one-year cache header, and all other files receive `no-cache`.
    response = client.get(path)

    assert response.status_code == 200
    assert response.content == body
    assert response.headers["cache-control"] == cache_control


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/assets/index-a1b2c3d4.js",
        "/theme/logo-e5f6a7b8.svg",
        "/logo.png",
        "/dc-logo.svg",
    ],
)
def test_every_static_response_forbids_content_sniffing(
    path: str, client: TestClient
) -> None:
    # Test: `X-Content-Type-Options` header on static responses.
    # Situation: A client requests HTML, JavaScript, PNG, and SVG files.
    # Expectation: Every response includes `X-Content-Type-Options: nosniff`.
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize(
    ("path", "is_sandboxed"),
    [
        ("/dc-logo.svg", True),
        ("/theme/logo-e5f6a7b8.svg", True),
        ("/", False),
        ("/index.html", False),
        ("/assets/index-a1b2c3d4.js", False),
        ("/logo.png", False),
    ],
)
def test_only_svg_files_are_sandboxed(
    path: str, is_sandboxed: bool, client: TestClient
) -> None:
    # Test: `Content-Security-Policy` header on SVG and non-SVG static files.
    # Situation: A client requests SVG files and non-SVG files.
    # Expectation: SVG responses include `Content-Security-Policy: sandbox`,
    #   and non-SVG responses omit the header.
    response = client.get(path)

    assert response.status_code == 200
    if is_sandboxed:
        assert response.headers["content-security-policy"] == "sandbox"
    else:
        assert "content-security-policy" not in response.headers


@pytest.mark.parametrize(
    ("path", "cache_control", "csp"),
    [
        ("/", "no-cache", None),
        ("/assets/index-a1b2c3d4.js", _IMMUTABLE, None),
        ("/theme/logo-e5f6a7b8.svg", _IMMUTABLE, "sandbox"),
        ("/logo.png", "no-cache", None),
    ],
)
def test_revalidation_returns_304_with_the_same_headers(
    path: str,
    cache_control: str,
    csp: str | None,
    client: TestClient,
) -> None:
    # Test: Conditional `If-None-Match` requests against static files.
    # Situation: A client repeats a GET request with the `ETag` from the first
    #   response.
    # Expectation: The server returns 304 with the same cache and security
    #   headers as the 200 response.
    etag = client.get(path).headers["etag"]

    response = client.get(path, headers={"If-None-Match": etag})

    assert response.status_code == 304
    assert response.headers["cache-control"] == cache_control
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers.get("content-security-policy") == csp


def test_head_returns_headers_and_an_empty_body(client: TestClient) -> None:
    # Test: HEAD request against a static file.
    # Situation: A client sends `HEAD /logo.png`.
    # Expectation: The server returns 200 with headers and an empty body.
    response = client.head("/logo.png")

    assert response.status_code == 200
    assert response.headers["content-length"] == str(len(_LOGO))
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.content == b""


@pytest.mark.parametrize(
    "path", ["/%2e%2e/config.json", "/assets/%2e%2e/%2e%2e/config.json"]
)
def test_encoded_traversal_returns_404(path: str, client: TestClient) -> None:
    # Test: Confinement of the static mount to the static root.
    # Situation: A client requests `config.json`, which sits in the agent root
    #   beside the static root, through percent-encoded `..` segments that the
    #   client does not normalize away.
    # Expectation: The application answers 404.
    response = client.get(path)

    assert response.status_code == 404


def test_unknown_file_returns_404(client: TestClient) -> None:
    # Test: A request for a file the UI build does not contain.
    # Situation: A client requests `/missing.png`, which is not in the static
    #   root.
    # Expectation: The application answers 404 rather than serving the shell.
    response = client.get("/missing.png")

    assert response.status_code == 404


def test_missing_static_root_returns_404(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Serving when no UI has been built.
    # Situation: `STATIC_ROOT` names a directory that does not exist.
    # Expectation: The shell and other files answer 404 rather than a server
    #   error, and `/healthz` still answers 200.
    monkeypatch.setenv("AGENT_ROOT", str(tmp_path))
    monkeypatch.setenv("STATIC_ROOT", str(tmp_path / "missing"))
    client = TestClient(create_app())

    assert client.get("/").status_code == 404
    assert client.get("/logo.png").status_code == 404
    assert client.get("/healthz").status_code == 200


def test_healthz_answers_ok(client: TestClient) -> None:
    # Test: The liveness route that the Cloud Run startup probe calls.
    # Situation: A client sends `GET /healthz`.
    # Expectation: The response is 200 with the plain-text body `ok`.
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.text == "ok\n"
