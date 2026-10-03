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
"""Gemini model client built on the official `google-genai` SDK.

The client authenticates in one of two modes. When
`GOOGLE_GENAI_USE_VERTEXAI` is true it calls Vertex AI with Application
Default Credentials against `GOOGLE_CLOUD_PROJECT` and
`GOOGLE_CLOUD_LOCATION`; otherwise it calls the Gemini Developer API with the
key that `get_gemini_api_key()` resolves.

Every Gemini operation is asynchronous and shares the code that builds
requests, parses responses, counts tokens, and reports errors:
`async_gemini_request`, `async_gemini_stream`, and
`async_gemini_request_with_thought_streaming`. Each accepts an optional
`TokenUsage` to which the call's token counts are added, for the turn's
telemetry record.

The SDK returns response objects, but the code in `workflows/` (the model loop)
reads responses as plain dictionaries, for example
`response["candidates"][0]["content"]["parts"][0]["text"]`. Every function
therefore converts the SDK's response into a dictionary with the keys the
Gemini REST API uses (`candidates`, `content`, `parts`, `functionCall`,
`usageMetadata`).

Errors are reported in one of two ways:

- If the request fails before Gemini returns any output, the function returns
  `{"error": <message>}`.
- If a streamed response fails after output has started, the stream raises
  `GeminiStreamError`, because the caller already holds the stream and can no
  longer receive a returned value.

In both cases, the API key is removed from the error message.
"""

import asyncio
import copy
import logging
import re
import threading
from collections.abc import (
    AsyncGenerator,
    AsyncIterator,
    Callable,
    Sequence,
)
from dataclasses import dataclass, field
from typing import Any, NamedTuple

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from narratives_agent.config import get_gemini_api_key, render_prompt
from narratives_agent.settings import get_settings
from narratives_agent.telemetry import TokenUsage

logger = logging.getLogger(__name__)

# Name both Secret Manager and config.json so the error message is actionable
# in both deployed and local environments.
_NO_KEY_ERROR = (
    "No Gemini API key configured: set GEMINI_API_KEY_SECRET, or "
    "gemini.api_key in the agent config for local development"
)

_NO_PROJECT_ERROR = (
    "Vertex AI mode is enabled by GOOGLE_GENAI_USE_VERTEXAI, but the "
    "GOOGLE_CLOUD_PROJECT environment variable is not set"
)

_THINKING_LEVELS = {
    "low": types.ThinkingLevel.LOW,
    "medium": types.ThinkingLevel.MEDIUM,
    "high": types.ThinkingLevel.HIGH,
}
_DEFAULT_THINKING_LEVEL = "low"

# Thinking level for the small structured calls that run after the answer:
# chart configuration, chart validation, and follow-up questions.
LIGHTWEIGHT_THINKING_LEVEL = "low"

# Upper bound on a single Gemini call, including a full streamed response.
# `HttpOptions.timeout` is in milliseconds.
_REQUEST_TIMEOUT_MS = 300_000  # 5 minutes

# All Gemini calls share one SDK client so that they reuse open TLS
# connections instead of opening a new one for each call. The keep-alive pool
# is larger than the number of calls an instance makes at the same time,
# so no connection is discarded under load.
_CONNECTION_LIMITS = httpx.Limits(max_keepalive_connections=64)

# Maximum characters of an upstream error body included in the returned error
# string and log message.
_ERROR_BODY_LENGTH = 500

# Redact `key=...` query parameters from upstream error bodies so API keys
# echoed by intermediate proxies or frontends are never logged or streamed to
# the browser.
_CREDENTIAL_PATTERN = re.compile(r"\bkey=[^&\s\"'<>]*", re.IGNORECASE)
_REDACTED = "[REDACTED]"
_CREDENTIAL_REPLACEMENT = f"key={_REDACTED}"

type Message = types.Content | dict[str, Any]
type ResponseSchema = type[BaseModel] | dict[str, Any]
type StreamItem = dict[str, str] | str


