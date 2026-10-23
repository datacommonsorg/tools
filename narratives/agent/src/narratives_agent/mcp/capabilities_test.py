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

Verifies that `capabilities.from_tools` derives the support status, tool
names, and missing `REQUIRED_TOOLS` from the tool definitions returned by
`tools/list`, and that `capabilities.warn_on_missing_tools` logs the missing
tools. The fixtures cover two tool lists:
- MCP 1.2.x: `search_indicators` and `get_observations` (`unsupported`)
- MCP 1.3.x+ (public Data Commons): all six required tools
"""

import logging

import pytest

from narratives_agent.json_value import JsonObject
from narratives_agent.mcp import capabilities, client


def _tools(*names: str) -> list[client.McpTool]:
    """Returns one `McpTool` per name, with an empty object schema."""
    return [
        client.McpTool(
            name=name,
            description="",
            input_schema={"type": "object", "properties": {}},
        )
        for name in names
    ]


TOOLS_121 = _tools("search_indicators", "get_observations")
TOOLS_130 = _tools(
    "search_indicators",
    "search_child_indicators",
    "get_variable_metadata",
    "get_observations",
    "get_child_observations",
    "get_multi_entity_observations",
)


@pytest.mark.parametrize(
    ("tools", "expected"),
    [(TOOLS_121, False), (TOOLS_130, True)],
    ids=["1.2.x -> no source attribution", "1.3.x -> source attribution"],
)
def test_source_attribution_follows_the_metadata_tool(
    tools: list[client.McpTool], expected: bool
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
    tools: list[client.McpTool], expected: int
) -> None:
    # Test: Filtering of observation tools exposed to the model.
    # Situation: An MCP 1.2.x server provides one observation tool
    #   (`get_observations`), while an MCP 1.3.x server provides three.
    # Expectation: `caps.observation_tools` contains only the observation tools
    #   supported by the target server so the model does not invoke nonexistent
    #   tools.
    caps = capabilities.from_tools(tools)
    assert len(caps.observation_tools) == expected


def test_a_server_with_no_tools_reports_unknown_support() -> None:
    # Test: Support status when the server returns an empty tool list.
    # Situation: `capabilities.from_tools` is given an empty list `[]`.
    # Expectation: `support` is `"unknown"` rather than `"unsupported"`.
    assert capabilities.from_tools([]).support == "unknown"


def test_support_labels_the_full_and_the_partial_surface() -> None:
    # Test: Support status for full and partial tool lists.
    # Situation: `capabilities.from_tools` is called with the MCP 1.3.x tool
    #   list, the MCP 1.2.x tool list, and a list that contains only a tool
    #   that is not required.
    # Expectation: `support` is `"supported"` for the MCP 1.3.x list and
    #   `"unsupported"` for the other two, because each lacks at least one
    #   required tool.
    assert capabilities.from_tools(TOOLS_130).support == "supported"
    assert capabilities.from_tools(TOOLS_121).support == "unsupported"
    assert (
        capabilities.from_tools(_tools("unrelated_tool")).support
        == "unsupported"
    )


def test_required_tools_are_checked_against_the_served_surface() -> None:
    # Test: `required_tools_present` and `missing_tools`.
    # Situation: Capabilities are built from the full six-tool list, a list
    #   missing the two child-place tools, and an empty list.
    # Expectation: The full list reports all required tools present and none
    #   missing; the partial list reports the two missing tools in sorted
    #   order; the empty list reports all six tools as missing.
    full = capabilities.from_tools(TOOLS_130)
    assert full.required_tools_present is True
    assert full.missing_tools == ()

    partial = capabilities.from_tools(
        [
            tool
            for tool in TOOLS_130
            if tool.name
            not in ("get_child_observations", "search_child_indicators")
        ]
    )
    assert partial.required_tools_present is False
    assert partial.missing_tools == (
        "get_child_observations",
        "search_child_indicators",
    )

    empty = capabilities.from_tools([])
    assert empty.required_tools_present is False
    assert empty.missing_tools == (
        "get_child_observations",
        "get_multi_entity_observations",
        "get_observations",
        "get_variable_metadata",
        "search_child_indicators",
        "search_indicators",
    )


def test_a_tool_with_an_empty_name_is_ignored() -> None:
    # Test: Filtering of nameless tools in `capabilities.from_tools`.
    # Situation: The tool list holds a tool with an empty name and one tool
    #   named `"valid_tool"`.
    # Expectation: `from_tools` retains only the non-empty tool name
    #   (`"valid_tool"`).
    caps = capabilities.from_tools(_tools("", "valid_tool"))
    assert caps.tool_names == frozenset({"valid_tool"})


def test_empty_tool_list_yields_empty_tool_names() -> None:
    # Test: `tool_names` when `tools/list` returns an empty list.
    # Situation: `capabilities.from_tools` is called with `[]`.
    # Expectation: `tool_names` is an empty `frozenset`.
    assert capabilities.from_tools([]).tool_names == frozenset()


@pytest.mark.parametrize(
    ("tools", "expected"),
    [
        (
            TOOLS_121,
            {
                "support": "unsupported",
                "tool_count": 2,
                "tools": ["get_observations", "search_indicators"],
                "supports_source_attribution": False,
                "missing_tools": [
                    "get_child_observations",
                    "get_multi_entity_observations",
                    "get_variable_metadata",
                    "search_child_indicators",
                ],
            },
        ),
        (
            TOOLS_130,
            {
                "support": "supported",
                "tool_count": 6,
                "tools": [
                    "get_child_observations",
                    "get_multi_entity_observations",
                    "get_observations",
                    "get_variable_metadata",
                    "search_child_indicators",
                    "search_indicators",
                ],
                "supports_source_attribution": True,
                "missing_tools": [],
            },
        ),
    ],
    ids=["1.2.x surface", "1.3.x surface"],
)
def test_describe_reports_discovered_tool_surface(
    tools: list[client.McpTool], expected: JsonObject
) -> None:
    # Test: Summary dictionary returned by `Capabilities.describe`.
    # Situation: `describe()` is called on capabilities derived from MCP 1.2.x
    #   and MCP 1.3.x tool lists.
    # Expectation: `describe()` returns the support status, tool count,
    #   alphabetically sorted tool names, `supports_source_attribution` flag,
    #   and sorted `missing_tools` for each surface.
    assert capabilities.from_tools(tools).describe() == expected


def test_warn_on_missing_tools_logs_missing_required_tools(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Test: Warning logged by `warn_on_missing_tools` when tools are missing.
    # Situation: `warn_on_missing_tools` is called with the MCP 1.3.x tool list
    #   and then with the MCP 1.2.x tool list.
    # Expectation: The MCP 1.3.x list logs no warning, and the MCP 1.2.x list
    #   logs one warning naming each missing tool.
    with caplog.at_level(logging.WARNING, logger=capabilities.logger.name):
        capabilities.warn_on_missing_tools(TOOLS_130)
        assert caplog.records == []
        capabilities.warn_on_missing_tools(TOOLS_121)

    (warning,) = caplog.records
    assert warning.levelno == logging.WARNING
    assert warning.getMessage().endswith(
        "missing required tools: get_child_observations, "
        "get_multi_entity_observations, get_variable_metadata, "
        "search_child_indicators"
    )


def test_current_cached_reads_cached_tools_without_warning(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Test: `current_cached` builds capabilities from `client.cached_tools`
    #   without logging gap warnings.
    # Situation: `client.cached_tools` returns an MCP 1.2.x tool list.
    # Expectation: `current_cached` returns the corresponding `Capabilities`
    #   snapshot and logs no warning.
    monkeypatch.setattr(client, "cached_tools", lambda: TOOLS_121)

    with caplog.at_level(logging.WARNING, logger=capabilities.logger.name):
        caps = capabilities.current_cached()

    assert caps.tool_names == frozenset(
        {"search_indicators", "get_observations"}
    )
    assert caplog.text == ""
