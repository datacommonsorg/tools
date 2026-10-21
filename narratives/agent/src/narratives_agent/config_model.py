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
`thinking.mcp_level` in the document.

The module also holds the Gemini settings of every role in the agent loop.
`GeminiRole` names the roles, `_ROLE_TEMPERATURES` and
`_FIXED_THINKING_LEVELS` hold the settings that the document cannot change,
and `AgentConfig.resolve_role_config` combines them with the configured
models and thinking levels into the `RoleConfig` that the workflows pass to
the Gemini client, raising a thinking level that the role's model does not
accept to the lowest level it does. Every model and reasoning setting the
agent relies on can therefore be read from this one module. This module
does no I/O and does not import `config.py`.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from enum import Enum
from types import MappingProxyType
from typing import Any

from google.genai import types

logger = logging.getLogger(__name__)

# Default models used when agent-config.json omits a model name or leaves it
# blank. The parser applies them, so no reader spells its own default.
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
DEFAULT_GEMINI_CLASSIFY_MODEL = "gemini-3.5-flash-lite"

# Thinking level of the tool loop and synthesis when agent-config.json omits
# `thinking.mcp_level` or `thinking.synthesis_level`. It matches the
# `"default"` that `schemas/agent-config.schema.json` declares for both keys.
DEFAULT_THINKING_LEVEL = types.ThinkingLevel.MEDIUM


class GeminiRole(Enum):
    """Reasoning roles across the agent loop."""

    CLASSIFY = "classify"
    MCP = "mcp"
    SYNTHESIS = "synthesis"
    CHART_CONFIG = "chart_config"
    CHART_VALIDATION = "chart_validation"
    FOLLOW_UP = "follow_up"
    COMPACTION = "compaction"


@dataclass(frozen=True)
class RoleConfig:
    """Model, sampling temperature, and thinking level for one Gemini role."""

    model: str
    temperature: float
    thinking_level: types.ThinkingLevel


# Sampling temperature of each role. agent-config.json cannot change these.
_ROLE_TEMPERATURES: Mapping[GeminiRole, float] = {
    GeminiRole.CLASSIFY: 0.0,
    GeminiRole.MCP: 0.2,
    GeminiRole.SYNTHESIS: 0.3,
    GeminiRole.CHART_CONFIG: 0.2,
    GeminiRole.CHART_VALIDATION: 0.0,
    # A higher temperature varies the phrasing of the follow-up questions.
    GeminiRole.FOLLOW_UP: 0.8,
    GeminiRole.COMPACTION: 0.1,
}

# Thinking level of the roles that agent-config.json cannot change. `MCP` and
# `SYNTHESIS` are absent because they read `thinking.mcp_level` and
# `thinking.synthesis_level`. `CLASSIFY` asks for the least reasoning
# because it returns a short structured verdict on every turn;
# `_clamp_thinking_level` raises it on a model that does not accept
# `MINIMAL`.
_FIXED_THINKING_LEVELS: Mapping[GeminiRole, types.ThinkingLevel] = {
    GeminiRole.CLASSIFY: types.ThinkingLevel.MINIMAL,
    GeminiRole.CHART_CONFIG: types.ThinkingLevel.LOW,
    GeminiRole.CHART_VALIDATION: types.ThinkingLevel.LOW,
    GeminiRole.FOLLOW_UP: types.ThinkingLevel.LOW,
    GeminiRole.COMPACTION: types.ThinkingLevel.LOW,
}

# The thinking levels that `thinking.mcp_level` and `thinking.synthesis_level`
# accept, keyed by their configuration string. They match the `enum` that
# `schemas/agent-config.schema.json` declares for both keys; `MINIMAL` is
# excluded because the default `gemini.mcp_model` rejects it.
_CONFIGURABLE_THINKING_LEVELS: Mapping[str, types.ThinkingLevel] = {
    "low": types.ThinkingLevel.LOW,
    "medium": types.ThinkingLevel.MEDIUM,
    "high": types.ThinkingLevel.HIGH,
}

# Name prefixes of the models that the Gemini model documentation lists as
# accepting `ThinkingLevel.MINIMAL`. Every other text model in that table
# requires at least `LOW` and rejects `MINIMAL` with HTTP 400. The API does
# not report the levels a model accepts (`Model.thinking` is a boolean), so
# this list is the only source; a model it does not name runs at `LOW` or
# above, which every model accepts.
_MINIMAL_THINKING_MODEL_PREFIXES = (
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3-flash-preview",
)

# Thinking levels from the least to the most reasoning, for comparing a
# requested level with a model's floor.
_THINKING_LEVEL_ORDER = (
    types.ThinkingLevel.MINIMAL,
    types.ThinkingLevel.LOW,
    types.ThinkingLevel.MEDIUM,
    types.ThinkingLevel.HIGH,
)


