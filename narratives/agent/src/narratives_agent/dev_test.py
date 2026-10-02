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
"""Tests for local development environment and config staging in `dev`."""

import json
import os
from pathlib import Path
from typing import Any

import pytest

from narratives_agent import dev


def _write_baseline_checkout(root: Path, base_config: dict[str, Any]) -> None:
    """Creates a minimal `defaults/agent-config.json` in `root`."""
    defaults_dir = root / "defaults"
    defaults_dir.mkdir(parents=True, exist_ok=True)
    (defaults_dir / "agent-config.json").write_text(
        json.dumps(base_config), encoding="utf-8"
    )


def test_creates_env_local_from_example_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Test: Automatic creation of .env.local from .env.local.example.
    # Situation: .env.local does not exist, .env.local.example exists with
    #   DATA_PLANE_URL and GEMINI_API_KEY, and stage_local_environment runs.
    # Expectation: .env.local is copied from .env.local.example, its variables
    #   are loaded into os.environ, and agent/config.json gets GEMINI_API_KEY.
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("DATA_PLANE_URL", raising=False)
    _write_baseline_checkout(tmp_path, {"thinking": {"mcp_level": "medium"}})
    (tmp_path / ".env.local.example").write_text(
        "DATA_PLANE_URL=https://api.datacommons.org\n"
        "GEMINI_API_KEY=example-gemini-key\n",
        encoding="utf-8",
    )

    config_path = dev.stage_local_environment(tmp_path)

    assert (tmp_path / ".env.local").is_file()
    assert os.environ.get("DATA_PLANE_URL") == "https://api.datacommons.org"
    staged = json.loads(config_path.read_text(encoding="utf-8"))
    assert staged["gemini"]["api_key"] == "example-gemini-key"


def test_touches_empty_env_local_when_example_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Test: Fallback creation of an empty .env.local when .env.local.example is
    #   absent.
    # Situation: Neither .env.local nor .env.local.example exists in root dir.
    # Expectation: An empty .env.local file is created, a warning is logged for
    #   the missing GEMINI_API_KEY, and config staging succeeds with the
    #   placeholder key.
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    _write_baseline_checkout(tmp_path, {"thinking": {"mcp_level": "medium"}})

    config_path = dev.stage_local_environment(tmp_path)

    assert (tmp_path / ".env.local").read_text(encoding="utf-8") == ""
    staged = json.loads(config_path.read_text(encoding="utf-8"))
    assert staged["gemini"]["api_key"] == "REPLACE_ME_WITH_GEMINI_API_KEY"
    assert "GEMINI_API_KEY is not set" in caplog.text


def test_parses_env_local_quotes_exports_and_inline_comments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Test: Parsing of .env.local with export prefixes, quotes, and comments.
    # Situation: .env.local contains `export` prefixes, double- and
    #   single-quoted values with trailing inline comments, and unquoted values
    #   with inline comments.
    # Expectation: Keys and values are cleanly extracted without leaking quotes,
    #   `export` prefixes, or inline comments.
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("MCP_SERVER_URL", raising=False)
    monkeypatch.delenv("DC_API_KEY", raising=False)
    _write_baseline_checkout(tmp_path, {})
    (tmp_path / ".env.local").write_text(
        "# Comment line\n"
        'export GEMINI_API_KEY="quoted-gemini-key" # inline comment\n'
        "MCP_SERVER_URL='https://api.datacommons.org/mcp' # single-quoted\n"
        "DC_API_KEY=unquoted-dc-key # trailing note\n",
        encoding="utf-8",
    )

    config_path = dev.stage_local_environment(tmp_path)

    assert os.environ.get("MCP_SERVER_URL") == "https://api.datacommons.org/mcp"
    assert os.environ.get("DC_API_KEY") == "unquoted-dc-key"
    staged = json.loads(config_path.read_text(encoding="utf-8"))
    assert staged["gemini"]["api_key"] == "quoted-gemini-key"


def test_shell_environment_overrides_env_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Test: Precedence of non-empty shell environment variables over .env.local.
    # Situation: GEMINI_API_KEY and DATA_PLANE_URL are set in os.environ, while
    #   DC_API_KEY is set to an empty string "", and .env.local defines all 3.
    # Expectation: Non-empty shell variables win over .env.local, while an empty
    #   shell variable is treated as unset and populated from .env.local.
    monkeypatch.setenv("GEMINI_API_KEY", "shell-gemini-key")
    monkeypatch.setenv("DATA_PLANE_URL", "https://custom.example.org")
    monkeypatch.setenv("DC_API_KEY", "   ")
    _write_baseline_checkout(tmp_path, {})
    (tmp_path / ".env.local").write_text(
        "GEMINI_API_KEY=dotenv-gemini-key\n"
        "DATA_PLANE_URL=https://api.datacommons.org\n"
        "DC_API_KEY=dotenv-dc-key\n",
        encoding="utf-8",
    )

    config_path = dev.stage_local_environment(tmp_path)

    assert os.environ.get("DATA_PLANE_URL") == "https://custom.example.org"
    assert os.environ.get("DC_API_KEY") == "dotenv-dc-key"
    staged = json.loads(config_path.read_text(encoding="utf-8"))
    assert staged["gemini"]["api_key"] == "shell-gemini-key"


