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

"""Loads the agent configuration and renders prompts from it.

The configuration is held in process memory. It is loaded from `CONFIG_URL` once
at startup, from `agent_root/config.json` in local development (reloaded when
the file's modification time changes), or from the `defaults/` directory shipped
with the image.
"""

import copy
import json
import logging
import posixpath
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse
from zoneinfo import ZoneInfo

import requests

from narratives_agent.settings import get_settings

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Model used whenever agent-config.json names none. The shipped defaults name
# no model, so this is the model a deployment runs unless it overrides it.
# Every caller reads the model through get_gemini_model() rather than spelling
# its own default, so that every call in a turn uses the same model.
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"


def get_gemini_model(config: dict[str, Any]) -> str:
    """Returns the model `gemini.mcp_model` names, or the shared default."""
    gemini_cfg = config.get("gemini")
    model = (
        gemini_cfg.get("mcp_model") if isinstance(gemini_cfg, dict) else None
    )
    if isinstance(model, str) and model.strip():
        return model.strip()
    return DEFAULT_GEMINI_MODEL


# Secret Manager client for runtime key loading (optional import).
try:
    from google.cloud import secretmanager

    _SECRET_MANAGER_AVAILABLE = True
except ImportError:
    _SECRET_MANAGER_AVAILABLE = False
    logger.warning(
        "google-cloud-secret-manager not installed; "
        "GEMINI_API_KEY_SECRET will be ignored"
    )


_bootstrapped_config: dict[str, Any] | None = None
_config_cache: dict[str, Any] | None = None
_config_mtime = 0.0
_config_path: Path | None = None
_defaults_config: dict[str, Any] | None = None
_defaults_dir: Path | None = None

# Secret Manager lookup cache and TTL (seconds)
_SECRET_MANAGER_TTL_SECONDS = 300
# `_SECRET_MANAGER_TIMEOUT_SECONDS` bounds a single Secret Manager read.
# Concurrent cache misses wait on the thread performing the read, so an
# unbounded read would stall all of them.
_SECRET_MANAGER_TIMEOUT_SECONDS = 10.0
_secret_manager_cache: dict[str, tuple[float, str]] = {}
# The Gemini client resolves the key on a worker thread
# (`asyncio.to_thread`), so concurrent turns can miss the cache together. The
# lock makes them share one Secret Manager request.
_secret_manager_lock = threading.Lock()

# Prompt slots the workflows read out of config["prompts"]. Bodies are authored
# as `prompts/<slot>.md` and land beside agent-config.json in the config bucket.
# `follow_up` is the only slot with an in-code default
# (DEFAULT_FOLLOW_UP_PROMPT), so a failed fetch there degrades to that rather
# than to no system instruction.
PROMPT_SLOTS = ("mcp", "synthesis", "follow_up")

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def strip_prompt_comments(text: str) -> str:
    """Strips HTML authoring comments and surrounding whitespace."""
    return _HTML_COMMENT_RE.sub("", text).strip()


def _fetch_gcs_url(url: str) -> requests.Response:
    """Fetch from GCS.

    When running in GCP, attach the metadata service-account token so private
    config buckets are readable; falls back to an unauthenticated GET (public
    buckets / local dev) if the metadata server is unavailable.
    """
    headers = {}
    if "storage.googleapis.com" in url:
        try:
            token_url = (
                "http://metadata.google.internal/computeMetadata/v1/"
                "instance/service-accounts/default/token"
            )
            r = requests.get(
                token_url, headers={"Metadata-Flavor": "Google"}, timeout=2
            )
            if r.status_code == 200:
                token = r.json().get("access_token")
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                    logger.info(
                        "Using GCP metadata service account token for GCS fetch"
                    )
        except Exception as e:
            logger.debug(
                "Metadata token fetch skipped/failed (normal if local): %s", e
            )
    response = requests.get(url, headers=headers, timeout=15)
    # `gcloud storage rsync` uploads .md as text/markdown with no charset, and
    # requests then falls back to guessing the encoding from the bytes. Every
    # file in the config bucket is UTF-8 by contract, and the prompts carry ₹, →
    # and em-dashes, so a wrong guess silently corrupts the text we hand Gemini.
    response.encoding = "utf-8"
    return response


