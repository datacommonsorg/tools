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
"""Google Cloud Model Armor client for screening user prompts.

When `MODEL_ARMOR_TEMPLATE` is configured in the environment
(`projects/<project>/locations/<location>/templates/<template>`),
`screen_user_prompt` sends the user query to the regional Model Armor REST API
(`sanitizeUserPrompt`) authenticated with Application Default Credentials.

If `MODEL_ARMOR_TEMPLATE` is unset, `screen_user_prompt` returns `None` without
making any network or credential calls. If the template path is malformed or the
Model Armor API request fails or times out, a warning is logged (without the
user query text) and the turn proceeds rather than failing closed on a
transient infrastructure error.
"""

import asyncio
import logging
import re
import threading
from dataclasses import dataclass
from typing import Any

import google.auth
import google.auth.exceptions
import httpx
from google.auth.credentials import Credentials
from google.auth.transport.requests import Request

from narratives_agent.settings import get_settings

logger = logging.getLogger(__name__)

_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"

# Bounded timeout for each Model Armor screening call so an unresponsive
# regional endpoint cannot stall the admission phase.
_REQUEST_TIMEOUT_SECONDS = 5.0
_CONNECT_TIMEOUT_SECONDS = 2.0
_MAX_IDLE_CONNECTIONS = 16

_MATCH_FOUND = "MATCH_FOUND"
_DEFAULT_MATCH_LABEL = "model_armor"

_TEMPLATE_PATTERN = re.compile(
    r"^projects/[^/]+/locations/(?P<location>[^/]+)/templates/[^/]+$"
)


@dataclass
class _ClientState:
    """Holds the shared HTTP client, its event loop, and ADC credentials."""

    client: httpx.AsyncClient | None = None
    loop: asyncio.AbstractEventLoop | None = None
    credentials: Credentials | None = None


_STATE = _ClientState()
_AUTH_LOCK = threading.Lock()


def reset_model_armor_client() -> None:
    """Clears cached credentials and HTTP client state (for testing)."""
    with _AUTH_LOCK:
        _STATE.credentials = None
    _STATE.client = None
    _STATE.loop = None


async def aclose() -> None:
    """Closes the shared HTTP client if one is open on the running loop."""
    running = asyncio.get_running_loop()
    client, loop = _STATE.client, _STATE.loop
    _STATE.client = None
    _STATE.loop = None
    if client is not None and loop is running:
        await client.aclose()


def _http_transport() -> httpx.AsyncBaseTransport | None:
    """Returns the transport for the shared client (`None` uses the network)."""
    return None


def _http_client() -> httpx.AsyncClient:
    """Returns the shared HTTP client for the running event loop."""
    loop = asyncio.get_running_loop()
    if (
        _STATE.client is None
        or _STATE.client.is_closed
        or _STATE.loop is not loop
    ):
        _STATE.client = httpx.AsyncClient(
            transport=_http_transport(),
            timeout=httpx.Timeout(
                _REQUEST_TIMEOUT_SECONDS, connect=_CONNECT_TIMEOUT_SECONDS
            ),
            limits=httpx.Limits(
                max_keepalive_connections=_MAX_IDLE_CONNECTIONS
            ),
        )
        _STATE.loop = loop
    return _STATE.client


def _load_credentials() -> Credentials:
    """Loads Application Default Credentials scoped for Google Cloud APIs."""
    credentials, _ = google.auth.default(scopes=[_CLOUD_PLATFORM_SCOPE])
    if not isinstance(credentials, Credentials):
        raise RuntimeError("ADC did not return google.auth Credentials")
    return credentials


def _refresh_credentials(credentials: Credentials) -> None:
    """Refreshes `credentials` synchronously using a transport request."""
    credentials.refresh(Request())  # type: ignore[no-untyped-call]


def _build_auth_headers(credentials: Credentials) -> dict[str, str]:
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


