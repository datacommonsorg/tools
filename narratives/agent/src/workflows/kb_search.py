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
from typing import Optional

import requests

from src.config import get_api_keys, inject_datetime, load_config
from src.gemini.client import build_thinking_config, get_api_key_filestore_mapping
from src.session_logger import SessionLogger

logger = logging.getLogger(__name__)


def execute_kb_query(user_message: str, session_logger: Optional[SessionLogger] = None, thought_callback: callable = None, demo_mode: bool = False, effective_config: dict = None) -> dict:
    """Execute Knowledge Base query using file search with key rotation and thought streaming.

    Each API key automatically uses its paired filestore from the config mapping.

    Args:
        user_message: The user's query
        session_logger: Optional SessionLogger for logging
        thought_callback: Optional callback for streaming thought chunks.
                         Signature: callback(thought_text: str) -> None
        demo_mode: If True, uses demo API keys and filestores reserved for internal demos.
        effective_config: Optional config dict with query param overrides applied.

    Returns:
        dict with keys:
        - response: str (the response text)
        - sources: list of dicts with 'title' and 'uri'
    """
    config = effective_config if effective_config else load_config()
    kb_config = config.get("knowledge_base", {})

    if not kb_config.get("enabled", False):
        return {"response": "", "sources": []}

    kb_prompt = config.get("prompts", {}).get("kb", "")
    kb_model = config.get("gemini", {}).get("kb_model", "gemini-3-flash-preview")
    kb_temperature = kb_config.get("temperature", 0.3)
    kb_dynamic_threshold = kb_config.get("dynamic_threshold", 0.3)

    # Get API key -> filestore mapping (demo or regular based on mode)
    key_filestore_map = get_api_key_filestore_mapping(demo_mode=demo_mode)

    if not key_filestore_map:
        logger.warning("No API key to filestore mapping configured")
        return {"response": "", "sources": []}

    # Get all available keys (demo or regular based on mode)
    all_keys = get_api_keys(demo_mode=demo_mode)
    if not all_keys:
        return {"response": "", "sources": []}

    api_base = config.get("gemini", {}).get("api_base", "https://generativelanguage.googleapis.com/v1beta/models")

    # Shuffle keys for random order
    keys_to_try = all_keys.copy()
    random.shuffle(keys_to_try)

    last_error = None
    attempt_count = 0

    for api_key in keys_to_try:
        # Get the filestore for this specific API key
        store_id = key_filestore_map.get(api_key, "")
        if not store_id:
            logger.warning(f"No filestore configured for API key, skipping...")
            continue

        logger.info(f"KB query using filestore: {store_id[:50]}...")

        # Build payload with this key's filestore and thinking config
        thinking_level = config.get("thinking", {}).get("kb_level", "low")
        payload = {
            "contents": [{"role": "user", "parts": [{"text": user_message}]}],
            "systemInstruction": {"parts": [{"text": inject_datetime(kb_prompt)}]},
            "generationConfig": {
                "temperature": kb_temperature,
            },
            "tools": [{
                "fileSearch": {
                    "dynamicFileSearchConfig": {
                        "mode": "MODE_DYNAMIC",
                        "dynamicThreshold": kb_dynamic_threshold
                    }
                }
            }],
            "toolConfig": {
                "fileSearch": {
                    "vectorStore": {"storeResourceId": store_id}
                }
            }
        }

        # Add thinking config with includeThoughts for streaming
        if thinking_level:
            payload["generationConfig"].update(
                build_thinking_config(thinking_level, include_thoughts=True)
            )

        attempt_count += 1
        start_time = time.time()

        # Log retry attempt (if not first attempt)
        if attempt_count > 1 and session_logger:
            session_logger.log("KB_KEY_ROTATION", {
                "attempt": attempt_count,
                "total_keys": len(all_keys),
                "reason": str(last_error)
            })

        try:
            # Use streaming endpoint to get thoughts in real-time
            url = f"{api_base}/{kb_model}:streamGenerateContent?key={api_key}&alt=sse"
            response = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                stream=True,
                timeout=300
            )

            # Check for rate limit - immediately switch key
            if response.status_code == 429:
                last_error = "Rate limited (429)"
                logger.warning(f"KB API key rate limited, switching to next key...")
                continue

            # Check for other retryable errors
            if response.status_code in [500, 503]:
                last_error = f"Server error ({response.status_code})"
                logger.warning(f"KB server error {response.status_code}, switching to next key...")
                continue

            # Collect response while streaming thoughts
            result_text = ""
            sources = []
            collected_thoughts = ""
            grounding_metadata = {}
            kb_usage = None

            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        try:
                            data = json.loads(line_str[6:])
                            if 'usageMetadata' in data:
                                kb_usage = data['usageMetadata']
                            if 'candidates' in data and data['candidates']:
                                candidate = data['candidates'][0]

                                # Extract grounding metadata when available
                                if 'groundingMetadata' in candidate:
                                    grounding_metadata = candidate['groundingMetadata']

                                if 'content' in candidate and 'parts' in candidate['content']:
                                    for part in candidate['content']['parts']:
                                        if 'text' in part:
                                            is_thought = part.get('thought', False)
                                            if is_thought:
                                                collected_thoughts += part['text']
                                                if thought_callback:
                                                    thought_callback(part['text'])
                                            else:
                                                result_text += part['text']
                        except json.JSONDecodeError:
                            continue

            # Accumulate this call's token usage into the request total.
            if session_logger:
                session_logger.add_usage(kb_usage)

            # Extract source citations from grounding metadata
            grounding_chunks = grounding_metadata.get("groundingChunks", [])
            seen_titles = set()
            for chunk in grounding_chunks:
                retrieved_context = chunk.get("retrievedContext", {})
                if retrieved_context:
                    title = retrieved_context.get("title", "Unknown")
                    uri = retrieved_context.get("uri", "")
                    # Deduplicate by title
                    if title not in seen_titles:
                        seen_titles.add(title)
                        sources.append({
                            "title": title,
                            "uri": uri
                        })

            # Log KB query
            if session_logger:
                duration_ms = (time.time() - start_time) * 1000
                session_logger.log_kb_query(user_message, result_text, duration_ms)
                if sources:
                    session_logger.log("KB_SOURCES", {"sources": sources})
                if collected_thoughts:
                    session_logger.log("KB_THOUGHTS_STREAMED", {"thoughts_length": len(collected_thoughts)})

            return {"response": result_text, "sources": sources}

        except requests.exceptions.Timeout:
            last_error = "Request timeout"
            logger.warning(f"KB request timeout, trying next key...")
            continue
        except Exception as e:
            last_error = str(e)
            logger.error(f"KB query error: {e}")
            if session_logger:
                session_logger.log_error("KB_QUERY_ERROR", str(e), {"query": user_message, "attempt": attempt_count})
            continue

    # All keys exhausted
    logger.error(f"KB query failed: All {len(all_keys)} API keys exhausted. Last error: {last_error}")
    if session_logger:
        session_logger.log_error("KB_ALL_KEYS_EXHAUSTED", f"All keys failed: {last_error}", {"total_keys": len(all_keys)})
    return {"response": "", "sources": []}
