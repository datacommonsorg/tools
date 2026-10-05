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

import logging
from urllib.parse import urlparse

from narratives_agent.settings import get_settings

logger = logging.getLogger(__name__)


# Hosts DC_API_KEY may be sent to.
#
# Public Data Commons authenticates with an API key. The endpoint is
# configuration-driven and that configuration is fetched from a GCS bucket, so
# without this allowlist an edit to branding/agent config could point the agent
# at an arbitrary host and hand it our key. Restricting the header to known
# Data Commons hosts keeps a config change from becoming a credential leak.
_API_KEY_HOSTS = frozenset({"api.datacommons.org", "datacommons.org"})


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
        key = settings.dc_api_key
        if key:
            headers["X-API-Key"] = key
        else:
            logger.warning(
                "%s expects an API key but DC_API_KEY is unset; requests will "
                "be rejected.",
                parsed.hostname,
            )
