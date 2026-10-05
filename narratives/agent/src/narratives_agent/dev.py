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
"""Runs the agent for local development as `uv run narratives-agent-dev`.

Local development only — not used in production or deployments.

In production on Cloud Run, the container image carries no configuration;
instead, `bootstrap_config_from_url()` downloads `agent-config.json` and inlines
`prompts/*.md` from a GCS bucket at boot, while Secret Manager provides API
credentials.

On a developer machine without GCP infrastructure, this module emulates that
cloud bootloader locally before starting Uvicorn:
1. Ensures `.env.local` exists (copying `.env.local.example` if needed) and
   loads its variables into `os.environ`.
2. Layers `defaults/agent-config.json` with optional `config/agent-config.json`
   overrides.
3. Inlines system prompt markdown files from `defaults/prompts/` and
   `config/prompts/`, preserving any inline `prompts` overrides.
4. Injects `GEMINI_API_KEY` from the environment or `.env.local` into
   `agent/config.json`.
"""

import contextlib
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

import uvicorn
from dotenv import dotenv_values

from narratives_agent.config import (
    PROMPT_SLOTS,
    strip_prompt_comments,
)
from narratives_agent.settings import get_settings

logger = logging.getLogger(__name__)

_NARRATIVES_DIR = Path(__file__).resolve().parents[3]
_PLACEHOLDER_API_KEY_PREFIX = "REPLACE_ME"
_DEFAULT_PLACEHOLDER_API_KEY = "REPLACE_ME_WITH_GEMINI_API_KEY"


def _load_env_vars(env_file: Path) -> dict[str, str]:
    """Reads `.env.local` and parses key-value pairs."""
    if not env_file.is_file():
        return {}
    return {
        key: value
        for key, value in dotenv_values(env_file).items()
        if value is not None
    }


def _ensure_env_file(root_dir: Path) -> Path:
    """Returns `.env.local`, creating it from `.env.local.example` if absent."""
    env_file = root_dir / ".env.local"
    if env_file.is_file():
        return env_file

    example_env_file = root_dir / ".env.local.example"
    if example_env_file.is_file():
        shutil.copy(example_env_file, env_file)
        logger.warning(
            "Created .env.local from .env.local.example — please add your "
            "GEMINI_API_KEY"
        )
    else:
        env_file.touch()
    return env_file


def _populate_environment(root_dir: Path) -> dict[str, str]:
    """Ensures `.env.local` exists and loads unset vars into `os.environ`."""
    env_file = _ensure_env_file(root_dir)
    env_vars = _load_env_vars(env_file)
    for key, value in env_vars.items():
        if value and not os.environ.get(key, "").strip():
            os.environ[key] = value
    get_settings.cache_clear()
    return env_vars


