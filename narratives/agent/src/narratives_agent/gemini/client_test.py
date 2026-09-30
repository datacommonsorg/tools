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
"""Tests for the google-genai Gemini client.

Every test drives a real `genai.Client` whose HTTP traffic is served by an
`httpx.MockTransport`, so request serialization, SSE parsing, and the SDK's
`APIError` mapping all run as they do in production; only the network is
replaced.
"""

import base64
import json
import logging
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from google import genai
from google.genai import types
from pydantic import BaseModel

from narratives_agent.gemini import client
from narratives_agent.gemini.schemas import (
    ChartConfigResponse,
    DataValidationResponse,
    FollowUpResponse,
)

_MODEL = "gemini-3-flash-preview"
_MESSAGES = [{"role": "user", "parts": [{"text": "What is the population?"}]}]

_FAKE_KEY = "test-gemini-credential-for-redaction-0000"

_BAD_REQUEST_BODY = {
    "error": {
        "code": 400,
        "message": (
            'Invalid JSON payload received. Unknown name "thinkingLevel" '
            "at 'generation_config'."
        ),
        "status": "INVALID_ARGUMENT",
    }
}

_PROXY_ERROR_BODY = (
    "<html><head><title>403 Forbidden</title></head><body>"
    "Error fetching https://generativelanguage.googleapis.com/v1beta/"
    f"models/{_MODEL}:streamGenerateContent?key={_FAKE_KEY}&alt=sse"
    "</body></html>"
)

_USAGE = {
    "promptTokenCount": 11,
    "candidatesTokenCount": 7,
    "thoughtsTokenCount": 5,
    "totalTokenCount": 23,
}

_SIGNATURE = b"\x00opaque-thought-signature\xff"

# The fixture replaces `genai.Client`; keep the real class for assertions.
_SDK_CLIENT = genai.Client

type Handler = Callable[[httpx.Request], httpx.Response]

# Names of all client entry points for parametrized tests. Streaming entry
# points return an error dict when a request fails before yielding any chunk.
_MODES = [
    "sync_request",
    "sync_stream",
    "sync_thought_streaming",
    "async_request",
    "async_stream",
    "async_thought_streaming",
]


