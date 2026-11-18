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
2. Every static response, the shell included, carries the security headers,
   with or without `BASE_PATH`. Every SVG carries
   `Content-Security-Policy: sandbox`, and no other static file except the
   shell carries a policy.
3. A revalidation that returns 304 carries the same cache and security headers.
4. HEAD returns the headers and an empty body.
5. Percent-encoded `..` segments cannot reach files outside the static root,
   and an unknown file or a missing static root returns 404.
6. `/healthz` answers `ok`.
7. The root `index.html` is served with the effective chat availability and
7. The root `index.html` is served with the effective chat availability, the
   chart hosts, and any configured reCAPTCHA site keys injected into
   `#runtime-config`, escaped for a `<script>` element, under a SHA-256 `ETag`
   of the stamped bytes that changes when runtime settings change, without
   `Last-Modified`, and revalidated only through `If-None-Match`. The stamped
   chart hosts and reCAPTCHA site keys are the ones the app starts with.
8. The shell carries the page's Content-Security-Policy on 200 and 304
   responses, with or without `BASE_PATH`. The policy allows no inline or
   evaluated script, names the configured chart hosts (and reCAPTCHA endpoints
   when a site key is set), and is absent from the other static files and
   `/agent/*`. The source `ui/index.html` holds no inline script that a
   browser would run.
