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
"""Tests for non-200 HTTP error reporting and redaction in the Gemini client.

Verifies that:
1. Non-200 HTTP responses (such as 400 Bad Request) return a structured
   `{"error": "<message>"}` dictionary in streaming, non-streaming, and
   thought-streaming modes.
2. Any `key=<value>` query parameter echoed in an upstream error body or
   raised in a transport exception is redacted to `key=[REDACTED]` in both the
   returned error string and the logged error message.
"""

import io
import json
import logging
from collections.abc import Callable
from typing import Any

import pytest
import requests

from narratives_agent.gemini import client

_MODEL = "gemini-3-flash-preview"
_MESSAGES = [{"role": "user", "parts": [{"text": "What is the population?"}]}]

_BAD_REQUEST_BODY = json.dumps(
    {
        "error": {
            "code": 400,
            "message": (
                'Invalid JSON payload received. Unknown name "thinkingLevel" '
                "at 'generation_config'."
            ),
            "status": "INVALID_ARGUMENT",
        }
    }
)

_FAKE_KEY = "test-gemini-credential-for-redaction-0000"

_PROXY_ERROR_BODY = (
    "<html><head><title>502 Bad Gateway</title></head><body>"
    "Error fetching https://generativelanguage.googleapis.com/v1beta/"
    f"models/{_MODEL}:streamGenerateContent?key={_FAKE_KEY}&alt=sse"
    "</body></html>"
)


@pytest.fixture
def gemini_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[int, str], None]:
    """Stub `client._SESSION.post` to return a fresh `Response` per call."""
    monkeypatch.setattr(client, "load_config", lambda: {})
    monkeypatch.setattr(client, "get_gemini_api_key", lambda: _FAKE_KEY)

    def install(status: int, body: str) -> None:
        def post(*args: Any, **kwargs: Any) -> requests.Response:
            response = requests.Response()
            response.status_code = status
            response.raw = io.BytesIO(body.encode("utf-8"))
            response.headers["Content-Type"] = "application/json"
            return response

        monkeypatch.setattr(client._SESSION, "post", post)

    return install


@pytest.mark.parametrize("stream", [True, False])
def test_a_rejected_payload_is_reported_as_a_string_error(
    gemini_answers: Callable[[int, str], None], stream: bool
) -> None:
    # Test: Error reporting for an HTTP 400 response in gemini_request.
    # Situation: The Gemini endpoint returns HTTP 400 with a JSON error payload
    #   for both streaming and non-streaming requests.
    # Expectation: gemini_request returns a dict whose "error" value is a
    #   formatted string starting with "HTTP 400:" and containing the upstream
    #   status text.
    gemini_answers(400, _BAD_REQUEST_BODY)

    result = client.gemini_request(
        messages=_MESSAGES,
        system_instruction="",
        model=_MODEL,
        stream=stream,
    )

    assert isinstance(result, dict)
    assert isinstance(result["error"], str)
    assert result["error"].startswith("HTTP 400:")
    assert "INVALID_ARGUMENT" in result["error"]


def test_a_rejected_payload_while_thought_streaming_is_reported(
    gemini_answers: Callable[[int, str], None],
) -> None:
    # Test: Error reporting for an HTTP 400 response in
    #   gemini_request_with_thought_streaming.
    # Situation: The Gemini endpoint returns HTTP 400 during a thought-streaming
    #   request.
    # Expectation: The function returns a dict containing an "error" string and
    #   omits "candidates" so callers detect the failed request instead of
    #   reading an empty candidate list.
    gemini_answers(400, _BAD_REQUEST_BODY)

    result = client.gemini_request_with_thought_streaming(
        messages=_MESSAGES, system_instruction="", model=_MODEL
    )

    assert isinstance(result["error"], str)
    assert "candidates" not in result


def test_an_echoed_api_key_is_redacted_from_the_error_and_the_log(
    gemini_answers: Callable[[int, str], None], caplog: pytest.LogCaptureFixture
) -> None:
    # Test: Redaction of the API key from upstream error bodies and logs.
    # Situation: An intermediate proxy returns an HTTP 502 error page that
    #   echoes the request URL containing `key=<api_key>`.
    # Expectation: Both the returned error string and the error log replace the
    #   credential with `key=[REDACTED]` and never expose the raw API key.
    gemini_answers(502, _PROXY_ERROR_BODY)

    with caplog.at_level(logging.ERROR, logger=client.logger.name):
        result = client.gemini_request(
            messages=_MESSAGES,
            system_instruction="",
            model=_MODEL,
            stream=True,
        )

    assert isinstance(result, dict)
    assert _FAKE_KEY not in result["error"]
    assert "key=[REDACTED]" in result["error"]
    assert _FAKE_KEY not in caplog.text
    assert "key=[REDACTED]" in caplog.text


def test_transport_exception_redacts_api_key_from_error_and_log(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # Test: Redaction of the API key when _SESSION.post raises a transport
    #   exception containing the request URL.
    # Situation: _SESSION.post raises a ConnectionError whose message includes
    #   `?key=<api_key>` in the failed request path.
    # Expectation: Both the returned error string and the error log replace the
    #   credential with `key=[REDACTED]` and never expose the raw API key.
    monkeypatch.setattr(client, "load_config", lambda: {})
    monkeypatch.setattr(client, "get_gemini_api_key", lambda: _FAKE_KEY)

    def raise_connection_error(*args: Any, **kwargs: Any) -> requests.Response:
        raise requests.exceptions.ConnectionError(
            f"HTTPSConnectionPool: Max retries exceeded with url: "
            f"/v1beta/models/{_MODEL}:generateContent?key={_FAKE_KEY}"
        )

    monkeypatch.setattr(client._SESSION, "post", raise_connection_error)

    with caplog.at_level(logging.ERROR, logger=client.logger.name):
        result = client.gemini_request(
            messages=_MESSAGES,
            system_instruction="",
            model=_MODEL,
            stream=False,
        )

    assert isinstance(result, dict)
    assert _FAKE_KEY not in result["error"]
    assert "key=[REDACTED]" in result["error"]
    assert _FAKE_KEY not in caplog.text
    assert "key=[REDACTED]" in caplog.text


@pytest.mark.parametrize("status_code", [400, 429, 500, 503])
def test_non_200_streaming_responses_are_closed(
    monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    # Test: Connection cleanup for non-200 streaming responses.
    # Situation: _SESSION.post(..., stream=True) returns a non-200 status
    #   (400, 429, 500, or 503).
    # Expectation: _status_error calls response.close() so the underlying
    #   socket is released back to _SESSION's connection pool.
    monkeypatch.setattr(client, "load_config", lambda: {})
    monkeypatch.setattr(client, "get_gemini_api_key", lambda: _FAKE_KEY)
    closed = False

    class _TrackingResponse(requests.Response):
        def close(self) -> None:
            nonlocal closed
            closed = True
            super().close()

    def post(*args: Any, **kwargs: Any) -> requests.Response:
        response = _TrackingResponse()
        response.status_code = status_code
        response.raw = io.BytesIO(_BAD_REQUEST_BODY.encode("utf-8"))
        response.headers["Content-Type"] = "application/json"
        return response

    monkeypatch.setattr(client._SESSION, "post", post)

    result = client.gemini_request(
        messages=_MESSAGES,
        system_instruction="",
        model=_MODEL,
        stream=True,
    )

    assert isinstance(result, dict)
    assert "error" in result
    assert closed is True
