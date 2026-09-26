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
UI build: `index.html`, the content-hashed bundle under `assets/`, and the
bare files the UI loads from the root, such as `logo.png`. `config.json` and
`logs/` live under `agent_root`, outside the static root, so no file needs to
be filtered by name or suffix.
"""

import os
from pathlib import PurePath

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

router = APIRouter()


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
    """Serves the UI build with a cache policy for each kind of file.

    The shell is never cached -- a stale index.html can reference a superseded
    bundle -- while the content-hashed assets it points at are immutable. Every
    other file is cached for an hour: its name carries no content hash, so a
    replaced file has to be able to take effect.
    """

    def file_response(
        self,
        full_path: str | os.PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        """Returns the file's response with the Cache-Control for its kind.

        The header is set after the base class chooses between the file and a
        304, so a 304 carries the same policy as the file it stands for.
        """
        response = super().file_response(
            full_path, stat_result, scope, status_code
        )
        if PurePath(full_path).name == "index.html":
            cache_control = "no-store"
        elif PurePath(self.get_path(scope)).parts[:1] == ("assets",):
            cache_control = "public, max-age=31536000, immutable"
        else:
            cache_control = "public, max-age=3600"
        response.headers["Cache-Control"] = cache_control
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
