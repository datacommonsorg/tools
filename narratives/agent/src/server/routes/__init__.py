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

import os

from src.server.routes.brand import brand_bp, load_branding
from src.server.routes.chat import chat_bp
from src.server.routes.dcproxy import dcproxy_bp
from src.server.routes.spa import spa_bp
from src.server.routes.system import system_bp
from src.server.routes.tools import tools_bp

# The API blueprints declare their routes at the root (/brand, /chat/stream,
# /health) because the services container's nginx used to strip the /agent
# prefix before proxying here. With the app plane serving its own ingress there
# is nothing in front to strip it, so the prefix is applied here instead --
# which keeps every URL the browser already calls working untouched, and leaves
# the root free for the SPA.
#
# brand.py reads the same variable to rewrite the asset URLs it embeds in the
# branding document. The two must agree, or the browser requests a logo from a
# path nothing serves.
_API_PREFIX = os.environ.get("AGENT_API_PREFIX", "/agent")


def register_all(app):
    """Register every route blueprint, and load branding into memory.

    Branding is read from GCS here, once, so every later request is served from
    process memory rather than from the bucket. load_branding() swallows its own
    failures: a missing, unreachable or malformed config leaves the UI on its
    shipped design tokens rather than stopping the server from starting.

    Registration order is not significant -- Werkzeug matches on rule
    specificity, not registration order -- but the grouping reflects who owns
    which URL space:

      /agent/*                  the agent's own API, including branding
      /core, /api, /tools, ...  the data plane, reverse-proxied by dcproxy
      everything else           the SPA
    """
    for bp in (brand_bp, system_bp, tools_bp, chat_bp):
        app.register_blueprint(bp, url_prefix=_API_PREFIX)

    # No prefix: these own the browser-facing root.
    app.register_blueprint(dcproxy_bp)
    app.register_blueprint(spa_bp)

    load_branding()
