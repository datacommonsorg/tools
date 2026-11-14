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
7. The root `index.html` is served with the effective chat availability
   stamped into `#runtime-config`, escaped for a `<script>` element, under a
   SHA-256 `ETag` of the stamped bytes that changes with the chat settings,
   without `Last-Modified`, and revalidated only through `If-None-Match`.
"""

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from narratives_agent.server.app import create_app
from narratives_agent.settings import (
    ENABLE_CHAT_ENV,
    UNAVAILABLE_MESSAGE_ENV,
    get_settings,
)

_SHELL_HEAD = b"<!doctype html><title>Narratives</title>"
_RUNTIME_OPEN = b'<script id="runtime-config" type="application/json">'
_INDEX = _SHELL_HEAD + _RUNTIME_OPEN + b"</script>"
# `_INDEX` as served when chat is enabled with the default message.
_STAMPED_INDEX = (
    _SHELL_HEAD
    + _RUNTIME_OPEN
    + b'{"enable_chat":true,"unavailable_message":"This Data Commons tool '
    + b'is temporarily unavailable due to high traffic."}</script>'
)
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
        ("/", _STAMPED_INDEX, "no-cache"),
        ("/index.html", _STAMPED_INDEX, "no-cache"),
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


@pytest.mark.parametrize("base_path", ["/narratives", "/labs/discover"])
@pytest.mark.parametrize(
    ("subpath", "body", "cache_control"),
    [
        ("/", _STAMPED_INDEX, "no-cache"),
        ("/index.html", _STAMPED_INDEX, "no-cache"),
        ("/assets/index-a1b2c3d4.js", _BUNDLE, _IMMUTABLE),
        ("/dc-logo.svg", _SVG, "no-cache"),
    ],
)
def test_static_files_serve_under_base_path(
    base_path: str,
    subpath: str,
    body: bytes,
    cache_control: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Static SPA mount under a configured `BASE_PATH`.
    # Situation: `BASE_PATH` is a single- or multi-segment subpath and a client
    #   requests the SPA shell, a hashed bundle under `assets/`, and an SVG
    #   asset under `<base_path>/*`, as well as paths outside `<base_path>`.
    # Expectation: Subpath requests return the expected content and cache
    #   headers, while `/` and parent prefixes outside `<base_path>` return 404.
    agent_root = tmp_path / "agent"
    static_root = agent_root / "static"
    (static_root / "assets").mkdir(parents=True)
    (static_root / "index.html").write_bytes(_INDEX)
    (static_root / "assets" / "index-a1b2c3d4.js").write_bytes(_BUNDLE)
    (static_root / "dc-logo.svg").write_bytes(_SVG)
    monkeypatch.setenv("AGENT_ROOT", str(agent_root))
    monkeypatch.setenv("STATIC_ROOT", str(static_root))
    monkeypatch.setenv("BASE_PATH", base_path)
    subpath_client = TestClient(create_app())

    response = subpath_client.get(f"{base_path}{subpath}")

    assert response.status_code == 200
    assert response.content == body
    assert response.headers["cache-control"] == cache_control
    assert subpath_client.get("/").status_code == 404
    assert subpath_client.get("/labs").status_code == 404


def _set_chat_env(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    """Exports `name` and drops the cached settings so the next read sees it."""
    monkeypatch.setenv(name, value)
    get_settings.cache_clear()


def _read_runtime_config(body: bytes) -> object:
    """Returns the JSON decoded from the stamped `#runtime-config` element."""
    start = body.index(_RUNTIME_OPEN) + len(_RUNTIME_OPEN)
    return json.loads(body[start : body.index(b"</script>", start)])


@pytest.mark.parametrize("path", ["/", "/index.html"])
def test_the_shell_carries_a_hash_of_the_stamped_bytes(
    path: str, client: TestClient
) -> None:
    # Test: Headers of the stamped HTML shell.
    # Situation: A client requests `/` or `/index.html` with no chat
    #   settings configured.
    # Expectation: The body is the shell with the default chat availability
    #   stamped in, served as HTML with a strong `ETag` that is the SHA-256 of
    #   those bytes, a matching `Content-Length`, and no `Last-Modified`.
    response = client.get(path)

    assert response.status_code == 200
    assert response.content == _STAMPED_INDEX
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert response.headers["etag"] == (
        f'"{hashlib.sha256(_STAMPED_INDEX).hexdigest()}"'
    )
    assert response.headers["content-length"] == str(len(_STAMPED_INDEX))
    assert "last-modified" not in response.headers


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        pytest.param(
            ENABLE_CHAT_ENV,
            "false",
            {
                "enable_chat": False,
                "unavailable_message": (
                    "This Data Commons tool is temporarily unavailable due "
                    "to high traffic."
                ),
            },
            id="ENABLE_CHAT",
        ),
        pytest.param(
            UNAVAILABLE_MESSAGE_ENV,
            "Back at noon.",
            {"enable_chat": True, "unavailable_message": "Back at noon."},
            id="UNAVAILABLE_MESSAGE",
        ),
    ],
)
def test_a_chat_setting_change_invalidates_the_shell_etag(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    name: str,
    value: str,
    expected: dict[str, object],
) -> None:
    # Test: Revalidation of the shell after a chat setting changes.
    # Situation: A client holds the `ETag` of the shell served with the
    #   default settings; `ENABLE_CHAT` or `UNAVAILABLE_MESSAGE` then changes.
    # Expectation: Revalidating with the old `ETag` returns 200 with the new
    #   settings stamped in and a different `ETag`, and revalidating with the
    #   new `ETag` returns 304 with the cache and security headers.
    old_etag = client.get("/").headers["etag"]
    _set_chat_env(monkeypatch, name, value)

    updated = client.get("/", headers={"If-None-Match": old_etag})

    assert updated.status_code == 200
    assert _read_runtime_config(updated.content) == expected
    new_etag = updated.headers["etag"]
    assert new_etag != old_etag

    revalidated = client.get("/", headers={"If-None-Match": new_etag})

    assert revalidated.status_code == 304
    assert revalidated.headers["etag"] == new_etag
    assert revalidated.headers["cache-control"] == "no-cache"
    assert revalidated.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize(
    "if_none_match",
    ["*", "W/{etag}", '"other", {etag}'],
    ids=["wildcard", "weak", "list"],
)
def test_the_shell_honors_if_none_match_forms(
    client: TestClient, if_none_match: str
) -> None:
    # Test: `If-None-Match` forms accepted for the shell.
    # Situation: A client revalidates `/` with `*`, the weak form of the
    #   current `ETag`, or a list that contains the current `ETag`.
    # Expectation: Each revalidation returns 304.
    etag = client.get("/").headers["etag"]

    response = client.get(
        "/", headers={"If-None-Match": if_none_match.format(etag=etag)}
    )

    assert response.status_code == 304


def test_if_modified_since_alone_never_returns_a_stale_shell(
    client: TestClient,
) -> None:
    # Test: `If-Modified-Since` without `If-None-Match` on the shell.
    # Situation: A client sends a date later than the file's modification
    #   time and no `If-None-Match`.
    # Expectation: The server returns 200 with the stamped body, because the
    #   file date does not change when the chat settings do.
    response = client.get(
        "/", headers={"If-Modified-Since": "Fri, 01 Jan 2100 00:00:00 GMT"}
    )

    assert response.status_code == 200
    assert response.content == _STAMPED_INDEX


def test_head_of_the_shell_reports_the_stamped_length(
    client: TestClient,
) -> None:
    # Test: HEAD request against the stamped shell.
    # Situation: A client sends `HEAD /`.
    # Expectation: The server returns 200 with an empty body, the
    #   `Content-Length` of the stamped body, and the same `ETag` as GET.
    response = client.head("/")

    assert response.status_code == 200
    assert response.content == b""
    assert response.headers["content-length"] == str(len(_STAMPED_INDEX))
    assert response.headers["etag"] == client.get("/").headers["etag"]
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_the_unavailable_message_cannot_break_out_of_the_script(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    # Test: Escaping of the stamped JSON.
    # Situation: `UNAVAILABLE_MESSAGE` holds `</script><script>`, `&`,
    #   U+2028, and U+2029.
    # Expectation: `<`, `>`, `&`, U+2028, and U+2029 are written as JSON
    #   escapes, so the page holds one `</script>` (the element's own close
    #   tag), and the decoded JSON carries the message unchanged.
    message = "</script><script>alert(1)&\u2028\u2029end"
    _set_chat_env(monkeypatch, UNAVAILABLE_MESSAGE_ENV, message)

    body = client.get("/").content

    assert body.count(b"</script>") == 1
    assert (
        b"\\u003c/script\\u003e\\u003cscript\\u003ealert(1)\\u0026"
        b"\\u2028\\u2029end" in body
    )
    assert _read_runtime_config(body) == {
        "enable_chat": True,
        "unavailable_message": message,
    }


def test_a_shell_without_the_slot_is_served_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Test: Serving an `index.html` that has no `#runtime-config` element.
    # Situation: The static root holds an `index.html` without the slot.
    # Expectation: The body is the file's bytes, with a matching `ETag`.
    static_root = tmp_path / "agent" / "static"
    static_root.mkdir(parents=True)
    (static_root / "index.html").write_bytes(_SHELL_HEAD)
    monkeypatch.setenv("AGENT_ROOT", str(tmp_path / "agent"))
    monkeypatch.setenv("STATIC_ROOT", str(static_root))

    response = TestClient(create_app()).get("/")

    assert response.content == _SHELL_HEAD
    assert response.headers["etag"] == (
        f'"{hashlib.sha256(_SHELL_HEAD).hexdigest()}"'
    )
