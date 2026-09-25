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
"""
MCP Proxy Server (Proxy-Only Mode)

This script provides a REST API with CORS for browser-based frontends
to communicate with an already running Data Commons MCP server.

Prerequisites:
    Start the MCP server first:
    python3 -m uv tool run datacommons-mcp serve http --port 3000

Usage:
    python main.py
"""

from narratives_agent.config import _bootstrap_config_from_url
from narratives_agent.mcp.client import (
    get_tools,
    initialize_mcp,
    mcp_url,
)
from narratives_agent.server.app import app
from narratives_agent.server.routes import register_all
from narratives_agent.settings import get_settings

# Startup work runs at import time, not inside main(), because production
# serves `main:app` through gunicorn and never calls main() at all. Importing
# this module has to be enough to produce a fully-configured app: the config
# bootstrap writes config.json, which every later load_config() reads, and the
# blueprints have to be registered before the first request arrives.
#
# `python main.py` imports this module too, so both paths run identical setup
# and there is no second code path to keep in sync.
_bootstrap_config_from_url()
register_all(app)


def main():
    """Local development entry point.

    Production runs `gunicorn main:app` (see the Dockerfile); this exists so a
    developer can still `python main.py` and get the same app on a plain
    threaded server, with the MCP connection reported at startup.
    """
    settings = get_settings()
    print("=" * 60)
    print("Data Commons MCP Proxy Server (Proxy-Only Mode)")
    print("=" * 60)
    print(f"\nMCP endpoint: {mcp_url()}")
    print("\nIf that is a localhost URL, make sure the MCP server is running:")
    print(
        "  python3 -m uv tool run datacommons-mcp serve http --port "
        f"{settings.mcp_port}"
    )

    # Try to connect to MCP server
    print("\nChecking MCP server connection...")
    if initialize_mcp():
        tools = get_tools()
        print(f"\nConnected! Found {len(tools)} tools:")
        for t in tools:
            print(f"  - {t.get('name')}")
    else:
        print("\nWARNING: Could not connect to MCP server")
        print("The proxy will start anyway - MCP server can be started later")

    # Start proxy
    print(f"\nStarting proxy on port {settings.agent_port}...")
    print(f"Frontend should connect to: http://localhost:{settings.agent_port}")
    print("\nPress Ctrl+C to stop")
    print("=" * 60)

    app.run(
        host="0.0.0.0", port=settings.agent_port, debug=False, threaded=True
    )


if __name__ == "__main__":
    main()