def _lowest_thinking_level(model: str) -> types.ThinkingLevel:
    """Returns the lowest thinking level that `model` accepts.

    `model` is a bare name or a `models/` or Vertex AI resource path; only
    its final path segment is matched against the prefixes.
    """
    name = model.rsplit("/", 1)[-1]
    if name.startswith(_MINIMAL_THINKING_MODEL_PREFIXES):
        return types.ThinkingLevel.MINIMAL
    return types.ThinkingLevel.LOW


def _clamp_thinking_level(
    level: types.ThinkingLevel, model: str
) -> types.ThinkingLevel:
    """Returns `level`, raised to the lowest level `model` accepts if below it.

    A level at or above the floor is returned unchanged; the clamp never
    lowers a level. `level` is one of `_THINKING_LEVEL_ORDER`; the parser
    and the role tables produce nothing else.
    """
    floor = _lowest_thinking_level(model)
    if _THINKING_LEVEL_ORDER.index(level) < _THINKING_LEVEL_ORDER.index(floor):
        return floor
    return level


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
    """Holds the `thinking` section: the configurable thinking levels.

    `mcp_level` applies to the tool loop and `synthesis_level` to synthesis.
    The parser accepts `"low"`, `"medium"`, and `"high"` and falls back to
    `DEFAULT_THINKING_LEVEL` for any other value. The other roles run at the
    levels in `_FIXED_THINKING_LEVELS`.
    """

    mcp_level: types.ThinkingLevel = DEFAULT_THINKING_LEVEL
    synthesis_level: types.ThinkingLevel = DEFAULT_THINKING_LEVEL


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


# Prompt slots, derived from the fields of `Prompts` so the loader and the
# typed model share one list of slot names. Bodies are authored as
# `prompts/<slot>.md` in `defaults/prompts/` and in the config bucket.
PROMPT_SLOTS: tuple[str, ...] = tuple(f.name for f in fields(Prompts))


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

    def resolve_role_config(self, role: GeminiRole) -> RoleConfig:
        """Returns the model, temperature, and thinking level of `role`.

        `CLASSIFY` runs on `gemini.classify_model` and every other role on
        `gemini.mcp_model`. `MCP` and `SYNTHESIS` think at
        `thinking.mcp_level` and `thinking.synthesis_level`; the other roles
        think at their level in `_FIXED_THINKING_LEVELS`. A level below the
        lowest the role's model accepts is raised to that floor, so the
        classifier runs at `LOW` on a model that rejects `MINIMAL` rather
        than failing its call on every turn and leaving the turn
        unclassified. Every role samples at its temperature in
        `_ROLE_TEMPERATURES`.
        """
        model = (
            self.gemini.classify_model
            if role is GeminiRole.CLASSIFY
            else self.gemini.mcp_model
        )
        if role is GeminiRole.MCP:
            thinking_level = self.thinking.mcp_level
        elif role is GeminiRole.SYNTHESIS:
            thinking_level = self.thinking.synthesis_level
        else:
            thinking_level = _FIXED_THINKING_LEVELS[role]
        return RoleConfig(
            model=model,
            temperature=_ROLE_TEMPERATURES[role],
            thinking_level=_clamp_thinking_level(thinking_level, model),
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


def _read_thinking_level(
    section: Mapping[str, Any], key: str, default: types.ThinkingLevel
) -> types.ThinkingLevel:
    """Returns the thinking level under `thinking.<key>`, or `default`.

    A string is stripped, lowercased, and matched against
    `_CONFIGURABLE_THINKING_LEVELS` rather than passed to
    `types.ThinkingLevel`, whose constructor returns a pseudo-member for an
    unknown string instead of raising. A value that is present but not a
    string, or not one of the accepted levels, is reported once with its
    dotted key and replaced by `default`.
    """
    if key not in section:
        return default
    value = section[key]
    if isinstance(value, str):
        level = _CONFIGURABLE_THINKING_LEVELS.get(value.strip().lower())
        if level is not None:
            return level
    logger.warning(
        "Agent configuration key %r is not one of %s; using %r",
        f"thinking.{key}",
        list(_CONFIGURABLE_THINKING_LEVELS),
        default.value.lower(),
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
        if isinstance(value, (str, int, float, bool)):
            template_vars[key] = str(value)
        else:
            logger.warning(
                "Agent configuration key %r is not a string, a number, or a "
                "boolean; ignoring it",
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
            mcp_level=_read_thinking_level(
                thinking, "mcp_level", ThinkingLevels.mcp_level
            ),
            synthesis_level=_read_thinking_level(
                thinking, "synthesis_level", ThinkingLevels.synthesis_level
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
