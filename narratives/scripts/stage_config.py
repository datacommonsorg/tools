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
"""Stages agent/config.json for local development.

Local development only — not used in production or deployments.

In production on Cloud Run, the container image carries no configuration;
instead, `bootstrap_config_from_url()` downloads `agent-config.json` and inlines
`prompts/*.md` from a GCS bucket at boot, while Secret Manager provides API
credentials.

On a developer machine without GCP infrastructure, this script emulates that
cloud bootloader locally:
1. Layers `defaults/agent-config.json` with optional `config/` overrides.
2. Inlines system prompt markdown files from `defaults/prompts/` and
   `config/prompts/`.
3. Injects `GEMINI_API_KEY` from `.env.local`.
4. Writes `agent/config.json` so
   `uv run --env-file ../.env.local narratives-agent-dev` runs without
   the developer needing to manually configure agent/config.json.
"""

import contextlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

NARRATIVES_DIR = Path(__file__).resolve().parents[1]
DEFAULTS_DIR = NARRATIVES_DIR / "defaults"
CONFIG_DIR = NARRATIVES_DIR / "config"
AGENT_DIR = NARRATIVES_DIR / "agent"
TARGET_CONFIG_FILE = AGENT_DIR / "config.json"
ENV_FILE = NARRATIVES_DIR / ".env.local"

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _strip_html_comments(text: str) -> str:
    """Strips HTML authoring comments so they are not sent in prompts."""
    return _HTML_COMMENT_RE.sub("", text).strip()


def _load_env_vars() -> dict[str, str]:
    """Reads .env.local and parses key-value pairs."""
    if not ENV_FILE.is_file():
        return {}

    content = ENV_FILE.read_text(encoding="utf-8")
    vars_dict: dict[str, str] = {}
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        k, v = stripped.split("=", 1)
        vars_dict[k.strip()] = v.strip().strip("'\"")
    return vars_dict


def _load_base_config() -> dict[str, Any]:
    """Loads defaults/agent-config.json with optional config/ overrides."""
    base_config_path = DEFAULTS_DIR / "agent-config.json"
    if not base_config_path.is_file():
        raise SystemExit(
            f"FATAL: Missing baseline config at {base_config_path}"
        )

    config: dict[str, Any] = json.loads(
        base_config_path.read_text(encoding="utf-8")
    )
    override_config_path = CONFIG_DIR / "agent-config.json"
    if override_config_path.is_file():
        try:
            config.update(
                json.loads(override_config_path.read_text(encoding="utf-8"))
            )
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: Failed to parse {override_config_path}: {e}")
    return config


def _load_prompts() -> dict[str, str]:
    """Inlines prompt markdown files, prioritizing config/ over defaults/."""
    prompt_files: dict[str, Path] = {}

    # 1. Discover baseline prompts in defaults/prompts/*.md
    defaults_prompts_dir = DEFAULTS_DIR / "prompts"
    if defaults_prompts_dir.is_dir():
        for path in sorted(defaults_prompts_dir.glob("*.md")):
            prompt_files[path.stem] = path

    # 2. Layer optional overrides from config/prompts/*.md
    config_prompts_dir = CONFIG_DIR / "prompts"
    if config_prompts_dir.is_dir():
        for path in sorted(config_prompts_dir.glob("*.md")):
            prompt_files[path.stem] = path

    # 3. Read and clean prompt contents
    prompts: dict[str, str] = {}
    for slot, path in prompt_files.items():
        cleaned = _strip_html_comments(path.read_text(encoding="utf-8"))
        if cleaned:
            prompts[slot] = cleaned

    return prompts


def _resolve_gemini_api_key(env_vars: dict[str, str]) -> str:
    """Resolves Gemini API key from .env.local, existing config, or fallback."""
    existing_key = ""
    if TARGET_CONFIG_FILE.is_file():
        # Target config may be corrupted or unreadable; ignore and overwrite.
        with contextlib.suppress(json.JSONDecodeError, OSError):
            existing = json.loads(
                TARGET_CONFIG_FILE.read_text(encoding="utf-8")
            )
            k = existing.get("gemini", {}).get("api_key", "")
            if k and not k.startswith("REPLACE_ME"):
                existing_key = k

    return (
        env_vars.get("GEMINI_API_KEY", "")
        or existing_key
        or "REPLACE_ME_WITH_GEMINI_API_KEY"
    )


def _write_config(config: dict[str, Any]) -> None:
    """Writes the compiled configuration into agent/config.json."""
    AGENT_DIR.mkdir(parents=True, exist_ok=True)
    TARGET_CONFIG_FILE.write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    # Ensure .env.local exists so `uv run --env-file ../.env.local` succeeds
    example_env = NARRATIVES_DIR / ".env.example"
    if not ENV_FILE.is_file():
        if example_env.is_file():
            shutil.copy(example_env, ENV_FILE)
            print(
                "Created .env.local from .env.example — please add your"
                " GEMINI_API_KEY"
            )
        else:
            ENV_FILE.touch()

    env_vars = _load_env_vars()
    config = _load_base_config()
    config["prompts"] = _load_prompts()
    config.setdefault("gemini", {})["api_key"] = _resolve_gemini_api_key(
        env_vars
    )

    _write_config(config)
    print("✓ Staged local config into agent/config.json")


if __name__ == "__main__":
    main()