def _fetch_prompt_bodies(config_url: str) -> dict[str, str]:
    """Fetches `prompts/<slot>.md` from beside `config_url`.

    The prompt URLs are derived from `config_url`, so the prompts always come
    from the same bucket as the configuration they belong to.

    A slot that fails to fetch is skipped with a warning instead of failing
    startup: an absent prompt leaves that phase with no system instruction, so
    a partial fetch degrades the agent rather than taking it down.
    """
    # Prompt bodies live in a `prompts/` directory beside the config object, so
    # the URL is the config's own with its last path segment swapped out. Query
    # and fragment are dropped: they address that one object (e.g. ?generation=)
    # and mean nothing for a prompt. posixpath.join keeps the host-root case
    # right, where dirname is "/".
    parsed = urlparse(config_url)
    base_path = posixpath.dirname(parsed.path)
    prompts = {}
    for slot in PROMPT_SLOTS:
        prompt_url = urlunparse(
            parsed._replace(
                path=posixpath.join(base_path, "prompts", f"{slot}.md"),
                query="",
                fragment="",
            )
        )
        try:
            r = _fetch_gcs_url(prompt_url)
            r.raise_for_status()
            # Strip HTML comments so the .md files can carry authoring notes —
            # provenance, "keep in sync with X" reminders — without those notes
            # being sent to Gemini as part of the system instruction.
            body = strip_prompt_comments(r.text)
        except Exception as e:
            logger.warning(
                "Prompt %r fetch failed (%s): %s", slot, prompt_url, e
            )
            continue
        if not body:
            logger.warning(
                "Prompt %r at %s is empty; leaving slot unset", slot, prompt_url
            )
            continue
        prompts[slot] = body
        logger.info(
            "Prompt %r loaded: %d bytes from %s", slot, len(body), prompt_url
        )
    return prompts


def _read_prompt_files(prompts_dir: Path) -> dict[str, str]:
    """Reads `<slot>.md` files from `prompts_dir` and strips HTML comments."""
    prompts: dict[str, str] = {}
    for slot in PROMPT_SLOTS:
        prompt_path = prompts_dir / f"{slot}.md"
        if not prompt_path.is_file():
            continue
        try:
            body = strip_prompt_comments(
                prompt_path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError) as e:
            logger.warning(
                "Prompt %r read failed (%s): %s", slot, prompt_path, e
            )
            continue
        if body:
            prompts[slot] = body
    return prompts


def _apply_prompts(config: dict[str, Any], prompts: dict[str, str]) -> None:
    """Merges `prompts` into `config["prompts"]`, keeping inline overrides."""
    inline = config.get("prompts")
    if isinstance(inline, dict):
        for slot, body in inline.items():
            if isinstance(body, str) and body.strip():
                logger.info(
                    "Prompt %r overridden inline by agent-config.json", slot
                )
                prompts[slot] = body
    if prompts:
        config["prompts"] = prompts
    else:
        config.pop("prompts", None)
    missing = [slot for slot in PROMPT_SLOTS if slot not in prompts]
    if missing:
        logger.warning(
            "Missing prompt bodies for %s. 'follow_up' falls back to its "
            "in-code default; any other missing slot runs without a system "
            "instruction.",
            missing,
        )


def bootstrap_config_from_url() -> None:
    """Fetches `CONFIG_URL` at startup and caches the merged configuration.

    Merges prompt bodies from `<bucket>/prompts/<slot>.md` into
    `config["prompts"]`, while allowing non-empty inline `prompts` entries in
    `agent-config.json` to take precedence.

    If the fetch fails or the response is not a JSON object, an empty
    configuration is cached so that `load_config()` does not fall back to the
    shipped defaults when `CONFIG_URL` is explicitly configured.
    """
    global _bootstrapped_config

    url = get_settings().config_url
    if not url:
        _bootstrapped_config = None
        return
    try:
        r = _fetch_gcs_url(url)
        r.raise_for_status()
        raw = r.text
        logger.info("CONFIG_URL fetched %d bytes from %s", len(raw), url)
    except Exception as e:
        logger.error(
            "CONFIG_URL fetch failed (%s): %s; running without configuration",
            url,
            e,
        )
        _bootstrapped_config = {}
        return

    try:
        config = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(
            "CONFIG_URL is not valid JSON (%s); running without configuration",
            e,
        )
        _bootstrapped_config = {}
        return

    if not isinstance(config, dict):
        logger.error(
            "CONFIG_URL did not contain a JSON object; running without "
            "configuration"
        )
        _bootstrapped_config = {}
        return

    _apply_prompts(config, _fetch_prompt_bodies(url))
    _bootstrapped_config = config


