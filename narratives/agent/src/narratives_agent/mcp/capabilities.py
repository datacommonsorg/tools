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
"""Inspects the MCP server's tool list and summarizes it for `/agent/health`.

Checks the tools returned by `tools/list` against `REQUIRED_TOOLS`, logs a
warning when required tools are missing, and formats the capability summary
reported by `/agent/health`.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from narratives_agent.json_value import JsonObject, JsonValue
from narratives_agent.mcp import client

logger = logging.getLogger(__name__)

TOOL_SEARCH_INDICATORS = "search_indicators"
TOOL_SEARCH_CHILD_INDICATORS = "search_child_indicators"
TOOL_GET_VARIABLE_METADATA = "get_variable_metadata"
TOOL_GET_OBSERVATIONS = "get_observations"
TOOL_GET_CHILD_OBSERVATIONS = "get_child_observations"
TOOL_GET_MULTI_ENTITY_OBSERVATIONS = "get_multi_entity_observations"

# Tools that return observations.
_OBSERVATION_TOOLS = frozenset(
    {
        TOOL_GET_OBSERVATIONS,
        TOOL_GET_CHILD_OBSERVATIONS,
        TOOL_GET_MULTI_ENTITY_OBSERVATIONS,
    }
)

_SEARCH_TOOLS = frozenset(
    {
        TOOL_SEARCH_INDICATORS,
        TOOL_SEARCH_CHILD_INDICATORS,
    }
)

# The six tools of the MCP 1.3.x surface, all of which the agent requires.
REQUIRED_TOOLS: frozenset[str] = (
    _SEARCH_TOOLS | _OBSERVATION_TOOLS | {TOOL_GET_VARIABLE_METADATA}
)

type McpSupport = Literal["supported", "unsupported", "unknown"]


@dataclass(frozen=True)
class Capabilities:
    """An immutable snapshot of one MCP server's tool surface."""

    tool_names: frozenset[str] = field(default_factory=frozenset)

    def has(self, tool: str) -> bool:
        """Returns whether the MCP server exposes `tool`."""
        return tool in self.tool_names

    @property
    def supports_source_attribution(self) -> bool:
        """Returns whether the server provides `get_variable_metadata`.

        Without `get_variable_metadata`, the agent cannot look up facet
        metadata and must fall back to the source fields embedded in
        observation responses.
        """
        return self.has(TOOL_GET_VARIABLE_METADATA)

    @property
    def observation_tools(self) -> frozenset[str]:
        """Returns the observation-fetching tools exposed by the server."""
        return _OBSERVATION_TOOLS & self.tool_names

    @property
    def search_tools(self) -> frozenset[str]:
        """Returns the indicator-search tools exposed by the server."""
        return _SEARCH_TOOLS & self.tool_names

    @property
    def missing_tools(self) -> tuple[str, ...]:
        """Returns the sorted names of any missing required tools."""
        return tuple(sorted(REQUIRED_TOOLS - self.tool_names))

    @property
    def required_tools_present(self) -> bool:
        """Returns whether every tool in `REQUIRED_TOOLS` is available."""
        return REQUIRED_TOOLS.issubset(self.tool_names)

    @property
    def support(self) -> McpSupport:
        """Returns the agent's support status for this MCP server.

        Returns `"supported"` when every tool in `REQUIRED_TOOLS` is
        available, `"unsupported"` when the server lists tools but at least
        one required tool is missing, and `"unknown"` when the tool list is
        empty.
        """
        if not self.tool_names:
            return "unknown"
        return "supported" if self.required_tools_present else "unsupported"

    def describe(self) -> JsonObject:
        """Returns a JSON-serializable summary of the server's capabilities."""
        # `list` is invariant, so the sorted names are typed as JSON values
        # to fit in a `JsonObject`.
        tools: list[JsonValue] = [*sorted(self.tool_names)]
        missing: list[JsonValue] = [*self.missing_tools]
        return {
            "support": self.support,
            "tool_count": len(self.tool_names),
            "tools": tools,
            "supports_source_attribution": self.supports_source_attribution,
            "missing_tools": missing,
        }


def from_tools(tools: Sequence[client.McpTool] | None) -> Capabilities:
    """Builds a snapshot from the tools that `tools/list` returned.

    A tool with an empty name is left out.
    """
    names: frozenset[str] = frozenset(
        tool.name for tool in (tools or []) if tool.name
    )
    return Capabilities(tool_names=names)


def warn_on_missing_tools(tools: Sequence[client.McpTool]) -> None:
    """Logs a single warning that names every missing tool in `REQUIRED_TOOLS`.

    Args:
        tools: The tool definitions returned by `tools/list`.
    """
    caps = from_tools(tools)
    if not caps.required_tools_present:
        logger.warning(
            "The MCP server is missing required tools: %s",
            ", ".join(caps.missing_tools),
        )


def current_cached() -> Capabilities:
    """Returns capabilities from the cached tool list without blocking.

    Used by `/agent/health`. Does not log a warning when tools are missing,
    because the cache is empty before the first fetch completes and health
    checks should not log a warning on every poll.
    """
    return from_tools(client.cached_tools())
