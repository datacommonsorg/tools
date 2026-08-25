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
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from zoneinfo import ZoneInfo

import requests

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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


# Agent package root (the `agent/` dir). Config and logs live here — this
# module is `agent/src/config.py`, so the root is two levels up. Keeps
# config.json / logs at the same on-disk location as before the src/ split.
AGENT_ROOT = Path(__file__).resolve().parent.parent

# Backend config cache
_config_cache = None
_config_mtime = 0

# Prompt slots the workflows read out of config["prompts"]. Bodies are authored
# as `prompts/<slot>.md` and land beside agent-config.json in the config bucket.
# `follow_up` is the only slot with an in-code default
# (DEFAULT_FOLLOW_UP_PROMPT), so a failed fetch there degrades to that rather
# than to no system instruction at all.
PROMPT_SLOTS = ("mcp", "kb", "synthesis", "follow_up")

# Authoring notes in the .md files must not reach Gemini.
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
    # requests then guesses the encoding from the bytes. Every file in the config
    # bucket is UTF-8 by contract, and the prompts carry currency symbols, arrows
    # and em-dashes, so a wrong guess silently corrupts the text sent to Gemini.
    response.encoding = "utf-8"
    return response


def _fetch_prompt_bodies(config_url: str) -> dict:
    """Fetches ``prompts/<slot>.md`` from the config bucket.

    The base is derived from ``CONFIG_URL`` rather than ``BRAND_CONFIG_URL`` so
    the prompts always come from the same bucket as the config they belong to,
    even if the two ever disagree.

    A slot that 404s or errors is skipped with a warning instead of failing
    startup. An absent prompt leaves that phase with no system instruction, which
    is how the agent behaved before the files were wired up — so a partial fetch
    degrades to the old behaviour rather than taking the agent down.
    """
    # Split the parsed path, not the raw string: a query with a slash in it
    # (``?prefix=a/b``) would otherwise be split mid-query and yield a nonsense
    # base. Query and fragment are dropped because they address the config
    # object, not the prompt objects — a `generation` or a signed-URL signature
    # is per-object and would 403 if carried across. Reading a private bucket
    # goes through the metadata token in _fetch_gcs_url, so nothing here depends
    # on the query surviving.
    parsed = urlparse(config_url)
    base_path = parsed.path.rsplit("/", 1)[0]
    prompts = {}
    for slot in PROMPT_SLOTS:
        prompt_url = urlunparse(
            parsed._replace(
                path=f"{base_path}/prompts/{slot}.md", query="", fragment=""
            )
        )
        try:
            response = _fetch_gcs_url(prompt_url)
            response.raise_for_status()
            # Strip HTML comments so the .md files can carry authoring notes —
            # provenance, "keep in sync with X" reminders — without those notes
            # reaching Gemini as part of the system instruction.
            body = _HTML_COMMENT_RE.sub("", response.text).strip()
        except Exception as e:
            logger.warning("Prompt %r fetch failed (%s): %s", slot, prompt_url, e)
            continue
        if not body:
            logger.warning(
                "Prompt %r at %s is empty; leaving the slot unset", slot, prompt_url
            )
            continue
        prompts[slot] = body
        logger.info("Prompt %r loaded: %d bytes", slot, len(body))
    return prompts