class _ClientKey(NamedTuple):
    """The credential inputs that select a cached SDK client."""

    # Whether to call Vertex AI with Application Default Credentials (`True`)
    # or the Gemini Developer API with `api_key` (`False`).
    use_vertexai: bool
    # GCP project ID for Vertex AI calls; empty in API-key mode.
    project: str = ""
    # GCP region for Vertex AI calls (for example, `"us-central1"`); empty in
    # API-key mode.
    location: str = ""
    # Resolved raw Gemini API key (already read from Secret Manager or
    # `config.json` by `get_gemini_api_key()`); empty in Vertex AI mode.
    api_key: str = ""


_client_lock = threading.Lock()
_cached_client: tuple[_ClientKey, genai.Client] | None = None


class GeminiStreamError(RuntimeError):
    """Raised when a stream fails after its first chunk was delivered.

    The message is the same redacted error string that `_report_failure`
    logs.
    """


def reset_client() -> None:
    """Discards the cached SDK client so the next call builds a new one."""
    global _cached_client
    with _client_lock:
        _cached_client = None


def _build_client(key: _ClientKey) -> genai.Client:
    """Builds an SDK client for the given credential selection."""
    http_options = types.HttpOptions(
        timeout=_REQUEST_TIMEOUT_MS,
        client_args={"limits": _CONNECTION_LIMITS},
        async_client_args={"limits": _CONNECTION_LIMITS},
    )
    if key.use_vertexai:
        return genai.Client(
            vertexai=True,
            project=key.project,
            location=key.location,
            http_options=http_options,
        )
    return genai.Client(
        vertexai=False, api_key=key.api_key, http_options=http_options
    )


async def _get_client() -> genai.Client | str:
    """Returns the shared SDK client, or an error when credentials are absent.

    The client is rebuilt only when the credential selection changes, so its
    connection pools survive across calls. In API-key mode the key is
    resolved in a worker thread, because a cold cache makes a blocking
    Secret Manager request that would otherwise stall the event loop.
    """
    global _cached_client
    settings = get_settings()
    if settings.google_genai_use_vertexai:
        if not settings.google_cloud_project:
            return _NO_PROJECT_ERROR
        key = _ClientKey(
            use_vertexai=True,
            project=settings.google_cloud_project,
            location=settings.google_cloud_location,
        )
    else:
        api_key = await asyncio.to_thread(get_gemini_api_key)
        if not api_key:
            return _NO_KEY_ERROR
        key = _ClientKey(use_vertexai=False, api_key=api_key)

    with _client_lock:
        if _cached_client is None or _cached_client[0] != key:
            # The replaced client is not closed here, because a call in another
            # thread may still be using it. `genai.Client` closes its
            # connection pools when the last reference to it is dropped.
            _cached_client = (key, _build_client(key))
        return _cached_client[1]


def _active_api_key() -> str:
    """Returns the API key of the cached client, or "" in Vertex AI mode."""
    with _client_lock:
        return _cached_client[0].api_key if _cached_client else ""


def _redact(text: str) -> str:
    """Returns `text` with every `key=...` credential replaced.

    The active API key is also replaced wherever it appears, because the SDK
    sends it in the `x-goog-api-key` header, which a proxy may echo in a form
    the `key=` pattern does not match.
    """
    redacted = _CREDENTIAL_PATTERN.sub(_CREDENTIAL_REPLACEMENT, text)
    api_key = _active_api_key()
    if api_key:
        redacted = redacted.replace(api_key, _REDACTED)
    return redacted


def _describe_error(error: Exception) -> str:
    """Returns the caller-facing message for a failed Gemini call."""
    if isinstance(error, errors.APIError):
        code = error.code
        if code == 429:
            return "Rate limited (429)"
        if 500 <= code < 600:
            return f"Server error ({code})"
        # Redact before truncating: a cut through the middle of an echoed
        # key would leave a partial key that no longer matches.
        return f"HTTP {code}: {_redact(str(error))[:_ERROR_BODY_LENGTH]}"
    if isinstance(error, (httpx.TimeoutException, TimeoutError)):
        return "Request timeout"
    if isinstance(error, ValidationError):
        # str(error) quotes the invalid input, which can be user message text,
        # so report only where validation failed.
        locations = [
            ".".join(str(step) for step in detail["loc"])
            for detail in error.errors()
        ]
        return (
            f"Invalid Gemini request: {error.error_count()} validation "
            f"error(s) at {locations}"
        )
    return str(error)


