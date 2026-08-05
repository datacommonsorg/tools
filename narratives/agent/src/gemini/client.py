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
import random
import time
from typing import Generator, Optional

import requests

from src.config import get_api_keys, inject_datetime, load_config
from src.session_logger import SessionLogger

logger = logging.getLogger(__name__)


def build_thinking_config(thinking_value: str, include_thoughts: bool = False) -> dict:
    """Build thinking configuration for Gemini 3 models.

    Args:
        thinking_value: Thinking level ('minimal', 'low', 'medium', 'high')
        include_thoughts: If True, includes thought summaries in the response

    Returns:
        dict: thinkingConfig for Gemini generationConfig
    """
    # Gemini 3 Flash valid levels
    valid_levels = ["minimal", "low", "medium", "high"]
    level = thinking_value.lower() if thinking_value.lower() in valid_levels else "low"

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
    tools: list = None,
    temperature: float = 0.3,
    thinking_level: str = None,
    response_schema: dict = None,
    stream: bool = False,
    session_logger: Optional[SessionLogger] = None,
    include_thoughts: bool = False,
    demo_mode: bool = False
) -> Generator | dict:
    """Make a request to the Gemini API with key rotation and retry.

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
        include_thoughts: If True (and stream=True), yields dicts with 'type' and 'content'
                         for both thoughts and text. If False, yields plain text strings.
        demo_mode: If True, uses demo API keys reserved for internal demos.

    Returns:
        If stream=False: dict with response
        If stream=True and include_thoughts=False: Generator yielding text chunks (str)
        If stream=True and include_thoughts=True: Generator yielding dicts {'type': 'thought'|'text', 'content': str}
    """
    config = load_config()
    api_base = config.get("gemini", {}).get("api_base", "https://generativelanguage.googleapis.com/v1beta/models")

    # Get all available keys (demo or regular based on mode)
    all_keys = get_api_keys(demo_mode=demo_mode)
    if not all_keys:
        return {"error": "No Gemini API keys configured in config.json"}

    # Shuffle keys for random order
    keys_to_try = all_keys.copy()
    random.shuffle(keys_to_try)

    # Build the payload (same for all attempts)
    payload = {
        "contents": messages,
        "generationConfig": {
            "temperature": temperature,
        }
    }

    if system_instruction:
        payload["systemInstruction"] = {
            "parts": [{"text": inject_datetime(system_instruction)}]
        }

    if tools:
        payload["tools"] = [{"functionDeclarations": tools}]

    if thinking_level:
        # Enable includeThoughts in API if caller wants thought streaming
        payload["generationConfig"].update(
            build_thinking_config(thinking_level, include_thoughts=(stream and include_thoughts))
        )

    if response_schema:
        payload["generationConfig"]["responseMimeType"] = "application/json"
        payload["generationConfig"]["responseSchema"] = response_schema

    endpoint = "streamGenerateContent" if stream else "generateContent"

    # Log request (once, before attempting)
    if session_logger:
        session_logger.log_gemini_request(model, endpoint, {
            "messages_count": len(messages),
            "has_tools": bool(tools),
            "tool_count": len(tools) if tools else 0,
            "temperature": temperature,
            "thinking_level": thinking_level,
            "has_response_schema": bool(response_schema),
            "stream": stream,
            "total_keys_available": len(all_keys)
        })

    last_error = None
    attempt_count = 0

    for api_key in keys_to_try:
        attempt_count += 1

        # Build URL with current key
        url = f"{api_base}/{model}:{endpoint}"
        if stream:
            url += f"?key={api_key}&alt=sse"
        else:
            url += f"?key={api_key}"

        # Log retry attempt (if not first attempt)
        if attempt_count > 1 and session_logger:
            session_logger.log("GEMINI_KEY_ROTATION", {
                "attempt": attempt_count,
                "total_keys": len(all_keys),
                "reason": str(last_error)
            })

        start_time = time.time()

        try:
            if stream:
                response = requests.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    stream=True,
                    timeout=300
                )
                # Check for rate limit before streaming
                if response.status_code == 429:
                    last_error = "Rate limited (429)"
                    logger.warning(f"API key rate limited, switching to next key...")
                    continue  # Immediately try next key
                if response.status_code in [500, 503]:
                    last_error = f"Server error ({response.status_code})"
                    logger.warning(f"Server error {response.status_code}, switching to next key...")
                    continue  # Try next key
                return _stream_gemini_response(response, session_logger, return_dicts=include_thoughts)
            else:
                response = requests.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=300
                )

                # Check for rate limit - immediately switch key
                if response.status_code == 429:
                    last_error = "Rate limited (429)"
                    logger.warning(f"API key rate limited, switching to next key...")
                    continue  # Immediately try next key

                # Check for other retryable errors (500, 503)
                if response.status_code in [500, 503]:
                    last_error = f"Server error ({response.status_code})"
                    logger.warning(f"Server error {response.status_code}, switching to next key...")
                    continue  # Try next key

                result = response.json()

                # Log response
                if session_logger:
                    duration_ms = (time.time() - start_time) * 1000
                    session_logger.log_gemini_response(model, result, duration_ms)
                    session_logger.add_usage(result.get("usageMetadata"))

                return result

        except requests.exceptions.Timeout:
            last_error = "Request timeout"
            logger.warning(f"Request timeout, trying next key...")
            continue
        except Exception as e:
            last_error = str(e)
            logger.error(f"Gemini API error: {e}")
            if session_logger:
                session_logger.log_error("GEMINI_API_ERROR", str(e), {"attempt": attempt_count, "model": model})
            continue

    # All keys exhausted
    error_msg = f"All {len(all_keys)} API keys failed. Last error: {last_error}"
    logger.error(error_msg)
    if session_logger:
        session_logger.log_error("GEMINI_ALL_KEYS_EXHAUSTED", error_msg, {"total_keys": len(all_keys)})
    return {"error": error_msg}