def _bootstrap_config_from_url() -> None:
    """If CONFIG_URL is set, fetch the file once at startup and save
    it as config.json so the existing load_config() path finds it. This makes
    the agent compatible with the bucket-driven config model (BRAND_CONFIG_URL +
    CONFIG_URL) without rewriting the upstream loader.

    The prompt bodies are merged in here. ``config/prompts/*.md`` is the
    authoring format, but the workflows only ever read ``config["prompts"]`` and
    nothing populated it — so the MCP tool loop, the KB phase and synthesis all
    ran with an empty system instruction while the .md files sat unread in the
    bucket. An inline ``prompts`` slot in agent-config.json still wins, as the
    schema documents.
    """
    url = os.environ.get("CONFIG_URL", "").strip()
    if not url:
        return
    config_path = AGENT_ROOT / "config.json"
    try:
        response = _fetch_gcs_url(url)
        response.raise_for_status()
        raw = response.text
        logger.info("CONFIG_URL fetched %d bytes from %s", len(raw), url)
    except Exception as e:
        logger.error("CONFIG_URL fetch failed (%s): %s", url, e)
        return

    try:
        config = json.loads(raw)
    except json.JSONDecodeError as e:
        # Write it through unmodified so the failure surfaces at load_config()
        # exactly as it did before, rather than becoming a silent no-config.
        logger.error(
            "CONFIG_URL is not valid JSON (%s); writing through unmodified", e
        )
        config_path.write_text(raw, encoding="utf-8")
        return

    if not isinstance(config, dict):
        logger.error(
            "CONFIG_URL did not contain a JSON object; writing through unmodified"
        )
        config_path.write_text(raw, encoding="utf-8")
        return

    prompts = _fetch_prompt_bodies(url)
    inline = config.get("prompts")
    if isinstance(inline, dict):
        for slot, body in inline.items():
            if isinstance(body, str) and body.strip():
                logger.info("Prompt %r overridden inline by agent-config.json", slot)
                prompts[slot] = body
    if prompts:
        config["prompts"] = prompts

    missing = [slot for slot in PROMPT_SLOTS if slot not in prompts]
    if missing:
        logger.warning(
            "No prompt body for %s; only follow_up has an in-code default, so the "
            "rest of those phases run with no system instruction",
            missing,
        )

    config_path.write_text(json.dumps(config), encoding="utf-8")


def load_config() -> dict:
    """Load configuration from config.json file."""
    global _config_cache, _config_mtime

    config_path = AGENT_ROOT / 'config.json'

    if not config_path.exists():
        logger.warning(f"Config file not found at {config_path}")
        return {}

    # Check if file was modified
    current_mtime = config_path.stat().st_mtime
    if _config_cache is not None and current_mtime == _config_mtime:
        return _config_cache

    try:
        # Pinned to match the encoding _bootstrap_config_from_url writes with;
        # the platform default would decode a non-ASCII config wrongly on Windows.
        with config_path.open(encoding='utf-8') as f:
            _config_cache = json.load(f)
            _config_mtime = current_mtime
            logger.info("Config loaded/reloaded from config.json")
            return _config_cache
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return {}


def get_current_datetime_ist() -> str:
    """Get current date/time formatted for the configured TIMEZONE.

    The TIMEZONE env var controls the
    zone (e.g. "Asia/Kolkata", "America/Los_Angeles"); the function name and the
    "{{CURRENT_DATETIME}}" placeholder are preserved so prompt templates don't
    need to change. The label suffix ("IST", "PT", ...) is derived from the zone
    abbreviation at runtime.
    """
    tz_name = os.environ.get("TIMEZONE", "UTC")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        logger.warning(f"Unknown TIMEZONE={tz_name!r}; falling back to UTC")
        tz = ZoneInfo("UTC")
    now = datetime.now(tz)
    return now.strftime("%A, %B %d, %Y at %I:%M %p ") + now.strftime("%Z")


def inject_datetime(prompt: str) -> str:
    """Replace {{CURRENT_DATETIME}} placeholder with the configured-timezone datetime."""
    return prompt.replace('{{CURRENT_DATETIME}}', get_current_datetime_ist())


# Secret Manager lookups are cached so a burst of requests doesn't re-fetch the
# key list on every call.
_SECRET_MANAGER_CACHE: dict[str, tuple[float, list[str]]] = {}
_SECRET_MANAGER_TTL_SECONDS = 300


