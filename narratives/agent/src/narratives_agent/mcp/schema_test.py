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
"""Argument coercion, covering every generation's tool names.

Part of the plug-and-play guarantee: one agent, either MCP server generation.
The agent must run unchanged against a CDC services container (MCP 1.2.x, two
fat tools, `place_observations` / `time_series` payloads) and a DCP or public
instance (1.3.x, six tools, columnar `data.rows` payloads).

A coercion that names only the 1.2.x tool is not a missing feature on 1.3.x: it
is a request that goes out malformed against the tool the model actually chose.
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
    # Test: the date/date_range_start pairing the model routinely gets wrong.
    # Situation: the model supplies date_range_start without date="range", on
    #   each of the observation tools that takes the date trio.
    # Expectation: date is forced to "range". Load-bearing, not cosmetic: the
    #   server ignores the range bounds unless date is exactly "range" and
    #   returns a single latest value instead. The fix has to cover every tool
    #   name or a range request against child places silently collapses to one
    #   date.
    args = schema.fix_tool_arguments(tool, {"date_range_start": "2000"})
    assert args["date"] == "range"


def test_scalar_places_is_coerced_to_a_list() -> None:
    # Test: list coercion on search_child_indicators, a 1.3.x tool.
    # Situation: the model passes a bare string for `places`.
    # Expectation: it is wrapped in a list, which is what the server requires.
    args = schema.fix_tool_arguments(
        "search_child_indicators", {"places": "India"}
    )
    assert args["places"] == ["India"]


def test_scalar_variable_dcids_is_coerced_to_a_list() -> None:
    # Test: list coercion on get_variable_metadata, a 1.3.x tool.
    # Situation: the model asks about a single variable and passes a bare
    #   string for `variable_dcids`.
    # Expectation: it is wrapped in a list -- the server rejects the string
    #   outright rather than coercing it.
    args = schema.fix_tool_arguments(
        "get_variable_metadata", {"variable_dcids": "Count_Person"}
    )
    assert args["variable_dcids"] == ["Count_Person"]