@dataclass
class _RecordingSessionLogger:
    """Records the calls the client makes on its session logger."""

    usage: list[dict[str, Any] | None] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)

    def log(self, event_type: str, data: dict[str, Any]) -> None:
        self.events.append(event_type)

    def log_gemini_request(
        self, model: str, endpoint: str, payload_info: dict[str, Any]
    ) -> None:
        self.events.append("GEMINI_REQUEST")

    def log_gemini_response(
        self, model: str, response: dict[str, Any], duration_ms: float
    ) -> None:
        self.events.append("GEMINI_RESPONSE")

    def log_error(
        self,
        error_type: str,
        error_message: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.errors.append(error_message)

    def add_usage(self, usage_metadata: dict[str, Any] | None) -> None:
        self.usage.append(usage_metadata)


@dataclass
class _FakeGemini:
    """Serves Gemini HTTP traffic and records client construction."""

    handler: Handler | None = None
    constructions: list[dict[str, Any]] = field(default_factory=list)
    sent: list[httpx.Request] = field(default_factory=list)

    def dispatch(self, request: httpx.Request) -> httpx.Response:
        self.sent.append(request)
        assert self.handler is not None, "no Gemini response installed"
        return self.handler(request)

    def respond(self, handler: Handler) -> None:
        self.handler = handler

    def body(self, index: int = -1) -> dict[str, Any]:
        body: dict[str, Any] = json.loads(self.sent[index].content)
        return body


@pytest.fixture
def gemini(monkeypatch: pytest.MonkeyPatch) -> Iterator[_FakeGemini]:
    """Routes every SDK client the module builds through a mock transport."""
    client.reset_client()
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_LOCATION", raising=False)
    monkeypatch.setattr(client, "get_gemini_api_key", lambda: _FAKE_KEY)
    monkeypatch.setattr(client, "render_prompt", lambda p: f"rendered:{p}")
    fake = _FakeGemini()

    def build(**kwargs: Any) -> genai.Client:
        fake.constructions.append(kwargs)
        transport = httpx.MockTransport(fake.dispatch)
        options = kwargs["http_options"].model_copy(
            update={
                "httpx_client": httpx.Client(transport=transport),
                "httpx_async_client": httpx.AsyncClient(transport=transport),
            }
        )
        return _SDK_CLIENT(**{**kwargs, "http_options": options})

    monkeypatch.setattr(genai, "Client", build)
    yield fake
    client.reset_client()


def _response_json(
    parts: list[dict[str, Any]], usage: dict[str, int] | None = None
) -> dict[str, Any]:
    """Returns a REST generateContent response body."""
    body: dict[str, Any] = {
        "candidates": [{"content": {"parts": parts, "role": "model"}}]
    }
    if usage:
        body["usageMetadata"] = usage
    return body


def _sse(*chunks: dict[str, Any]) -> bytes:
    """Returns chunks encoded as a streamGenerateContent SSE body."""
    return b"".join(
        f"data: {json.dumps(chunk)}\r\n\r\n".encode() for chunk in chunks
    )


def _answer(status: int, **kwargs: Any) -> Handler:
    """Returns a handler that answers every request identically."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, **kwargs)

    return handler


def _raise(error: Exception) -> Handler:
    """Returns a handler that fails every request with `error`."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    return handler


async def _call(mode: str, **kwargs: Any) -> Any:
    """Invokes the entry point named by `mode` with the default request."""
    request: dict[str, Any] = {
        "messages": _MESSAGES,
        "system_instruction": "",
        "model": _MODEL,
        **kwargs,
    }
    match mode:
        case "sync_request":
            return client.gemini_request(**request)
        case "sync_stream":
            return client.gemini_request(**request, stream=True)
        case "sync_thought_streaming":
            return client.gemini_request_with_thought_streaming(**request)
        case "async_request":
            return await client.async_gemini_request(**request)
        case "async_stream":
            return await client.async_gemini_stream(**request)
        case "async_thought_streaming":
            return await client.async_gemini_request_with_thought_streaming(
                **request
            )
    raise AssertionError(f"unknown mode {mode}")


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", _MODES)
@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (400, "HTTP 400: "),
        (403, "HTTP 403: "),
        (429, "Rate limited (429)"),
        (500, "Server error (500)"),
        (503, "Server error (503)"),
    ],
)
async def test_a_non_200_response_is_reported_as_a_string_error(
    gemini: _FakeGemini, mode: str, status: int, expected: str
) -> None:
    # Test: Error formatting for non-200 responses in every entry point.
    # Situation: Gemini answers with HTTP 400, 403, 429, 500, or 503 and a
    #   JSON error payload.
    # Expectation: The entry point returns a dict whose "error" string is
    #   "HTTP <code>: <excerpt>" for client errors, "Rate limited (429)" for
    #   429, and "Server error (<code>)" for 5xx, with no "candidates" key.
    gemini.respond(_answer(status, json=_BAD_REQUEST_BODY))

    result = await _call(mode)

    assert isinstance(result, dict)
    assert "candidates" not in result
    assert result["error"].startswith(expected)
    if status in (400, 403):
        assert "INVALID_ARGUMENT" in result["error"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", _MODES)
async def test_an_echoed_api_key_is_redacted_from_the_error_and_the_log(
    gemini: _FakeGemini, caplog: pytest.LogCaptureFixture, mode: str
) -> None:
    # Test: Redaction of an API key echoed in an upstream error body.
    # Situation: An intermediate proxy returns an HTTP 403 page that echoes
    #   a request URL containing `key=<api_key>`.
    # Expectation: The returned error, the error log, and the session log
    #   all show `key=[REDACTED]` and never the raw key.
    gemini.respond(_answer(403, text=_PROXY_ERROR_BODY))
    session_logger = _RecordingSessionLogger()

    with caplog.at_level(logging.ERROR, logger=client.logger.name):
        result = await _call(mode, session_logger=session_logger)

    assert _FAKE_KEY not in result["error"]
    assert "key=[REDACTED]" in result["error"]
    assert _FAKE_KEY not in caplog.text
    assert "key=[REDACTED]" in caplog.text
    assert session_logger.errors == [result["error"]]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", _MODES)
async def test_a_transport_exception_is_redacted_from_the_error_and_log(
    gemini: _FakeGemini, caplog: pytest.LogCaptureFixture, mode: str
) -> None:
    # Test: Redaction of an API key carried in a transport exception.
    # Situation: The connection fails with an error whose message includes
    #   `?key=<api_key>` in the failed request path.
    # Expectation: Both the returned error and the error log replace the
    #   credential with `key=[REDACTED]`.
    gemini.respond(
        _raise(
            httpx.ConnectError(
                "Max retries exceeded with url: "
                f"/v1beta/models/{_MODEL}:generateContent?key={_FAKE_KEY}"
            )
        )
    )

    with caplog.at_level(logging.ERROR, logger=client.logger.name):
        result = await _call(mode)

    assert _FAKE_KEY not in result["error"]
    assert "key=[REDACTED]" in result["error"]
    assert _FAKE_KEY not in caplog.text
    assert "key=[REDACTED]" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", _MODES)
async def test_a_timeout_is_reported_as_a_request_timeout(
    gemini: _FakeGemini, mode: str
) -> None:
    # Test: Timeout reporting.
    # Situation: The request times out while waiting for Gemini.
    # Expectation: The entry point returns {"error": "Request timeout"}.
    gemini.respond(_raise(httpx.ReadTimeout("timed out")))

    result = await _call(mode)

    assert result == {"error": "Request timeout"}


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", _MODES)
async def test_a_missing_api_key_fails_without_sending_a_request(
    gemini: _FakeGemini, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    # Test: API key mode with no key configured.
    # Situation: GOOGLE_GENAI_USE_VERTEXAI is unset and get_gemini_api_key()
    #   returns an empty string.
    # Expectation: The entry point returns the actionable _NO_KEY_ERROR
    #   without building a client or sending a request.
    monkeypatch.setattr(client, "get_gemini_api_key", lambda: "")

    result = await _call(mode)

    assert result == {"error": client._NO_KEY_ERROR}
    assert gemini.constructions == []
    assert gemini.sent == []


@pytest.mark.parametrize(
    ("location_env", "expected_location"),
    [("", "us-central1"), ("europe-west4", "europe-west4")],
)
def test_vertex_ai_mode_builds_an_adc_client_for_the_project(
    gemini: _FakeGemini,
    monkeypatch: pytest.MonkeyPatch,
    location_env: str,
    expected_location: str,
) -> None:
    # Test: Vertex AI mode client construction.
    # Situation: GOOGLE_GENAI_USE_VERTEXAI is "true", GOOGLE_CLOUD_PROJECT
    #   is set to a project ID, and GOOGLE_CLOUD_LOCATION is either unset or
    #   set to a region.
    # Expectation: The client is built for Vertex AI with that project and
    #   the configured location, defaulting to us-central1, and no API key is
    #   resolved.
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", location_env)
    monkeypatch.setattr(
        client,
        "get_settings",
        lambda: SimpleNamespace(google_cloud_project="dc-narratives"),
    )

    def fail() -> str:
        raise AssertionError("API key resolved in Vertex AI mode")

    monkeypatch.setattr(client, "get_gemini_api_key", fail)

    built = client._get_client()

    assert isinstance(built, _SDK_CLIENT)
    assert len(gemini.constructions) == 1
    construction = gemini.constructions[0]
    assert construction["vertexai"] is True
    assert construction["project"] == "dc-narratives"
    assert construction["location"] == expected_location
    assert "api_key" not in construction


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", _MODES)
async def test_vertex_ai_mode_without_a_project_names_the_variable(
    gemini: _FakeGemini, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    # Test: Vertex AI mode with no project configured.
    # Situation: GOOGLE_GENAI_USE_VERTEXAI is "1" but GOOGLE_CLOUD_PROJECT is
    #   empty.
    # Expectation: The entry point returns an error message mentioning
    #   GOOGLE_CLOUD_PROJECT without instantiating a client.
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "1")
    monkeypatch.setattr(
        client, "get_settings", lambda: SimpleNamespace(google_cloud_project="")
    )

    result = await _call(mode)

    assert "GOOGLE_CLOUD_PROJECT" in result["error"]
    assert gemini.constructions == []


def test_the_client_is_reused_until_its_credentials_change(
    gemini: _FakeGemini, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Test: Client caching across calls.
    # Situation: Two calls are made with the same API key, then a third
    #   after the key changes.
    # Expectation: The first two calls reuse the same client instance and its
    #   connection pool, while the third call builds a new client after the
    #   key changes. The API key is sent in the x-goog-api-key header, never
    #   in the URL.
    gemini.respond(_answer(200, json=_response_json([{"text": "ok"}])))

    client.gemini_request(_MESSAGES, "", _MODEL)
    client.gemini_request(_MESSAGES, "", _MODEL)
    assert len(gemini.constructions) == 1

    monkeypatch.setattr(client, "get_gemini_api_key", lambda: "rotated-key")
    client.gemini_request(_MESSAGES, "", _MODEL)

    assert len(gemini.constructions) == 2
    assert gemini.sent[0].headers["x-goog-api-key"] == _FAKE_KEY
    assert _FAKE_KEY not in str(gemini.sent[0].url)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["sync_request", "async_request"])
async def test_a_structured_output_request_sends_the_schema_and_config(
    gemini: _FakeGemini, mode: str
) -> None:
    # Test: Request configuration for a structured-output call.
    # Situation: A caller passes ChartConfigResponse as response_schema with a
    #   system instruction, temperature 0.2, and "minimal" thinking.
    # Expectation: The request sets responseMimeType to "application/json"
    #   with the converted responseSchema, includes the rendered system
    #   instruction and generation settings, and returns the response in the
    #   Gemini REST dictionary format with usage metadata.
    answer = json.dumps({"should_render": True, "charts": []})
    gemini.respond(
        _answer(200, json=_response_json([{"text": answer}], _USAGE))
    )

    result = await _call(
        mode,
        system_instruction="Extract charts.",
        temperature=0.2,
        thinking_level="minimal",
        response_schema=ChartConfigResponse,
    )

    config = gemini.body()["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["responseSchema"]["required"] == ["should_render"]
    assert config["temperature"] == 0.2
    # The SDK serializes ThinkingConfig fields in snake_case, which the
    # Gemini API's protobuf JSON parser accepts alongside camelCase.
    assert config["thinkingConfig"] == {"thinking_level": "MINIMAL"}
    assert gemini.body()["systemInstruction"]["parts"] == [
        {"text": "rendered:Extract charts."}
    ]
    text = result["candidates"][0]["content"]["parts"][0]["text"]
    assert json.loads(text) == {"should_render": True, "charts": []}
    assert result["usageMetadata"] == _USAGE


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["sync_request", "async_request"])
async def test_a_complete_response_records_its_usage(
    gemini: _FakeGemini, mode: str
) -> None:
    # Test: Token accounting for a non-streaming call.
    # Situation: Gemini returns a complete response with usage metadata.
    # Expectation: The session logger records the response and receives the
    #   call's four token counts once.
    gemini.respond(_answer(200, json=_response_json([{"text": "ok"}], _USAGE)))
    session_logger = _RecordingSessionLogger()

    await _call(mode, session_logger=session_logger)

    assert session_logger.usage == [_USAGE]
    assert session_logger.events == ["GEMINI_REQUEST", "GEMINI_RESPONSE"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", _MODES)
async def test_an_invalid_message_is_reported_without_its_content(
    gemini: _FakeGemini, caplog: pytest.LogCaptureFixture, mode: str
) -> None:
    # Test: Invalid message in conversation history.
    # Situation: A message part passes a list containing user text instead of
    #   a string for its "text" field.
    # Expectation: The entry point returns an "Invalid Gemini request" error
    #   indicating which field failed validation, sends no HTTP request, and
    #   does not include the user text in the returned error or the logs.
    private = "my private question"
    messages = [{"role": "user", "parts": [{"text": [private]}]}]

    with caplog.at_level(logging.ERROR, logger=client.logger.name):
        result = await _call(mode, messages=messages)

    assert result["error"].startswith("Invalid Gemini request: ")
    assert "parts.0.text" in result["error"]
    assert private not in result["error"]
    assert private not in caplog.text
    assert gemini.sent == []


def test_a_dict_schema_is_not_modified_by_the_request(
    gemini: _FakeGemini,
) -> None:
    # Test: Reuse of a dict response schema.
    # Situation: A caller passes a JSON schema dict with an optional field,
    #   which the SDK rewrites while converting it.
    # Expectation: The request carries the converted schema, and the
    #   caller's dict is unchanged so it can be passed again.
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "note": {"anyOf": [{"type": "string"}, {"type": "null"}]}
        },
        "required": [],
    }
    original = json.loads(json.dumps(schema))
    gemini.respond(_answer(200, json=_response_json([{"text": "{}"}])))

    client.gemini_request(_MESSAGES, "", _MODEL, response_schema=schema)

    assert schema == original
    assert "responseSchema" in gemini.body()["generationConfig"]


def test_an_api_key_echoed_from_the_header_is_redacted(
    gemini: _FakeGemini, caplog: pytest.LogCaptureFixture
) -> None:
    # Test: Redaction of an API key echoed without a `key=` prefix.
    # Situation: A proxy rejects the request with HTTP 400 and echoes the
    #   request headers, including `x-goog-api-key: <api_key>`.
    # Expectation: The returned error and the log replace the key with
    #   [REDACTED].
    gemini.respond(
        _answer(400, text=f"bad request; headers: x-goog-api-key: {_FAKE_KEY}")
    )

    with caplog.at_level(logging.ERROR, logger=client.logger.name):
        result = client.gemini_request(_MESSAGES, "", _MODEL)

    assert isinstance(result, dict)
    assert _FAKE_KEY not in result["error"]
    assert "x-goog-api-key: [REDACTED]" in result["error"]
    assert _FAKE_KEY not in caplog.text


def test_an_api_key_crossing_the_error_length_limit_is_redacted(
    gemini: _FakeGemini, caplog: pytest.LogCaptureFixture
) -> None:
    # Test: Redaction of an echoed API key that crosses the error length limit.
    # Situation: A proxy rejects the request with HTTP 400 and echoes the
    #   API key without a `key=` prefix, at a position where the
    #   500-character limit on error text falls in the middle of the key.
    # Expectation: The key is redacted before the text is shortened, so
    #   neither the key nor its first part appears in the returned error or
    #   the log.
    prefix = "HTTP 400: "
    gemini.respond(_answer(400, text="@"))
    marker = client.gemini_request(_MESSAGES, "", _MODEL)
    assert isinstance(marker, dict)
    offset = marker["error"].index("@") - len(prefix)
    padding = client._ERROR_BODY_LENGTH - offset - len(_FAKE_KEY) // 2
    gemini.respond(_answer(400, text="x" * padding + _FAKE_KEY))

    with caplog.at_level(logging.ERROR, logger=client.logger.name):
        result = client.gemini_request(_MESSAGES, "", _MODEL)

    assert isinstance(result, dict)
    key_start = _FAKE_KEY[:8]
    assert key_start not in result["error"]
    assert key_start not in caplog.text


@pytest.mark.parametrize(
    ("schema", "required"),
    [
        (ChartConfigResponse, ["should_render"]),
        (DataValidationResponse, ["data_found"]),
        (FollowUpResponse, ["questions"]),
    ],
)
def test_each_schema_is_sent_to_gemini_as_expected(
    gemini: _FakeGemini, schema: type[BaseModel], required: list[str]
) -> None:
    # Test: The response schema each workflow sends on the wire.
    # Situation: A structured-output request is made with each of the three
    #   workflow schemas.
    # Expectation: The request carries the required fields and typed
    #   properties, and omits additional_properties (which the Gemini
    #   Developer API rejects with HTTP 400).
    gemini.respond(_answer(200, json=_response_json([{"text": "{}"}])))

    client.gemini_request(_MESSAGES, "", _MODEL, response_schema=schema)

    sent = gemini.body()["generationConfig"]["responseSchema"]
    assert sent["type"] == "OBJECT"
    assert sent["required"] == required
    assert "additional_properties" not in sent
    assert set(sent["properties"]) == set(schema.model_fields)


def test_the_chart_schema_constrains_each_chart_on_the_wire(
    gemini: _FakeGemini,
) -> None:
    # Test: The nested chart item in the chart config schema.
    # Situation: A request is made with the chart config schema.
    # Expectation: Each chart item requires a title, enumerates only the
    #   supported chart types, marks optional fields nullable, and omits
    #   additional_properties.
    gemini.respond(_answer(200, json=_response_json([{"text": "{}"}])))

    client.gemini_request(
        _MESSAGES, "", _MODEL, response_schema=ChartConfigResponse
    )

    charts = gemini.body()["generationConfig"]["responseSchema"]["properties"][
        "charts"
    ]
    item = charts["items"]
    assert charts["nullable"] is True
    assert item["required"] == ["title"]
    assert "additional_properties" not in item
    assert item["properties"]["viz_type"]["enum"] == [
        "line",
        "bar",
        "ranking",
        "pie",
        "highlight",
        "gauge",
        "scatter",
        "slider",
    ]
    assert item["properties"]["viz_type"]["nullable"] is True
    assert item["properties"]["date"]["nullable"] is True


def test_an_empty_response_omits_candidates(gemini: _FakeGemini) -> None:
    # Test: A response with no candidates.
    # Situation: Gemini returns a body with usage metadata but no candidates.
    # Expectation: The result has no "candidates" key, matching the REST
    #   shape that callers test with `"candidates" in response`.
    gemini.respond(_answer(200, json={"usageMetadata": _USAGE}))

    result = client.gemini_request(_MESSAGES, "", _MODEL)

    assert isinstance(result, dict)
    assert "candidates" not in result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode", ["sync_thought_streaming", "async_thought_streaming"]
)
async def test_thought_streaming_forwards_thoughts_and_returns_the_response(
    gemini: _FakeGemini, mode: str
) -> None:
    # Test: Thought streaming with a function call.
    # Situation: The stream delivers two thought chunks, a text chunk, and a
    #   function call carrying a thought signature, with usage on the final
    #   chunk.
    # Expectation: The callback receives each thought in order; the result
    #   holds the function call (with its signature) followed by the text;
    #   the usage is accumulated once; and tools and thinking settings are
    #   sent on a streamGenerateContent request with thoughts included.
    signature = base64.b64encode(_SIGNATURE).decode()
    gemini.respond(
        _answer(
            200,
            content=_sse(
                _response_json([{"text": "Planning ", "thought": True}]),
                _response_json([{"text": "the query.", "thought": True}]),
                _response_json([{"text": "Looking up."}]),
                _response_json(
                    [
                        {
                            "functionCall": {
                                "name": "get_observations",
                                "args": {"place": "geoId/06"},
                            },
                            "thoughtSignature": signature,
                        }
                    ],
                    _USAGE,
                ),
            ),
        )
    )
    thoughts: list[str] = []
    session_logger = _RecordingSessionLogger()
    tool = {
        "name": "get_observations",
        "description": "Fetch observations.",
        "parameters": {
            "type": "object",
            "properties": {"place": {"type": "string"}},
            "required": ["place"],
        },
    }

    result = await _call(
        mode,
        tools=[tool],
        thinking_level="low",
        session_logger=session_logger,
        thought_callback=thoughts.append,
    )

    assert thoughts == ["Planning ", "the query."]
    parts = result["candidates"][0]["content"]["parts"]
    assert parts[0]["functionCall"] == {
        "name": "get_observations",
        "args": {"place": "geoId/06"},
    }
    assert base64.urlsafe_b64decode(parts[0]["thoughtSignature"]) == _SIGNATURE
    assert parts[1] == {"text": "Looking up."}
    assert session_logger.usage == [_USAGE]
    request = gemini.sent[0]
    assert "streamGenerateContent" in request.url.path
    body = gemini.body()
    assert body["tools"][0]["functionDeclarations"][0]["name"] == (
        "get_observations"
    )
    # The SDK sends ThinkingConfig fields in snake_case (see above).
    assert body["generationConfig"]["thinkingConfig"] == {
        "thinking_level": "LOW",
        "include_thoughts": True,
    }