def _resolve_auth_headers_sync() -> dict[str, str]:
    """Resolves and refreshes ADC authentication headers under `_AUTH_LOCK`."""
    with _AUTH_LOCK:
        if _STATE.credentials is None:
            _STATE.credentials = _load_credentials()
        credentials = _STATE.credentials
        if not credentials.valid or not credentials.token:
            _refresh_credentials(credentials)
        return _build_auth_headers(credentials)


async def _get_auth_headers() -> dict[str, str]:
    """Returns valid ADC request headers without blocking the event loop."""
    credentials = _STATE.credentials
    if (
        credentials is not None
        and credentials.valid
        and isinstance(credentials.token, str)
        and credentials.token
    ):
        return _build_auth_headers(credentials)
    return await asyncio.to_thread(_resolve_auth_headers_sync)


def _sanitize_prompt_url(template: str) -> str | None:
    """Builds the regional `sanitizeUserPrompt` URL for `template`.

    Args:
        template: Model Armor template resource name
            (`projects/<project>/locations/<location>/templates/<template>`).

    Returns:
        The regional `sanitizeUserPrompt` endpoint URL, or `None` if `template`
        does not match the expected resource path format.
    """
    normalized = template.strip().strip("/")
    match = _TEMPLATE_PATTERN.match(normalized)
    if match is None:
        logger.warning(
            "Invalid MODEL_ARMOR_TEMPLATE %r; skipping Model Armor screening",
            template,
        )
        return None
    location = match.group("location")
    return (
        f"https://modelarmor.{location}.rep.googleapis.com"
        f"/v1/{normalized}:sanitizeUserPrompt"
    )


def _has_match_found(node: object) -> bool:
    """Returns whether `node` or any nested dict reports `MATCH_FOUND`."""
    if not isinstance(node, dict):
        return False
    if node.get("matchState") == _MATCH_FOUND:
        return True
    return any(_has_match_found(child) for child in node.values())


def _extract_matched_filters(sanitization_result: dict[str, Any]) -> str:
    """Returns a comma-separated summary of the filters that matched."""
    filter_results = sanitization_result.get("filterResults")
    if isinstance(filter_results, dict):
        matched = [
            str(name)
            for name, entry in filter_results.items()
            if _has_match_found(entry)
        ]
        if matched:
            return ", ".join(matched)
    return _DEFAULT_MATCH_LABEL


async def screen_user_prompt(query: str) -> str | None:
    """Screens `query` against the configured Model Armor template.

    Args:
        query: The user query text to inspect.

    Returns:
        A comma-separated string of matched Model Armor filter names (or
        `"model_armor"`) when `filterMatchState` is `"MATCH_FOUND"`, or `None`
        when `MODEL_ARMOR_TEMPLATE` is unset, no filter matched, or the
        Model Armor request failed open.
    """
    template = get_settings().model_armor_template
    if not template:
        return None
    url = _sanitize_prompt_url(template)
    if url is None:
        return None

    try:
        headers = await _get_auth_headers()
        response = await _http_client().post(
            url,
            headers=headers,
            json={"userPromptData": {"text": query}},
        )
        response.raise_for_status()
        payload: object = response.json()
    except httpx.HTTPStatusError as error:
        logger.warning(
            "Model Armor request failed (HTTP %d); proceeding without "
            "screening",
            error.response.status_code,
        )
        return None
    except (
        httpx.RequestError,
        google.auth.exceptions.GoogleAuthError,
        ValueError,
        RuntimeError,
    ) as error:
        logger.warning(
            "Model Armor request failed (%s); proceeding without screening",
            type(error).__name__,
        )
        return None

    if not isinstance(payload, dict):
        logger.warning(
            "Model Armor response is not a JSON object; proceeding without "
            "screening"
        )
        return None
    sanitization_result = payload.get("sanitizationResult")
    if not isinstance(sanitization_result, dict):
        logger.warning(
            "Model Armor response missing sanitizationResult; proceeding "
            "without screening"
        )
        return None

    if sanitization_result.get("filterMatchState") == _MATCH_FOUND:
        return _extract_matched_filters(sanitization_result)
    return None
