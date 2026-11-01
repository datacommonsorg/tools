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
"""Tests for `parse_agent_config` and `AgentConfig.resolve_role_config`.

Covers the per-field rules the parser applies to a configuration document:
1. A model name that is absent, null, blank, or not a string gives the
   default; a configured name is stripped.
2. A section that is not a JSON object gives that section's defaults with
   one warning, and every other section is still parsed.
3. A value of the wrong type for `enabled`, a thinking level, a prompt, or
   the API key gives the default with one warning naming the key.
4. A thinking level is matched case-insensitively against `low`, `medium`,
   and `high`; any other string gives the default with one warning.
5. `template_vars` drops `_`-prefixed keys, renders numbers as strings,
   and drops other values with a warning.
6. Unknown keys are ignored without a warning.

And the resolution of each `GeminiRole` to its model, temperature, and
thinking level, with and without configured values, including the clamp that
raises a level the role's model does not accept. The loading paths that
produce the document are tested in `config_test.py`.
"""

import logging
from typing import Any

import pytest
from google.genai import types

from narratives_agent import config_model
from narratives_agent.config_model import (
    DEFAULT_GEMINI_CLASSIFY_MODEL,
    DEFAULT_GEMINI_MODEL,
    AgentConfig,
    GeminiConfig,
    GeminiRole,
    McpConfig,
    Prompts,
    RoleConfig,
    ThinkingLevels,
    parse_agent_config,
)

_ABSENT = object()


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    """Returns the warning messages logged by the parser."""
    return [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.WARNING
        and record.name == config_model.logger.name
    ]


def test_an_empty_document_gives_every_default() -> None:
    # Test: Parsing a document with no recognized keys.
    # Situation: The document is `{}`.
    # Expectation: Every field carries its default, which is the same value an
    #   `AgentConfig()` constructed without arguments carries.
    parsed = parse_agent_config({})

    assert parsed == AgentConfig()
    assert parsed.gemini == GeminiConfig(
        classify_model=DEFAULT_GEMINI_CLASSIFY_MODEL,
        discovery_model=DEFAULT_GEMINI_MODEL,
        synthesis_model=DEFAULT_GEMINI_MODEL,
        follow_up_model=DEFAULT_GEMINI_MODEL,
        compaction_model=DEFAULT_GEMINI_MODEL,
    )
    assert parsed.mcp == McpConfig(server_url="", enabled=True)
    assert parsed.thinking == ThinkingLevels(
        discovery_level=types.ThinkingLevel.MEDIUM,
        synthesis_level=types.ThinkingLevel.MEDIUM,
    )
    assert parsed.prompts == Prompts()
    assert parsed.template_vars == {}


def test_configured_values_are_carried_through() -> None:
    # Test: Parsing a fully populated document.
    # Situation: Every section sets every field the agent reads, with
    #   surrounding whitespace on the model names, the key, and the URL.
    # Expectation: The parsed configuration carries each value, with the model
    #   names, the key, and the URL stripped and the prompt bodies and levels
    #   unchanged.
    parsed = parse_agent_config(
        {
            "gemini": {
                "classify_model": " gemini-3.8-flash ",
                "discovery_model": " gemini-3-pro ",
                "synthesis_model": " gemini-3-pro-synthesis ",
                "follow_up_model": " gemini-3-flash-followup ",
                "compaction_model": " gemini-3-flash-compact ",
                "api_key": " test-key ",
            },
            "mcp": {"server_url": " https://mcp.example ", "enabled": False},
            "thinking": {
                "discovery_level": "high",
                "synthesis_level": "medium",
            },
            "prompts": {
                "classify": "Classify. ",
                "discovery": "Gather.",
                "synthesis": "Write.",
                "follow_up": "Suggest.",
            },
            "template_vars": {"name": "Example DC"},
        }
    )

    assert parsed == AgentConfig(
        gemini=GeminiConfig(
            classify_model="gemini-3.8-flash",
            discovery_model="gemini-3-pro",
            synthesis_model="gemini-3-pro-synthesis",
            follow_up_model="gemini-3-flash-followup",
            compaction_model="gemini-3-flash-compact",
            api_key="test-key",
        ),
        mcp=McpConfig(server_url="https://mcp.example", enabled=False),
        thinking=ThinkingLevels(
            discovery_level=types.ThinkingLevel.HIGH,
            synthesis_level=types.ThinkingLevel.MEDIUM,
        ),
        prompts=Prompts(
            classify="Classify. ",
            discovery="Gather.",
            synthesis="Write.",
            follow_up="Suggest.",
        ),
        template_vars={"name": "Example DC"},
    )


