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
"""What the MCP server we are actually talking to can do.

The agent runs against three different backends -- a self-hosted CDC services
container, a Data Commons Platform instance, or public datacommons.org -- and
those do not all serve the same MCP tool surface. Server 1.2.1 exposes two fat
tools; 1.3.0 splits them into six and adds get_variable_metadata.

Nothing in this repo verifies which generation a given DCP deployment serves,
and we cannot pin it: the image is Google's and moves independently of us. So
the tool surface is treated as a property to be *discovered*, not declared.

Hardcoding a union of both generations -- the previous approach -- fails in a
particularly unhelpful way. The model is offered a tool the server does not
have, calls it, gets "Unknown tool", and burns an iteration of a capped loop.
The user sees a slower, worse answer and nothing anywhere says why.

This module answers the only questions the rest of the code actually asks:
which tools exist, and does source attribution work here.
"""

import logging
from dataclasses import dataclass, field
from typing import FrozenSet

logger = logging.getLogger(__name__)

# The tool whose presence decides whether we can attribute a number to a named
# source with a licence. Only 1.3.0 serves it; without it the best available
# provenance is a bare domain scraped from the observation payload.
_METADATA_TOOL = "get_variable_metadata"

# Tools that return observations. Used to decide whether a turn actually
# fetched any numbers.
_OBSERVATION_TOOLS = frozenset({
    "get_observations",
    "get_child_observations",
    "get_multi_entity_observations",
})

_SEARCH_TOOLS = frozenset({
    "search_indicators",
    "search_child_indicators",
})


@dataclass(frozen=True)
class Capabilities:
    """An immutable snapshot of one MCP server's tool surface."""

    tool_names: FrozenSet[str] = field(default_factory=frozenset)

    def has(self, tool: str) -> bool:
        return tool in self.tool_names

    @property
    def supports_source_attribution(self) -> bool:
        """Can we name the source behind a number, with its licence?

        When false, `_sources_from_variable_metadata` has nothing to work with
        and provenance degrades to whatever the observation payload carries.
        Worth surfacing rather than discovering from an unattributed answer.
        """
        return self.has(_METADATA_TOOL)

    @property
    def observation_tools(self) -> FrozenSet[str]:
        return _OBSERVATION_TOOLS & self.tool_names

    @property
    def search_tools(self) -> FrozenSet[str]:
        return _SEARCH_TOOLS & self.tool_names

    @property
    def generation(self) -> str:
        """A human label for logs and /agent/health. Not used for branching.

        Behaviour is driven by which tools are present, never by this string --
        a version label invites `if generation == "1.3.0"` and that is exactly
        the assumption that breaks when Google ships 1.4.
        """
        if not self.tool_names:
            return "unknown"
        return "1.3.x-or-later" if self.supports_source_attribution else "1.2.x"

    def describe(self) -> dict:
        return {
            "generation": self.generation,
            "tool_count": len(self.tool_names),
            "tools": sorted(self.tool_names),
            "supports_source_attribution": self.supports_source_attribution,
        }


def from_tools(tools: list) -> Capabilities:
    """Build a snapshot from whatever `tools/list` returned."""
    names = frozenset(
        t.get("name") for t in (tools or []) if isinstance(t, dict) and t.get("name")
    )
    return Capabilities(tool_names=names)


def current_cached() -> Capabilities:
    """Capabilities from the cache only -- never triggers a fetch.

    Use where blocking is unacceptable, e.g. a health endpoint.
    """
    from src.mcp.client import cached_tools  # noqa: PLC0415  (circular by design)

    return from_tools(cached_tools())


def current() -> Capabilities:
    """Capabilities of the configured MCP server.

    Imported lazily so this module stays independent of the client -- the
    client's schema helpers would otherwise import it back.
    """
    from src.mcp.client import get_tools  # noqa: PLC0415  (circular by design)

    caps = from_tools(get_tools())
    if not caps.tool_names:
        logger.warning(
            "MCP exposed no tools; running with no data-fetching capability."
        )
    elif not caps.supports_source_attribution:
        logger.warning(
            "MCP server has no %s: answers will carry weaker provenance "
            "(no named source, no licence). Tools present: %s",
            _METADATA_TOOL, sorted(caps.tool_names),
        )
    return caps
