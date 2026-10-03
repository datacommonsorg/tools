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

"""Generates follow-up questions suggested after a completed answer."""

import json
import logging
import re
from typing import Any

from narratives_agent.config import get_gemini_model, load_config
from narratives_agent.gemini.client import (
    LIGHTWEIGHT_THINKING_LEVEL,
    async_gemini_request,
)
from narratives_agent.gemini.schemas import (
    DEFAULT_FOLLOW_UP_PROMPT,
    FOLLOW_UP_SCHEMA,
)
from narratives_agent.telemetry import TokenUsage

logger = logging.getLogger(__name__)

# Max number of follow-up questions returned to the UI.
MAX_FOLLOW_UP_QUESTIONS = 3


async def generate_follow_up_questions(
    user_message: str,
    topics: list[str],
    token_usage: TokenUsage | None = None,
) -> list[str]:
    """Generate self-contained follow-up questions grounded in the resolved
    topics.

    Mirrors datacommons.org's related.generate_follow_up_questions: returns []
    when there are no topics (no static fallback), uses a structured Gemini
    call, and filters out any question that leaks a context-dependent pronoun.
    """
    topics = [
        t.strip() for t in (topics or []) if isinstance(t, str) and t.strip()
    ]
    if not topics or not user_message:
        return []

    config = load_config()
    model = get_gemini_model(config)
    system_prompt = (
        config.get("prompts", {}).get("follow_up") or DEFAULT_FOLLOW_UP_PROMPT
    )

    prompt = f"""The user's original research question is: {user_message}

RELATED TOPICS START: {"; ".join(topics)}. RELATED TOPICS END.

Generate the self-contained follow-up questions now."""

    try:
        response = await async_gemini_request(
            messages=[{"role": "user", "parts": [{"text": prompt}]}],
            system_instruction=system_prompt,
            model=model,
            temperature=0.8,  # higher for varied phrasing
            thinking_level=LIGHTWEIGHT_THINKING_LEVEL,
            response_schema=FOLLOW_UP_SCHEMA,
            token_usage=token_usage,
        )
        questions: list[Any] = []
        if "candidates" in response:
            text = response["candidates"][0]["content"]["parts"][0].get(
                "text", "{}"
            )
            loaded = json.loads(text)
            questions = (
                loaded.get("questions", []) if isinstance(loaded, dict) else []
            ) or []
    except Exception as error:
        logger.error("Follow-up generation error: %s", error)
        return []

    # Safety net: drop empties, context-dependent pronouns, and duplicates;
    # cap 3.
    cleaned: list[str] = []
    seen: set[str] = set()
    for q in questions:
        if not isinstance(q, str):
            continue
        q = q.strip()
        if not q or re.search(r"\b(this|that|these|those)\b", q, re.IGNORECASE):
            continue
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(q)
        if len(cleaned) >= MAX_FOLLOW_UP_QUESTIONS:
            break
    return cleaned