def test_merges_nested_config_overrides_without_losing_sibling_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Test: Recursive merging of config/agent-config.json over defaults/.
    # Situation: defaults/agent-config.json defines multiple keys under
    #   `template_vars` and `thinking`, and config/agent-config.json overrides
    #   only `template_vars.name` and `gemini: null`.
    # Expectation: `template_vars.region` and `thinking.mcp_level` from defaults
    #   are preserved alongside the overridden `template_vars.name`, and
    #   `gemini: null` is safely normalized to a dict carrying `api_key`.
    monkeypatch.setenv("GEMINI_API_KEY", "merged-key")
    _write_baseline_checkout(
        tmp_path,
        {
            "thinking": {"mcp_level": "medium", "synthesis_level": "medium"},
            "template_vars": {
                "name": "Example Data Commons",
                "region": "the world",
            },
        },
    )
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "agent-config.json").write_text(
        json.dumps(
            {
                "template_vars": {"name": "Acme Data Commons"},
                "gemini": None,
            }
        ),
        encoding="utf-8",
    )

    config_path = dev.stage_local_environment(tmp_path)

    staged = json.loads(config_path.read_text(encoding="utf-8"))
    assert staged["template_vars"] == {
        "name": "Acme Data Commons",
        "region": "the world",
    }
    assert staged["thinking"] == {
        "mcp_level": "medium",
        "synthesis_level": "medium",
    }
    assert staged["gemini"] == {"api_key": "merged-key"}


def test_inlines_prompt_slots_and_preserves_inline_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Test: Prompt markdown inlining, HTML comment stripping, and precedence.
    # Situation: defaults/prompts/ provides mcp.md (with HTML comments),
    #   synthesis.md, and an unrelated README.md; config/prompts/ overrides
    #   synthesis.md and has a comment-only follow_up.md;
    #   config/agent-config.json defines an inline `prompts.mcp` override.
    # Expectation: HTML comments are stripped, non-slot files (README.md) and
    #   comment-only files are omitted, config/prompts/ overrides
    #   defaults/prompts/, and inline `prompts` in agent-config.json win over
    #   markdown files.
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    _write_baseline_checkout(tmp_path, {})
    defaults_prompts = tmp_path / "defaults" / "prompts"
    defaults_prompts.mkdir()
    (defaults_prompts / "mcp.md").write_text(
        "<!-- header comment -->\nDefault MCP prompt", encoding="utf-8"
    )
    (defaults_prompts / "synthesis.md").write_text(
        "Default synthesis prompt", encoding="utf-8"
    )
    (defaults_prompts / "README.md").write_text(
        "Unrelated documentation", encoding="utf-8"
    )

    config_prompts = tmp_path / "config" / "prompts"
    config_prompts.mkdir(parents=True)
    (config_prompts / "synthesis.md").write_text(
        "Overridden synthesis <!-- note --> prompt", encoding="utf-8"
    )
    (config_prompts / "follow_up.md").write_text(
        "<!-- comment only -->", encoding="utf-8"
    )

    (tmp_path / "config" / "agent-config.json").write_text(
        json.dumps({"prompts": {"mcp": "Inline MCP override"}}),
        encoding="utf-8",
    )

    config_path = dev.stage_local_environment(tmp_path)

    staged = json.loads(config_path.read_text(encoding="utf-8"))
    assert staged["prompts"] == {
        "mcp": "Inline MCP override",
        "synthesis": "Overridden synthesis  prompt",
    }


def test_preserves_existing_config_api_key_when_env_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Test: Fallback to existing Gemini API key in agent/config.json.
    # Situation: Neither os.environ nor .env.local provides GEMINI_API_KEY, but
    #   agent/config.json already contains a valid non-placeholder key.
    # Expectation: The existing key in agent/config.json is preserved.
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    _write_baseline_checkout(tmp_path, {})
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "config.json").write_text(
        json.dumps({"gemini": {"api_key": "existing-staged-key"}}),
        encoding="utf-8",
    )

    config_path = dev.stage_local_environment(tmp_path)

    staged = json.loads(config_path.read_text(encoding="utf-8"))
    assert staged["gemini"]["api_key"] == "existing-staged-key"


def test_exits_on_missing_or_malformed_config(tmp_path: Path) -> None:
    # Test: Fail-fast behavior when baseline or override config is invalid.
    # Situation: First defaults/agent-config.json is missing; next
    #   config/agent-config.json contains invalid JSON.
    # Expectation: Both cases raise SystemExit with a clear FATAL message.
    with pytest.raises(SystemExit, match="Missing baseline config"):
        dev.stage_local_environment(tmp_path)

    _write_baseline_checkout(tmp_path, {})
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "agent-config.json").write_text("{broken", encoding="utf-8")

    with pytest.raises(SystemExit, match="Failed to load"):
        dev.stage_local_environment(tmp_path)
