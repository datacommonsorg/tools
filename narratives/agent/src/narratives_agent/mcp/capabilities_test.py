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
"""Capability discovery from whatever tool surface a server happens to serve.

Part of the plug-and-play guarantee: one agent, either MCP server generation.
The agent must run unchanged against a CDC services container (MCP 1.2.x, two
fat tools, `place_observations` / `time_series` payloads) and a DCP or public
instance (1.3.x, six tools, columnar `data.rows` payloads).
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
    # Test: whether an answer can be attributed to a named source.
    # Situation: a 1.2.x tool surface, which has no get_variable_metadata, and
    #   a 1.3.x one, which does.
    # Expectation: the capability is reported from the tool surface itself.
    #   Without the tool the best available provenance is a bare domain
    #   scraped from the observation payload, which is worth surfacing rather
    #   than discovering from an unattributed answer.
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
    # Test: which observation tools the agent will offer the model.
    # Situation: 1.2.x serves one fat observations tool; 1.3.x splits it into
    #   three.
    # Expectation: only the tools the server actually has. Offering a tool the
    #   server lacks means the model calls it, gets "Unknown tool", and burns
    #   an iteration of a capped loop -- a slower, worse answer, with nothing
    #   anywhere saying why.
    caps = capabilities.from_tools(tools)
    assert len(caps.observation_tools) == expected


def test_a_server_with_no_tools_reports_an_unknown_generation() -> None:
    # Test: the label for a server whose tool surface could not be read.
    # Situation: tools/list returned nothing at all.
    # Expectation: "unknown" rather than a guess -- an empty surface is not
    #   evidence of an old server.
    assert capabilities.from_tools([]).generation == "unknown"


def test_generation_labels_both_known_surfaces() -> None:
    # Test: the human label attached to each surface.
    # Situation: the two generations the agent meets in the wild.
    # Expectation: labels that do not invite version branching. Behavior is
    #   driven by which tools are present, never by this string -- a version
    #   label invites `if generation == "1.3.0"`, and that is exactly the
    #   assumption that breaks when Google ships 1.4.
    assert capabilities.from_tools(TOOLS_130).generation == "1.3.x-or-later"
    assert capabilities.from_tools(TOOLS_121).generation == "1.2.x"
