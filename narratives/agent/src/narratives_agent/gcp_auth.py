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
"""Credentials for Data Commons data-plane and Google Cloud API calls.

`attach_auth` picks the credential by target host: the `DC_API_KEY` API key
for public Data Commons hosts, and nothing for any other host.

`get_adc_auth_headers` resolves and refreshes Google Cloud Application Default
Credentials (`cloud-platform` scope) off the event loop and returns the
`Authorization` Bearer header (plus `x-goog-user-project` when a quota project
is configured).
"""

import asyncio
import functools
import logging
import threading
from urllib.parse import urlparse

import google.auth
import requests
from google.auth.credentials import Credentials
from google.auth.transport.requests import Request

from narratives_agent.secret_manager import fetch_secret_with_ttl
from narratives_agent.settings import (
    DC_API_KEY_SECRET_ENV,
    get_settings,
)

logger = logging.getLogger(__name__)

_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
_ADC_LOCK = threading.Lock()
_adc_credentials: Credentials | None = None


# Hosts DC_API_KEY may be sent to.
#
# Public Data Commons authenticates with an API key. The endpoint is
# configuration-driven and that configuration is fetched from a GCS bucket, so
# without this allowlist an edit to the agent config could point the agent at
# an arbitrary host and hand it our key. Restricting the header to known Data
# Commons hosts keeps a config change from becoming a credential leak.
_API_KEY_HOSTS = frozenset(
    {
        "api.datacommons.org",
        "autopush.api.datacommons.org",
        "dev.api.datacommons.org",
        "staging.api.datacommons.org",
        "datacommons.org",
    }
)


@functools.cache
def _resolve_dc_api_key() -> str:
    """Returns the Data Commons API key, resolved once per process.

    Resolution order:
    1. `DC_API_KEY` set: returns the configured API key string.
    2. `DC_API_KEY_SECRET` set: loads the key from Secret Manager.
    3. Neither set: returns an empty string.

    Raises:
        RuntimeError: `DC_API_KEY_SECRET` is configured but could not be loaded
            from Secret Manager.
    """
    settings = get_settings()
    if settings.dc_api_key:
        return settings.dc_api_key
    if settings.dc_api_key_secret:
        key = fetch_secret_with_ttl(
            settings.dc_api_key_secret, DC_API_KEY_SECRET_ENV
        )
        if not key:
            raise RuntimeError(
                f"{DC_API_KEY_SECRET_ENV} could not be loaded from "
                "Secret Manager."
            )
        return key
    return ""


def init_dc_api_key() -> None:
    """Resolves and caches the Data Commons API key at server startup."""
    _resolve_dc_api_key()


def reset_dc_api_key() -> None:
    """Makes the next request resolve the Data Commons API key again."""
    _resolve_dc_api_key.cache_clear()


def reset_adc_credentials() -> None:
    """Clears cached Application Default Credentials (for testing)."""
    global _adc_credentials
    with _ADC_LOCK:
        _adc_credentials = None


def _load_adc_credentials() -> Credentials:
    """Loads Application Default Credentials scoped for Google Cloud APIs."""
    credentials, _ = google.auth.default(scopes=[_CLOUD_PLATFORM_SCOPE])
    if not isinstance(credentials, Credentials):
        raise RuntimeError("ADC did not return google.auth Credentials")
    return credentials


def _refresh_adc_credentials(credentials: Credentials) -> None:
    """Refreshes `credentials` synchronously using a scoped session."""
    with requests.Session() as session:
        credentials.refresh(Request(session))  # type: ignore[no-untyped-call]


def _build_adc_auth_headers(credentials: Credentials) -> dict[str, str]:
    """Builds the `Authorization` and optional quota-project headers."""
    token = credentials.token
    if not isinstance(token, str) or not token:
        raise RuntimeError(
            "Application Default Credentials returned no access token"
        )
    headers = {"Authorization": f"Bearer {token}"}
    quota_project = credentials.quota_project_id
    if isinstance(quota_project, str) and quota_project:
        headers["x-goog-user-project"] = quota_project
    return headers


def _resolve_adc_auth_headers_sync() -> dict[str, str]:
    """Resolves and refreshes ADC authentication headers under `_ADC_LOCK`."""
    global _adc_credentials
    with _ADC_LOCK:
        if _adc_credentials is None:
            _adc_credentials = _load_adc_credentials()
        credentials = _adc_credentials
        if not credentials.valid or not credentials.token:
            _refresh_adc_credentials(credentials)
        return _build_adc_auth_headers(credentials)


async def get_adc_auth_headers() -> dict[str, str]:
    """Returns valid ADC request headers without blocking the event loop."""
    credentials = _adc_credentials
    if (
        credentials is not None
        and credentials.valid
        and isinstance(credentials.token, str)
        and credentials.token
    ):
        return _build_adc_auth_headers(credentials)
    return await asyncio.to_thread(_resolve_adc_auth_headers_sync)


def attach_auth(headers: dict[str, str], target_url: str) -> None:
    """Attach whatever credential `target_url` expects.

    Public Data Commons hosts get X-API-Key from DC_API_KEY; any other host
    gets nothing.

    Mutates `headers` in place. No-ops for http:// and for localhost, so a
    co-located sidecar deployment is unaffected.
    """
    settings = get_settings()
    if settings.data_plane_auth.lower() == "off":
        return

    parsed = urlparse(target_url)
    if parsed.scheme != "https":
        return
    if parsed.hostname in ("localhost", "127.0.0.1", "::1"):
        return

    if parsed.hostname in _API_KEY_HOSTS:
        key = _resolve_dc_api_key()
        if key:
            headers["X-API-Key"] = key
        else:
            logger.warning(
                "%s expects an API key but DC_API_KEY is unset; requests will "
                "be rejected.",
                parsed.hostname,
            )