@pytest.mark.parametrize("role", list(GeminiRole), ids=lambda role: role.value)
@pytest.mark.parametrize(
    ("value", "warned"),
    [
        (_ABSENT, False),
        (None, True),
        ("", True),
        ("   ", True),
        (123, True),
    ],
    ids=["absent", "null", "empty", "whitespace", "wrong type"],
)
def test_an_unusable_model_name_gives_the_default(
    caplog: pytest.LogCaptureFixture,
    role: GeminiRole,
    value: object,
    warned: bool,
) -> None:
    # Test: Model-name fallback in `parse_agent_config`.
    # Situation: `gemini.<role>_model` is absent, null, empty, whitespace-only,
    #   or not a string.
    # Expectation: The role's model falls back to its default on `GeminiConfig`.
    #   An absent key is not reported; every other case logs one warning naming
    #   `gemini.<role>_model`.
    key = f"{role.value}_model"
    gemini: dict[str, Any] = {} if value is _ABSENT else {key: value}
    with caplog.at_level(logging.WARNING):
        parsed = parse_agent_config({"gemini": gemini})

    default_model = getattr(GeminiConfig, key)
    assert getattr(parsed.gemini, key) == default_model
    assert parsed.resolve_role_config(role).model == default_model
    warnings = _warnings(caplog)
    if warned:
        assert len(warnings) == 1
        assert f"'gemini.{key}'" in warnings[0]
    else:
        assert warnings == []


@pytest.mark.parametrize(
    "section", ["gemini", "mcp", "thinking", "prompts", "template_vars"]
)
@pytest.mark.parametrize(
    "value", [None, "high", 3, ["low"]], ids=["null", "str", "int", "list"]
)
def test_a_section_of_the_wrong_type_gives_its_defaults(
    caplog: pytest.LogCaptureFixture, section: str, value: object
) -> None:
    # Test: Section-level type checking in `parse_agent_config`.
    # Situation: One top-level section is null, a string, a number, or a list
    #   rather than an object, and another section is valid.
    # Expectation: The malformed section carries its defaults, the valid
    #   section is parsed, nothing is raised, and exactly one warning names
    #   the malformed section.
    document: dict[str, Any] = {
        section: value,
        "gemini": {"discovery_model": "gemini-test"},
    }
    if section == "gemini":
        document = {section: value, "mcp": {"enabled": False}}

    with caplog.at_level(logging.WARNING):
        parsed = parse_agent_config(document)

    expected_default = getattr(AgentConfig(), section)
    assert getattr(parsed, section) == expected_default
    if section == "gemini":
        assert parsed.mcp.enabled is False
    else:
        assert parsed.gemini.discovery_model == "gemini-test"
    assert [f"'{section}'" in message for message in _warnings(caplog)] == [
        True
    ]


