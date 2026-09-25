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
"""Builds the FastAPI application that serves the agent API, proxy, and UI.

Uvicorn serves the module-level `app`, as `narratives_agent.server.app:app`,
both in the container and in local development.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from narratives_agent.config import bootstrap_config_from_url
from narratives_agent.server.routes import brand, chat, dcproxy, spa, system
from narratives_agent.settings import get_settings

logger = logging.getLogger(__name__)


def _allowed_origins() -> list[str]:
    """Resolves the CORS allow-list, failing closed outside local development.

    ALLOWED_ORIGIN is a comma-separated list of origins. It is required whenever
    the process is not running locally: a deployed service that fell back to "*"
    would let any site drive the agent with the caller's credentials.

    Returns:
        The configured origins, or the loopback origins when unset locally.
    """
    settings = get_settings()
    configured = settings.allowed_origin
    if configured:
        return [
            origin.strip() for origin in configured.split(",") if origin.strip()
        ]

    # K_SERVICE is set by Cloud Run; its presence means "not local dev".
    if settings.k_service:
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


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Writes config.json and loads branding before the first request.

    The config bootstrap writes config.json, which every later load_config()
    reads. Branding is then read from GCS once, so every later request is
    served from process memory rather than from the bucket. load_branding()
    swallows its own failures: a missing, unreachable or malformed config
    leaves the UI on its shipped design tokens rather than stopping the server
    from starting.
    """
    bootstrap_config_from_url()
    brand.load_branding()
    yield


def create_app() -> FastAPI:
    """Builds the application from its middleware, routers, and static files.

    Each part of the URL space has one owner:

      /agent/*                  the agent's own API, including branding
      /core, /api, /tools, ...  the data plane, reverse-proxied by dcproxy
      everything else           the SPA

    The API routers are included under `agent_api_prefix`, and brand.py builds
    its asset URLs from the same setting.

    Returns:
        The application, without API documentation routes.
    """
    settings = get_settings()
    app = FastAPI(
        lifespan=_lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        # No trailing-slash redirects: one would be built from the request
        # URL, which names http:// behind Cloud Run.
        redirect_slashes=False,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins(),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # The app serves each request from the first route that matches, in
    # registration order, and the static mount at "/" matches every path. The
    # mount therefore comes last, so the proxy routes win over a static file of
    # the same name and every path the routers do not claim falls through to
    # the SPA.
    for api_router in (brand.router, system.router, chat.router):
        app.include_router(api_router, prefix=settings.agent_api_prefix)
    app.include_router(dcproxy.router)
    app.include_router(spa.router)
    app.mount(
        "/",
        spa.SpaStaticFiles(
            directory=settings.static_root, html=True, check_dir=False
        ),
    )
    return app


app = create_app()
