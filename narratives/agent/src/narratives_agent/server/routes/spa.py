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
"""Serves the compiled React UI and the path Cloud Run probes for liveness.

`SpaStaticFiles` serves any file under the static root, which holds only the
UI build: `index.html`, the content-hashed files under `assets/` and
`theme/`, and the bare files the UI loads from the root, such as
`dc-logo.svg`. `config.json` lives under `agent_root`, outside the static
root, so no file needs to be filtered by name or suffix. The root
`index.html` is served with the runtime settings (the effective chat
availability and the chart hosts) stamped into its
`<script id="runtime-config" type="application/json">` element, and with the
page's Content-Security-Policy.
"""

import hashlib
import json
import os
import stat
from pathlib import PurePath

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette import status
from starlette.datastructures import Headers
from starlette.types import Scope

from narratives_agent.config import get_chat_config
from narratives_agent.settings import Settings, get_url_origin

router = APIRouter()

# Files under these directories carry content hashes in their filenames and
# can be cached indefinitely.
_IMMUTABLE_DIRECTORIES = frozenset({"assets", "theme"})

# Every other file, including the stamped HTML shell, is revalidated on each
# use.
_REVALIDATE_CACHE_CONTROL = "no-cache"

# The HTML shell, and the paths `get_path` returns for `/` and `/index.html`
# under the mount.
_SHELL_FILE_NAME = "index.html"
_SHELL_PATHS = frozenset({".", _SHELL_FILE_NAME})

# The empty element in `ui/index.html` that receives the runtime JSON.
_RUNTIME_CONFIG_OPEN_TAG = (
    b'<script id="runtime-config" type="application/json">'
)
_SCRIPT_CLOSE_TAG = b"</script>"
_RUNTIME_CONFIG_SLOT = _RUNTIME_CONFIG_OPEN_TAG + _SCRIPT_CLOSE_TAG

# Escapes applied to JSON embedded in a `<script>` element: `<`, `>`, and `&`
# can then neither close the element nor start markup, and U+2028 and U+2029
# cannot end a string if the payload is evaluated as JavaScript.
_HTML_JSON_ESCAPES = str.maketrans(
    {
        "<": "\\u003c",
        ">": "\\u003e",
        "&": "\\u0026",
        "\u2028": "\\u2028",
        "\u2029": "\\u2029",
    }
)


_CONTENT_SECURITY_POLICY_HEADER = "Content-Security-Policy"

# Sources of the HTML shell's Content-Security-Policy.
_SELF_SOURCE = "'self'"
_NONE_SOURCE = "'none'"
# `datacommons.js` inserts `<style>` elements (Emotion and styled-components)
# into each chart's shadow root, so styles cannot be limited to files.
_UNSAFE_INLINE_SOURCE = "'unsafe-inline'"
# The app stylesheet (`ui/src/index.css`) imports Google Fonts, and
# `datacommons.js` adds `<link>` tags for Google Sans and Material Icons. Both
# load stylesheets from the stylesheet host and font files from the file host.
_GOOGLE_FONTS_STYLESHEET_ORIGIN = "https://fonts.googleapis.com"
_GOOGLE_FONTS_FILE_ORIGIN = "https://fonts.gstatic.com"
# Images come from provenance and theme hosts over HTTPS, and the PDF export
# code draws `data:` and `blob:` images.
_HTTPS_SOURCE = "https:"
_DATA_SOURCE = "data:"
_BLOB_SOURCE = "blob:"


@router.api_route("/healthz", methods=["GET", "HEAD"])
async def healthz() -> PlainTextResponse:
    """Reports liveness to the Cloud Run startup probe and the uptime check.

    Kept at /healthz rather than folded into /agent/health because the probe
    and the monitoring config already point here, and neither has any reason
    to change just because the thing answering it did.

    Note Cloud Run's frontend reserves /healthz and answers it itself without
    forwarding -- so this works for the startup probe, which hits the container
    port directly, but an external uptime check must target /agent/health.
    """
    return PlainTextResponse("ok\n")


