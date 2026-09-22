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

import json
import logging
import time
from collections.abc import Callable, Generator

import requests
from requests.adapters import HTTPAdapter

from narratives_agent.config import (
    get_gemini_api_key,
    load_config,
    render_prompt,
)
from narratives_agent.session_logger import SessionLogger

logger = logging.getLogger(__name__)

# Name both Secret Manager and config.json so the error message is actionable
# in both deployed and local environments.
_NO_KEY_ERROR = (
    "No Gemini API key configured: set GEMINI_API_KEY_SECRET, or "
    "gemini.api_key in the agent config for local development"
)

# Shared connection pool for Gemini API requests, sized above the Gunicorn
# worker thread count so concurrent chat turns reuse TLS connections without
# blocking.
_SESSION = requests.Session()
_SESSION.mount("https://", HTTPAdapter(pool_connections=8, pool_maxsize=64))


def _status_error(status_code: int) -> str | None:
    """Return a descriptive error string for HTTP 429, 500, or 503 responses."""
    if status_code == 429:
        return "Rate limited (429)"
    if status_code in (500, 503):
        return f"Server error ({status_code})"
    return None


def _report_failure(
    error: str, model: str, session_logger: SessionLogger | None
) -> dict:
    """Log a failed Gemini call and shape it as the caller's error dict."""
    logger.error(f"Gemini request failed: {error}")
    if session_logger:
        session_logger.log_error(
            "GEMINI_REQUEST_FAILED", error, {"model": model}
        )
    return {"error": error}


def build_thinking_config(
    thinking_value: str, include_thoughts: bool = False
) -> dict:
    """Build thinking configuration for Gemini 3 models.

    Args:
        thinking_value: Thinking level ('minimal', 'low', 'medium', 'high')
        include_thoughts: If True, includes thought summaries in the response

    Returns:
        dict: thinkingConfig for Gemini generationConfig
    """
    # Gemini 3 Flash valid levels
    valid_levels = ["minimal", "low", "medium", "high"]
    level = (
        thinking_value.lower()
        if thinking_value.lower() in valid_levels
        else "low"
    )

    config = {
        "thinkingConfig": {
            "thinkingLevel": level  # Gemini 3 format (string)
        }
    }

    if include_thoughts:
        config["thinkingConfig"]["includeThoughts"] = True

    return config


def gemini_request(
    messages: list,
    system_instruction: str,
    model: str,
    tools: list | None = None,
    temperature: float = 0.3,
    thinking_level: str | None = None,
    response_schema: dict | None = None,
    stream: bool = False,
    session_logger: SessionLogger | None = None,
    include_thoughts: bool = False,
) -> Generator | dict:
    """Make a request to the Gemini API.

    Args:
        messages: Conversation history in Gemini format
        system_instruction: System prompt
        model: Model name (e.g., 'gemini-3-flash-preview')
        tools: Optional list of function declarations
        temperature: Sampling temperature
        thinking_level: Optional thinking budget level
        response_schema: Optional JSON schema for structured output
        stream: If True, returns a generator for SSE streaming
        session_logger: Optional SessionLogger for comprehensive logging
        include_thoughts: If True (and stream=True), yields dicts with 'type'
                         and 'content' for both thoughts and text. If False,
                         yields plain text strings.

    Returns:
        If stream=False: dict with response
        If stream=True and include_thoughts=False: Generator yielding text
            chunks (str)
        If stream=True and include_thoughts=True: Generator yielding dicts
            {'type': 'thought'|'text', 'content': str}
        On failure, in either mode: dict with an 'error' key.
    """
    config = load_config()
    api_base = config.get("gemini", {}).get(
        "api_base", "https://generativelanguage.googleapis.com/v1beta/models"
    )

    api_key = get_gemini_api_key()
    if not api_key:
        return _report_failure(_NO_KEY_ERROR, model, session_logger)

    # Build the payload
    payload = {
        "contents": messages,
        "generationConfig": {
            "temperature": temperature,
        },
    }

    if system_instruction:
        payload["systemInstruction"] = {
            "parts": [{"text": render_prompt(system_instruction)}]
        }

    if tools:
        payload["tools"] = [{"functionDeclarations": tools}]

    if thinking_level:
        # Enable includeThoughts in API if caller wants thought streaming
        payload["generationConfig"].update(
            build_thinking_config(
                thinking_level, include_thoughts=(stream and include_thoughts)
            )
        )

    if response_schema:
        payload["generationConfig"]["responseMimeType"] = "application/json"
        payload["generationConfig"]["responseSchema"] = response_schema

    endpoint = "streamGenerateContent" if stream else "generateContent"

    # Log request
    if session_logger:
        session_logger.log_gemini_request(
            model,
            endpoint,
            {
                "messages_count": len(messages),
                "has_tools": bool(tools),
                "tool_count": len(tools) if tools else 0,
                "temperature": temperature,
                "thinking_level": thinking_level,
                "has_response_schema": bool(response_schema),
                "stream": stream,
            },
        )

    url = f"{api_base}/{model}:{endpoint}?key={api_key}"
    if stream:
        url += "&alt=sse"

    start_time = time.time()

    try:
        if stream:
            response = _SESSION.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                stream=True,
                timeout=300,
            )
            # Check the HTTP status before streaming because error responses
            # return a JSON body rather than SSE frames.
            status_error = _status_error(response.status_code)
            if status_error:
                return _report_failure(status_error, model, session_logger)
            return _stream_gemini_response(
                response, session_logger, return_dicts=include_thoughts
            )

        response = _SESSION.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=300,
        )

        status_error = _status_error(response.status_code)
        if status_error:
            return _report_failure(status_error, model, session_logger)

        result = response.json()

        # Log response
        if session_logger:
            duration_ms = (time.time() - start_time) * 1000
            session_logger.log_gemini_response(model, result, duration_ms)
            session_logger.add_usage(result.get("usageMetadata"))

        return result

    except requests.exceptions.Timeout:
        return _report_failure("Request timeout", model, session_logger)
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        if session_logger:
            session_logger.log_error(
                "GEMINI_API_ERROR", str(e), {"model": model}
            )
        return {"error": str(e)}


