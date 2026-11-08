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
`index.html` is served with the effective chat availability stamped into its
`<script id="runtime-config" type="application/json">` element.
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


def _serialize_runtime_config() -> bytes:
    """Returns the chat availability JSON, escaped for a `<script>` element.

    Only `enable_chat` and `unavailable_message` are serialized; nothing
    else from the configuration reaches the page.
    """
    chat = get_chat_config()
    serialized = json.dumps(
        {
            "enable_chat": chat.enabled,
            "unavailable_message": chat.unavailable_message,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return serialized.translate(_HTML_JSON_ESCAPES).encode("utf-8")


def _render_shell(full_path: str) -> bytes:
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
        + _serialize_runtime_config()
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


def _build_shell_response(body: bytes, scope: Scope) -> Response:
    """Returns the stamped shell, or 304 when `If-None-Match` matches it.

    The `ETag` hashes the stamped bytes, so a change to the chat settings
    changes it. `Last-Modified` is omitted and `If-Modified-Since` ignored:
    the file keeps its build time across restarts that change the stamped
    JSON, so a date comparison would return a stale 304.
    """
    etag = f'"{hashlib.sha256(body).hexdigest()}"'
    headers = {
        "Cache-Control": _REVALIDATE_CACHE_CONTROL,
        "ETag": etag,
        "X-Content-Type-Options": "nosniff",
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
    """Serves the UI build with cache-control and security headers."""

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
                body = await run_in_threadpool(_render_shell, full_path)
                return _build_shell_response(body, scope)
        return await super().get_response(path, scope)

    def file_response(
        self,
        full_path: str | os.PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        """Returns a file or 304 response with cache and security headers."""
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
        response.headers["X-Content-Type-Options"] = "nosniff"
        if PurePath(full_path).suffix.lower() == ".svg":
            # Sandbox SVG responses so embedded scripts cannot execute in the
            # application's origin.
            response.headers["Content-Security-Policy"] = "sandbox"
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