def build_content_security_policy(settings: Settings) -> str:
    """Returns the Content-Security-Policy of the HTML shell.

    `script-src` allows only the app's own files and the origin of
    `DC_WEB_COMPONENT_URL`. It allows neither `'unsafe-inline'` nor
    `'unsafe-eval'`, because the page's inline `<script>` elements hold
    JSON, which browsers do not run. `connect-src` allows the agent API and
    `DC_WEB_COMPONENT_API_ROOT`, where the charts fetch their data.
    `base-uri 'none'` is safe because the app resolves paths from
    `location.pathname`, and `form-action 'self'` does not affect the chat
    input because the input submits through JavaScript.

    Args:
        settings: The validated settings, whose chart hosts contain no
            character that could end a source or a directive.

    Returns:
        The policy, with directives separated by `; `.
    """
    directives: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("default-src", (_SELF_SOURCE,)),
        (
            "script-src",
            (_SELF_SOURCE, get_url_origin(settings.dc_web_component_url)),
        ),
        (
            "style-src",
            (
                _SELF_SOURCE,
                _UNSAFE_INLINE_SOURCE,
                _GOOGLE_FONTS_STYLESHEET_ORIGIN,
            ),
        ),
        ("font-src", (_SELF_SOURCE, _GOOGLE_FONTS_FILE_ORIGIN, _DATA_SOURCE)),
        (
            "img-src",
            (_SELF_SOURCE, _HTTPS_SOURCE, _DATA_SOURCE, _BLOB_SOURCE),
        ),
        ("connect-src", (_SELF_SOURCE, settings.dc_web_component_api_root)),
        ("frame-src", (_SELF_SOURCE,)),
        ("object-src", (_NONE_SOURCE,)),
        ("base-uri", (_NONE_SOURCE,)),
        ("form-action", (_SELF_SOURCE,)),
        ("frame-ancestors", (_SELF_SOURCE,)),
    )
    return "; ".join(
        f"{name} {' '.join(sources)}" for name, sources in directives
    )