@pytest.mark.parametrize(
    ("section", "key", "value", "expected_default"),
    [
        ("mcp", "enabled", "yes", True),
        ("mcp", "enabled", 1, True),
        ("mcp", "enabled", None, True),
        ("mcp", "server_url", 8082, ""),
        ("thinking", "discovery_level", 2, types.ThinkingLevel.MEDIUM),
        ("thinking", "discovery_level", False, types.ThinkingLevel.MEDIUM),
        ("thinking", "discovery_level", 0, types.ThinkingLevel.MEDIUM),
        ("thinking", "synthesis_level", None, types.ThinkingLevel.MEDIUM),
        ("prompts", "classify", ["Classify."], ""),
        ("prompts", "follow_up", None, ""),
        ("gemini", "api_key", None, ""),
        ("gemini", "api_key", 12345, ""),
    ],
    ids=[
        "enabled str",
        "enabled int",
        "enabled null",
        "server_url int",
        "discovery_level int",
        "discovery_level false",
        "discovery_level zero",
        "synthesis_level null",
        "classify prompt list",
        "follow_up prompt null",
        "api_key null",
        "api_key int",
    ],
)
def test_a_value_of_the_wrong_type_gives_the_default(
    caplog: pytest.LogCaptureFixture,
    section: str,
    key: str,
    value: object,
    expected_default: object,
) -> None:
    # Test: Field-level type checking in `parse_agent_config`.
    # Situation: One field holds a value of the wrong type, including the
    #   truthy string `"yes"` and the integer `1` for `enabled`, and `False`
    #   and `0` for `thinking.discovery_level`.
    # Expectation: The field carries its default, nothing is raised, and
    #   exactly one warning names the field's dotted key.
    with caplog.at_level(logging.WARNING):
        parsed = parse_agent_config({section: {key: value}})

    assert getattr(getattr(parsed, section), key) == expected_default
    assert [
        f"'{section}.{key}'" in message for message in _warnings(caplog)
    ] == [True]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("HIGH", types.ThinkingLevel.HIGH),
        ("  low  ", types.ThinkingLevel.LOW),
        ("Medium", types.ThinkingLevel.MEDIUM),
    ],
    ids=["uppercase", "padded", "capitalized"],
)
def test_a_thinking_level_is_matched_without_regard_to_case_or_padding(
    caplog: pytest.LogCaptureFixture,
    value: str,
    expected: types.ThinkingLevel,
) -> None:
    # Test: Normalization of thinking levels in `parse_agent_config`.
    # Situation: `thinking.discovery_level` and `thinking.synthesis_level`
    #   carry an accepted level in uppercase, padded with whitespace, or
    #   capitalized.
    # Expectation: Both fields carry the matching `types.ThinkingLevel`, and
    #   no warning is logged.
    with caplog.at_level(logging.WARNING):
        parsed = parse_agent_config(
            {"thinking": {"discovery_level": value, "synthesis_level": value}}
        )

    assert parsed.thinking == ThinkingLevels(
        discovery_level=expected, synthesis_level=expected
    )
    assert _warnings(caplog) == []


@pytest.mark.parametrize(
    "value",
    ["", "   ", "minimal", "extreme"],
    ids=["empty", "whitespace", "minimal", "unknown"],
)
def test_an_unrecognized_thinking_level_gives_the_default(
    caplog: pytest.LogCaptureFixture, value: str
) -> None:
    # Test: Rejection of thinking levels outside the schema's enum in
    #   `parse_agent_config`.
    # Situation: `thinking.discovery_level` and `thinking.synthesis_level` are
    #   empty, whitespace, `"minimal"` (which `DEFAULT_GEMINI_MODEL` rejects),
    #   or an unknown string.
    # Expectation: Both fields fall back to `types.ThinkingLevel.MEDIUM`, and
    #   one warning per field names its dotted key.
    with caplog.at_level(logging.WARNING):
        parsed = parse_agent_config(
            {"thinking": {"discovery_level": value, "synthesis_level": value}}
        )

    assert parsed.thinking == ThinkingLevels(
        discovery_level=types.ThinkingLevel.MEDIUM,
        synthesis_level=types.ThinkingLevel.MEDIUM,
    )
    warnings = _warnings(caplog)
    assert len(warnings) == 2
    assert any("'thinking.discovery_level'" in message for message in warnings)
    assert any("'thinking.synthesis_level'" in message for message in warnings)


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        pytest.param(
            GeminiRole.CLASSIFY,
            RoleConfig(
                DEFAULT_GEMINI_CLASSIFY_MODEL, 0.0, types.ThinkingLevel.MINIMAL
            ),
            id="classify",
        ),
        pytest.param(
            GeminiRole.DISCOVERY,
            RoleConfig(DEFAULT_GEMINI_MODEL, 0.2, types.ThinkingLevel.MEDIUM),
            id="discovery",
        ),
        pytest.param(
            GeminiRole.SYNTHESIS,
            RoleConfig(DEFAULT_GEMINI_MODEL, 0.3, types.ThinkingLevel.MEDIUM),
            id="synthesis",
        ),
        pytest.param(
            GeminiRole.FOLLOW_UP,
            RoleConfig(DEFAULT_GEMINI_MODEL, 0.8, types.ThinkingLevel.LOW),
            id="follow_up",
        ),
        pytest.param(
            GeminiRole.COMPACTION,
            RoleConfig(DEFAULT_GEMINI_MODEL, 0.1, types.ThinkingLevel.LOW),
            id="compaction",
        ),
    ],
)
def test_a_default_configuration_resolves_each_role_to_its_defaults(
    role: GeminiRole, expected: RoleConfig
) -> None:
    # Test: `AgentConfig.resolve_role_config` without configured overrides.
    # Situation: The configuration is `AgentConfig()`, and every `GeminiRole`
    #   is resolved.
    # Expectation: Each role resolves to its default model on `GeminiConfig`,
    #   temperature, and thinking level; the classifier is the only role on
    #   the classify model and the only role at `MINIMAL`.
    resolved = AgentConfig().resolve_role_config(role)
    assert resolved == expected
    assert resolved.model == getattr(GeminiConfig, f"{role.value}_model")


