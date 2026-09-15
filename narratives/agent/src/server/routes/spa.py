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

Until the app plane was split out, the services container's nginx did three
jobs this process now takes on: serve the SPA and its assets, strip the /agent
prefix off agent calls, and answer /healthz. The prefix is handled by
registering the API blueprints under url_prefix (see routes/__init__.py); the
other two live here.

Cache headers deliberately mirror the nginx config they replace. The shell is
never cached -- a stale index.html can reference a superseded bundle -- while
the content-hashed assets it points at are immutable.
"""

import logging
import os
from pathlib import Path

from flask import Blueprint, Response, abort, send_from_directory

logger = logging.getLogger(__name__)

spa_bp = Blueprint("spa", __name__)

# The Dockerfile copies the `ui` build here. Overridable so a local
# `python main.py` can point straight at ui/dist without a container build.
# This module is agent/src/server/routes/spa.py, so parents[3] is agent/.
_DEFAULT_STATIC_ROOT = Path(__file__).resolve().parents[3] / "static"
STATIC_ROOT = Path(os.environ.get("STATIC_ROOT", _DEFAULT_STATIC_ROOT))

# Bare files the SPA loads from the root, e.g. /logo.png.
#
# Two branches previously each hardcoded their own list of these and the lists
# barely overlapped -- merging either wholesale would have 404'd the other's
# assets, silently, as missing images rather than as an error. Worse, adding a
# file to ui/public/ and forgetting the list produced the same silent failure.
#
# So the set is derived from what the UI build actually shipped, filtered to
# inert asset types. That keeps the security property the allowlist existed for
# -- this process still cannot be walked into serving config.json, the logs
# directory, or anything else that shares the image -- while removing the
# hand-maintenance that made it wrong.
_SERVABLE_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".woff", ".woff2", ".txt"}
)


def _discover_root_assets() -> frozenset:
    """Inert files sitting at the root of the built SPA."""
    if not STATIC_ROOT.is_dir():
        return frozenset()
    return frozenset(
        entry.name
        for entry in STATIC_ROOT.iterdir()
        if entry.is_file() and entry.suffix.lower() in _SERVABLE_SUFFIXES
    )


_ROOT_ASSETS = _discover_root_assets()


@spa_bp.route("/healthz", methods=["GET"])
def healthz():
    """Liveness for the Cloud Run startup probe and the uptime check.

    Kept at /healthz rather than folded into /agent/health because the probe
    and the monitoring config already point here, and neither has any reason
    to change just because the thing answering it did.

    Note Cloud Run's frontend reserves /healthz and answers it itself without
    forwarding -- so this works for the startup probe, which hits the container
    port directly, but an external uptime check must target /agent/health.
    """
    return Response("ok\n", mimetype="text/plain")


@spa_bp.route("/", methods=["GET"])
def index():
    """The SPA shell. Never cached: it names the hashed bundle."""
    response = send_from_directory(STATIC_ROOT, "index.html")
    response.headers["Cache-Control"] = "no-store"
    return response


@spa_bp.route("/assets/<path:name>", methods=["GET"])
def asset(name: str):
    """Content-hashed JS/CSS. Safe to cache forever -- the name changes."""
    response = send_from_directory(STATIC_ROOT / "assets", name)
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@spa_bp.route("/<name>", methods=["GET"])
def root_asset(name: str):
    """One of the bare files the SPA loads from the root.

    Not immutable: these names carry no content hash, so a swapped logo has to
    be able to take effect. An hour matches what nginx served.
    """
    if name not in _ROOT_ASSETS:
        abort(404)
    response = send_from_directory(STATIC_ROOT, name)
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response
