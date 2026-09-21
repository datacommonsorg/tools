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
"""Tests for MCP server capability discovery from `tools/list` responses.

Verifies that `capabilities.from_tools` derives supported features and tool
names from the tool definitions returned by either MCP server generation:
- MCP 1.2.x (CDC services container): `search_indicators` and `get_observations`
- MCP 1.3.x+ (DCP / public Data Commons): six tools including
  `get_variable_metadata`, `get_child_observations`, and
  `get_multi_entity_observations`
"""

from typing import Any

import pytest

from narratives_agent.mcp import capabilities

TOOLS_121 = [{"name": "search_indicators"}, {"name": "get_observations"}]
TOOLS_130 = [
    {"name": n}
    for n in (
        "search_indicators",
        "search_child_indicators",
        "get_variable_metadata",
        "get_observations",
        "get_child_observations",
        "get_multi_entity_observations",
    )
]


@pytest.mark.parametrize(
    ("tools", "expected"),
    [(TOOLS_121, False), (TOOLS_130, True)],
    ids=["1.2.x -> no source attribution", "1.3.x -> source attribution"],
)
def test_source_attribution_follows_the_metadata_tool(
    tools: list[dict[str, Any]], expected: bool
) -> None:
    # Test: Detection of source attribution support (`get_variable_metadata`).
    # Situation: `capabilities.from_tools` is called with an MCP 1.2.x tool
    #   list (which lacks `get_variable_metadata`) and an MCP 1.3.x tool list
    #   (which includes it).
    # Expectation: `supports_source_attribution` is True only when
    #   `get_variable_metadata` is present in the server's tool list.
    caps = capabilities.from_tools(tools)
    assert caps.supports_source_attribution is expected


@pytest.mark.parametrize(
    ("tools", "expected"),
    [(TOOLS_121, 1), (TOOLS_130, 3)],
    ids=["1.2.x observation tools = 1", "1.3.x observation tools = 3"],
)
def test_observation_tool_count_matches_the_served_surface(
    tools: list[dict[str, Any]], expected: int
) -> None:
    # Test: Filtering of observation tools exposed to the model.
    # Situation: An MCP 1.2.x server provides one observation tool
    #   (`get_observations`), while an MCP 1.3.x server provides three.
    # Expectation: `caps.observation_tools` contains only the observation tools
    #   supported by the target server so the model does not invoke nonexistent
    #   tools.
    caps = capabilities.from_tools(tools)
    assert len(caps.observation_tools) == expected


def test_a_server_with_no_tools_reports_an_unknown_generation() -> None:
    # Test: Generation label when the server returns an empty tool list.
    # Situation: `capabilities.from_tools` is given an empty list `[]`.
    # Expectation: `generation` is set to `"unknown"` rather than defaulting to
    #   a specific MCP server version.
    assert capabilities.from_tools([]).generation == "unknown"


def test_generation_labels_both_known_surfaces() -> None:
    # Test: Diagnostic generation label for known MCP tool surfaces.
    # Situation: `capabilities.from_tools` is called with the MCP 1.3.x and
    #   MCP 1.2.x tool lists.
    # Expectation: `generation` returns `"1.3.x-or-later"` for the six-tool
    #   surface and `"1.2.x"` for the two-tool surface.
    assert capabilities.from_tools(TOOLS_130).generation == "1.3.x-or-later"
    assert capabilities.from_tools(TOOLS_121).generation == "1.2.x"
