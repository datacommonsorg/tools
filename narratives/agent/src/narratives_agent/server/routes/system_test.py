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
"""Tests for the health route in `system`.

Verifies that `/health` reports the service status, the resolved MCP
endpoint, the cached tool surface, and the debug report mode, and that it
answers HEAD.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from narratives_agent import config
from narratives_agent.config_model import AgentConfig, DebugConfig
from narratives_agent.mcp.capabilities import Capabilities
from narratives_agent.server.routes import system
from narratives_agent.settings import DEBUG_REPORT_ENV


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Returns a test client for an app that serves only `system.router`.

    The MCP endpoint, the cached tool list, and the loaded configuration
    (none) are stubbed, so no request reads config.json or reaches an MCP
    server.
    """
    monkeypatch.setattr(config, "load_config", lambda: None)
    monkeypatch.setattr(system, "mcp_url", lambda: "http://mcp.test/mcp")
    monkeypatch.setattr(
        system,
        "mcp_capabilities",
        lambda: Capabilities(
            tool_names=frozenset({"get_observations", "get_variable_metadata"})
        ),
    )
    app = FastAPI()
    app.include_router(system.router, prefix="/agent")
    return TestClient(app)


def test_health_reports_status_mcp_endpoint_and_tool_surface(
    client: TestClient,
) -> None:
    # Test: Payload of `GET /agent/health`.
    # Situation: The MCP endpoint resolves to a test URL, and the cached tool
    #   list holds `get_observations` and `get_variable_metadata`.
    # Expectation: The route answers 200 with status `ok`, the endpoint, and
    #   the capabilities of that tool list, including `support` and
    #   `missing_tools`, serialized byte for byte with the keys in this order.
    response = client.get("/agent/health")

    assert response.status_code == 200
    assert response.content == (
        b'{"status":"ok","mcp_url":"http://mcp.test/mcp","mcp":{'
        b'"support":"unsupported","tool_count":2,'
        b'"tools":["get_observations","get_variable_metadata"],'
        b'"supports_source_attribution":true,'
        b'"missing_tools":['
        b'"get_child_observations",'
        b'"get_multi_entity_observations",'
        b'"search_child_indicators",'
        b'"search_indicators"'
        b']},"debug_report":"off"}'
    )


@pytest.mark.parametrize("mode", ["on", "flag"])
def test_health_reports_configured_debug_report_mode(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    # Test: `debug_report` field of `GET /agent/health`.
    # Situation: `DEBUG_REPORT` is configured in the environment.
    # Expectation: The health payload reflects the configured mode.
    monkeypatch.setenv(DEBUG_REPORT_ENV, mode)

    response = client.get("/agent/health")

    assert response.status_code == 200
    assert response.json()["debug_report"] == mode


def test_health_reports_the_debug_report_mode_from_the_config(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Test: `debug_report` field of `GET /agent/health` without the variable.
    # Situation: `DEBUG_REPORT` is unset, and the loaded configuration sets
    #   `debug.report` to `"on"`.
    # Expectation: The health payload reports `"on"`, the resolved mode.
    monkeypatch.setattr(
        config,
        "load_config",
        lambda: AgentConfig(debug=DebugConfig(report="on")),
    )

    response = client.get("/agent/health")

    assert response.status_code == 200
    assert response.json()["debug_report"] == "on"


def test_health_answers_head_with_an_empty_body(client: TestClient) -> None:
    # Test: HEAD support on `/agent/health`.
    # Situation: A client sends `HEAD /agent/health`.
    # Expectation: The route answers 200 with a JSON content type and an empty
    #   body.
    response = client.head("/agent/health")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.content == b""