def _fetch_keys_from_secret_manager(secret_name: str) -> list[str]:
    """Load a JSON-encoded key array from Secret Manager.

    secret_name is either "projects/<proj>/secrets/<name>/versions/<v>" (full
    resource name) or just "<name>" (resolved against GOOGLE_CLOUD_PROJECT, latest
    version). Cached for 5 minutes to avoid hammering Secret Manager on each call.
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
            logger.error("GOOGLE_CLOUD_PROJECT not set; cannot resolve short secret name %r", secret_name)
            return []
        full_name = f"projects/{project}/secrets/{secret_name}/versions/latest"
    else:
        full_name = secret_name
    try:
        client = secretmanager.SecretManagerServiceClient()
        response = client.access_secret_version(request={"name": full_name})
        payload = response.payload.data.decode("utf-8")
        keys = json.loads(payload)
        if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
            logger.error("Secret %s did not contain a JSON array of strings", full_name)
            return []
        _SECRET_MANAGER_CACHE[secret_name] = (now, keys)
        logger.info("Loaded %d keys from Secret Manager (%s)", len(keys), full_name)
        return keys
    except Exception as e:
        logger.error("Failed to load secret %s: %s", full_name, e)
        return []


def get_api_keys(demo_mode: bool = False) -> list:
    """Load API keys from Secret Manager (preferred) or local config (dev only).

    A deployed instance sets `GEMINI_API_KEYS_SECRET` (and optionally
    `GEMINI_DEMO_API_KEYS_SECRET`) and the value is resolved via Secret Manager.
    `agent-config.schema.json` defines no field for keys, so a config served from
    the instance's config bucket cannot carry them.

    The on-disk `config.json` `gemini.api_keys` array — and the legacy scalar
    `gemini.api_key` — remain readable for **local development only**, where the
    file is uncommitted. Both paths log a warning, so a deployment that is
    accidentally reading keys from config is visible in the logs.

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
                logger.info(f"Using demo API keys pool from Secret Manager ({len(keys)} keys)")
                return keys
        config = load_config()
        demo_keys = config.get("gemini", {}).get("demo_api_keys", [])
        if demo_keys:
            logger.info(f"Using demo API keys pool from config ({len(demo_keys)} keys)")
        else:
            logger.error("Demo mode requested but no demo_api_keys configured - will fail (no fallback to regular keys)")
        return demo_keys

    secret = os.environ.get("GEMINI_API_KEYS_SECRET", "")
    if secret:
        keys = _fetch_keys_from_secret_manager(secret)
        if keys:
            return keys
        logger.warning("GEMINI_API_KEYS_SECRET set but returned no keys; falling back to config")

    # Local-development fallback. These fields are not in
    # agent-config.schema.json, so reaching here in a deployed instance means the
    # keys came from somewhere they should not have — warn loudly rather than
    # silently succeeding.
    config = load_config()
    gemini_config = config.get("gemini", {})
    keys = gemini_config.get("api_keys", [])
    if keys:
        logger.warning(
            "Read %d Gemini key(s) from config rather than Secret Manager. This path is "
            "for local development only; set GEMINI_API_KEYS_SECRET for a deployed instance.",
            len(keys),
        )
    if not keys:
        single_key = gemini_config.get("api_key", "")
        if single_key and not single_key.startswith("DEPRECATED"):
            logger.warning(
                "Using deprecated scalar gemini.api_key from config; migrate to Secret "
                "Manager via GEMINI_API_KEYS_SECRET."
            )
            keys = [single_key]
    return keys


def get_query_param_key() -> str:
    """Get the secret key for query param overrides from config."""
    config = load_config()
    # TODO: replace the instance-specific "AISummit2026" fallback with a more
    # generic default, or require query_param_key to be configured explicitly.
    return config.get("query_param_key", "AISummit2026")  # Default fallback


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
        effective["gemini"]["kb_model"] = query_params["model"]

    # Knowledge base toggle
    if query_params.get("kb_enabled"):
        enabled = query_params["kb_enabled"].lower() == "true"
        effective["knowledge_base"]["enabled"] = enabled

    # MCP thinking budget override
    if query_params.get("mcp_thinking"):
        effective["thinking"]["mcp_level"] = query_params["mcp_thinking"]

    # Synthesis thinking budget override
    if query_params.get("synthesis_thinking"):
        effective["thinking"]["synthesis_level"] = query_params["synthesis_thinking"]

    return effective