def _load_config_file(config_path: Path) -> dict[str, Any]:
    """Loads `config_path` and caches it by path and modification time."""
    global _config_cache, _config_mtime, _config_path

    try:
        current_mtime = config_path.stat().st_mtime
        if (
            _config_cache is not None
            and _config_path == config_path
            and current_mtime == _config_mtime
        ):
            return _config_cache
        with open(config_path, encoding="utf-8") as f:
            document = json.load(f)
        if not isinstance(document, dict):
            logger.error("%s does not contain a JSON object", config_path)
            _config_cache = None
            _config_mtime = 0.0
            _config_path = None
            return {}
        _config_cache = document
        _config_mtime = current_mtime
        _config_path = config_path
        logger.info("Config loaded/reloaded from config.json")
        return document
    except (OSError, ValueError) as e:
        logger.error("Failed to load config from %s: %s", config_path, e)
        _config_cache = None
        _config_mtime = 0.0
        _config_path = None
        return {}


def _load_defaults_config(defaults_dir: Path) -> dict[str, Any]:
    """Loads `agent-config.json` and `prompts/` from `defaults_dir` once."""
    global _defaults_config, _defaults_dir

    if _defaults_config is not None and _defaults_dir == defaults_dir:
        return _defaults_config

    config_path = defaults_dir / "agent-config.json"
    config: dict[str, Any] = {}
    try:
        document = json.loads(config_path.read_text(encoding="utf-8"))
        if isinstance(document, dict):
            prompts = _read_prompt_files(defaults_dir / "prompts")
            _apply_prompts(document, prompts)
            config = document
            logger.info("Config loaded from %s", defaults_dir)
        else:
            logger.error("%s does not contain a JSON object", config_path)
    except FileNotFoundError:
        logger.warning("No agent configuration found at %s", config_path)
    except (OSError, ValueError) as e:
        logger.error(
            "Failed to load the configuration under %s: %s", defaults_dir, e
        )

    _defaults_config = config
    _defaults_dir = defaults_dir
    return config


def load_config() -> dict[str, Any]:
    """Returns a deep copy of the active agent configuration.

    Reads from `CONFIG_URL` (startup bootstrap), `agent_root/config.json`
    (local development), or `defaults_dir` (`agent-config.json` and
    `prompts/`), in that order.
    """
    if _bootstrapped_config is not None:
        return copy.deepcopy(_bootstrapped_config)

    settings = get_settings()
    config_path = settings.agent_root / "config.json"
    if config_path.exists():
        return copy.deepcopy(_load_config_file(config_path))
    return copy.deepcopy(_load_defaults_config(settings.defaults_dir))


def get_current_datetime() -> str:
    """Get the current date and time in the configured timezone.

    The TIMEZONE environment variable selects the zone (for example
    "Asia/Kolkata" or "America/Los_Angeles"), and the trailing label
    ("IST", "PT", ...) is the zone abbreviation resolved at runtime.
    Falls back to UTC when TIMEZONE names a zone that cannot be resolved.
    """
    tz_name = get_settings().timezone
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        logger.warning(f"Unknown TIMEZONE={tz_name!r}; falling back to UTC")
        tz = ZoneInfo("UTC")
    now = datetime.now(tz)
    return now.strftime("%A, %B %d, %Y at %I:%M %p ") + now.strftime("%Z")


