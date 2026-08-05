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

import logging
import os
import time

from flask import Blueprint, jsonify, request

from src.config import _fetch_gcs_url

logger = logging.getLogger(__name__)

brand_bp = Blueprint("brand", __name__)


# Route aliases the React UI expects. The upstream routes (/api/chat/stream,
# /api/config) stay live
# for backward compatibility; these aliases are what the SPA at /agent/* hits
# via the services container's nginx prefix-strip.
# Short-TTL cache for branding.json so we don't hit GCS (and the
# metadata token endpoint) on every page load. Bounds staleness to _BRAND_TTL
# seconds; /brand?refresh=1 forces an immediate refetch after a config sync
# (e.g. `deploy.sh --config-only`).
_BRAND_CACHE: dict = {"ts": 0.0, "payload": None}
_BRAND_TTL_SECONDS = int(os.environ.get("BRAND_CACHE_TTL", "60"))


def _build_brand_payload() -> dict:
    """Assemble the /brand payload: the config bucket URL plus, when available,
    the branding.json contents fetched from the (possibly private) bucket."""
    brand_config_url = os.environ.get("BRAND_CONFIG_URL", "").rstrip("/")
    branding_data = None
    if brand_config_url:
        try:
            r = _fetch_gcs_url(f"{brand_config_url}/branding.json")
            if r.status_code == 200:
                branding_data = r.json()
                logger.info("Successfully fetched branding.json from config bucket")
            else:
                logger.warning(f"Failed to fetch branding.json: HTTP {r.status_code}")
        except Exception as e:
            logger.error(f"Error fetching branding.json from bucket: {e}")

    return {
        "brand_config_url": brand_config_url,
        "instance": os.environ.get("INSTANCE_ID", ""),
        "branding": branding_data,
    }


@brand_bp.route("/brand", methods=["GET"])
def brand_alias():
    """Return the per-instance branding bucket URL and branding.json contents.

    Cached in-process for _BRAND_TTL_SECONDS; pass ?refresh=1 to force a fresh
    fetch (e.g. right after uploading a new branding.json to the bucket)."""
    force = request.args.get("refresh") == "1"
    now = time.time()
    cached = _BRAND_CACHE["payload"]
    if not force and cached is not None and now - _BRAND_CACHE["ts"] < _BRAND_TTL_SECONDS:
        payload = cached
    else:
        payload = _build_brand_payload()
        _BRAND_CACHE["payload"] = payload
        _BRAND_CACHE["ts"] = now

    resp = jsonify(payload)
    resp.headers["Cache-Control"] = "no-store"
    return resp
