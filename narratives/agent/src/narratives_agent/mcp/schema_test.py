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
"""Tests for MCP tool argument normalization in `schema.fix_tool_arguments`.

Verifies that `fix_tool_arguments` normalizes date-range and list parameters
across both MCP 1.2.x (`get_observations`) and MCP 1.3.x
(`get_child_observations`, `search_child_indicators`, `get_variable_metadata`)
tool names before requests are sent to the MCP server.
"""

import pytest

from narratives_agent.mcp import schema


@pytest.mark.parametrize(
    "tool",
    ["get_observations", "get_child_observations"],
    ids=["get_observations", "get_child_observations (1.3.x only)"],
)
def test_date_is_forced_to_range_when_range_bounds_are_given(
    tool: str,
) -> None:
    # Test: Automatic setting of `date="range"` when range bounds are provided.
    # Situation: The model passes `date_range_start` without setting
    #   `date="range"` on `get_observations` or `get_child_observations`.
    # Expectation: `fix_tool_arguments` sets `args["date"] = "range"` so the
    #   MCP server applies the requested date range instead of returning only
    #   the single latest observation.
    args = schema.fix_tool_arguments(tool, {"date_range_start": "2000"})
    assert args["date"] == "range"


def test_scalar_places_is_coerced_to_a_list() -> None:
    # Test: Coercion of a scalar `places` argument on `search_child_indicators`.
    # Situation: The model supplies a single string for `places` instead of a
    #   list of strings.
    # Expectation: `fix_tool_arguments` wraps the string in a single-element
    #   list to match the MCP server's schema.
    args = schema.fix_tool_arguments(
        "search_child_indicators", {"places": "India"}
    )
    assert args["places"] == ["India"]


def test_scalar_variable_dcids_is_coerced_to_a_list() -> None:
    # Test: Coercion of a scalar `variable_dcids` argument on
    #   `get_variable_metadata`.
    # Situation: The model supplies a single string for `variable_dcids`
    #   instead of a list of strings.
    # Expectation: `fix_tool_arguments` wraps the string in a single-element
    #   list to match the MCP server's schema.
    args = schema.fix_tool_arguments(
        "get_variable_metadata", {"variable_dcids": "Count_Person"}
    )
    assert args["variable_dcids"] == ["Count_Person"]