def _read_json_object(path: Path) -> dict[str, Any]:
    """Reads and validates a JSON object from `path`, or exits with an error."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"FATAL: Failed to load {path}: {error}") from error
    if not isinstance(data, dict):
        raise SystemExit(f"FATAL: Expected a JSON object in {path}")
    return data


def _merge_dicts(
    base: dict[str, Any], override: dict[str, Any]
) -> dict[str, Any]:
    """Recursively merges `override` into a copy of `base`."""
    merged = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(value, dict) and isinstance(existing, dict):
            merged[key] = _merge_dicts(existing, value)
        else:
            merged[key] = value
    return merged


def _load_base_config(defaults_dir: Path, config_dir: Path) -> dict[str, Any]:
    """Loads `defaults/agent-config.json` with optional `config/` overrides."""
    base_config_path = defaults_dir / "agent-config.json"
    if not base_config_path.is_file():
        raise SystemExit(
            f"FATAL: Missing baseline config at {base_config_path}"
        )

    config = _read_json_object(base_config_path)
    override_config_path = config_dir / "agent-config.json"
    if override_config_path.is_file():
        override = _read_json_object(override_config_path)
        config = _merge_dicts(config, override)
    return config


def _load_prompts(
    defaults_dir: Path, config_dir: Path, inline_prompts: Any = None
) -> dict[str, str]:
    """Inlines prompt markdown files and merges inline `prompts` overrides."""
    prompt_files: dict[str, Path] = {}
    for directory in (defaults_dir / "prompts", config_dir / "prompts"):
        if not directory.is_dir():
            continue
        for slot in PROMPT_SLOTS:
            candidate = directory / f"{slot}.md"
            if candidate.is_file():
                prompt_files[slot] = candidate

    prompts: dict[str, str] = {}
    for slot, path in prompt_files.items():
        cleaned = strip_prompt_comments(path.read_text(encoding="utf-8"))
        if cleaned:
            prompts[slot] = cleaned

    if isinstance(inline_prompts, dict):
        for slot, body in inline_prompts.items():
            if isinstance(body, str) and body.strip():
                prompts[slot] = body

    return prompts


def _is_usable_api_key(value: str) -> bool:
    """Returns True when `value` is non-empty and not a placeholder."""
    return bool(value) and not value.startswith(_PLACEHOLDER_API_KEY_PREFIX)


def _read_existing_api_key(target_config_file: Path) -> str:
    """Extracts `gemini.api_key` from an existing `agent/config.json` file."""
    if not target_config_file.is_file():
        return ""
    # Target config may be corrupted or unreadable; ignore and overwrite.
    with contextlib.suppress(json.JSONDecodeError, OSError):
        existing = json.loads(target_config_file.read_text(encoding="utf-8"))
        if isinstance(existing, dict) and isinstance(
            existing.get("gemini"), dict
        ):
            api_key = existing["gemini"].get("api_key", "")
            if isinstance(api_key, str):
                return api_key.strip()
    return ""


def _resolve_gemini_api_key(
    env_vars: dict[str, str], target_config_file: Path
) -> str:
    """Resolves the Gemini API key from env, `.env.local`, or staged config."""
    candidates = (
        os.environ.get("GEMINI_API_KEY", "").strip(),
        env_vars.get("GEMINI_API_KEY", "").strip(),
        _read_existing_api_key(target_config_file),
    )
    for candidate in candidates:
        if _is_usable_api_key(candidate):
            return candidate

    logger.warning(
        "GEMINI_API_KEY is not set in .env.local or the environment; "
        "chat requests will fail until a key is configured"
    )
    return _DEFAULT_PLACEHOLDER_API_KEY


def stage_local_environment(narratives_dir: Path | None = None) -> Path:
    """Loads `.env.local` into `os.environ` and stages `agent/config.json`.

    Args:
        narratives_dir: Root `narratives/` directory; defaults to the repository
            checkout root.

    Returns:
        Path to the written `agent/config.json` file.

    Raises:
        SystemExit: If `defaults/agent-config.json` is missing or if either the
            baseline or override config file is not a valid JSON object.
    """
    root_dir = narratives_dir or _NARRATIVES_DIR
    defaults_dir = root_dir / "defaults"
    config_dir = root_dir / "config"
    target_config_file = root_dir / "agent" / "config.json"

    env_vars = _populate_environment(root_dir)
    config = _load_base_config(defaults_dir, config_dir)

    prompts = _load_prompts(defaults_dir, config_dir, config.get("prompts"))
    if prompts:
        config["prompts"] = prompts

    if not isinstance(config.get("gemini"), dict):
        config["gemini"] = {}
    config["gemini"]["api_key"] = _resolve_gemini_api_key(
        env_vars, target_config_file
    )

    target_config_file.parent.mkdir(parents=True, exist_ok=True)
    target_config_file.write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )
    logger.info("Staged local config into %s", target_config_file)
    return target_config_file


def main() -> None:
    """Stages local configuration and serves the application with auto-reload.

    The port is `AGENT_PORT`, 5001 by default.
    """
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s:     %(message)s"
    )
    stage_local_environment()
    uvicorn.run(
        "narratives_agent.server.app:app",
        host="127.0.0.1",
        port=get_settings().agent_port,
        reload=True,
    )
