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

import copy
import json
import logging
import os
import posixpath
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from zoneinfo import ZoneInfo

import requests

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Model used whenever config.json names none. Read through get_gemini_model()
# rather than repeated inline, because the deployed config sets no model at all
# -- every caller runs on this default, so a caller that spells its own default
# differently silently calls a different model than the rest of the pipeline.
# That is not hypothetical: the chart-suppression check defaulted to
# "gemini-2.0-flash", which the project's API key cannot address at all. Every
# call 404'd, the 404 body carried no `candidates`, the check read that as
# "data found" and charts were never suppressed.
DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"


def get_gemini_model(config: dict, key: str = "mcp_model") -> str:
    """Returns the configured Gemini model for `key`, or the shared default."""
    return config.get("gemini", {}).get(key) or DEFAULT_GEMINI_MODEL


# Secret Manager client for runtime key loading (optional import).
try:
    from google.cloud import secretmanager

    _SECRET_MANAGER_AVAILABLE = True
except ImportError:
    _SECRET_MANAGER_AVAILABLE = False
    logger.warning(
        "google-cloud-secret-manager not installed; "
        "GEMINI_API_KEYS_SECRET will be ignored"
    )


# The `agent/` directory, where config.json, logs, and the staged SPA live.
# Set via `AGENT_ROOT` in the container (`Dockerfile`); falls back to three
# levels above `agent/src/narratives_agent/config.py` in a local checkout.
# Anything resolving a path against the agent directory should read this
# rather than counting parents of its own `__file__`.
AGENT_ROOT = Path(
    os.environ.get("AGENT_ROOT") or Path(__file__).resolve().parents[2]
)

# Backend config cache
_config_cache = None
_config_mtime = 0

# Prompt slots the workflows read out of config["prompts"]. Bodies are authored
# as `prompts/<slot>.md` and land beside agent-config.json in the config bucket.
# `follow_up` is the only slot with an in-code default
# (DEFAULT_FOLLOW_UP_PROMPT), so a failed fetch there degrades to that rather
# than to no system instruction.
PROMPT_SLOTS = ("mcp", "synthesis", "follow_up")

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


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