@pytest.mark.parametrize("role", list(GeminiRole), ids=lambda role: role.value)
def test_every_role_has_a_temperature_and_a_thinking_level(
    role: GeminiRole,
) -> None:
    # Test: Table coverage in `AgentConfig.resolve_role_config`.
    # Situation: Every member of `GeminiRole`, including any added after the
    #   tables were written, is resolved from a default configuration.
    # Expectation: Each resolves to a `RoleConfig` rather than raising
    #   `KeyError` for a role missing from `_ROLE_TEMPERATURES` or
    #   `_FIXED_THINKING_LEVELS`.
    assert isinstance(AgentConfig().resolve_role_config(role), RoleConfig)


@pytest.mark.parametrize("role", list(GeminiRole), ids=lambda role: role.value)
def test_each_role_model_is_configured_independently(
    role: GeminiRole,
) -> None:
    # Test: Independent per-role model selection in `parse_agent_config` and
    #   `AgentConfig.resolve_role_config`.
    # Situation: Only `gemini.<role>_model` is set in the configuration
    #   document.
    # Expectation: `role` resolves to `"custom-model-v1"`, and every other
    #   `GeminiRole` resolves to its default model on `GeminiConfig`.
    config = parse_agent_config(
        {"gemini": {f"{role.value}_model": "custom-model-v1"}}
    )

    assert config.resolve_role_config(role).model == "custom-model-v1"
    for other in GeminiRole:
        if other is not role:
            assert config.resolve_role_config(other).model == getattr(
                GeminiConfig, f"{other.value}_model"
            )


def test_configured_values_apply_to_the_roles_they_govern() -> None:
    # Test: `AgentConfig.resolve_role_config` with configured models and levels.
    # Situation: Every `gemini.<role>_model` field, `thinking.discovery_level`,
    #   and `thinking.synthesis_level` are set to distinct values.
    # Expectation: Each role receives its own configured model;
    #   `discovery_level` reaches `DISCOVERY` and `synthesis_level` reaches
    #   `SYNTHESIS`, while the fixed thinking levels of the other roles and
    #   every temperature are unchanged. The classify model accepts `MINIMAL`,
    #   so the clamp leaves that level in place.
    config = AgentConfig(
        gemini=GeminiConfig(
            classify_model="gemini-3.6-flash",
            discovery_model="gemini-discovery-custom",
            synthesis_model="gemini-synthesis-custom",
            follow_up_model="gemini-follow-up-custom",
            compaction_model="gemini-compaction-custom",
        ),
        thinking=ThinkingLevels(
            discovery_level=types.ThinkingLevel.HIGH,
            synthesis_level=types.ThinkingLevel.LOW,
        ),
    )

    assert config.resolve_role_config(GeminiRole.CLASSIFY) == RoleConfig(
        "gemini-3.6-flash", 0.0, types.ThinkingLevel.MINIMAL
    )
    assert config.resolve_role_config(GeminiRole.DISCOVERY) == RoleConfig(
        "gemini-discovery-custom", 0.2, types.ThinkingLevel.HIGH
    )
    assert config.resolve_role_config(GeminiRole.SYNTHESIS) == RoleConfig(
        "gemini-synthesis-custom", 0.3, types.ThinkingLevel.LOW
    )
    assert config.resolve_role_config(GeminiRole.FOLLOW_UP) == RoleConfig(
        "gemini-follow-up-custom", 0.8, types.ThinkingLevel.LOW
    )
    assert config.resolve_role_config(GeminiRole.COMPACTION) == RoleConfig(
        "gemini-compaction-custom", 0.1, types.ThinkingLevel.LOW
    )