def _report_failure(error: str, model: str) -> dict[str, Any]:
    """Logs a failed Gemini call with credentials redacted.

    Returns:
        A dict whose only key, "error", holds the redacted message.
    """
    redacted = _redact(error)
    logger.error("Gemini request to %s failed: %s", model, redacted)
    return {"error": redacted}


def build_thinking_config(
    thinking_value: str, include_thoughts: bool = False
) -> types.ThinkingConfig:
    """Builds the thinking configuration for Gemini 3 models.

    Args:
        thinking_value: Thinking level: "low", "medium", or "high", in any
            case. Any other value selects "low".
        include_thoughts: Whether the response includes thought summaries.

    Returns:
        The `ThinkingConfig` for `GenerateContentConfig`.
    """
    level = _THINKING_LEVELS.get(
        thinking_value.lower(), _THINKING_LEVELS[_DEFAULT_THINKING_LEVEL]
    )
    return types.ThinkingConfig(
        thinking_level=level,
        include_thoughts=True if include_thoughts else None,
    )


def _normalize_messages(messages: Sequence[Message]) -> list[types.Content]:
    """Converts REST-shaped message dicts into SDK `Content` objects.

    The SDK models accept the REST field names (`functionCall`,
    `functionResponse`, `thoughtSignature`), so parts returned by this module
    can be sent back unchanged on the next turn of a tool loop.
    """
    return [
        message
        if isinstance(message, types.Content)
        else types.Content.model_validate(message)
        for message in messages
    ]


def _normalize_tools(
    tools: Sequence[dict[str, Any]] | None,
) -> types.ToolListUnion | None:
    """Wraps function-declaration dicts in a single SDK `Tool`."""
    if not tools:
        return None
    declarations = [
        types.FunctionDeclaration.model_validate(tool) for tool in tools
    ]
    return [types.Tool(function_declarations=declarations)]


def _build_config(
    system_instruction: str,
    tools: Sequence[dict[str, Any]] | None,
    temperature: float,
    thinking_level: str | None,
    response_schema: ResponseSchema | None,
    include_thoughts: bool,
) -> types.GenerateContentConfig:
    """Builds the `GenerateContentConfig` shared by every entry point."""
    thinking_config: types.ThinkingConfig | None = None
    if thinking_level:
        thinking_config = build_thinking_config(
            thinking_level, include_thoughts
        )
    elif include_thoughts:
        # No level given: request thought summaries only, so the model keeps
        # its own default thinking level.
        thinking_config = types.ThinkingConfig(include_thoughts=True)
    return types.GenerateContentConfig(
        temperature=temperature,
        system_instruction=(
            render_prompt(system_instruction) if system_instruction else None
        ),
        tools=_normalize_tools(tools),
        thinking_config=thinking_config,
        response_mime_type=(
            "application/json" if response_schema is not None else None
        ),
        # The SDK rewrites a dict schema in place while converting it, so it
        # receives a copy and the caller's schema stays reusable.
        response_schema=(
            copy.deepcopy(response_schema)
            if isinstance(response_schema, dict)
            else response_schema
        ),
        # Tools are MCP function declarations executed by the workflows, not
        # Python callables, so the SDK must never try to run them itself.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(
            disable=True
        ),
    )


@dataclass(frozen=True)
class _GeminiCall:
    """A validated request, ready to send."""

    client: genai.Client
    model: str
    contents: list[types.Content]
    config: types.GenerateContentConfig