def _fetch_prompt_bodies(config_url: str) -> dict:
    """Fetch `prompts/<slot>.md` from the config bucket, beside
    agent-config.json.

    The base is derived from CONFIG_URL rather than read from BRAND_CONFIG_URL
    so the prompts always come from the same bucket as the config they belong
    to, even if the two env vars ever disagree.

    A slot that 404s or errors is skipped with a warning instead of failing
    startup: an absent prompt leaves that phase with no system instruction,
    which is exactly how the agent behaved before the files were wired up, so a
    partial fetch degrades to the old behaviour rather than taking the agent
    down.
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
            body = _HTML_COMMENT_RE.sub("", r.text).strip()
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


def _bootstrap_config_from_url() -> None:
    """Fetch CONFIG_URL at startup and write the merged config to config.json.

    Merges prompt bodies from `<bucket>/prompts/<slot>.md` into
    `config["prompts"]` before writing the file, while allowing non-empty inline
    `prompts` entries in `agent-config.json` to take precedence.
    """
    url = os.environ.get("CONFIG_URL", "").strip()
    if not url:
        return
    config_path = AGENT_ROOT / "config.json"
    try:
        r = _fetch_gcs_url(url)
        r.raise_for_status()
        raw = r.text
        logger.info("CONFIG_URL fetched %d bytes from %s", len(raw), url)
    except Exception as e:
        logger.error("CONFIG_URL fetch failed (%s): %s", url, e)
        return

    try:
        config = json.loads(raw)
    except json.JSONDecodeError as e:
        # Write it through unmodified so the failure surfaces at load_config()
        # exactly as it did before, rather than turning into a silent no-config.
        logger.error(
            "CONFIG_URL is not valid JSON (%s); writing through unmodified", e
        )
        config_path.write_text(raw, encoding="utf-8")
        return

    if not isinstance(config, dict):
        logger.error(
            "CONFIG_URL did not contain a JSON object; writing through "
            "unmodified"
        )
        config_path.write_text(raw, encoding="utf-8")
        return

    prompts = _fetch_prompt_bodies(url)
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
    missing = [slot for slot in PROMPT_SLOTS if slot not in prompts]
    if missing:
        logger.warning(
            "No prompt body for %s; only follow_up has an in-code default, "
            "so the rest of those phases run with no system instruction",
            missing,
        )

    config_path.write_text(json.dumps(config), encoding="utf-8")


def load_config() -> dict:
    """Load configuration from config.json file."""
    global _config_cache, _config_mtime

    config_path = AGENT_ROOT / "config.json"

    if not config_path.exists():
        logger.warning(f"Config file not found at {config_path}")
        return {}

    # Check if file was modified
    current_mtime = config_path.stat().st_mtime
    if _config_cache is not None and current_mtime == _config_mtime:
        return _config_cache

    try:
        # config.json is UTF-8 on both sides: _bootstrap_config_from_url pins
        # the same encoding when it writes. A config carrying non-ASCII --
        # prompt text with ₹ or an em-dash, an instance name -- would otherwise
        # decode by the platform locale and come back corrupted.
        with open(config_path, encoding="utf-8") as f:
            _config_cache = json.load(f)
            _config_mtime = current_mtime
            logger.info("Config loaded/reloaded from config.json")
            return _config_cache
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return {}


def get_current_datetime() -> str:
    """Get the current date and time in the configured timezone.

    The TIMEZONE environment variable selects the zone (for example
    "Asia/Kolkata" or "America/Los_Angeles"), and the trailing label
    ("IST", "PT", ...) is the zone abbreviation resolved at runtime.
    Falls back to UTC when TIMEZONE names a zone that cannot be resolved.
    """
    tz_name = os.environ.get("TIMEZONE", "UTC")
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


_SECRET_MANAGER_CACHE: dict[str, tuple[float, list[str]]] = {}
_SECRET_MANAGER_TTL_SECONDS = 300


def _fetch_keys_from_secret_manager(secret_name: str) -> list[str]:
    """Load a JSON-encoded key array from Secret Manager.

    secret_name is either "projects/<proj>/secrets/<name>/versions/<v>" (full
    resource name) or just "<name>" (resolved against GOOGLE_CLOUD_PROJECT,
    latest version). Cached for 5 minutes to avoid hammering Secret Manager on
    each call.
    """
    if not _SECRET_MANAGER_AVAILABLE:
        return []
    cached = _SECRET_MANAGER_CACHE.get(secret_name)
    now = time.time()
    if cached and now - cached[0] < _SECRET_MANAGER_TTL_SECONDS:
        return cached[1]
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    if not secret_name.startswith("projects/"):
        if not project:
            logger.error(
                "GOOGLE_CLOUD_PROJECT not set; cannot resolve short secret "
                "name %r",
                secret_name,
            )
            return []
        full_name = f"projects/{project}/secrets/{secret_name}/versions/latest"
    else:
        full_name = secret_name
    try:
        client = secretmanager.SecretManagerServiceClient()
        response = client.access_secret_version(request={"name": full_name})
        payload = response.payload.data.decode("utf-8")
        keys = json.loads(payload)
        if not isinstance(keys, list) or not all(
            isinstance(k, str) for k in keys
        ):
            logger.error(
                "Secret %s did not contain a JSON array of strings", full_name
            )
            return []
        _SECRET_MANAGER_CACHE[secret_name] = (now, keys)
        logger.info(
            "Loaded %d keys from Secret Manager (%s)", len(keys), full_name
        )
        return keys
    except Exception as e:
        logger.error("Failed to load secret %s: %s", full_name, e)
        return []


def get_api_keys(demo_mode: bool = False) -> list:
    """Load API keys from Secret Manager (preferred) or config (fallback).

    In `prod` mode the agent reads `GEMINI_API_KEYS_SECRET` (and
    optionally `GEMINI_DEMO_API_KEYS_SECRET`) and resolves the value via Secret
    Manager. The on-disk config.json `gemini.api_keys` array is honoured only as
    a dev fallback. The legacy scalar `gemini.api_key` is rejected outright.

    Args:
        demo_mode: If True, returns demo_api_keys for internal demo usage.
                   Demo keys are reserved for events/demos and won't be
                   affected by regular traffic rate limits.
                   If demo_mode=True but no demo keys configured, returns
                   empty list (will cause API call to fail - NO fallback).
    """
    if demo_mode:
        demo_secret = os.environ.get("GEMINI_DEMO_API_KEYS_SECRET", "")
        if demo_secret:
            keys = _fetch_keys_from_secret_manager(demo_secret)
            if keys:
                logger.info(
                    "Using demo API keys pool from Secret Manager "
                    f"({len(keys)} keys)"
                )
                return keys
        config = load_config()
        demo_keys = config.get("gemini", {}).get("demo_api_keys", [])
        if demo_keys:
            logger.info(
                f"Using demo API keys pool from config ({len(demo_keys)} keys)"
            )
        else:
            logger.error(
                "Demo mode requested but no demo_api_keys configured - will "
                "fail (no fallback to regular keys)"
            )
        return demo_keys

    secret = os.environ.get("GEMINI_API_KEYS_SECRET", "")
    if secret:
        keys = _fetch_keys_from_secret_manager(secret)
        if keys:
            return keys
        logger.warning(
            "GEMINI_API_KEYS_SECRET set but returned no keys; falling back "
            "to config"
        )

    config = load_config()
    gemini_config = config.get("gemini", {})
    keys = gemini_config.get("api_keys", [])
    if not keys:
        single_key = gemini_config.get("api_key", "")
        if single_key and not single_key.startswith("DEPRECATED"):
            logger.warning(
                "Using deprecated scalar gemini.api_key; migrate to "
                "api_keys[] or Secret Manager"
            )
            keys = [single_key]
    return keys


def get_query_param_key() -> str:
    """The secret gating ?key= overrides and demo mode, or "" if unconfigured.

    Returns empty rather than a default: this repo is public, so any literal
    here would be a published credential for every instance that did not
    override it. Callers must treat "" as "no override key configured" and
    reject every supplied key -- see routes/chat.py.
    """
    key = load_config().get("query_param_key", "")
    if not isinstance(key, str):
        return ""
    return key.strip()


def apply_query_overrides(config: dict, query_params: dict) -> dict:
    """Apply query parameter overrides to config.

    Returns a new config dict with overrides applied (does not modify original).
    """
    if not query_params:
        return config

    # Deep copy to avoid modifying cached config
    effective = copy.deepcopy(config)

    # Model override
    if query_params.get("model"):
        effective["gemini"]["mcp_model"] = query_params["model"]

    # MCP thinking budget override
    if query_params.get("mcp_thinking"):
        effective["thinking"]["mcp_level"] = query_params["mcp_thinking"]

    # Synthesis thinking budget override
    if query_params.get("synthesis_thinking"):
        effective["thinking"]["synthesis_level"] = query_params[
            "synthesis_thinking"
        ]

    return effective
