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

`load_config` returns the active configuration as a frozen `AgentConfig`
(see `config_model.py`), parsed once per load and held in process memory, or
`None` when no configuration could be loaded. The document is read from
`CONFIG_URL` once at startup, from `agent_root/config.json` in local
development (reloaded when the file's modification time changes), or from the
`defaults/` directory shipped with the image.

On every path the default prompt bodies in `defaults/prompts/` are read first,
and the configured prompts (`prompts/<slot>.md` beside `CONFIG_URL`, then
inline `prompts` entries) are layered over them slot by slot. A configured
prompt that is absent or fails to load leaves the default prompt in place.
"""

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

from narratives_agent.config_model import AgentConfig, parse_agent_config
from narratives_agent.settings import get_settings

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
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
        "GEMINI_API_KEY_SECRET will be ignored"
    )


# `_bootstrapped` records that `bootstrap_config_from_url` ran with
# `CONFIG_URL` set. While it is `True`, `load_config` returns
# `_bootstrapped_config` even when that is `None`, so a deployment whose
# configuration failed to load does not silently run on the local file or the
# defaults.
_bootstrapped = False
_bootstrapped_config: AgentConfig | None = None
_config_cache: AgentConfig | None = None
_config_mtime = 0.0
_config_path: Path | None = None
_defaults_config: AgentConfig | None = None
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

# Prompt slots, which the workflows read as the fields of `Prompts` in
# `config_model.py`. Bodies are authored as `prompts/<slot>.md`; default
# versions are found in `defaults/prompts/`, and a deployment's overrides are
# uploaded beside agent-config.json in the config bucket.
PROMPT_SLOTS = ("classify", "mcp", "synthesis", "follow_up")

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def strip_prompt_comments(text: str) -> str:
    """Strips HTML authoring comments and surrounding whitespace."""
    return _HTML_COMMENT_RE.sub("", text).strip()


def _is_gcs_url(url: str) -> bool:
    """Returns whether `url` is an HTTPS URL on `storage.googleapis.com`."""
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (
        hostname == "storage.googleapis.com"
        or hostname.endswith(".storage.googleapis.com")
    )


def _fetch_gcs_url(url: str) -> requests.Response:
    """Fetch from GCS.

    When running in GCP, attach the metadata service-account token so private
    config buckets are readable; falls back to an unauthenticated GET (public
    buckets / local dev) if the metadata server is unavailable.
    """
    headers = {}
    if _is_gcs_url(url):
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

    A slot that fails to fetch, or is empty once its comments are stripped, is
    left out of the result with a warning instead of failing startup. The
    caller layers the result over the default prompts, so that slot keeps the
    default body.
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
                "Prompt %r fetch failed (%s): %s; the default or inline "
                "prompt applies",
                slot,
                prompt_url,
                e,
            )
            continue
        if not body:
            logger.warning(
                "Prompt %r at %s is empty; the default or inline prompt "
                "applies",
                slot,
                prompt_url,
            )
            continue
        prompts[slot] = body
        logger.info(
            "Prompt %r loaded: %d characters from %s",
            slot,
            len(body),
            prompt_url,
        )
    return prompts


def _read_prompt_files(prompts_dir: Path) -> dict[str, str]:
    """Reads `<slot>.md` files from `prompts_dir` and strips HTML comments.

    A file that is unreadable, or empty once its comments are stripped, is
    left out of the result with a warning.
    """
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
        if not body:
            logger.warning("Prompt %r at %s is empty", slot, prompt_path)
            continue
        prompts[slot] = body
        logger.info(
            "Prompt %r read: %d characters from %s",
            slot,
            len(body),
            prompt_path,
        )
    return prompts


def _layer_prompts(
    config: dict[str, Any],
    fetched_prompts: dict[str, str],
    prompts_dir: Path,
) -> None:
    """Sets `config["prompts"]` to the default prompts with overrides applied.

    Precedence per slot, lowest first: the default `<slot>.md` in
    `prompts_dir`, then `fetched_prompts`, then a non-empty string already in
    `config["prompts"]`. The default prompts are read first so that a
    configured prompt that is absent or fails to load degrades to the default
    body, never to an empty slot. An inline key that is not in `PROMPT_SLOTS`
    is dropped with a warning, so a misspelled override is reported rather
    than silently replaced by the default prompt.

    A slot that is still empty after layering means the default file itself is
    missing, unreadable, or empty. That is a packaging defect, so it is logged
    as an error and loading continues with the slots that have a body.

    Args:
        config: The configuration document, updated in place.
        fetched_prompts: Prompt bodies fetched from beside `CONFIG_URL`, keyed
            by slot; empty when there is no `CONFIG_URL`. Every value must be
            a non-empty string, which `_fetch_prompt_bodies` guarantees.
        prompts_dir: The directory holding the default `<slot>.md` files.
    """
    prompts = _read_prompt_files(prompts_dir)
    sources = dict.fromkeys(prompts, "default")
    prompts.update(fetched_prompts)
    sources.update(dict.fromkeys(fetched_prompts, "fetched"))
    inline = config.get("prompts")
    if isinstance(inline, dict):
        for slot, body in inline.items():
            if slot not in PROMPT_SLOTS:
                logger.warning(
                    "Inline prompt slot %r is not one of %s; ignoring it",
                    slot,
                    PROMPT_SLOTS,
                )
                continue
            if isinstance(body, str) and body.strip():
                prompts[slot] = body
                sources[slot] = "inline"
    if prompts:
        config["prompts"] = prompts
    else:
        config.pop("prompts", None)
    logger.info("Prompt sources after layering: %s", sources)
    missing = [slot for slot in PROMPT_SLOTS if slot not in prompts]
    if missing:
        logger.error(
            "No prompt body for %s: the default prompt files under %s are "
            "missing, unreadable, or empty, and no configured prompt covers "
            "these slots",
            missing,
            prompts_dir,
        )


def bootstrap_config_from_url() -> None:
    """Fetches `CONFIG_URL` at startup and caches the parsed configuration.

    Prompt bodies are layered per slot: `defaults/prompts/<slot>.md` first,
    then `<bucket>/prompts/<slot>.md`, then any non-empty inline `prompts`
    entry in `agent-config.json`.

    If the fetch fails or the response is not a JSON object, `None` is cached
    and `load_config()` returns it rather than falling back to the local file
    or the shipped defaults, because `CONFIG_URL` was explicitly configured.
    """
    global _bootstrapped, _bootstrapped_config

    settings = get_settings()
    url = settings.config_url
    if not url:
        _bootstrapped = False
        _bootstrapped_config = None
        return
    _bootstrapped = True
    _bootstrapped_config = None
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
        return

    try:
        config = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(
            "CONFIG_URL is not valid JSON (%s); running without configuration",
            e,
        )
        return

    if not isinstance(config, dict):
        logger.error(
            "CONFIG_URL did not contain a JSON object; running without "
            "configuration"
        )
        return

    _layer_prompts(
        config, _fetch_prompt_bodies(url), settings.defaults_dir / "prompts"
    )
    _bootstrapped_config = parse_agent_config(config)


def _load_config_file(
    config_path: Path, prompts_dir: Path
) -> AgentConfig | None:
    """Loads `config_path` and caches it by path and modification time.

    The default prompts in `prompts_dir` are layered into the document each
    time it is read, so an edit to `config_path` also picks up the current
    default prompt files. Returns `None`, and clears the cache so the next
    call reads the file again, when the file is unreadable or does not hold
    a JSON object.
    """
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
            return None
        _layer_prompts(document, {}, prompts_dir)
        _config_cache = parse_agent_config(document)
        _config_mtime = current_mtime
        _config_path = config_path
        logger.info("Config loaded/reloaded from config.json")
        return _config_cache
    except (OSError, ValueError) as e:
        logger.error("Failed to load config from %s: %s", config_path, e)
        _config_cache = None
        _config_mtime = 0.0
        _config_path = None
        return None


def _load_defaults_config(defaults_dir: Path) -> AgentConfig | None:
    """Loads `agent-config.json` and `prompts/` from `defaults_dir` once.

    The outcome is cached for `defaults_dir` whether or not the file loaded,
    so a missing or unreadable defaults file is reported once rather than on
    every call.
    """
    global _defaults_config, _defaults_dir

    if _defaults_dir == defaults_dir:
        return _defaults_config

    config_path = defaults_dir / "agent-config.json"
    config: AgentConfig | None = None
    try:
        document = json.loads(config_path.read_text(encoding="utf-8"))
        if isinstance(document, dict):
            _layer_prompts(document, {}, defaults_dir / "prompts")
            config = parse_agent_config(document)
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


def load_config() -> AgentConfig | None:
    """Returns the active agent configuration, or `None` if none is loaded.

    Reads from `CONFIG_URL` (startup bootstrap), `agent_root/config.json`
    (local development), or `defaults_dir` (`agent-config.json` and
    `prompts/`), in that order. When `CONFIG_URL` is set, the result of the
    startup fetch is returned even if that fetch failed, and the other
    sources are not consulted. The returned instance is frozen and shared by
    every caller.
    """
    if _bootstrapped:
        return _bootstrapped_config

    settings = get_settings()
    config_path = settings.agent_root / "config.json"
    if config_path.exists():
        return _load_config_file(config_path, settings.defaults_dir / "prompts")
    return _load_defaults_config(settings.defaults_dir)


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


def render_prompt(prompt: str) -> str:
    """Substitute {{CURRENT_DATETIME}} and {{instance.<key>}} into a prompt.

    An {{instance.<key>}} with no matching template_vars entry is left in place
    rather than blanked: a visible placeholder in an answer is a far louder
    failure than a sentence that has silently lost its subject. When no
    configuration is loaded, every {{instance.<key>}} is left in place.
    """
    rendered = prompt.replace("{{CURRENT_DATETIME}}", get_current_datetime())
    config = load_config()
    template_vars = config.template_vars if config is not None else {}
    for key, value in template_vars.items():
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
                "name in GEMINI_API_KEY_SECRET"
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
                "GEMINI_API_KEY_SECRET holds a legacy JSON array of keys; "
                "re-run ./deploy.sh --bootstrap-secrets to store the bare key"
            )
            return ""
        _secret_manager_cache[secret_name] = (now, key)
        logger.info("Loaded the Gemini API key from Secret Manager")
        return key
    except Exception as e:
        logger.error(
            "Failed to load GEMINI_API_KEY_SECRET from Secret Manager (%s)",
            type(e).__name__,
        )
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

    config = load_config()
    config_key = config.gemini.api_key if config is not None else ""
    if not config_key or config_key.startswith(("DEPRECATED", "REPLACE_ME")):
        return ""
    return config_key
