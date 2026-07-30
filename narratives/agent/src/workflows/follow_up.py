#!/usr/bin/env python3
# Copyright 2024 Google LLC
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
import re

from src.config import load_config
from src.gemini.client import gemini_request
from src.gemini.schemas import DEFAULT_FOLLOW_UP_PROMPT, FOLLOW_UP_SCHEMA

logger = logging.getLogger(__name__)


def generate_follow_up_questions(user_message: str, topics: list) -> list:
    """Generate self-contained follow-up questions grounded in the resolved topics.

    Mirrors datacommons.org's related.generate_follow_up_questions: returns []
    when there are no topics (no static fallback), uses a structured Gemini call,
    and filters out any question that leaks a context-dependent pronoun.
    """
    topics = [t.strip() for t in (topics or []) if isinstance(t, str) and t.strip()]
    if not topics or not user_message:
        return []

    config = load_config()
    model = config.get("gemini", {}).get("mcp_model", "gemini-3-flash-preview")
    system_prompt = config.get("prompts", {}).get("follow_up") or DEFAULT_FOLLOW_UP_PROMPT

    prompt = f"""The user's original research question is: {user_message}

RELATED TOPICS START: {"; ".join(topics)}. RELATED TOPICS END.

Generate the self-contained follow-up questions now."""

    try:
        response = gemini_request(
            messages=[{"role": "user", "parts": [{"text": prompt}]}],
            system_instruction=system_prompt,
            model=model,
            temperature=0.8,  # higher for varied phrasing
            thinking_level="minimal",
            response_schema=FOLLOW_UP_SCHEMA,
            stream=False
        )
        questions = []
        if "candidates" in response:
            text = response["candidates"][0]["content"]["parts"][0].get("text", "{}")
            questions = (json.loads(text) or {}).get("questions", []) or []
    except Exception as e:
        logger.error(f"Follow-up generation error: {e}")
        return []

    # Safety net: drop empties, context-dependent pronouns, and duplicates; cap 3.
    cleaned, seen = [], set()
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
        if len(cleaned) >= 3:
            break
    return cleaned
