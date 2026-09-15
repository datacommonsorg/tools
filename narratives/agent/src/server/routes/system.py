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

from flask import Blueprint, jsonify

from src.config import get_gemini_model, load_config
from src.mcp.capabilities import current_cached as mcp_capabilities
from src.mcp.client import mcp_url
from src.server.app import PROXY_PORT

system_bp = Blueprint("system", __name__)


# Flask Routes

@system_bp.route("/health", methods=["GET"])
def health():
    """Health check.

    Reports the *resolved* MCP endpoint rather than a constant, so this can no
    longer disagree with where the agent is actually talking after the endpoint
    became configurable.
    """
    return jsonify({
        "status": "ok",
        "mcp_url": mcp_url(),
        # Discovered, not declared -- see src/mcp/capabilities.py. Tells an
        # operator at a glance whether this deployment can attribute sources.
        "mcp": mcp_capabilities().describe(),
    })


@system_bp.route("/", methods=["GET"])
def index():
    # Links are relative so they resolve under whatever AGENT_API_PREFIX the
    # blueprint was mounted at, rather than 404ing at the site root.
    return f"""
    <html>
    <head><title>Data Commons agent</title></head>
    <body>
    <h1>Data Commons agent</h1>
    <p>MCP server: {mcp_url()}</p>
    <ul>
        <li><a href="health">health</a> - health, MCP generation and tool surface</li>
        <li><a href="api/tools">api/tools</a> - discovered tool surface</li>
        <li><a href="api/config">api/config</a> - backend config (no API key)</li>
        <li><a href="brand">brand</a> - the branding document</li>
        <li>POST api/call - execute one tool</li>
        <li>POST chat/stream - chat, server-sent events</li>
    </ul>
    </body>
    </html>
    """


# ============================================================
# NEW BACKEND API ENDPOINTS FOR GEMINI CALLS
# ============================================================

@system_bp.route("/api/config", methods=["GET"])
def get_config_endpoint():
    """Return sanitized config (without API key) for frontend."""
    config = load_config()
    if not config:
        return jsonify({"success": False, "error": "Config not loaded"}), 500

    # Return config without sensitive data
    safe_config = {
        "proxy_url": config.get("proxy_url", f"http://localhost:{PROXY_PORT}"),
        "gemini": {
            "api_base": config.get("gemini", {}).get("api_base", ""),
            "mcp_model": get_gemini_model(config),
            "kb_model": get_gemini_model(config, "kb_model"),
        },
        "mcp": config.get("mcp", {}),
        "knowledge_base": config.get("knowledge_base", {}),
        "thinking": config.get("thinking", {}),
        "has_api_key": bool(config.get("gemini", {}).get("api_key")),
    }
    return jsonify({"success": True, "config": safe_config})
