#!/usr/bin/env python3
# Copyright 2024 Google LLC
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
import time
from datetime import datetime
from pathlib import Path
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
    return requests.get(url, headers=headers, timeout=15)


def _bootstrap_config_from_url() -> None:
    """If CONFIG_URL is set, fetch the file once at startup and save
    it as config.json so the existing load_config() path finds it. This makes
    the agent compatible with the bucket-driven config model (BRAND_CONFIG_URL +
    CONFIG_URL) without rewriting the upstream loader.
    """
    url = os.environ.get("CONFIG_URL", "").strip()
    if not url:
        return
    config_path = AGENT_ROOT / "config.json"
    try:
        r = _fetch_gcs_url(url)
        r.raise_for_status()
        config_path.write_text(r.text)
        logger.info("CONFIG_URL fetched %d bytes from %s", len(r.text), url)
    except Exception as e:
        logger.error("CONFIG_URL fetch failed (%s): %s", url, e)


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
        with open(config_path, 'r') as f:
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

    config = load_config()
    gemini_config = config.get("gemini", {})
    keys = gemini_config.get("api_keys", [])
    if not keys:
        single_key = gemini_config.get("api_key", "")
        if single_key and not single_key.startswith("DEPRECATED"):
            logger.warning("Using deprecated scalar gemini.api_key; migrate to api_keys[] or Secret Manager")
            keys = [single_key]
    return keys


def get_query_param_key() -> str:
    """Get the secret key for query param overrides from config."""
    config = load_config()
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
