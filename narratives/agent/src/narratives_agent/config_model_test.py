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
"""Tests for `parse_agent_config` in `config_model`.

Covers the per-field rules the parser applies to a configuration document:
1. A model name that is absent, null, blank, or not a string gives the
   default; a configured name is stripped.
2. A section that is not a JSON object gives that section's defaults with
   one warning, and every other section is still parsed.
3. A value of the wrong type for `enabled`, a thinking level, a prompt, or
   the API key gives the default with one warning naming the key.
4. `template_vars` drops `_`-prefixed keys, renders numbers as strings,
   and drops other values with a warning.
5. Unknown keys are ignored without a warning.

The loading paths that produce the document are tested in `config_test.py`.
"""

import logging
from typing import Any

import pytest

from narratives_agent import config_model
from narratives_agent.config_model import (
    DEFAULT_GEMINI_CLASSIFY_MODEL,
    DEFAULT_GEMINI_MODEL,
    AgentConfig,
    GeminiConfig,
    McpConfig,
    Prompts,
    ThinkingLevels,
    parse_agent_config,
)


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
    assert parsed.gemini.mcp_model == DEFAULT_GEMINI_MODEL
    assert parsed.gemini.classify_model == DEFAULT_GEMINI_CLASSIFY_MODEL
    assert parsed.mcp == McpConfig(server_url="", enabled=True)
    assert parsed.thinking == ThinkingLevels(
        mcp_level="low", synthesis_level="low"
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
                "mcp_model": " gemini-3-pro ",
                "classify_model": " gemini-3.8-flash ",
                "api_key": " test-key ",
            },
            "mcp": {"server_url": " https://mcp.example ", "enabled": False},
            "thinking": {"mcp_level": "high", "synthesis_level": "medium"},
            "prompts": {
                "classify": "Classify. ",
                "mcp": "Gather.",
                "synthesis": "Write.",
                "follow_up": "Suggest.",
            },
            "template_vars": {"name": "Example DC"},
        }
    )

    assert parsed == AgentConfig(
        gemini=GeminiConfig(
            mcp_model="gemini-3-pro",
            classify_model="gemini-3.8-flash",
            api_key="test-key",
        ),
        mcp=McpConfig(server_url="https://mcp.example", enabled=False),
        thinking=ThinkingLevels(mcp_level="high", synthesis_level="medium"),
        prompts=Prompts(
            classify="Classify. ",
            mcp="Gather.",
            synthesis="Write.",
            follow_up="Suggest.",
        ),
        template_vars={"name": "Example DC"},
    )


@pytest.mark.parametrize(
    ("gemini", "warned"),
    [
        ({}, False),
        ({"mcp_model": None, "classify_model": None}, True),
        ({"mcp_model": "", "classify_model": ""}, True),
        ({"mcp_model": "   ", "classify_model": "   "}, True),
        ({"mcp_model": 7, "classify_model": ["gemini"]}, True),
    ],
    ids=["absent", "null", "empty", "whitespace", "wrong type"],
)
def test_an_unusable_model_name_gives_the_default(
    caplog: pytest.LogCaptureFixture,
    gemini: dict[str, Any],
    warned: bool,
) -> None:
    # Test: Model-name fallback in `parse_agent_config`.
    # Situation: `gemini.mcp_model` and `gemini.classify_model` are absent,
    #   null, empty, whitespace-only, or not strings.
    # Expectation: Both models are the defaults. An absent name is not
    #   reported; every other case logs one warning per model naming its key.
    with caplog.at_level(logging.WARNING):
        parsed = parse_agent_config({"gemini": gemini})

    assert parsed.gemini.mcp_model == DEFAULT_GEMINI_MODEL
    assert parsed.gemini.classify_model == DEFAULT_GEMINI_CLASSIFY_MODEL
    warnings = _warnings(caplog)
    if warned:
        assert len(warnings) == 2
        assert any("'gemini.mcp_model'" in message for message in warnings)
        assert any("'gemini.classify_model'" in message for message in warnings)
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
        "gemini": {"mcp_model": "gemini-test"},
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
        assert parsed.gemini.mcp_model == "gemini-test"
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
        ("thinking", "mcp_level", 2, "low"),
        ("thinking", "mcp_level", False, "low"),
        ("thinking", "mcp_level", 0, "low"),
        ("thinking", "synthesis_level", None, "low"),
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
        "mcp_level int",
        "mcp_level false",
        "mcp_level zero",
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
    #   and `0` for `thinking.mcp_level`.
    # Expectation: The field carries its default, nothing is raised, and
    #   exactly one warning names the field's dotted key.
    with caplog.at_level(logging.WARNING):
        parsed = parse_agent_config({section: {key: value}})

    assert getattr(getattr(parsed, section), key) == expected_default
    assert [
        f"'{section}.{key}'" in message for message in _warnings(caplog)
    ] == [True]


def test_an_empty_thinking_level_is_preserved(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Test: Empty-string thinking levels in `parse_agent_config`.
    # Situation: `thinking.mcp_level` and `thinking.synthesis_level` are set to
    #   the empty string `""`.
    # Expectation: Both fields carry `""` so the Gemini client leaves the
    #   model's default level in place, and no warning is logged.
    with caplog.at_level(logging.WARNING):
        parsed = parse_agent_config(
            {"thinking": {"mcp_level": "", "synthesis_level": ""}}
        )

    assert parsed.thinking == ThinkingLevels(mcp_level="", synthesis_level="")
    assert _warnings(caplog) == []


def test_template_vars_are_coerced_to_strings(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Test: `template_vars` coercion in `parse_agent_config`.
    # Situation: `template_vars` holds a string, an integer, a float, a
    #   boolean, a `_comment` entry, a null value, and a nested object.
    # Expectation: The string is kept, the number-like values are rendered
    #   with `str`, the `_comment` entry is dropped without a warning, and the
    #   null and nested values are dropped with one warning each naming the
    #   key.
    with caplog.at_level(logging.WARNING):
        parsed = parse_agent_config(
            {
                "template_vars": {
                    "name": "Example DC",
                    "count": 7,
                    "ratio": 0.5,
                    "flag": True,
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
                "gemini": {"api_base": "https://example", "mcp_model": "m"},
                "mcp": {"_comment": "notes", "server_url": "https://mcp"},
                "thinkng": {"mcp_level": "high"},
            }
        )

    assert parsed == AgentConfig(
        gemini=GeminiConfig(mcp_model="m"),
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
