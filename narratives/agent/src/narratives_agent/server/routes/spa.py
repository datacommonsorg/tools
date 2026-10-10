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
root, so no file needs to be filtered by name or suffix.
"""

import os
from pathlib import PurePath

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

router = APIRouter()

# Files under these directories carry content hashes in their filenames and
# can be cached indefinitely.
_IMMUTABLE_DIRECTORIES = frozenset({"assets", "theme"})


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


class SpaStaticFiles(StaticFiles):
    """Serves the UI build with cache-control and security headers."""

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
            cache_control = "no-cache"
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