def test_returned_function_call_parts_can_be_sent_back_unchanged(
    gemini: _FakeGemini,
) -> None:
    # Test: Replaying a model turn in the next tool-loop request.
    # Situation: The model's function-call part, returned with a thought
    #   signature, is appended to the history as a model message followed by
    #   a functionResponse, as the MCP loop does.
    # Expectation: The next request carries the same thought signature and
    #   the function response, which Gemini 3 requires to continue the turn.
    signature = base64.b64encode(_SIGNATURE).decode()
    function_call = {
        "functionCall": {"name": "search", "args": {"q": "population"}},
        "thoughtSignature": signature,
    }
    gemini.respond(_answer(200, json=_response_json([function_call])))
    first = client.gemini_request_with_thought_streaming(_MESSAGES, "", _MODEL)
    parts = first["candidates"][0]["content"]["parts"]

    history = [
        *_MESSAGES,
        {"role": "model", "parts": parts},
        {
            "role": "user",
            "parts": [
                {
                    "functionResponse": {
                        "name": "search",
                        "response": {"result": "39M"},
                    }
                }
            ],
        },
    ]
    gemini.respond(_answer(200, json=_response_json([{"text": "39M."}])))
    client.gemini_request_with_thought_streaming(history, "", _MODEL)

    contents = gemini.body()["contents"]
    replayed = contents[1]["parts"][0]
    assert base64.urlsafe_b64decode(replayed["thoughtSignature"]) == _SIGNATURE
    assert replayed["functionCall"]["name"] == "search"
    assert contents[2]["parts"][0]["functionResponse"]["response"] == {
        "result": "39M"
    }