def _instance_template_vars() -> dict[str, str]:
    """agent-config's template_vars, coerced to strings.

    Keys beginning with "_" are dropped so the "_comment" convention used
    throughout the config files cannot be substituted into a prompt.
    """
    raw = load_config().get("template_vars")
    if not isinstance(raw, dict):
        return {}
    return {
        key: str(value)
        for key, value in raw.items()
        if not key.startswith("_") and isinstance(value, (str, int, float))
    }


def render_prompt(prompt: str) -> str:
    """Substitute {{CURRENT_DATETIME}} and {{instance.<key>}} into a prompt.

    An {{instance.<key>}} with no matching template_vars entry is left in place
    rather than blanked: a visible placeholder in an answer is a far louder
    failure than a sentence that has silently lost its subject.
    """
    rendered = prompt.replace("{{CURRENT_DATETIME}}", get_current_datetime())
    for key, value in _instance_template_vars().items():
        rendered = rendered.replace(f"{{{{instance.{key}}}}}", value)
    return rendered


def _fetch_key_from_secret_manager(secret_name: str) -> str:
    """Load the Gemini API key from Secret Manager, or return an empty string.

    The secret payload must contain the bare API key string. `secret_name` may
    be either a full resource name
    (`projects/<proj>/secrets/<name>/versions/<v>`) or a short secret ID
    resolved against `GOOGLE_CLOUD_PROJECT` at version `latest`. Successful
    lookups are cached for 5 minutes.
    """
    if not _SECRET_MANAGER_AVAILABLE:
        return ""
    cached = _secret_manager_cache.get(secret_name)
    if cached and time.time() - cached[0] < _SECRET_MANAGER_TTL_SECONDS:
        return cached[1]
    with _secret_manager_lock:
        # Another thread may have loaded the key while this one waited.
        cached = _secret_manager_cache.get(secret_name)
        now = time.time()
        if cached and now - cached[0] < _SECRET_MANAGER_TTL_SECONDS:
            return cached[1]
        return _load_secret(secret_name, now)


def _load_secret(secret_name: str, now: float) -> str:
    """Reads `secret_name` from Secret Manager and caches a usable key."""
    project = get_settings().google_cloud_project
    if not secret_name.startswith("projects/"):
        if not project:
            logger.error(
                "GOOGLE_CLOUD_PROJECT not set; cannot resolve short secret "
                "name %r",
                secret_name,
            )
            return ""
        full_name = f"projects/{project}/secrets/{secret_name}/versions/latest"
    else:
        full_name = secret_name
    try:
        client = secretmanager.SecretManagerServiceClient()
        response = client.access_secret_version(
            request={"name": full_name},
            timeout=_SECRET_MANAGER_TIMEOUT_SECONDS,
        )
        key = response.payload.data.decode("utf-8").strip()
        if not key:
            return ""
        if key.startswith(("[", '"')):
            logger.error(
                "Secret %s holds a legacy JSON array of keys; re-run "
                "./deploy.sh --bootstrap-secrets to store the bare key",
                full_name,
            )
            return ""
        _secret_manager_cache[secret_name] = (now, key)
        logger.info("Loaded the Gemini API key from %s", full_name)
        return key
    except Exception as e:
        logger.error("Failed to load secret %s: %s", full_name, e)
        return ""


def get_gemini_api_key() -> str:
    """Return the configured Gemini API key, or an empty string if unavailable.

    Resolves `GEMINI_API_KEY_SECRET` through Secret Manager when set, and falls
    back to `gemini.api_key` in `config.json` for local development. Placeholder
    strings (`REPLACE_ME*`, `DEPRECATED*`) are treated as unconfigured.
    """
    secret = get_settings().gemini_api_key_secret
    if secret:
        key = _fetch_key_from_secret_manager(secret)
        if key:
            return key
        logger.warning(
            "GEMINI_API_KEY_SECRET set but returned no key; falling back "
            "to config"
        )

    gemini_cfg = load_config().get("gemini")
    raw_key = (
        gemini_cfg.get("api_key", "") if isinstance(gemini_cfg, dict) else ""
    )
    config_key = raw_key.strip() if isinstance(raw_key, str) else ""
    if not config_key or config_key.startswith(("DEPRECATED", "REPLACE_ME")):
        return ""
    return config_key