async def _prepare_call(
    messages: Sequence[Message],
    system_instruction: str,
    model: str,
    tools: Sequence[dict[str, Any]] | None,
    temperature: float,
    thinking_level: str | None,
    response_schema: ResponseSchema | None,
    include_thoughts: bool,
) -> _GeminiCall | dict[str, Any]:
    """Resolves the client and builds the request, or reports why it cannot.

    Returns:
        The prepared call, or an error dict when credentials are missing or
        the messages, tools, or schema do not validate.
    """
    client = await _get_client()
    if isinstance(client, str):
        return _report_failure(client, model)
    try:
        contents = _normalize_messages(messages)
        config = _build_config(
            system_instruction,
            tools,
            temperature,
            thinking_level,
            response_schema,
            include_thoughts,
        )
    except Exception as error:
        return _report_failure(_describe_error(error), model)
    return _GeminiCall(client, model, contents, config)


def _dump_part(part: types.Part) -> dict[str, Any]:
    """Serializes an SDK `types.Part` in REST shape, keeping any signature."""
    return part.model_dump(mode="json", by_alias=True, exclude_none=True)


def _chunk_parts(response: types.GenerateContentResponse) -> list[types.Part]:
    """Returns the parts of a response's first candidate."""
    if not response.candidates:
        return []
    content = response.candidates[0].content
    if content is None or not content.parts:
        return []
    return list(content.parts)


def _usage_dict(
    usage: types.GenerateContentResponseUsageMetadata | None,
) -> dict[str, int] | None:
    """Returns token counts under the REST `usageMetadata` key names."""
    if usage is None:
        return None
    return {
        "promptTokenCount": usage.prompt_token_count or 0,
        "candidatesTokenCount": usage.candidates_token_count or 0,
        "thoughtsTokenCount": usage.thoughts_token_count or 0,
        "totalTokenCount": usage.total_token_count or 0,
    }


def _normalize_response(
    response: types.GenerateContentResponse,
) -> dict[str, Any]:
    """Converts an SDK response into the REST-shaped dict.

    `candidates` is omitted when the model returned none, as the REST API
    omits it, so callers that test `"candidates" in response` still detect
    the empty result.
    """
    result: dict[str, Any] = {}
    candidates = []
    for candidate in response.candidates or []:
        content = candidate.content or types.Content()
        parts = [_dump_part(part) for part in content.parts or []]
        role = content.role or "model"
        candidates.append({"content": {"parts": parts, "role": role}})
    if candidates:
        result["candidates"] = candidates
    usage = _usage_dict(response.usage_metadata)
    if usage:
        result["usageMetadata"] = usage
    return result


def _record_usage(
    token_usage: TokenUsage | None, usage: dict[str, int] | None
) -> None:
    """Adds one call's token counts to the turn's totals, if tracked."""
    if token_usage is not None:
        token_usage.add(usage)


@dataclass
class _TextStream:
    """Turns streamed chunks into text items.

    With `return_dicts`, both thoughts and text are emitted as
    `{"type": "thought" | "text", "content": str}`; without it, only text is
    emitted, as plain strings.
    """

    return_dicts: bool
    usage: dict[str, int] | None = None

    def items(self, chunk: types.GenerateContentResponse) -> list[StreamItem]:
        """Returns the items to emit for one chunk."""
        # Token counts arrive on the final chunk (cumulative for this call);
        # keep the latest seen.
        self.usage = _usage_dict(chunk.usage_metadata) or self.usage
        items: list[StreamItem] = []
        for part in _chunk_parts(chunk):
            if not part.text:
                continue
            if part.thought:
                if self.return_dicts:
                    items.append({"type": "thought", "content": part.text})
            else:
                items.append(
                    {"type": "text", "content": part.text}
                    if self.return_dicts
                    else part.text
                )
        return items


