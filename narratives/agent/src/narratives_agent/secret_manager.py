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
"""Google Cloud Secret Manager client and cached secret resolution.

Provides centralized access to Secret Manager secrets (`GEMINI_API_KEY_SECRET`,
`DC_API_KEY_SECRET`, and `TRANSCRIPT_HMAC_SECRET_NAME`). Secrets may be named by
short secret ID (resolved against `GOOGLE_CLOUD_PROJECT` at `latest`) or by full
resource path (`projects/<proj>/secrets/<name>/versions/<v>`).

Reuses a single lazy client singleton across lookups to share gRPC channels, and
provides thread-safe in-memory caching and test resets.
"""

import logging
import threading
import time

from google.cloud.secretmanager import SecretManagerServiceClient

from narratives_agent.settings import get_settings

logger = logging.getLogger(__name__)

_SECRET_MANAGER_TIMEOUT_SECONDS = 10.0
_SECRET_MANAGER_DEFAULT_TTL_SECONDS = 300.0
_SECRET_MANAGER_DEFAULT_NEGATIVE_TTL_SECONDS = 30.0

_secret_client: SecretManagerServiceClient | None = None
_secret_manager_lock = threading.RLock()
_secret_manager_cache: dict[str, tuple[float, str]] = {}


def _get_secret_client() -> SecretManagerServiceClient:
    """Returns the shared Secret Manager client, initializing it lazily."""
    global _secret_client
    if _secret_client is not None:
        return _secret_client
    with _secret_manager_lock:
        if _secret_client is None:
            _secret_client = SecretManagerServiceClient()
        return _secret_client


def reset_secret_manager_client() -> None:
    """Resets the cached Secret Manager client and cache (for testing)."""
    global _secret_client
    with _secret_manager_lock:
        _secret_client = None
        _secret_manager_cache.clear()


def _normalize_secret_resource_name(secret_name: str, env_var: str) -> str:
    """Normalizes `secret_name` to a versioned Secret Manager resource name."""
    normalized = secret_name.strip().rstrip("/")
    if not normalized:
        return ""
    project = get_settings().google_cloud_project
    if not normalized.startswith("projects/"):
        if not project:
            logger.error(
                "GOOGLE_CLOUD_PROJECT not set; cannot resolve short secret "
                "name in %s",
                env_var,
            )
            return ""
        return f"projects/{project}/secrets/{normalized}/versions/latest"
    if "/versions/" not in normalized:
        return f"{normalized}/versions/latest"
    return normalized


def _fetch_secret(secret_name: str, env_var: str) -> str:
    """Reads a secret payload from Secret Manager.

    Args:
        secret_name: Short secret ID (resolved against `GOOGLE_CLOUD_PROJECT` at
            `latest`) or full `projects/...` resource path.
        env_var: The name of the environment variable, used in log messages.

    Returns:
        The stripped UTF-8 secret payload, or an empty string on failure.
    """
    full_name = _normalize_secret_resource_name(secret_name, env_var)
    if not full_name:
        return ""
    try:
        client = _get_secret_client()
        response = client.access_secret_version(
            request={"name": full_name},
            timeout=_SECRET_MANAGER_TIMEOUT_SECONDS,
        )
        raw_payload: bytes = response.payload.data
        key = raw_payload.decode("utf-8").strip()
        if not key:
            return ""
        logger.info("Loaded %s from Secret Manager", env_var)
        return key
    except Exception as e:
        logger.error(
            "Failed to load %s from Secret Manager (%s)",
            env_var,
            type(e).__name__,
        )
        return ""


def fetch_secret_with_ttl(
    secret_name: str,
    env_var: str,
    ttl_seconds: float = _SECRET_MANAGER_DEFAULT_TTL_SECONDS,
    negative_ttl_seconds: float = _SECRET_MANAGER_DEFAULT_NEGATIVE_TTL_SECONDS,
) -> str:
    """Fetches a secret from Secret Manager with time-bounded in-memory caching.

    Multiple concurrent requests for the same secret share a single lookup.
    Cached values expire after `ttl_seconds` on success, or
    `negative_ttl_seconds` on failure (empty string) to prevent hammering Secret
    Manager while allowing quick recovery from transient errors.

    Args:
        secret_name: Short secret ID or full resource path.
        env_var: Name of the environment variable (for log messages).
        ttl_seconds: Seconds to retain successful lookups before refetching.
        negative_ttl_seconds: Seconds to retain failed lookups before retrying.

    Returns:
        The secret payload string, or an empty string on failure.
    """
    now = time.time()
    cached = _secret_manager_cache.get(secret_name)
    if cached:
        active_ttl = ttl_seconds if cached[1] else negative_ttl_seconds
        if now - cached[0] < active_ttl:
            return cached[1]
    with _secret_manager_lock:
        cached = _secret_manager_cache.get(secret_name)
        now = time.time()
        if cached:
            active_ttl = ttl_seconds if cached[1] else negative_ttl_seconds
            if now - cached[0] < active_ttl:
                return cached[1]
        key = _fetch_secret(secret_name, env_var)
        _secret_manager_cache[secret_name] = (now, key)
        return key