@pytest.mark.parametrize(
    ("classify_model", "expected"),
    [
        ("gemini-3.5-flash-lite", types.ThinkingLevel.MINIMAL),
        ("gemini-3.5-flash-lite-001", types.ThinkingLevel.MINIMAL),
        ("gemini-3.6-flash", types.ThinkingLevel.MINIMAL),
        ("models/gemini-3.5-flash-lite", types.ThinkingLevel.MINIMAL),
        (
            "projects/p/locations/l/publishers/google/models/"
            "gemini-3.5-flash-lite",
            types.ThinkingLevel.MINIMAL,
        ),
        ("gemini-3.8-flash", types.ThinkingLevel.LOW),
        ("gemini-4-argon", types.ThinkingLevel.LOW),
        ("some-future-model", types.ThinkingLevel.LOW),
    ],
    ids=[
        "lite",
        "lite with version suffix",
        "3.6 flash",
        "models path",
        "vertex resource path",
        "3.8 flash",
        "4 argon",
        "unknown model",
    ],
)
def test_the_classify_level_is_raised_to_what_the_model_accepts(
    classify_model: str, expected: types.ThinkingLevel
) -> None:
    # Test: The thinking-level clamp in `AgentConfig.resolve_role_config`.
    # Situation: `gemini.classify_model` names a model documented to accept
    #   `MINIMAL`, as a bare name with or without a version suffix or as a
    #   `models/` or Vertex AI resource path, a model documented to reject
    #   it, or a model the capability list does not know.
    # Expectation: `CLASSIFY` runs at `MINIMAL` on the first group and at
    #   `LOW`, which every model accepts, on the others, so an unlisted model
    #   runs rather than failing the classify call on every turn with HTTP
    #   400 and leaving the turn unclassified.
    config = AgentConfig(gemini=GeminiConfig(classify_model=classify_model))

    assert config.resolve_role_config(GeminiRole.CLASSIFY) == RoleConfig(
        classify_model, 0.0, expected
    )


def test_the_clamp_never_lowers_a_level() -> None:
    # Test: The thinking-level clamp on roles already at or above the floor.
    # Situation: `gemini.discovery_model`, `gemini.synthesis_model`, and
    #   `gemini.compaction_model` accept `MINIMAL`, `thinking.discovery_level`
    #   is `HIGH`, and `thinking.synthesis_level` is `LOW`.
    # Expectation: The configured levels and the fixed `LOW` of the
    #   lightweight roles are unchanged; the clamp only raises a level that
    #   is below the model's floor.
    config = AgentConfig(
        gemini=GeminiConfig(
            discovery_model="gemini-3.6-flash",
            synthesis_model="gemini-3.6-flash",
            compaction_model="gemini-3.6-flash",
        ),
        thinking=ThinkingLevels(
            discovery_level=types.ThinkingLevel.HIGH,
            synthesis_level=types.ThinkingLevel.LOW,
        ),
    )

    assert (
        config.resolve_role_config(GeminiRole.DISCOVERY).thinking_level
        is types.ThinkingLevel.HIGH
    )
    assert (
        config.resolve_role_config(GeminiRole.SYNTHESIS).thinking_level
        is types.ThinkingLevel.LOW
    )
    assert (
        config.resolve_role_config(GeminiRole.COMPACTION).thinking_level
        is types.ThinkingLevel.LOW
    )


