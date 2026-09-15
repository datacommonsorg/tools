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
"""Google-signed ID tokens for calling an IAM-gated Cloud Run service.

Once the data plane moved out of this container, every call to it became a
cross-service request. If that service is IAM-gated (rather than only
network-restricted by ingress=internal) the caller must present an ID token
minted for the target's audience.

Attaching a token the backend does not require is harmless -- it is simply
valid-but-unneeded -- so this is applied whenever the target is a remote HTTPS
URL, and is a no-op for localhost and when running off GCP. That keeps one code
path for both the ingress=internal and the IAM-gated deployments.
"""

import logging
import os
import time
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

_METADATA_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/"
    "service-accounts/default/identity"
)

# audience -> {"token": str, "exp": float}. Tokens are valid for an hour; we
# refresh at 50 minutes so a request never carries one that expires mid-flight.
_TOKEN_CACHE: dict = {}
_TOKEN_TTL_SECONDS = 50 * 60


def _audience_for(url: str) -> str:
    """Cloud Run expects the audience to be the service's origin, not the path."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def get_id_token(audience: str) -> str:
    """Fetch a cached ID token for `audience` from the metadata server.

    Returns "" when the metadata server is unreachable, which is the normal
    case for local development. Callers treat that as "send no Authorization
    header" rather than as an error, so a developer running against a public
    backend is unaffected.
    """
    cached = _TOKEN_CACHE.get(audience)
    if cached and cached["exp"] > time.time():
        return cached["token"]

    try:
        response = requests.get(
            _METADATA_TOKEN_URL,
            params={"audience": audience, "format": "full"},
            headers={"Metadata-Flavor": "Google"},
            timeout=5,
        )
        response.raise_for_status()
        token = response.text.strip()
    except Exception as e:  # pylint: disable=broad-except
        logger.debug("ID token fetch failed for %s (normal if local): %s", audience, e)
        return ""

    _TOKEN_CACHE[audience] = {"token": token, "exp": time.time() + _TOKEN_TTL_SECONDS}
    logger.info("Minted ID token for audience %s", audience)
    return token


# Hosts DC_API_KEY may be sent to.
#
# Public Data Commons authenticates with an API key rather than a Google ID
# token. The endpoint is configuration-driven and that configuration is fetched
# from a GCS bucket, so without this allowlist an edit to branding/agent config
# could point the agent at an arbitrary host and hand it our key. Restricting
# the header to known Data Commons hosts keeps a config change from becoming a
# credential leak.
_API_KEY_HOSTS = frozenset({"api.datacommons.org", "datacommons.org"})


def attach_auth(headers: dict, target_url: str) -> None:
    """Attach whatever credential `target_url` expects.

    Two backends, two mechanisms, chosen by host rather than by a backend flag:

      * public Data Commons -> X-API-Key from DC_API_KEY
      * a private Cloud Run data plane (CDC or DCP) -> a Google-signed ID token

    Mutates `headers` in place. No-ops for http:// and for localhost, so a
    co-located sidecar deployment is unaffected, and no-ops off GCP where the
    metadata server is unreachable.
    """
    if os.environ.get("DATA_PLANE_AUTH", "auto").lower() == "off":
        return

    parsed = urlparse(target_url)
    if parsed.scheme != "https":
        return
    if parsed.hostname in ("localhost", "127.0.0.1", "::1"):
        return

    # Public Data Commons: API key, never an ID token -- our service account
    # means nothing to it.
    if parsed.hostname in _API_KEY_HOSTS:
        key = os.environ.get("DC_API_KEY", "").strip()
        if key:
            headers["X-API-Key"] = key
        else:
            logger.warning(
                "%s expects an API key but DC_API_KEY is unset; requests will "
                "be rejected.", parsed.hostname
            )
        return

    token = get_id_token(_audience_for(target_url))
    if token:
        headers["Authorization"] = f"Bearer {token}"
