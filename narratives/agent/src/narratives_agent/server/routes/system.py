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
"""Serves the agent's health report under the agent API prefix."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from narratives_agent.mcp.capabilities import current_cached as mcp_capabilities
from narratives_agent.mcp.client import mcp_url

router = APIRouter()


@router.api_route("/health", methods=["GET", "HEAD"])
def health() -> JSONResponse:
    """Returns service health status, resolved MCP endpoint, and tool surface.

    Returns:
        A JSON response with the keys `status`, `mcp_url`, and `mcp`.
    """
    return JSONResponse(
        {
            "status": "ok",
            "mcp_url": mcp_url(),
            # Capabilities are discovered from the MCP server tool list rather
            # than statically configured (see mcp/capabilities.py).
            "mcp": mcp_capabilities().describe(),
        }
    )
