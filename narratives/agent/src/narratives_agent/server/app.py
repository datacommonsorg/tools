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
"""Builds the FastAPI application that serves the agent API and UI.

Uvicorn serves the module-level `app`, as `narratives_agent.server.app:app`,
both in the container and in local development.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from narratives_agent import telemetry
from narratives_agent.config import bootstrap_config_from_url
from narratives_agent.mcp import client as mcp_client
from narratives_agent.server.routes import chat, spa, system
from narratives_agent.settings import get_settings
from narratives_agent.workflows.transcript import init_signing_key

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
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Bootstraps the agent config and closes pooled clients at shutdown.

    The config bootstrap runs before the first request, so every later
    load_config() call is served from process memory. It swallows its own
    failures rather than stopping the server from starting: an unreachable or
    malformed CONFIG_URL leaves the agent with no configuration, so the broken
    bucket surfaces as a `config_missing` error on every turn instead of being
    masked by the configuration shipped with the image.

    The MCP client's pooled HTTP client is opened on first use and closed here
    at shutdown.

    Telemetry is configured here rather than when the module is imported, so
    importing the application in a test or a tool installs no global tracer
    provider. Spans that are still buffered are written at shutdown.
    """
    telemetry.configure_telemetry()
    bootstrap_config_from_url()
    init_signing_key()
    try:
        yield
    finally:
        await mcp_client.aclose()
        telemetry.flush_telemetry()


def create_app() -> FastAPI:
    """Builds the application from its middleware, routers, and static files.

    Each part of the URL space has one owner:

      /agent/*                  the agent's own API
      everything else           the SPA

    The API routers are included under `agent_api_prefix`.

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
    telemetry.instrument_app(app)

    # The app serves each request from the first route that matches, in
    # registration order, and the static mount at "/" matches every path. The
    # mount therefore comes last, so every path the routers do not claim falls
    # through to the SPA.
    for api_router in (system.router, chat.router):
        app.include_router(api_router, prefix=settings.agent_api_prefix)
    app.include_router(spa.router)
    app.mount(
        "/",
        spa.SpaStaticFiles(
            directory=settings.static_root, html=True, check_dir=False
        ),
    )
    return app


app = create_app()