def test_template_vars_are_coerced_to_strings(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Test: `template_vars` coercion in `parse_agent_config`.
    # Situation: `template_vars` holds a string, an integer, a float, `True`
    #   and `False` booleans, a `_comment` entry, a null value, and a nested
    #   object.
    # Expectation: The string is kept, the numeric and boolean values are
    #   rendered with `str`, the `_comment` entry is dropped without a warning,
    #   and the null and nested values are dropped with one warning each naming
    #   the key.
    with caplog.at_level(logging.WARNING):
        parsed = parse_agent_config(
            {
                "template_vars": {
                    "name": "Example DC",
                    "count": 7,
                    "ratio": 0.5,
                    "flag": True,
                    "disabled": False,
                    "_comment": "notes for humans",
                    "missing": None,
                    "nested": {"a": 1},
                }
            }
        )

    assert parsed.template_vars == {
        "name": "Example DC",
        "count": "7",
        "ratio": "0.5",
        "flag": "True",
        "disabled": "False",
    }
    warnings = _warnings(caplog)
    assert len(warnings) == 2
    assert any("'template_vars.missing'" in message for message in warnings)
    assert any("'template_vars.nested'" in message for message in warnings)


def test_template_vars_cannot_be_modified() -> None:
    # Test: Runtime immutability of `AgentConfig.template_vars`.
    # Situation: Configurations are built both via `parse_agent_config` and
    #   by direct `AgentConfig` construction, and a caller mutates the input
    #   dictionary and attempts to assign to `template_vars`.
    # Expectation: Item assignment raises `TypeError` on both instances, and
    #   mutating the input dictionary does not alter the stored mapping.
    parsed = parse_agent_config({"template_vars": {"name": "Example DC"}})
    raw_vars = {"name": "Example DC"}
    direct = AgentConfig(template_vars=raw_vars)
    raw_vars["name"] = "Mutated"

    for config in (parsed, direct, AgentConfig()):
        template_vars: Any = config.template_vars
        with pytest.raises(TypeError):
            template_vars["region"] = "the world"

    assert parsed.template_vars == {"name": "Example DC"}
    assert direct.template_vars == {"name": "Example DC"}


def test_unknown_keys_are_ignored_without_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Test: Keys the agent does not read.
    # Situation: The document carries `$schema`, `$comment`, `proxy_url`,
    #   `gemini.api_base`, `mcp._comment`, and a misspelled top-level key.
    # Expectation: The recognized values are parsed, the other keys are
    #   ignored, and no warning is logged.
    with caplog.at_level(logging.WARNING):
        parsed = parse_agent_config(
            {
                "$schema": "../schemas/agent-config.schema.json",
                "$comment": "notes",
                "proxy_url": "http://127.0.0.1:5001",
                "gemini": {
                    "api_base": "https://example",
                    "discovery_model": "m",
                },
                "mcp": {"_comment": "notes", "server_url": "https://mcp"},
                "thinkng": {"discovery_level": "high"},
            }
        )

    assert parsed == AgentConfig(
        gemini=GeminiConfig(discovery_model="m"),
        mcp=McpConfig(server_url="https://mcp"),
    )
    assert _warnings(caplog) == []


def test_the_api_key_is_left_out_of_repr() -> None:
    # Test: `repr` of a configuration that carries an API key.
    # Situation: `gemini.api_key` is set.
    # Expectation: Neither the `GeminiConfig` nor the `AgentConfig` `repr`
    #   contains the key, so a logged configuration never discloses it.
    parsed = parse_agent_config({"gemini": {"api_key": "secret-key-value"}})

    assert parsed.gemini.api_key == "secret-key-value"
    assert "secret-key-value" not in repr(parsed.gemini)
    assert "secret-key-value" not in repr(parsed)