_STREAM_BODY = _sse(
    _response_json([{"text": "Weighing sources.", "thought": True}]),
    _response_json([{"text": "California has "}]),
    _response_json([{"text": "39 million people."}], _USAGE),
)


@pytest.mark.parametrize(
    ("include_thoughts", "expected"),
    [
        (
            True,
            [
                {"type": "thought", "content": "Weighing sources."},
                {"type": "text", "content": "California has "},
                {"type": "text", "content": "39 million people."},
            ],
        ),
        (False, ["California has ", "39 million people."]),
    ],
)
def test_a_sync_stream_yields_text_and_records_usage(
    gemini: _FakeGemini, include_thoughts: bool, expected: list[Any]
) -> None:
    # Test: Synchronous streaming output.
    # Situation: The stream delivers a thought chunk and two text chunks,
    #   with usage on the last.
    # Expectation: When include_thoughts is True, the stream yields
    #   {"type": ..., "content": ...} dicts for both thoughts and text; when
    #   False, it yields only plain text strings. Token usage is recorded once
    #   the stream finishes.
    gemini.respond(_answer(200, content=_STREAM_BODY))
    session_logger = _RecordingSessionLogger()

    stream = client.gemini_request(
        _MESSAGES,
        "",
        _MODEL,
        thinking_level="low",
        stream=True,
        session_logger=session_logger,
        include_thoughts=include_thoughts,
    )

    assert not isinstance(stream, dict)
    assert list(stream) == expected
    assert session_logger.usage == [_USAGE]
    thinking = gemini.body()["generationConfig"]["thinkingConfig"]
    assert thinking.get("include_thoughts", False) is include_thoughts


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("include_thoughts", "expected"),
    [
        (
            True,
            [
                {"type": "thought", "content": "Weighing sources."},
                {"type": "text", "content": "California has "},
                {"type": "text", "content": "39 million people."},
            ],
        ),
        (False, ["California has ", "39 million people."]),
    ],
)
async def test_an_async_stream_yields_text_and_records_usage(
    gemini: _FakeGemini, include_thoughts: bool, expected: list[Any]
) -> None:
    # Test: Asynchronous streaming output.
    # Situation: The stream delivers a thought chunk and two text chunks,
    #   with usage on the last.
    # Expectation: When include_thoughts is True, the stream yields
    #   {"type": ..., "content": ...} dicts for both thoughts and text; when
    #   False, it yields only plain text strings. Token usage is recorded once
    #   the stream finishes.
    gemini.respond(_answer(200, content=_STREAM_BODY))
    session_logger = _RecordingSessionLogger()

    stream = await client.async_gemini_stream(
        _MESSAGES,
        "",
        _MODEL,
        thinking_level="low",
        session_logger=session_logger,
        include_thoughts=include_thoughts,
    )

    assert not isinstance(stream, dict)
    assert [item async for item in stream] == expected
    assert session_logger.usage == [_USAGE]