def _stream_gemini_response(response, session_logger: Optional[SessionLogger] = None, return_dicts: bool = False) -> Generator:
    """Parse streaming response from Gemini API.

    Args:
        response: The requests response object with streaming enabled
        session_logger: Optional SessionLogger for logging
        return_dicts: If True, yields dicts with 'type' and 'content' keys
                      for both thoughts and text. If False, yields plain text strings.

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
            line_str = line.decode('utf-8')
            if line_str.startswith('data: '):
                try:
                    data = json.loads(line_str[6:])
                    # Token counts arrive on the final SSE chunk (cumulative for
                    # this call); keep the latest seen.
                    if 'usageMetadata' in data:
                        usage_metadata = data['usageMetadata']
                    if 'candidates' in data and data['candidates']:
                        candidate = data['candidates'][0]
                        if 'content' in candidate and 'parts' in candidate['content']:
                            for part in candidate['content']['parts']:
                                if 'text' in part:
                                    # Check if this is a thought summary or regular text
                                    is_thought = part.get('thought', False)
                                    if is_thought:
                                        total_thoughts += part['text']
                                        if return_dicts:
                                            yield {'type': 'thought', 'content': part['text']}
                                        # Skip thoughts in legacy mode (return_dicts=False)
                                    else:
                                        total_text += part['text']
                                        if return_dicts:
                                            yield {'type': 'text', 'content': part['text']}
                                        else:
                                            yield part['text']
                except json.JSONDecodeError:
                    continue

    # Accumulate this call's token usage into the request total.
    if session_logger:
        session_logger.add_usage(usage_metadata)

    # Log streaming completion
    if session_logger:
        duration_ms = (time.time() - start_time) * 1000
        session_logger.log("GEMINI_STREAM_COMPLETE", {
            "duration_ms": round(duration_ms, 2),
            "total_text_length": len(total_text),
            "total_thoughts_length": len(total_thoughts)
        })


def gemini_request_with_thought_streaming(
    messages: list,
    system_instruction: str,
    model: str,
    tools: list = None,
    temperature: float = 0.3,
    thinking_level: str = None,
    response_schema: dict = None,
    session_logger: Optional[SessionLogger] = None,
    thought_callback: callable = None,
    demo_mode: bool = False
) -> dict:
    """Make a streaming Gemini request, calling thought_callback for thoughts but returning complete response.

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
        thought_callback: Optional callback function called with each thought chunk.
                         Signature: callback(thought_text: str) -> None
        demo_mode: If True, uses demo API keys reserved for internal demos.

    Returns:
        dict: Complete response (same format as non-streaming gemini_request)
    """
    config = load_config()
    api_base = config.get("gemini", {}).get("api_base", "https://generativelanguage.googleapis.com/v1beta/models")

    # Get all available keys (demo or regular based on mode)
    all_keys = get_api_keys(demo_mode=demo_mode)
    if not all_keys:
        return {"error": "No Gemini API keys configured in config.json"}

    # Shuffle keys for random order
    keys_to_try = all_keys.copy()
    random.shuffle(keys_to_try)

    # Build payload
    payload = {
        "contents": messages,
        "generationConfig": {
            "temperature": temperature,
        }
    }

    if system_instruction:
        payload["systemInstruction"] = {
            "parts": [{"text": inject_datetime(system_instruction)}]
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
        session_logger.log_gemini_request(model, "streamGenerateContent", {
            "messages_count": len(messages),
            "has_tools": bool(tools),
            "tool_count": len(tools) if tools else 0,
            "temperature": temperature,
            "thinking_level": thinking_level,
            "include_thoughts": True,
            "total_keys_available": len(all_keys)
        })

    last_error = None
    attempt_count = 0

    for api_key in keys_to_try:
        attempt_count += 1

        # Build URL for streaming
        url = f"{api_base}/{model}:streamGenerateContent?key={api_key}&alt=sse"

        # Log retry attempt (if not first attempt)
        if attempt_count > 1 and session_logger:
            session_logger.log("GEMINI_KEY_ROTATION", {
                "attempt": attempt_count,
                "total_keys": len(all_keys),
                "reason": str(last_error)
            })

        start_time = time.time()

        try:
            response = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                stream=True,
                timeout=300
            )

            # Check for rate limit before streaming
            if response.status_code == 429:
                last_error = "Rate limited (429)"
                logger.warning(f"API key rate limited, switching to next key...")
                continue
            if response.status_code in [500, 503]:
                last_error = f"Server error ({response.status_code})"
                logger.warning(f"Server error {response.status_code}, switching to next key...")
                continue

            # Collect response while streaming thoughts
            collected_text = ""
            collected_function_calls = []
            collected_thoughts = ""
            collected_usage = None

            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        try:
                            data = json.loads(line_str[6:])
                            if 'usageMetadata' in data:
                                collected_usage = data['usageMetadata']
                            if 'candidates' in data and data['candidates']:
                                candidate = data['candidates'][0]
                                if 'content' in candidate and 'parts' in candidate['content']:
                                    for part in candidate['content']['parts']:
                                        if 'functionCall' in part:
                                            collected_function_calls.append(part)
                                        elif 'text' in part:
                                            is_thought = part.get('thought', False)
                                            if is_thought:
                                                collected_thoughts += part['text']
                                                if thought_callback:
                                                    thought_callback(part['text'])
                                            else:
                                                collected_text += part['text']
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
                "candidates": [{
                    "content": {
                        "parts": result_parts,
                        "role": "model"
                    }
                }]
            }

            # Log response
            if session_logger:
                duration_ms = (time.time() - start_time) * 1000
                session_logger.log_gemini_response(model, result, duration_ms)
                if collected_thoughts:
                    session_logger.log("THOUGHTS_STREAMED", {
                        "thoughts_length": len(collected_thoughts)
                    })

            return result

        except requests.exceptions.Timeout:
            last_error = "Request timeout"
            logger.warning(f"Request timeout, trying next key...")
            continue
        except Exception as e:
            last_error = str(e)
            logger.error(f"Gemini API error: {e}")
            if session_logger:
                session_logger.log_error("GEMINI_API_ERROR", str(e), {"attempt": attempt_count, "model": model})
            continue

    # All keys exhausted
    error_msg = f"All {len(all_keys)} API keys failed. Last error: {last_error}"
    logger.error(error_msg)
    if session_logger:
        session_logger.log_error("GEMINI_ALL_KEYS_EXHAUSTED", error_msg, {"total_keys": len(all_keys)})
    return {"error": error_msg}


def get_api_key_filestore_mapping(demo_mode: bool = False) -> dict:
    """Build mapping of API key -> filestore from config.

    Each API key in gemini.api_keys maps to the filestore at the same index
    in gemini.filestores array.

    Args:
        demo_mode: If True, uses demo_api_keys and demo_filestores for mapping.

    Returns:
        dict mapping api_key -> filestore_id
    """
    config = load_config()
    gemini_config = config.get("gemini", {})

    if demo_mode:
        api_keys = gemini_config.get("demo_api_keys", [])
        filestores = gemini_config.get("demo_filestores", [])
        if api_keys:
            logger.info(f"Using demo filestore mapping ({len(api_keys)} keys)")
    else:
        api_keys = gemini_config.get("api_keys", [])
        filestores = gemini_config.get("filestores", [])

    # Build the mapping - each key maps to filestore at same index
    mapping = {}
    for i, key in enumerate(api_keys):
        if i < len(filestores):
            mapping[key] = filestores[i]
        else:
            # Fallback to legacy store_id if no filestore configured for this key
            legacy_store = config.get("knowledge_base", {}).get("store_id", "")
            mapping[key] = legacy_store

    return mapping