def _stream_gemini_response(
    response,
    session_logger: SessionLogger | None = None,
    return_dicts: bool = False,
) -> Generator:
    """Parse streaming response from Gemini API.

    Args:
        response: The requests response object with streaming enabled
        session_logger: Optional SessionLogger for logging
        return_dicts: If True, yields dicts with 'type' and 'content' keys
                      for both thoughts and text. If False, yields plain
                      text strings.

    Yields:
        If return_dicts=True: {'type': 'thought'|'text', 'content': str}
        If return_dicts=False: str (text only, for backward compatibility)
    """
    start_time = time.time()
    total_text = ""
    total_thoughts = ""
    usage_metadata = None

    for line in response.iter_lines():
        if line:
            line_str = line.decode("utf-8")
            if line_str.startswith("data: "):
                try:
                    data = json.loads(line_str[6:])
                    # Token counts arrive on the final SSE chunk (cumulative for
                    # this call); keep the latest seen.
                    if "usageMetadata" in data:
                        usage_metadata = data["usageMetadata"]
                    if data.get("candidates"):
                        candidate = data["candidates"][0]
                        if (
                            "content" in candidate
                            and "parts" in candidate["content"]
                        ):
                            for part in candidate["content"]["parts"]:
                                if "text" in part:
                                    # Check if this is a thought summary or
                                    # regular text
                                    is_thought = part.get("thought", False)
                                    if is_thought:
                                        total_thoughts += part["text"]
                                        if return_dicts:
                                            yield {
                                                "type": "thought",
                                                "content": part["text"],
                                            }
                                        # Skip thoughts in legacy mode
                                        # (return_dicts=False)
                                    else:
                                        total_text += part["text"]
                                        if return_dicts:
                                            yield {
                                                "type": "text",
                                                "content": part["text"],
                                            }
                                        else:
                                            yield part["text"]
                except json.JSONDecodeError:
                    continue

    # Accumulate this call's token usage into the request total.
    if session_logger:
        session_logger.add_usage(usage_metadata)

    # Log streaming completion
    if session_logger:
        duration_ms = (time.time() - start_time) * 1000
        session_logger.log(
            "GEMINI_STREAM_COMPLETE",
            {
                "duration_ms": round(duration_ms, 2),
                "total_text_length": len(total_text),
                "total_thoughts_length": len(total_thoughts),
            },
        )