@dataclass
class _ThoughtStreamCollector:
    """Assembles a complete response from chunks, forwarding thoughts."""

    thought_callback: Callable[[str], None] | None
    text: str = ""
    function_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] | None = None

    def add(self, chunk: types.GenerateContentResponse) -> None:
        """Accumulates one chunk and forwards any thought text."""
        self.usage = _usage_dict(chunk.usage_metadata) or self.usage
        for part in _chunk_parts(chunk):
            if part.function_call:
                self.function_calls.append(_dump_part(part))
            elif part.text:
                if part.thought:
                    if self.thought_callback:
                        self.thought_callback(part.text)
                else:
                    self.text += part.text

    def finish(self) -> dict[str, Any]:
        """Returns the assembled response.

        A stream that produced neither a function call nor answer text (such
        as an empty or safety-blocked reply) is returned without `candidates`,
        matching the non-streamed response shape so callers can distinguish it
        from a normal final reply.
        """
        parts = list(self.function_calls)
        if self.text:
            parts.append({"text": self.text})
        result: dict[str, Any] = {}
        if parts:
            result["candidates"] = [
                {"content": {"parts": parts, "role": "model"}}
            ]
        if self.usage:
            result["usageMetadata"] = self.usage
        return result


async def _close_chunks(
    chunks: AsyncIterator[types.GenerateContentResponse] | None,
) -> None:
    """Closes the SDK's chunk iterator once the caller stops reading it.

    Closing the iterator explicitly releases its HTTP response as soon as
    reading stops, for example when the caller raises between chunks, rather
    than when the garbage collector finalizes the iterator.
    """
    close = getattr(chunks, "aclose", None)
    if close is not None:
        await close()


async def _async_iterate_stream(
    first: types.GenerateContentResponse | None,
    chunks: AsyncIterator[types.GenerateContentResponse],
    stream: _TextStream,
    model: str,
    token_usage: TokenUsage | None,
) -> AsyncGenerator[StreamItem]:
    """Yields items from a stream whose first chunk was already fetched.

    Token usage is recorded when the stream ends, whether it completes,
    fails, or is closed early by the consumer, so a canceled turn still
    accounts for the tokens it spent. The SDK's chunk iterator is closed at
    the same point.
    """
    try:
        if first is not None:
            for item in stream.items(first):
                yield item
        async for chunk in chunks:
            for item in stream.items(chunk):
                yield item
    except Exception as error:
        report = _report_failure(_describe_error(error), model)
        raise GeminiStreamError(report["error"]) from error
    finally:
        _record_usage(token_usage, stream.usage)
        await _close_chunks(chunks)


async def async_gemini_request(
    messages: Sequence[Message],
    system_instruction: str,
    model: str,
    tools: Sequence[dict[str, Any]] | None = None,
    temperature: float = 0.3,
    thinking_level: str | None = None,
    response_schema: ResponseSchema | None = None,
    token_usage: TokenUsage | None = None,
) -> dict[str, Any]:
    """Sends a request to Gemini without blocking the event loop.

    Args:
        messages: Conversation history as REST-shaped dicts or `Content`.
        system_instruction: System prompt, rendered with `render_prompt`.
        model: Model name, such as "gemini-3-flash-preview".
        tools: Optional function declarations, each a dict with "name",
            "description", and "parameters".
        temperature: Sampling temperature.
        thinking_level: Optional thinking level.
        response_schema: Optional Pydantic model or JSON schema for
            structured output.
        token_usage: Optional turn totals to which this call's token counts
            are added.

    Returns:
        The response dict, or a dict with an "error" key if the call failed.
    """
    call = await _prepare_call(
        messages,
        system_instruction,
        model,
        tools,
        temperature,
        thinking_level,
        response_schema,
        include_thoughts=False,
    )
    if isinstance(call, dict):
        return call
    try:
        response = await call.client.aio.models.generate_content(
            model=model, contents=call.contents, config=call.config
        )
    except Exception as error:
        return _report_failure(_describe_error(error), model)
    result = _normalize_response(response)
    _record_usage(token_usage, result.get("usageMetadata"))
    return result


