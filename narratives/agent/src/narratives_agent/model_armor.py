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

If `MODEL_ARMOR_TEMPLATE` is unset, `init_model_armor` logs a startup warning
and `screen_user_prompt` returns `None` without making any network or credential
calls. If `MODEL_ARMOR_TEMPLATE` is set to a malformed resource path,
`init_model_armor` raises `RuntimeError` so startup fails fast instead of
silently running unscreened. If a runtime Model Armor API request fails or times
out, a warning is logged (without the user query text) and the turn proceeds
rather than failing closed on a transient infrastructure error.
"""

import asyncio
import logging
import re
from dataclasses import dataclass

import google.auth.exceptions
import httpx
from pydantic import BaseModel, ConfigDict, Field

from narratives_agent.gcp_auth import get_adc_auth_headers
from narratives_agent.json_value import JsonValue
from narratives_agent.settings import get_settings

logger = logging.getLogger(__name__)

# Bounded timeout for each Model Armor screening call so an unresponsive
# regional endpoint cannot stall the admission phase.
_REQUEST_TIMEOUT_SECONDS = 5.0
_CONNECT_TIMEOUT_SECONDS = 2.0
_MAX_IDLE_CONNECTIONS = 16

_MATCH_FOUND = "MATCH_FOUND"
_INVOCATION_SUCCESS = "SUCCESS"
_DEFAULT_MATCH_LABEL = "model_armor"

# Matches a Google Cloud Model Armor template resource name
# (`projects/<project>/locations/<location>/templates/<template>`) and captures
# `<location>` so requests target the regional Model Armor endpoint.
_MODEL_ARMOR_TEMPLATE_PATTERN = re.compile(
    r"^projects/[A-Za-z0-9._:-]+/locations/(?P<location>[a-z0-9-]+)"
    r"/templates/[A-Za-z0-9._-]+$"
)


@dataclass
class _ClientState:
    """Holds the shared Model Armor HTTP client and its event loop."""

    client: httpx.AsyncClient | None = None
    loop: asyncio.AbstractEventLoop | None = None


_STATE = _ClientState()


def reset_model_armor_client() -> None:
    """Clears cached HTTP client state (for testing)."""
    _STATE.client = None
    _STATE.loop = None


def init_model_armor() -> None:
    """Validates `MODEL_ARMOR_TEMPLATE` and logs status at server startup.

    Raises:
        RuntimeError: `MODEL_ARMOR_TEMPLATE` is set but does not match the
            expected resource path format.
    """
    template = get_settings().model_armor_template
    if not template:
        logger.warning(
            "MODEL_ARMOR_TEMPLATE is unset; Model Armor prompt screening "
            "is disabled."
        )
        return
    _sanitize_prompt_url(template)


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


def _sanitize_prompt_url(template: str) -> str:
    """Builds the regional `sanitizeUserPrompt` URL for `template`.

    Args:
        template: Model Armor template resource name
            (`projects/<project>/locations/<location>/templates/<template>`).

    Returns:
        The regional `sanitizeUserPrompt` endpoint URL.

    Raises:
        RuntimeError: `template` does not match the expected resource path
            format.
    """
    normalized = template.strip().strip("/")
    match = _MODEL_ARMOR_TEMPLATE_PATTERN.match(normalized)
    if match is None:
        raise RuntimeError(
            f"Invalid MODEL_ARMOR_TEMPLATE {template!r}; expected "
            "'projects/<project>/locations/<location>/templates/<template>'."
        )
    location = match.group("location")
    return (
        f"https://modelarmor.{location}.rep.googleapis.com"
        f"/v1/{normalized}:sanitizeUserPrompt"
    )


class _SanitizationResult(BaseModel):
    """Subset of Model Armor's `SanitizationResult` inspected by the agent."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    filter_match_state: str = Field(default="", alias="filterMatchState")
    invocation_result: str = Field(default="", alias="invocationResult")
    filter_results: dict[str, JsonValue] = Field(
        default_factory=dict, alias="filterResults"
    )


class _SanitizePromptResponse(BaseModel):
    """Top-level response payload from `:sanitizeUserPrompt`."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    sanitization_result: _SanitizationResult = Field(alias="sanitizationResult")


def _has_match_found(node: JsonValue) -> bool:
    """Returns whether `node` or any nested dict reports `MATCH_FOUND`."""
    if not isinstance(node, dict):
        return False
    if node.get("matchState") == _MATCH_FOUND:
        return True
    return any(_has_match_found(child) for child in node.values())


def _extract_matched_filters(sanitization_result: _SanitizationResult) -> str:
    """Returns a comma-separated summary of the filters that matched."""
    matched = [
        name
        for name, entry in sanitization_result.filter_results.items()
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

    Raises:
        RuntimeError: `MODEL_ARMOR_TEMPLATE` is set but does not match the
            expected resource path format.
    """
    template = get_settings().model_armor_template
    if not template:
        return None
    url = _sanitize_prompt_url(template)

    try:
        async with asyncio.timeout(_REQUEST_TIMEOUT_SECONDS):
            headers = await get_adc_auth_headers()
            response = await _http_client().post(
                url,
                headers=headers,
                json={"userPromptData": {"text": query}},
            )
        response.raise_for_status()
        parsed = _SanitizePromptResponse.model_validate(response.json())
    except httpx.HTTPStatusError as error:
        logger.warning(
            "Model Armor request failed (HTTP %d); proceeding without "
            "screening",
            error.response.status_code,
        )
        return None
    except (
        TimeoutError,
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

    sanitization_result = parsed.sanitization_result
    if sanitization_result.invocation_result not in ("", _INVOCATION_SUCCESS):
        logger.warning(
            "Model Armor sanitization returned invocationResult=%r",
            sanitization_result.invocation_result,
        )
    if sanitization_result.filter_match_state == _MATCH_FOUND:
        return _extract_matched_filters(sanitization_result)
    return None