class _BrokenStream(httpx.SyncByteStream, httpx.AsyncByteStream):
    """A response body that fails after delivering its first chunk."""

    _first = _sse(_response_json([{"text": "California has "}]))
    _error = httpx.ReadError(f"connection reset for ?key={_FAKE_KEY}")

    def __iter__(self) -> Iterator[bytes]:
        yield self._first
        raise self._error

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self._first
        raise self._error


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["sync_stream", "async_stream"])
async def test_a_stream_that_breaks_midway_raises_a_redacted_error(
    gemini: _FakeGemini, caplog: pytest.LogCaptureFixture, mode: str
) -> None:
    # Test: A stream failing after its first chunk.
    # Situation: The connection resets after one text chunk, with the API key
    #   in the transport error message.
    # Expectation: The first chunk is yielded, then iteration raises
    #   GeminiStreamError whose message and log redact the key.
    gemini.respond(_answer(200, stream=_BrokenStream()))

    stream = await _call(mode)
    received: list[Any] = []
    with (
        caplog.at_level(logging.ERROR, logger=client.logger.name),
        pytest.raises(client.GeminiStreamError) as raised,
    ):
        if mode == "sync_stream":
            for item in stream:
                received.append(item)
        else:
            async for item in stream:
                received.append(item)

    assert received == ["California has "]
    assert _FAKE_KEY not in str(raised.value)
    assert "key=[REDACTED]" in str(raised.value)
    assert _FAKE_KEY not in caplog.text


@pytest.mark.parametrize(
    ("value", "include_thoughts", "expected"),
    [
        (
            "HIGH",
            False,
            types.ThinkingConfig(thinking_level=types.ThinkingLevel.HIGH),
        ),
        (
            "Minimal",
            False,
            types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL),
        ),
        (
            "extreme",
            False,
            types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
        ),
        (
            "medium",
            True,
            types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.MEDIUM, include_thoughts=True
            ),
        ),
    ],
)
def test_build_thinking_config_normalizes_the_level(
    value: str, include_thoughts: bool, expected: types.ThinkingConfig
) -> None:
    # Test: Thinking level normalization.
    # Situation: build_thinking_config is called with uppercase, mixed-case,
    #   lowercase, and unrecognized level strings, both with and without
    #   include_thoughts.
    # Expectation: Known levels match case-insensitively, unrecognized values
    #   default to "low", and include_thoughts is set only when True.
    assert client.build_thinking_config(value, include_thoughts) == expected
