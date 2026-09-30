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
1. `SpaStaticFiles` sets `Cache-Control` by kind of file: `no-store` for
   `index.html`, immutable for files under `assets/`, and one hour for every
   other file.
2. A revalidation that returns 304 carries the same `Cache-Control`.
3. HEAD returns the headers and an empty body.
4. Percent-encoded `..` segments cannot reach files outside the static root,
   and an unknown file or a missing static root returns 404.
5. `/healthz` answers `ok`.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from narratives_agent.server.app import create_app

_INDEX = b"<!doctype html><title>Narratives</title>"
_BUNDLE = b"console.log('narratives');"
_LOGO = b"\x89PNG\r\n\x1a\n"
_CONFIG = b'{"mcp": {"server_url": "http://mcp.test/mcp"}}'


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Returns a test client for the app over a UI build under `tmp_path`.

    The agent root holds `config.json` beside the static root, as in the
    container, so the traversal tests aim at a file that exists.
    """
    agent_root = tmp_path / "agent"
    static_root = agent_root / "static"
    (static_root / "assets").mkdir(parents=True)
    (static_root / "index.html").write_bytes(_INDEX)
    (static_root / "assets" / "index-a1b2c3d4.js").write_bytes(_BUNDLE)
    (static_root / "logo.png").write_bytes(_LOGO)
    (agent_root / "config.json").write_bytes(_CONFIG)
    monkeypatch.setenv("AGENT_ROOT", str(agent_root))
    monkeypatch.setenv("STATIC_ROOT", str(static_root))
    return TestClient(create_app())


@pytest.mark.parametrize(
    ("path", "body", "cache_control"),
    [
        ("/", _INDEX, "no-store"),
        ("/index.html", _INDEX, "no-store"),
        (
            "/assets/index-a1b2c3d4.js",
            _BUNDLE,
            "public, max-age=31536000, immutable",
        ),
        ("/logo.png", _LOGO, "public, max-age=3600"),
    ],
)
def test_cache_control_follows_the_kind_of_file(
    path: str,
    body: bytes,
    cache_control: str,
    client: TestClient,
) -> None:
    # Test: `Cache-Control` for each kind of file in the UI build.
    # Situation: A client requests the shell, at `/` or by name, the
    #   content-hashed bundle under `assets/`, or a bare file at the root.
    # Expectation: The shell is `no-store`, the bundle is immutable for a
    #   year, and the bare file is cacheable for an hour.
    response = client.get(path)

    assert response.status_code == 200
    assert response.content == body
    assert response.headers["cache-control"] == cache_control


@pytest.mark.parametrize(
    ("path", "cache_control"),
    [
        ("/", "no-store"),
        ("/assets/index-a1b2c3d4.js", "public, max-age=31536000, immutable"),
        ("/logo.png", "public, max-age=3600"),
    ],
)
def test_revalidation_returns_304_with_the_same_cache_control(
    path: str,
    cache_control: str,
    client: TestClient,
) -> None:
    # Test: Conditional requests against the static mount.
    # Situation: A client repeats a request, sending the `ETag` it received
    #   in `If-None-Match`.
    # Expectation: The response is 304 and carries the same `Cache-Control`
    #   as the full response.
    etag = client.get(path).headers["etag"]

    response = client.get(path, headers={"If-None-Match": etag})

    assert response.status_code == 304
    assert response.headers["cache-control"] == cache_control


def test_head_returns_headers_and_an_empty_body(client: TestClient) -> None:
    # Test: HEAD requests against the static mount.
    # Situation: A client sends `HEAD /logo.png`.
    # Expectation: The response is 200 with the file's `Content-Length` and
    #   `Cache-Control`, and its body is empty.
    response = client.head("/logo.png")

    assert response.status_code == 200
    assert response.headers["content-length"] == str(len(_LOGO))
    assert response.headers["cache-control"] == "public, max-age=3600"
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
