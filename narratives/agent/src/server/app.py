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

from flask import Flask
from flask_cors import CORS

# Configuration
PROXY_PORT = int(os.environ.get("PROXY_PORT", 5001))

logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)


def _allowed_origins() -> list[str]:
    """Resolves the CORS allow-list, failing closed outside local development.

    ALLOWED_ORIGIN is a comma-separated list of origins. It is required whenever
    the process is not running locally: a deployed service that fell back to "*"
    would let any site drive the agent with the caller's credentials.

    Returns:
        The configured origins, or the loopback origins when unset locally.
    """
    configured = os.environ.get("ALLOWED_ORIGIN", "").strip()
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]

    # K_SERVICE is set by Cloud Run; its presence means "not local dev".
    if os.environ.get("K_SERVICE"):
        logger.error(
            "ALLOWED_ORIGIN is unset in a deployed environment; refusing to "
            "allow all origins. Set it to the service URL."
        )
        return []

    logger.warning(
        "ALLOWED_ORIGIN is unset; defaulting to localhost origins for local "
        "development only."
    )
    return ["http://localhost:3000", "http://127.0.0.1:3000"]


CORS(app, origins=_allowed_origins())
