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
"""Typed agent configuration and the parser that produces it.

`config.py` reads the configuration document (`agent-config.json`, or the
local `config.json`), layers the prompt bodies into it, and calls
`parse_agent_config` once per load. The workflows read the resulting frozen
`AgentConfig`, so the document's shape, the type of each value, and the
default that applies when a value is absent are known in this one module.
Field names follow the JSON keys, so `config.thinking.mcp_level` is
`thinking.mcp_level` in the document. This module does no I/O and does not
import `config.py`.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

logger = logging.getLogger(__name__)

# Default models used when agent-config.json omits a model name or leaves it
# blank. The parser applies them, so no reader spells its own default.
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
DEFAULT_GEMINI_CLASSIFY_MODEL = "gemini-3.5-flash-lite"


@dataclass(frozen=True)
class GeminiConfig:
    """Holds the `gemini` section: the model each phase calls and the key.

    `mcp_model` runs the tool loop, synthesis, chart configuration, follow-up
    generation, and transcript compaction; `classify_model` runs the classify
    phase. `api_key` is the local-development key from `config.json`, which
    `get_gemini_api_key` in `config.py` applies after Secret Manager; it is
    excluded from `repr` so that a logged or printed configuration never
    carries the key.
    """

    mcp_model: str = DEFAULT_GEMINI_MODEL
    classify_model: str = DEFAULT_GEMINI_CLASSIFY_MODEL
    api_key: str = field(default="", repr=False)


@dataclass(frozen=True)
class McpConfig:
    """Holds the `mcp` section.

    `server_url` is the MCP endpoint used when the `MCP_SERVER_URL`
    environment variable is unset, and `""` selects the localhost fallback.
    `enabled` set to `False` skips the tool loop and runs synthesis alone.
    """

    server_url: str = ""
    enabled: bool = True


@dataclass(frozen=True)
class ThinkingLevels:
    """Holds the `thinking` section: the reasoning level of each model phase.

    The levels are passed to the Gemini client as strings. The client maps
    them to `types.ThinkingLevel` and selects `"low"` for a value it does not
    recognize; an empty level leaves the model's own default in place.
    """

    mcp_level: str = "low"
    synthesis_level: str = "low"


@dataclass(frozen=True)
class Prompts:
    """Holds the system prompt body of each slot after layering.

    `config.py` layers the default prompt files, the fetched prompts, and the
    inline `prompts` entries before parsing, so a slot is `""` only when none
    of those sources covers it, which the layering reports as an error.
    """

    classify: str = ""
    mcp: str = ""
    synthesis: str = ""
    follow_up: str = ""


@dataclass(frozen=True)
class AgentConfig:
    """Represents one loaded agent configuration.

    Instances are immutable, and one instance is shared by every turn, so a
    reader must not modify it. `template_vars` holds the values substituted
    for `{{instance.<key>}}` placeholders in prompts, coerced to strings and
    stored as a read-only mapping proxy.
    """

    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    mcp: McpConfig = field(default_factory=McpConfig)
    thinking: ThinkingLevels = field(default_factory=ThinkingLevels)
    prompts: Prompts = field(default_factory=Prompts)
    template_vars: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.template_vars, MappingProxyType):
            object.__setattr__(
                self,
                "template_vars",
                MappingProxyType(dict(self.template_vars)),
            )


def _read_section(document: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    """Returns the JSON object under `key`, or `{}` when there is none.

    A value that is present but not an object is reported once and treated
    as absent, so every field of that section takes its default.
    """
    if key not in document:
        return {}
    value = document[key]
    if isinstance(value, Mapping):
        return value
    logger.warning(
        "Agent configuration key %r is not an object; using the defaults for "
        "that section",
        key,
    )
    return {}


def _read_string(
    section: Mapping[str, Any], section_key: str, key: str, default: str
) -> str:
    """Returns the string under `key`, or `default` when there is none.

    A value that is present but not a string is reported once with its
    dotted key and replaced by `default`.
    """
    if key not in section:
        return default
    value = section[key]
    if isinstance(value, str):
        return value
    logger.warning(
        "Agent configuration key %r is not a string; using %r",
        f"{section_key}.{key}",
        default,
    )
    return default


def _read_model_name(section: Mapping[str, Any], key: str, default: str) -> str:
    """Returns the model name under `gemini.<key>`, stripped, or `default`.

    A blank name is reported and replaced by `default`, like a name of the
    wrong type, because an empty model name fails every request.
    """
    name = _read_string(section, "gemini", key, default).strip()
    if name:
        return name
    logger.warning(
        "Agent configuration key %r is blank; using %r",
        f"gemini.{key}",
        default,
    )
    return default


def _read_bool(
    section: Mapping[str, Any], section_key: str, key: str, default: bool
) -> bool:
    """Returns the boolean under `key`, or `default` when there is none.

    A value that is present but not a boolean is reported once with its
    dotted key and replaced by `default`.
    """
    if key not in section:
        return default
    value = section[key]
    if isinstance(value, bool):
        return value
    logger.warning(
        "Agent configuration key %r is not a boolean; using %r",
        f"{section_key}.{key}",
        default,
    )
    return default


def _read_template_vars(document: Mapping[str, Any]) -> dict[str, str]:
    """Returns `template_vars` with every value coerced to a string.

    Keys beginning with `_` are left out, so the `_comment` convention used
    throughout the configuration files cannot be substituted into a prompt.
    Numbers and booleans are rendered with `str`, and a value of any other
    type is left out with a warning.
    """
    template_vars: dict[str, str] = {}
    for key, value in _read_section(document, "template_vars").items():
        if key.startswith("_"):
            continue
        if isinstance(value, (str, int, float)):
            template_vars[key] = str(value)
        else:
            logger.warning(
                "Agent configuration key %r is not a string or a number; "
                "ignoring it",
                f"template_vars.{key}",
            )
    return template_vars


def parse_agent_config(document: Mapping[str, Any]) -> AgentConfig:
    """Parses a configuration document into an `AgentConfig`.

    Each field is parsed on its own: a section that is not a JSON object, or
    a value that is absent or not of the expected type, takes the field's
    default, and a value that is present but unusable is logged once at
    warning with its key. The document as a whole is never rejected, so one
    bad value cannot stop every turn with `config_missing`. Keys that the
    agent does not read are ignored.

    Args:
        document: The decoded JSON object, with the prompt slot bodies that
            `config.py` layered into `prompts`.

    Returns:
        The parsed configuration.
    """
    gemini = _read_section(document, "gemini")
    mcp = _read_section(document, "mcp")
    thinking = _read_section(document, "thinking")
    prompts = _read_section(document, "prompts")
    return AgentConfig(
        gemini=GeminiConfig(
            mcp_model=_read_model_name(
                gemini, "mcp_model", GeminiConfig.mcp_model
            ),
            classify_model=_read_model_name(
                gemini, "classify_model", GeminiConfig.classify_model
            ),
            api_key=_read_string(
                gemini, "gemini", "api_key", GeminiConfig.api_key
            ).strip(),
        ),
        mcp=McpConfig(
            server_url=_read_string(
                mcp, "mcp", "server_url", McpConfig.server_url
            ).strip(),
            enabled=_read_bool(mcp, "mcp", "enabled", McpConfig.enabled),
        ),
        thinking=ThinkingLevels(
            mcp_level=_read_string(
                thinking, "thinking", "mcp_level", ThinkingLevels.mcp_level
            ),
            synthesis_level=_read_string(
                thinking,
                "thinking",
                "synthesis_level",
                ThinkingLevels.synthesis_level,
            ),
        ),
        prompts=Prompts(
            classify=_read_string(
                prompts, "prompts", "classify", Prompts.classify
            ),
            mcp=_read_string(prompts, "prompts", "mcp", Prompts.mcp),
            synthesis=_read_string(
                prompts, "prompts", "synthesis", Prompts.synthesis
            ),
            follow_up=_read_string(
                prompts, "prompts", "follow_up", Prompts.follow_up
            ),
        ),
        template_vars=_read_template_vars(document),
    )
