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

import json
import logging
import posixpath
import re
import time
from datetime import datetime
from urllib.parse import urlparse, urlunparse
from zoneinfo import ZoneInfo

import requests

from narratives_agent.settings import get_settings

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Model used whenever agent-config.json names none. Read through
# get_gemini_model() rather than repeated inline, because the deployed config
# sets no model at all -- every caller runs on this default, so a caller that
# spells its own default differently silently calls a different model than the
# rest of the pipeline. That is not hypothetical: the chart-suppression check
# defaulted to "gemini-2.0-flash", which the project's API key cannot address
# at all. Every call 404'd, the 404 body carried no `candidates`, the check
# read that as "data found" and charts were never suppressed.
DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"


def get_gemini_model(config: dict, key: str = "mcp_model") -> str:
    """Returns the configured Gemini model for `key`, or the shared default."""
    gemini_cfg = config.get("gemini")
    model = gemini_cfg.get(key) if isinstance(gemini_cfg, dict) else None
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


# Backend config cache
_config_cache = None
_config_mtime = 0

# Secret Manager lookup cache and TTL (seconds)
_SECRET_MANAGER_TTL_SECONDS = 300
_secret_manager_cache: dict[str, tuple[float, str]] = {}

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
    partial fetch degrades to the old behavior rather than taking the agent
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
    settings = get_settings()
    url = settings.config_url
    if not url:
        return
    config_path = settings.agent_root / "config.json"
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

    config_path = get_settings().agent_root / "config.json"

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
    now = time.time()
    if cached and now - cached[0] < _SECRET_MANAGER_TTL_SECONDS:
        return cached[1]
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
        response = client.access_secret_version(request={"name": full_name})
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
