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
"""Tests for Google Cloud Model Armor screening in `model_armor`."""

import json
import logging
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from google.auth.credentials import Credentials

from narratives_agent import model_armor
from narratives_agent.settings import MODEL_ARMOR_TEMPLATE_ENV

_TEMPLATE = (
    "projects/datcom-website-autopush/locations/us-central1"
    "/templates/narratives-autopush"
)
_EXPECTED_URL = (
    "https://modelarmor.us-central1.rep.googleapis.com"
    f"/v1/{_TEMPLATE}:sanitizeUserPrompt"
)
_QUERY = "What is the population of California?"


class _StubCredentials(Credentials):
    """In-memory `google.auth` credentials stub for unit tests."""

    def __init__(
        self,
        token: str | None = "test-access-token",
        expired: bool = False,
        quota_project_id: str | None = None,
    ) -> None:
        super().__init__()  # type: ignore[no-untyped-call]
        self.token = token
        self._expired = expired
        self._quota_project_id = quota_project_id
        self.refresh_calls = 0

    @property
    def expired(self) -> bool:
        return self._expired

    def refresh(self, request: Any) -> None:
        self.refresh_calls += 1
        self._expired = False
        self.token = f"refreshed-token-{self.refresh_calls}"


@pytest.fixture
def install_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[Callable[[httpx.Request], httpx.Response]], list[httpx.Request]]:
    """Installs a mock HTTP transport and returns the recorded requests."""
    requests: list[httpx.Request] = []

    def install(
        handler: Callable[[httpx.Request], httpx.Response],
    ) -> list[httpx.Request]:
        def wrapped(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return handler(request)

        transport = httpx.MockTransport(wrapped)
        monkeypatch.setattr(model_armor, "_http_transport", lambda: transport)
        model_armor.reset_model_armor_client()
        return requests

    return install


@pytest.mark.asyncio
async def test_unset_template_skips_screening_without_auth_or_http(
    monkeypatch: pytest.MonkeyPatch,
    install_transport: Callable[
        [Callable[[httpx.Request], httpx.Response]], list[httpx.Request]
    ],
) -> None:
    # Test: No-op behavior when `MODEL_ARMOR_TEMPLATE` is unset.
    # Situation: `MODEL_ARMOR_TEMPLATE` is not set in the environment.
    # Expectation: `screen_user_prompt` returns `None` without loading
    #   credentials or sending an HTTP request.
    def _unexpected_creds() -> Credentials:
        raise AssertionError("Credentials must not be loaded when unset")

    monkeypatch.setattr(model_armor, "_load_credentials", _unexpected_creds)
    requests = install_transport(lambda req: httpx.Response(200, json={}))

    result = await model_armor.screen_user_prompt(_QUERY)

    assert result is None
    assert requests == []


@pytest.mark.asyncio
async def test_malformed_template_logs_warning_and_skips_screening(
    monkeypatch: pytest.MonkeyPatch,
    install_transport: Callable[
        [Callable[[httpx.Request], httpx.Response]], list[httpx.Request]
    ],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Test: Validation of `MODEL_ARMOR_TEMPLATE` resource path format.
    # Situation: `MODEL_ARMOR_TEMPLATE` is set to a string that does not match
    #   `projects/<project>/locations/<location>/templates/<template>`.
    # Expectation: `screen_user_prompt` logs a warning and returns `None`
    #   without making an HTTP request.
    monkeypatch.setenv(MODEL_ARMOR_TEMPLATE_ENV, "invalid-template-path")
    requests = install_transport(lambda req: httpx.Response(200, json={}))

    with caplog.at_level(logging.WARNING, logger=model_armor.logger.name):
        result = await model_armor.screen_user_prompt(_QUERY)

    assert result is None
    assert requests == []
    assert "Invalid MODEL_ARMOR_TEMPLATE" in caplog.text


@pytest.mark.asyncio
async def test_no_match_found_returns_none_and_sends_regional_request(
    monkeypatch: pytest.MonkeyPatch,
    install_transport: Callable[
        [Callable[[httpx.Request], httpx.Response]], list[httpx.Request]
    ],
) -> None:
    # Test: Regional endpoint request format and `NO_MATCH_FOUND` handling.
    # Situation: `MODEL_ARMOR_TEMPLATE` is configured in `us-central1` and
    #   Model Armor responds with `filterMatchState="NO_MATCH_FOUND"`.
    # Expectation: `screen_user_prompt` sends a POST request to the regional
    #   `us-central1` endpoint with the ADC Bearer token and `userPromptData`
    #   payload, and returns `None`.
    creds = _StubCredentials(
        token="adc-token-123", quota_project_id="datcom-website-autopush"
    )
    monkeypatch.setenv(MODEL_ARMOR_TEMPLATE_ENV, f"/{_TEMPLATE}/")
    monkeypatch.setattr(model_armor, "_load_credentials", lambda: creds)
    requests = install_transport(
        lambda req: httpx.Response(
            200,
            json={
                "sanitizationResult": {
                    "filterMatchState": "NO_MATCH_FOUND",
                    "invocationResult": "SUCCESS",
                }
            },
        )
    )

    result = await model_armor.screen_user_prompt(_QUERY)

    assert result is None
    assert creds.refresh_calls == 0
    (request,) = requests
    assert str(request.url) == _EXPECTED_URL
    assert request.headers["Authorization"] == "Bearer adc-token-123"
    assert request.headers["x-goog-user-project"] == "datcom-website-autopush"
    assert json.loads(request.content) == {"userPromptData": {"text": _QUERY}}


@pytest.mark.parametrize(
    ("filter_results", "expected_match"),
    [
        pytest.param(
            {
                "pi_and_jailbreak": {
                    "piAndJailbreakFilterResult": {
                        "matchState": "MATCH_FOUND",
                        "confidenceLevel": "HIGH",
                    }
                },
                "rai": {
                    "raiFilterResult": {
                        "matchState": "NO_MATCH_FOUND",
                    }
                },
            },
            "pi_and_jailbreak",
            id="pi-and-jailbreak",
        ),
        pytest.param(
            {
                "sdp": {
                    "sdpFilterResult": {
                        "inspectResult": {
                            "matchState": "MATCH_FOUND",
                        }
                    }
                },
                "malicious_uris": {
                    "maliciousUriFilterResult": {
                        "matchState": "MATCH_FOUND",
                    }
                },
            },
            "sdp, malicious_uris",
            id="multiple-filters-including-nested-sdp",
        ),
        pytest.param(
            {},
            "model_armor",
            id="fallback-when-filter-results-empty",
        ),
    ],
)
@pytest.mark.asyncio
async def test_match_found_returns_matched_filter_names(
    monkeypatch: pytest.MonkeyPatch,
    install_transport: Callable[
        [Callable[[httpx.Request], httpx.Response]], list[httpx.Request]
    ],
    filter_results: dict[str, Any],
    expected_match: str,
) -> None:
    # Test: `MATCH_FOUND` response parsing in `screen_user_prompt`.
    # Situation: Model Armor returns `filterMatchState="MATCH_FOUND"` with
    #   single, multiple/nested, or empty `filterResults`.
    # Expectation: `screen_user_prompt` returns the comma-separated names of
    #   the matched filters, or `"model_armor"` when none are listed.
    monkeypatch.setenv(MODEL_ARMOR_TEMPLATE_ENV, _TEMPLATE)
    monkeypatch.setattr(
        model_armor, "_load_credentials", lambda: _StubCredentials()
    )
    install_transport(
        lambda req: httpx.Response(
            200,
            json={
                "sanitizationResult": {
                    "filterMatchState": "MATCH_FOUND",
                    "filterResults": filter_results,
                }
            },
        )
    )

    result = await model_armor.screen_user_prompt(_QUERY)

    assert result == expected_match


@pytest.mark.asyncio
async def test_expired_credentials_are_refreshed_and_reused(
    monkeypatch: pytest.MonkeyPatch,
    install_transport: Callable[
        [Callable[[httpx.Request], httpx.Response]], list[httpx.Request]
    ],
) -> None:
    # Test: ADC credential refresh and reuse across calls.
    # Situation: The loaded credentials start without a token (`expired=True`)
    #   and two `screen_user_prompt` calls are made in succession.
    # Expectation: The first call refreshes the credentials once, and the
    #   second call reuses the refreshed token without refreshing again.
    creds = _StubCredentials(token=None, expired=True)
    load_calls = 0

    def _load() -> Credentials:
        nonlocal load_calls
        load_calls += 1
        return creds

    monkeypatch.setenv(MODEL_ARMOR_TEMPLATE_ENV, _TEMPLATE)
    monkeypatch.setattr(model_armor, "_load_credentials", _load)
    requests = install_transport(
        lambda req: httpx.Response(
            200,
            json={"sanitizationResult": {"filterMatchState": "NO_MATCH_FOUND"}},
        )
    )

    await model_armor.screen_user_prompt(_QUERY)
    await model_armor.screen_user_prompt(_QUERY)

    assert load_calls == 1
    assert creds.refresh_calls == 1
    assert len(requests) == 2
    assert requests[0].headers["Authorization"] == "Bearer refreshed-token-1"
    assert requests[1].headers["Authorization"] == "Bearer refreshed-token-1"


@pytest.mark.parametrize(
    ("response_factory", "expected_log"),
    [
        pytest.param(
            lambda req: httpx.Response(503, text="Service Unavailable"),
            "HTTP 503",
            id="http-503",
        ),
        pytest.param(
            lambda req: (_ for _ in ()).throw(
                httpx.ConnectTimeout("timed out")
            ),
            "ConnectTimeout",
            id="connect-timeout",
        ),
        pytest.param(
            lambda req: httpx.Response(200, text="{not valid json"),
            "JSONDecodeError",
            id="invalid-json",
        ),
        pytest.param(
            lambda req: httpx.Response(200, json=["not-a-dict"]),
            "not a JSON object",
            id="non-object-json",
        ),
        pytest.param(
            lambda req: httpx.Response(200, json={}),
            "missing sanitizationResult",
            id="missing-sanitization-result",
        ),
    ],
)
@pytest.mark.asyncio
async def test_upstream_errors_fail_open_without_logging_query(
    monkeypatch: pytest.MonkeyPatch,
    install_transport: Callable[
        [Callable[[httpx.Request], httpx.Response]], list[httpx.Request]
    ],
    caplog: pytest.LogCaptureFixture,
    response_factory: Callable[[httpx.Request], httpx.Response],
    expected_log: str,
) -> None:
    # Test: Fail-open error handling on upstream Model Armor failures.
    # Situation: The Model Armor call encounters an HTTP 503 error, a network
    #   timeout, malformed JSON, a non-object JSON payload, or a response
    #   missing `sanitizationResult`.
    # Expectation: `screen_user_prompt` logs a warning containing the failure
    #   summary (without leaking the user query text) and returns `None`.
    monkeypatch.setenv(MODEL_ARMOR_TEMPLATE_ENV, _TEMPLATE)
    monkeypatch.setattr(
        model_armor, "_load_credentials", lambda: _StubCredentials()
    )
    install_transport(response_factory)

    with caplog.at_level(logging.WARNING, logger=model_armor.logger.name):
        result = await model_armor.screen_user_prompt(_QUERY)

    assert result is None
    assert expected_log in caplog.text
    assert _QUERY not in caplog.text


@pytest.mark.asyncio
async def test_aclose_closes_the_shared_http_client(
    monkeypatch: pytest.MonkeyPatch,
    install_transport: Callable[
        [Callable[[httpx.Request], httpx.Response]], list[httpx.Request]
    ],
) -> None:
    # Test: Closing the shared HTTP client via `aclose()`.
    # Situation: A request initializes the shared `httpx.AsyncClient` and
    #   `aclose()` is called on the same event loop.
    # Expectation: The client is closed and cleared from `_STATE`.
    monkeypatch.setenv(MODEL_ARMOR_TEMPLATE_ENV, _TEMPLATE)
    monkeypatch.setattr(
        model_armor, "_load_credentials", lambda: _StubCredentials()
    )
    install_transport(
        lambda req: httpx.Response(
            200,
            json={"sanitizationResult": {"filterMatchState": "NO_MATCH_FOUND"}},
        )
    )

    await model_armor.screen_user_prompt(_QUERY)
    client = model_armor._STATE.client
    assert client is not None
    assert not client.is_closed

    await model_armor.aclose()

    assert client.is_closed
    assert model_armor._STATE.client is None
