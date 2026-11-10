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

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

import google.auth.exceptions
import httpx
import pytest

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
_AUTH_HEADERS = {
    "Authorization": "Bearer adc-token-123",
    "x-goog-user-project": "datcom-website-autopush",
}


async def _stub_auth_headers() -> dict[str, str]:
    """Returns canned ADC headers for Model Armor HTTP tests."""
    return dict(_AUTH_HEADERS)


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


def test_init_model_armor_logs_warning_when_template_unset(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Test: Startup warning when `MODEL_ARMOR_TEMPLATE` is unset.
    # Situation: `MODEL_ARMOR_TEMPLATE` is not set in the environment.
    # Expectation: `init_model_armor` logs a warning indicating screening is
    #   disabled.
    with caplog.at_level(logging.WARNING, logger=model_armor.logger.name):
        model_armor.init_model_armor()

    (record,) = caplog.records
    assert "MODEL_ARMOR_TEMPLATE is unset" in record.getMessage()


def test_init_model_armor_logs_nothing_when_template_set(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Test: Startup log behavior when `MODEL_ARMOR_TEMPLATE` is set.
    # Situation: `MODEL_ARMOR_TEMPLATE` is configured.
    # Expectation: `init_model_armor` logs no warning.
    monkeypatch.setenv(MODEL_ARMOR_TEMPLATE_ENV, _TEMPLATE)

    with caplog.at_level(logging.WARNING, logger=model_armor.logger.name):
        model_armor.init_model_armor()

    assert caplog.records == []


def test_init_model_armor_raises_when_template_malformed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Fail-fast startup validation of `MODEL_ARMOR_TEMPLATE`.
    # Situation: `MODEL_ARMOR_TEMPLATE` is set to a string that does not match
    #   `projects/<project>/locations/<location>/templates/<template>`.
    # Expectation: `init_model_armor` raises `RuntimeError`.
    monkeypatch.setenv(MODEL_ARMOR_TEMPLATE_ENV, "invalid-template-path")

    with pytest.raises(RuntimeError, match="MODEL_ARMOR_TEMPLATE"):
        model_armor.init_model_armor()


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
    async def _unexpected_auth() -> dict[str, str]:
        raise AssertionError("ADC headers must not be resolved when unset")

    monkeypatch.setattr(model_armor, "get_adc_auth_headers", _unexpected_auth)
    requests = install_transport(lambda req: httpx.Response(200, json={}))

    result = await model_armor.screen_user_prompt(_QUERY)

    assert result is None
    assert requests == []


@pytest.mark.asyncio
async def test_malformed_template_raises_without_http(
    monkeypatch: pytest.MonkeyPatch,
    install_transport: Callable[
        [Callable[[httpx.Request], httpx.Response]], list[httpx.Request]
    ],
) -> None:
    # Test: Validation of `MODEL_ARMOR_TEMPLATE` resource path format in
    #   `screen_user_prompt`.
    # Situation: `MODEL_ARMOR_TEMPLATE` is set to a string that does not match
    #   `projects/<project>/locations/<location>/templates/<template>`.
    # Expectation: `screen_user_prompt` raises `RuntimeError` without making an
    #   HTTP request instead of silently skipping screening.
    monkeypatch.setenv(MODEL_ARMOR_TEMPLATE_ENV, "invalid-template-path")
    requests = install_transport(lambda req: httpx.Response(200, json={}))

    with pytest.raises(RuntimeError, match="MODEL_ARMOR_TEMPLATE"):
        await model_armor.screen_user_prompt(_QUERY)

    assert requests == []


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
    #   `us-central1` endpoint with the ADC headers and `userPromptData`
    #   payload, and returns `None`.
    monkeypatch.setenv(MODEL_ARMOR_TEMPLATE_ENV, f"/{_TEMPLATE}/")
    monkeypatch.setattr(model_armor, "get_adc_auth_headers", _stub_auth_headers)
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
    monkeypatch.setattr(model_armor, "get_adc_auth_headers", _stub_auth_headers)
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
            "ValidationError",
            id="non-object-json",
        ),
        pytest.param(
            lambda req: httpx.Response(200, json={}),
            "ValidationError",
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
    monkeypatch.setattr(model_armor, "get_adc_auth_headers", _stub_auth_headers)
    install_transport(response_factory)

    with caplog.at_level(logging.WARNING, logger=model_armor.logger.name):
        result = await model_armor.screen_user_prompt(_QUERY)

    assert result is None
    assert expected_log in caplog.text
    assert _QUERY not in caplog.text


@pytest.mark.parametrize(
    ("error", "expected_log"),
    [
        pytest.param(
            google.auth.exceptions.DefaultCredentialsError("no ADC"),  # type: ignore[no-untyped-call]
            "DefaultCredentialsError",
            id="default-credentials-error",
        ),
        pytest.param(
            RuntimeError(
                "Application Default Credentials returned no access token"
            ),
            "RuntimeError",
            id="missing-access-token",
        ),
    ],
)
@pytest.mark.asyncio
async def test_auth_errors_fail_open_without_http_or_logging_query(
    monkeypatch: pytest.MonkeyPatch,
    install_transport: Callable[
        [Callable[[httpx.Request], httpx.Response]], list[httpx.Request]
    ],
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    expected_log: str,
) -> None:
    # Test: Fail-open error handling on ADC credential failures.
    # Situation: Resolving ADC headers raises `GoogleAuthError` or
    #   `RuntimeError`.
    # Expectation: `screen_user_prompt` logs a warning with the exception type
    #   (without leaking the user query text), makes no HTTP request, and
    #   returns `None`.
    async def _failing_headers() -> dict[str, str]:
        raise error

    monkeypatch.setenv(MODEL_ARMOR_TEMPLATE_ENV, _TEMPLATE)
    monkeypatch.setattr(model_armor, "get_adc_auth_headers", _failing_headers)
    requests = install_transport(lambda req: httpx.Response(200, json={}))

    with caplog.at_level(logging.WARNING, logger=model_armor.logger.name):
        result = await model_armor.screen_user_prompt(_QUERY)

    assert result is None
    assert requests == []
    assert expected_log in caplog.text
    assert _QUERY not in caplog.text


@pytest.mark.asyncio
async def test_auth_header_timeout_fails_open_without_http_or_logging_query(
    monkeypatch: pytest.MonkeyPatch,
    install_transport: Callable[
        [Callable[[httpx.Request], httpx.Response]], list[httpx.Request]
    ],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Test: Bounded timeout around ADC credential resolution in
    #   `screen_user_prompt`.
    # Situation: `get_adc_auth_headers` stalls longer than
    #   `_REQUEST_TIMEOUT_SECONDS`.
    # Expectation: `screen_user_prompt` times out, logs a `TimeoutError`
    #   warning (without the query text), makes no HTTP request, and returns
    #   `None`.
    async def _slow_headers() -> dict[str, str]:
        await asyncio.sleep(1.0)
        return {"Authorization": "Bearer late"}

    monkeypatch.setenv(MODEL_ARMOR_TEMPLATE_ENV, _TEMPLATE)
    monkeypatch.setattr(model_armor, "_REQUEST_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(model_armor, "get_adc_auth_headers", _slow_headers)
    requests = install_transport(lambda req: httpx.Response(200, json={}))

    with caplog.at_level(logging.WARNING, logger=model_armor.logger.name):
        result = await model_armor.screen_user_prompt(_QUERY)

    assert result is None
    assert requests == []
    assert "TimeoutError" in caplog.text
    assert _QUERY not in caplog.text


@pytest.mark.parametrize(
    ("sanitization_result", "expected_result"),
    [
        pytest.param(
            {
                "invocationResult": "FAILURE",
                "filterMatchState": "NO_MATCH_FOUND",
            },
            None,
            id="failure-no-match",
        ),
        pytest.param(
            {
                "invocationResult": "PARTIAL",
                "filterMatchState": "MATCH_FOUND",
                "filterResults": {
                    "pi_and_jailbreak": {
                        "piAndJailbreakFilterResult": {
                            "matchState": "MATCH_FOUND",
                        }
                    }
                },
            },
            "pi_and_jailbreak",
            id="partial-with-match",
        ),
    ],
)
@pytest.mark.asyncio
async def test_non_success_invocation_result_logs_warning_and_preserves_verdict(
    monkeypatch: pytest.MonkeyPatch,
    install_transport: Callable[
        [Callable[[httpx.Request], httpx.Response]], list[httpx.Request]
    ],
    caplog: pytest.LogCaptureFixture,
    sanitization_result: dict[str, Any],
    expected_result: str | None,
) -> None:
    # Test: Warning and verdict handling when `invocationResult` is not
    #   `"SUCCESS"`.
    # Situation: Model Armor returns HTTP 200 with `invocationResult` set to
    #   `"FAILURE"` (`NO_MATCH_FOUND`) or `"PARTIAL"` (`MATCH_FOUND`).
    # Expectation: `screen_user_prompt` logs a warning reporting the
    #   `invocationResult` value, returns `None` when no filter matched, and
    #   still enforces `MATCH_FOUND` when a partial invocation matched a filter.
    monkeypatch.setenv(MODEL_ARMOR_TEMPLATE_ENV, _TEMPLATE)
    monkeypatch.setattr(model_armor, "get_adc_auth_headers", _stub_auth_headers)
    install_transport(
        lambda req: httpx.Response(
            200, json={"sanitizationResult": sanitization_result}
        )
    )

    with caplog.at_level(logging.WARNING, logger=model_armor.logger.name):
        result = await model_armor.screen_user_prompt(_QUERY)

    assert result == expected_result
    assert (
        f"invocationResult={sanitization_result['invocationResult']!r}"
        in caplog.text
    )
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
    monkeypatch.setattr(model_armor, "get_adc_auth_headers", _stub_auth_headers)
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