def gemini_request_with_thought_streaming(
    messages: list,
    system_instruction: str,
    model: str,
    tools: list | None = None,
    temperature: float = 0.3,
    thinking_level: str | None = None,
    response_schema: dict | None = None,
    session_logger: SessionLogger | None = None,
    thought_callback: Callable[[str], None] | None = None,
) -> dict:
    """Make a streaming Gemini request, calling thought_callback for thoughts
    but returning complete response.

    This enables thought streaming for reduced TTFT while still getting the
    complete response needed for tool call processing.

    Args:
        messages: Conversation history in Gemini format
        system_instruction: System prompt
        model: Model name (e.g., 'gemini-3-flash-preview')
        tools: Optional list of function declarations
        temperature: Sampling temperature
        thinking_level: Optional thinking budget level
        response_schema: Optional JSON schema for structured output
        session_logger: Optional SessionLogger for comprehensive logging
        thought_callback: Optional callback function called with each
                         thought chunk.
                         Signature: callback(thought_text: str) -> None

    Returns:
        dict: Complete response (same format as non-streaming gemini_request),
            or a dict with an 'error' key if the call failed.
    """
    config = load_config()
    api_base = config.get("gemini", {}).get(
        "api_base", "https://generativelanguage.googleapis.com/v1beta/models"
    )

    api_key = get_gemini_api_key()
    if not api_key:
        return _report_failure(_NO_KEY_ERROR, model, session_logger)

    # Build payload
    payload = {
        "contents": messages,
        "generationConfig": {
            "temperature": temperature,
        },
    }

    if system_instruction:
        payload["systemInstruction"] = {
            "parts": [{"text": render_prompt(system_instruction)}]
        }

    if tools:
        payload["tools"] = [{"functionDeclarations": tools}]

    if thinking_level:
        # Enable includeThoughts for streaming thought summaries
        payload["generationConfig"].update(
            build_thinking_config(thinking_level, include_thoughts=True)
        )

    if response_schema:
        payload["generationConfig"]["responseMimeType"] = "application/json"
        payload["generationConfig"]["responseSchema"] = response_schema

    # Log request
    if session_logger:
        session_logger.log_gemini_request(
            model,
            "streamGenerateContent",
            {
                "messages_count": len(messages),
                "has_tools": bool(tools),
                "tool_count": len(tools) if tools else 0,
                "temperature": temperature,
                "thinking_level": thinking_level,
                "include_thoughts": True,
            },
        )

    url = f"{api_base}/{model}:streamGenerateContent?key={api_key}&alt=sse"

    start_time = time.time()

    try:
        response = _SESSION.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            stream=True,
            timeout=300,
        )

        # Check the HTTP status before streaming because error responses
        # return a JSON body rather than SSE frames.
        status_error = _status_error(response.status_code)
        if status_error:
            return _report_failure(status_error, model, session_logger)

        # Collect response while streaming thoughts
        collected_text = ""
        collected_function_calls = []
        collected_thoughts = ""
        collected_usage = None

        for line in response.iter_lines():
            if line:
                line_str = line.decode("utf-8")
                if line_str.startswith("data: "):
                    try:
                        data = json.loads(line_str[6:])
                        if "usageMetadata" in data:
                            collected_usage = data["usageMetadata"]
                        if data.get("candidates"):
                            candidate = data["candidates"][0]
                            if (
                                "content" in candidate
                                and "parts" in candidate["content"]
                            ):
                                for part in candidate["content"]["parts"]:
                                    if "functionCall" in part:
                                        collected_function_calls.append(part)
                                    elif "text" in part:
                                        is_thought = part.get("thought", False)
                                        if is_thought:
                                            collected_thoughts += part["text"]
                                            if thought_callback:
                                                thought_callback(part["text"])
                                        else:
                                            collected_text += part["text"]
                    except json.JSONDecodeError:
                        continue

        # Accumulate this call's token usage into the request total.
        if session_logger:
            session_logger.add_usage(collected_usage)

        # Build response in same format as non-streaming
        result_parts = []
        for fc in collected_function_calls:
            result_parts.append(fc)
        if collected_text:
            result_parts.append({"text": collected_text})

        result = {
            "candidates": [
                {"content": {"parts": result_parts, "role": "model"}}
            ]
        }

        # Log response
        if session_logger:
            duration_ms = (time.time() - start_time) * 1000
            session_logger.log_gemini_response(model, result, duration_ms)
            if collected_thoughts:
                session_logger.log(
                    "THOUGHTS_STREAMED",
                    {"thoughts_length": len(collected_thoughts)},
                )

        return result

    except requests.exceptions.Timeout:
        return _report_failure("Request timeout", model, session_logger)
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        if session_logger:
            session_logger.log_error(
                "GEMINI_API_ERROR", str(e), {"model": model}
            )
        return {"error": str(e)}