async def async_gemini_stream(
    messages: Sequence[Message],
    system_instruction: str,
    model: str,
    tools: Sequence[dict[str, Any]] | None = None,
    temperature: float = 0.3,
    thinking_level: str | None = None,
    response_schema: ResponseSchema | None = None,
    token_usage: TokenUsage | None = None,
    include_thoughts: bool = False,
) -> AsyncGenerator[StreamItem] | dict[str, Any]:
    """Starts a streamed request to Gemini without blocking the event loop.

    The coroutine completes once the first chunk has arrived, so a request
    that fails outright is reported as an error dict rather than surfacing
    partway through iteration.

    Args:
        messages: Conversation history as REST-shaped dicts or `Content`.
        system_instruction: System prompt, rendered with `render_prompt`.
        model: Model name, such as "gemini-3-flash-preview".
        tools: Optional function declarations.
        temperature: Sampling temperature.
        thinking_level: Optional thinking level.
        response_schema: Optional Pydantic model or JSON schema for
            structured output.
        token_usage: Optional turn totals to which this call's token counts
            are added when the stream ends.
        include_thoughts: Whether to yield thought summaries as well as text.

    Returns:
        An async generator yielding text strings, or `{"type": "thought" |
        "text", "content": str}` dicts with `include_thoughts`; it raises
        `GeminiStreamError` if the stream fails after its first chunk. If
        the request fails before then, a dict with an "error" key.
    """
    call = await _prepare_call(
        messages,
        system_instruction,
        model,
        tools,
        temperature,
        thinking_level,
        response_schema,
        include_thoughts=include_thoughts,
    )
    if isinstance(call, dict):
        return call
    chunks: AsyncIterator[types.GenerateContentResponse] | None = None
    try:
        chunks = await call.client.aio.models.generate_content_stream(
            model=model, contents=call.contents, config=call.config
        )
        # The SDK sends the request when the first chunk is requested, so
        # fetch it here to report a failed request as an error dict.
        first = await anext(chunks, None)
    except BaseException as error:
        await _close_chunks(chunks)
        if isinstance(error, Exception):
            return _report_failure(_describe_error(error), model)
        raise
    return _async_iterate_stream(
        first,
        chunks,
        _TextStream(return_dicts=include_thoughts),
        model,
        token_usage,
    )


async def async_gemini_request_with_thought_streaming(
    messages: Sequence[Message],
    system_instruction: str,
    model: str,
    tools: Sequence[dict[str, Any]] | None = None,
    temperature: float = 0.3,
    thinking_level: str | None = None,
    response_schema: ResponseSchema | None = None,
    token_usage: TokenUsage | None = None,
    thought_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Streams a request without blocking, forwarding thoughts as they arrive.

    Thought summaries reach `thought_callback` while the response streams,
    which shortens time to first output, and the complete response is still
    returned for tool-call processing.

    Args:
        messages: Conversation history as REST-shaped dicts or `Content`.
        system_instruction: System prompt, rendered with `render_prompt`.
        model: Model name, such as "gemini-3-flash-preview".
        tools: Optional function declarations.
        temperature: Sampling temperature.
        thinking_level: Optional thinking level.
        response_schema: Optional Pydantic model or JSON schema for
            structured output.
        token_usage: Optional turn totals to which this call's token counts
            are added.
        thought_callback: Optional callable invoked with each thought chunk.

    Returns:
        The complete response dict, or a dict with an "error" key if the
        call failed.
    """
    call = await _prepare_call(
        messages,
        system_instruction,
        model,
        tools,
        temperature,
        thinking_level,
        response_schema,
        include_thoughts=True,
    )
    if isinstance(call, dict):
        return call
    collector = _ThoughtStreamCollector(thought_callback)
    chunks: AsyncIterator[types.GenerateContentResponse] | None = None
    try:
        chunks = await call.client.aio.models.generate_content_stream(
            model=model, contents=call.contents, config=call.config
        )
        async for chunk in chunks:
            collector.add(chunk)
    except Exception as error:
        return _report_failure(_describe_error(error), model)
    finally:
        _record_usage(token_usage, collector.usage)
        await _close_chunks(chunks)
    return collector.finish()