"""

import hashlib
import json
from collections.abc import Mapping
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from narratives_agent.config_model import DEFAULT_UNAVAILABLE_MESSAGE
from narratives_agent.mcp.capabilities import Capabilities
from narratives_agent.server.app import create_app
from narratives_agent.server.routes import system
from narratives_agent.server.security_headers import SECURITY_HEADERS
from narratives_agent.settings import (
    DC_WEB_COMPONENT_API_ROOT_ENV,
    DC_WEB_COMPONENT_URL_ENV,
    ENABLE_CHAT_ENV,
    RECAPTCHA_CHECKBOX_SITE_KEY_ENV,
    RECAPTCHA_SESSION_SITE_KEY_ENV,
    UNAVAILABLE_MESSAGE_ENV,
    get_settings,
)

_SHELL_HEAD = b"<!doctype html><title>Narratives</title>"
_RUNTIME_OPEN = b'<script id="runtime-config" type="application/json">'
_INDEX = _SHELL_HEAD + _RUNTIME_OPEN + b"</script>"
# `_INDEX` as served when chat is enabled with the default message and the
# chart hosts are the defaults.
_STAMPED_INDEX = (
    _SHELL_HEAD
    + _RUNTIME_OPEN
    + b'{"enable_chat":true,"unavailable_message":"This Data Commons tool '
    + b'is temporarily unavailable due to high traffic.",'
    + b'"web_component_url":"https://datacommons.org/datacommons.js",'
    + b'"web_component_api_root":"https://datacommons.org"}</script>'
)
# The chart host entries of `#runtime-config` when no override is set.
_DEFAULT_CHART_HOSTS = {
    "web_component_url": "https://datacommons.org/datacommons.js",
    "web_component_api_root": "https://datacommons.org",
}
_BUNDLE = b"console.log('narratives');"
_LOGO = b"\x89PNG\r\n\x1a\n"
_SVG = b"<svg xmlns='http://www.w3.org/2000/svg'/>"
_CONFIG = b'{"mcp": {"server_url": "http://mcp.test/mcp"}}'

_IMMUTABLE = "public, max-age=31536000, immutable"

# The page's Content-Security-Policy when the chart hosts are the defaults.
_DEFAULT_PAGE_POLICY = (
    "default-src 'self'; "
    "script-src 'self' https://datacommons.org; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' https: data: blob:; "
    "connect-src 'self' https://datacommons.org; "
    "frame-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'self'; "
    "frame-ancestors 'self'"
)

# The path of the source HTML shell, `narratives/ui/index.html`, resolved
# from this file in `narratives/agent/src/narratives_agent/server/routes/`.
_SOURCE_SHELL = Path(__file__).resolve().parents[5] / "ui" / "index.html"

# A `<script>` without `src` may appear in the shell only with this `type`,
# because browsers do not run JSON data blocks.
_DATA_BLOCK_TYPE = "application/json"


def _assert_has_security_headers(headers: Mapping[str, str]) -> None:
    """Asserts that `headers` carries every header in `SECURITY_HEADERS`."""
    for name, value in SECURITY_HEADERS:
        assert headers[name.lower()] == value


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
        "/index.html",
        "/assets/index-a1b2c3d4.js",
        "/theme/logo-e5f6a7b8.svg",
        "/logo.png",
        "/dc-logo.svg",
    ],
)
def test_every_static_response_carries_the_security_headers(
    path: str, client: TestClient
) -> None:
    # Test: Security headers on static responses.
    # Situation: A client requests the HTML shell and JavaScript, PNG, and
    #   SVG files.
    # Expectation: Every response carries every header in
    #   `SECURITY_HEADERS`.
    response = client.get(path)

    assert response.status_code == 200
    _assert_has_security_headers(response.headers)


@pytest.mark.parametrize(
    ("path", "is_sandboxed"),
    [
        ("/dc-logo.svg", True),
        ("/theme/logo-e5f6a7b8.svg", True),
        ("/assets/index-a1b2c3d4.js", False),
        ("/logo.png", False),
    ],
)
def test_only_svg_files_are_sandboxed(
    path: str, is_sandboxed: bool, client: TestClient
) -> None:
    # Test: `Content-Security-Policy` header on SVG and non-SVG static files.
    # Situation: A client requests SVG files and non-SVG files other than
    #   the HTML shell.
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
    _assert_has_security_headers(response.headers)
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
    # Expectation: Subpath requests return the expected content, cache
    #   headers, and security headers, while `/` and parent prefixes outside
    #   `<base_path>` return 404.
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
    _assert_has_security_headers(response.headers)
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
                **_DEFAULT_CHART_HOSTS,
            },
            id="ENABLE_CHAT",
        ),
        pytest.param(
            UNAVAILABLE_MESSAGE_ENV,
            "Back at noon.",
            {
                "enable_chat": True,
                "unavailable_message": "Back at noon.",
                **_DEFAULT_CHART_HOSTS,
            },
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
    _assert_has_security_headers(revalidated.headers)


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
        **_DEFAULT_CHART_HOSTS,
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


def _create_shell_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    """Returns a test client for an app whose static root holds `_INDEX`."""
    static_root = tmp_path / "agent" / "static"
    static_root.mkdir(parents=True, exist_ok=True)
    (static_root / "index.html").write_bytes(_INDEX)
    monkeypatch.setenv("AGENT_ROOT", str(tmp_path / "agent"))
    monkeypatch.setenv("STATIC_ROOT", str(static_root))
    return TestClient(create_app())


@pytest.mark.parametrize(
    ("env", "expected_recaptcha"),
    [
        pytest.param(
            {RECAPTCHA_SESSION_SITE_KEY_ENV: "6Lc_session_only"},
            {"recaptcha_session_site_key": "6Lc_session_only"},
            id="session-only",
        ),
        pytest.param(
            {RECAPTCHA_CHECKBOX_SITE_KEY_ENV: "6Lc_checkbox_only"},
            {"recaptcha_checkbox_site_key": "6Lc_checkbox_only"},
            id="checkbox-only",
        ),
        pytest.param(
            {
                RECAPTCHA_SESSION_SITE_KEY_ENV: "6Lc_session_both",
                RECAPTCHA_CHECKBOX_SITE_KEY_ENV: "6Lc_checkbox_both",
            },
            {
                "recaptcha_session_site_key": "6Lc_session_both",
                "recaptcha_checkbox_site_key": "6Lc_checkbox_both",
            },
            id="both-keys",
        ),
    ],
)
def test_recaptcha_keys_inject_into_runtime_config_and_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env: dict[str, str],
    expected_recaptcha: dict[str, str],
) -> None:
    # Test: Injecting configured reCAPTCHA site keys into `#runtime-config` and
    #   allowing reCAPTCHA endpoints in the shell's Content-Security-Policy.
    # Situation: `index.html` is first served with no reCAPTCHA keys set, and
    #   a restarted app then starts with one or both reCAPTCHA site keys set.
    # Expectation: Only the non-empty site keys are added alongside
    #   `enable_chat`, `unavailable_message`, and the chart hosts; the `ETag`
    #   changes; and `script-src`, `connect-src`, and `frame-src` add Google's
    #   reCAPTCHA endpoints.
    initial = _create_shell_client(tmp_path, monkeypatch).get("/")
    assert _read_runtime_config(initial.content) == {
        "enable_chat": True,
        "unavailable_message": DEFAULT_UNAVAILABLE_MESSAGE,
        **_DEFAULT_CHART_HOSTS,
    }
    assert initial.headers["content-security-policy"] == _DEFAULT_PAGE_POLICY
    old_etag = initial.headers["etag"]

    for name, value in env.items():
        _set_chat_env(monkeypatch, name, value)

    updated = _create_shell_client(tmp_path, monkeypatch).get(
        "/", headers={"If-None-Match": old_etag}
    )

    assert updated.status_code == 200
    assert _read_runtime_config(updated.content) == {
        "enable_chat": True,
        "unavailable_message": DEFAULT_UNAVAILABLE_MESSAGE,
        **_DEFAULT_CHART_HOSTS,
        **expected_recaptcha,
    }
    assert updated.headers["etag"] != old_etag
    assert updated.headers["cache-control"] == "no-cache"
    _assert_has_security_headers(updated.headers)
    directives = _read_policy_directives(
        updated.headers["content-security-policy"]
    )
    assert directives["script-src"] == [
        "'self'",
        "https://datacommons.org",
        "https://www.google.com/recaptcha/",
        "https://www.gstatic.com/recaptcha/",
    ]
    assert directives["connect-src"] == [
        "'self'",
        "https://datacommons.org",
        "https://www.google.com/recaptcha/",
        "https://www.gstatic.com/recaptcha/",
        "https://recaptcha.google.com/recaptcha/",
    ]
    assert directives["frame-src"] == [
        "'self'",
        "https://www.google.com/recaptcha/",
        "https://recaptcha.google.com/recaptcha/",
    ]


def test_recaptcha_keys_cannot_break_out_of_the_runtime_config_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Test: HTML `<script>` escaping for injected reCAPTCHA site keys.
    # Situation: `RECAPTCHA_SESSION_SITE_KEY` contains `</script><script>`, `&`,
    #   U+2028, and U+2029.
    # Expectation: Hazardous characters are escaped as `\u003c`, `\u003e`,
    #   `\u0026`, `\u2028`, and `\u2029` so the page still contains only one
    #   `</script>` tag, and decoding `#runtime-config` recovers the raw value.
    tricky_key = "</script><script>alert(1)&\u2028\u2029key"
    _set_chat_env(monkeypatch, RECAPTCHA_SESSION_SITE_KEY_ENV, tricky_key)

    body = _create_shell_client(tmp_path, monkeypatch).get("/").content

    assert body.count(b"</script>") == 1
    parsed = _read_runtime_config(body)
    assert isinstance(parsed, dict)
    assert parsed["recaptcha_session_site_key"] == tricky_key


def test_the_shell_carries_the_configured_chart_hosts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Test: Chart host settings in the stamped `#runtime-config`.
    # Situation: When the app starts, `DC_WEB_COMPONENT_URL` and
    #   `DC_WEB_COMPONENT_API_ROOT` name autopush, and the API root ends with
    #   a trailing slash.
    # Expectation: `#runtime-config` carries both hosts, with the trailing
    #   slash removed from the API root, alongside the default chat
    #   availability.
    monkeypatch.setenv(
        DC_WEB_COMPONENT_URL_ENV,
        "https://autopush.datacommons.org/datacommons.js",
    )
    monkeypatch.setenv(
        DC_WEB_COMPONENT_API_ROOT_ENV, "https://autopush.datacommons.org/"
    )

    body = _create_shell_client(tmp_path, monkeypatch).get("/").content

    assert _read_runtime_config(body) == {
        "enable_chat": True,
        "unavailable_message": DEFAULT_UNAVAILABLE_MESSAGE,
        "web_component_url": "https://autopush.datacommons.org/datacommons.js",
        "web_component_api_root": "https://autopush.datacommons.org",
    }


def test_the_chart_hosts_are_fixed_when_the_app_starts(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    # Test: Chart host settings changed after the app is built.
    # Situation: The app starts with the default chart hosts. Then
    #   `DC_WEB_COMPONENT_API_ROOT` changes, and the cached settings are
    #   cleared.
    # Expectation: The stamped chart hosts and the page policy both keep the
    #   defaults the app was built with, so they cannot disagree.
    monkeypatch.setenv(
        DC_WEB_COMPONENT_API_ROOT_ENV, "https://autopush.datacommons.org"
    )
    get_settings.cache_clear()

    response = client.get("/")

    assert _read_runtime_config(response.content) == {
        "enable_chat": True,
        "unavailable_message": DEFAULT_UNAVAILABLE_MESSAGE,
        **_DEFAULT_CHART_HOSTS,
    }
    assert response.headers["content-security-policy"] == _DEFAULT_PAGE_POLICY


def _read_policy_directives(policy: str) -> dict[str, list[str]]:
    """Returns each directive of `policy` mapped to its sources."""
    directives: dict[str, list[str]] = {}
    for directive in policy.split(";"):
        name, *sources = directive.split()
        directives[name] = sources
    return directives


@pytest.mark.parametrize("base_path", ["", "/labs/discover"])
@pytest.mark.parametrize("subpath", ["/", "/index.html"])
def test_the_shell_carries_the_page_policy_on_200_and_304(
    base_path: str,
    subpath: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: The page's Content-Security-Policy on the HTML shell.
    # Situation: `BASE_PATH` is unset or a subpath, the chart hosts are the
    #   defaults, and a client requests `/` or `/index.html`, then
    #   revalidates it with its `ETag`.
    # Expectation: The 200 response and the 304 response both carry the
    #   default page policy and every header in `SECURITY_HEADERS`, so a page
    #   revalidated from the browser cache keeps its policy.
    if base_path:
        monkeypatch.setenv("BASE_PATH", base_path)
    client = _create_shell_client(tmp_path, monkeypatch)
    path = f"{base_path}{subpath}"

    response = client.get(path)
    revalidated = client.get(
        path, headers={"If-None-Match": response.headers["etag"]}
    )

    assert response.status_code == 200
    assert response.headers["content-security-policy"] == _DEFAULT_PAGE_POLICY
    _assert_has_security_headers(response.headers)
    assert revalidated.status_code == 304
    assert (
        revalidated.headers["content-security-policy"] == _DEFAULT_PAGE_POLICY
    )
    _assert_has_security_headers(revalidated.headers)


def test_the_page_policy_allows_no_inline_or_evaluated_script(
    client: TestClient,
) -> None:
    # Test: `script-src`, `form-action`, and `frame-ancestors` of the page
    #   policy.
    # Situation: A client requests the shell with the default chart hosts.
    # Expectation: `script-src` allows the app's own files and the web
    #   component origin, but neither `'unsafe-inline'` nor `'unsafe-eval'`.
    #   `form-action` and `frame-ancestors` allow only the app's origin.
    directives = _read_policy_directives(
        client.get("/").headers["content-security-policy"]
    )

    assert directives["script-src"] == ["'self'", "https://datacommons.org"]
    assert "'unsafe-inline'" not in directives["script-src"]
    assert "'unsafe-eval'" not in directives["script-src"]
    assert directives["form-action"] == ["'self'"]
    assert directives["frame-ancestors"] == ["'self'"]


def test_the_page_policy_names_the_configured_chart_hosts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Test: Chart host settings in the page policy.
    # Situation: `DC_WEB_COMPONENT_URL` names a script on a CDN host with a
    #   port, and `DC_WEB_COMPONENT_API_ROOT` names autopush.
    # Expectation: `script-src` names the origin of the script URL, without
    #   its path, and `connect-src` names the API root.
    monkeypatch.setenv(
        DC_WEB_COMPONENT_URL_ENV,
        "https://cdn.example.com:8443/dc/datacommons.js",
    )
    monkeypatch.setenv(
        DC_WEB_COMPONENT_API_ROOT_ENV, "https://autopush.datacommons.org"
    )

    response = _create_shell_client(tmp_path, monkeypatch).get("/")

    directives = _read_policy_directives(
        response.headers["content-security-policy"]
    )
    assert directives["script-src"] == [
        "'self'",
        "https://cdn.example.com:8443",
    ]
    assert directives["connect-src"] == [
        "'self'",
        "https://autopush.datacommons.org",
    ]


@pytest.mark.parametrize(
    ("path", "expected_policy"),
    [
        ("/assets/index-a1b2c3d4.js", None),
        ("/logo.png", None),
        ("/dc-logo.svg", "sandbox"),
        ("/agent/health", None),
        ("/healthz", None),
    ],
)
def test_only_the_shell_carries_the_page_policy(
    path: str,
    expected_policy: str | None,
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    # Test: Responses other than the HTML shell.
    # Situation: A client requests a script, an image, an SVG, the health
    #   report, and the liveness route. The MCP lookups are stubbed.
    # Expectation: No response carries the page policy. The SVG keeps
    #   `sandbox`, and the others carry no `Content-Security-Policy`.
    monkeypatch.setattr(system, "mcp_url", lambda: "http://mcp.test/mcp")
    monkeypatch.setattr(system, "mcp_capabilities", lambda: Capabilities())

    response = client.get(path)

    assert response.status_code == 200
    assert response.headers.get("content-security-policy") == expected_policy


class _InlineScriptFinder(HTMLParser):
    """Collects the inline script forms that the page policy blocks.

    The parser records the `type` of every `<script>` element without `src`,
    and every event handler attribute (`on*`) or `javascript:` attribute
    value.
    """

    def __init__(self) -> None:
        super().__init__()
        self.inline_script_types: list[str] = []
        self.inline_handlers: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        """Records the inline script forms of one start tag."""
        attributes = dict(attrs)
        if tag == "script" and "src" not in attributes:
            self.inline_script_types.append(attributes.get("type") or "")
        for name, value in attrs:
            is_handler = name.startswith("on")
            is_script_url = (
                (value or "").strip().lower().startswith("javascript:")
            )
            if is_handler or is_script_url:
                self.inline_handlers.append(f"<{tag} {name}>")


def test_the_source_shell_holds_no_runnable_inline_script() -> None:
    # Test: Inline scripts in `ui/index.html`, which the page policy blocks.
    # Situation: The source HTML shell is parsed. The agent tests run
    #   without a UI build, so the source file stands in for the built shell,
    #   which adds only `<script>` elements with `src`.
    # Expectation: Every `<script>` without `src` is a JSON data block, which
    #   browsers do not run, the shell holds at least one such block, and no
    #   element carries an event handler attribute or a `javascript:` URL.
    finder = _InlineScriptFinder()
    finder.feed(_SOURCE_SHELL.read_text(encoding="utf-8"))

    assert finder.inline_script_types
    assert all(
        script_type == _DATA_BLOCK_TYPE
        for script_type in finder.inline_script_types
    )
    assert finder.inline_handlers == []
