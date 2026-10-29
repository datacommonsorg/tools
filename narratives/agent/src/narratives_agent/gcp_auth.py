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
"""Credentials for calls to the Data Commons data plane.

`attach_auth` picks the credential by target host: the `DC_API_KEY` API key
for public Data Commons hosts, and nothing for any other host.
"""

import functools
import logging
from urllib.parse import urlparse

from narratives_agent.secret_manager import fetch_secret_with_ttl
from narratives_agent.settings import (
    DC_API_KEY_SECRET_ENV,
    get_settings,
)

logger = logging.getLogger(__name__)


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