def _serialize_runtime_config(settings: Settings) -> bytes:
    """Returns the runtime settings JSON, escaped for a `<script>` element.

    Only the chat availability (`enable_chat`, `unavailable_message`) and
    the chart hosts (`web_component_url`, `web_component_api_root`) are
    serialized, so nothing else from the configuration reaches the page.
    The chart hosts come from `settings`, the `Settings` instance that the
    application was built with, so they stay fixed for the life of the
    process and match the Content-Security-Policy built from the same
    instance.
    """
    chat = get_chat_config()
    serialized = json.dumps(
        {
            "enable_chat": chat.enabled,
            "unavailable_message": chat.unavailable_message,
            "web_component_url": settings.dc_web_component_url,
            "web_component_api_root": settings.dc_web_component_api_root,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return serialized.translate(_HTML_JSON_ESCAPES).encode("utf-8")


def _render_shell(full_path: str, settings: Settings) -> bytes:
    """Returns the HTML shell with the runtime JSON stamped into its slot.

    Reads the file, so callers run it off the event loop. A file without the
    empty `#runtime-config` element is returned unchanged; only the first
    occurrence is stamped.
    """
    with open(full_path, "rb") as shell_file:
        template = shell_file.read()
    if _RUNTIME_CONFIG_SLOT not in template:
        return template
    stamped_slot = (
        _RUNTIME_CONFIG_OPEN_TAG
        + _serialize_runtime_config(settings)
        + _SCRIPT_CLOSE_TAG
    )
    return template.replace(_RUNTIME_CONFIG_SLOT, stamped_slot, 1)


def _matches_if_none_match(if_none_match: str, etag: str) -> bool:
    """Returns whether an `If-None-Match` value matches the strong `etag`.

    Accepts `*` and comma-separated lists, and compares weakly, so
    `W/"<hash>"` matches `"<hash>"`.
    """
    tags = [tag.strip() for tag in if_none_match.split(",")]
    return "*" in tags or etag in [tag.removeprefix("W/") for tag in tags]


def _build_shell_response(
    body: bytes, scope: Scope, content_security_policy: str
) -> Response:
    """Returns the stamped shell, or 304 when `If-None-Match` matches it.

    The 200 and 304 responses both carry `content_security_policy`, so a
    page revalidated from the browser cache keeps its policy.

    The `ETag` hashes the stamped bytes, so a change to the runtime
    settings changes it. The response omits `Last-Modified` and ignores
    `If-Modified-Since` because the file keeps its build time across
    restarts that change the stamped JSON, so a date comparison would
    return a stale 304.
    """
    etag = f'"{hashlib.sha256(body).hexdigest()}"'
    headers = {
        "Cache-Control": _REVALIDATE_CACHE_CONTROL,
        _CONTENT_SECURITY_POLICY_HEADER: content_security_policy,
        "ETag": etag,
    }
    if _matches_if_none_match(
        Headers(scope=scope).get("if-none-match", ""), etag
    ):
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED, headers=headers
        )
    headers["Content-Length"] = str(len(body))
    content = b"" if scope["method"] == "HEAD" else body
    return Response(content, media_type="text/html", headers=headers)


class SpaStaticFiles(StaticFiles):
    """Serves the UI build with cache and Content-Security-Policy headers.

    The HTML shell carries the chart hosts from the `Settings` that this
    instance is constructed with. The shell also carries the page's
    Content-Security-Policy, which is built once from the same `Settings`,
    so the hosts and the policy cannot disagree.
    """

    def __init__(
        self,
        *,
        directory: str | os.PathLike[str],
        html: bool,
        check_dir: bool,
        settings: Settings,
    ) -> None:
        """Configures `StaticFiles` for `directory` and stores `settings`.

        Args:
            directory: The static root.
            html: Whether a directory path serves its `index.html`.
            check_dir: Whether a missing `directory` raises at construction.
            settings: The settings that supply the chart hosts stamped
                into the shell and named in the shell's policy.
        """
        super().__init__(directory=directory, html=html, check_dir=check_dir)
        self._settings = settings
        self._content_security_policy = build_content_security_policy(settings)

    async def get_response(self, path: str, scope: Scope) -> Response:
        """Returns the stamped HTML shell for `/`, else the static file.

        `/` and `/index.html` (under the mount, so also under `BASE_PATH`)
        serve the root `index.html` through `_build_shell_response`. Every
        other path, method, or a missing shell takes the base class path.
        """
        if path in _SHELL_PATHS and scope["method"] in ("GET", "HEAD"):
            full_path, stat_result = await run_in_threadpool(
                self.lookup_path, _SHELL_FILE_NAME
            )
            if stat_result is not None and stat.S_ISREG(stat_result.st_mode):
                body = await run_in_threadpool(
                    _render_shell, full_path, self._settings
                )
                return _build_shell_response(
                    body, scope, self._content_security_policy
                )
        return await super().get_response(path, scope)

    def file_response(
        self,
        full_path: str | os.PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        """Returns a file or 304 response with cache headers.

        SVG files also carry `Content-Security-Policy: sandbox`. The other
        security headers are set by `SecurityHeadersMiddleware`.
        """
        response = super().file_response(
            full_path, stat_result, scope, status_code
        )
        parts = PurePath(self.get_path(scope)).parts
        if parts and parts[0] in _IMMUTABLE_DIRECTORIES:
            # One year (the standard HTTP max-age for indefinite caching).
            cache_control = "public, max-age=31536000, immutable"
        else:
            cache_control = _REVALIDATE_CACHE_CONTROL
        response.headers["Cache-Control"] = cache_control
        if PurePath(full_path).suffix.lower() == ".svg":
            # Sandbox SVG responses so embedded scripts cannot execute in the
            # application's origin.
            response.headers[_CONTENT_SECURITY_POLICY_HEADER] = "sandbox"
        return response

    async def check_config(self) -> None:
        """Skips the configuration check when the static root is missing.

        Without a UI build every path then answers 404, as a missing file does,
        instead of every request failing on the base class's `RuntimeError`.
        """
        if self.directory is not None and not await run_in_threadpool(
            os.path.isdir, self.directory
        ):
            return
        await super().check_config()
