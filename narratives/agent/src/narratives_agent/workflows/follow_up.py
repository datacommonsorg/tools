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
from dataclasses import dataclass
from typing import Any

from narratives_agent.config_model import AgentConfig, GeminiRole
from narratives_agent.gemini.client import (
    GeminiBlockedError,
    GeminiError,
    async_gemini_request,
)
from narratives_agent.gemini.schemas import FOLLOW_UP_SCHEMA
from narratives_agent.telemetry import TokenUsage

logger = logging.getLogger(__name__)

# Max number of follow-up questions returned to the UI.
MAX_FOLLOW_UP_QUESTIONS = 3
# Headings of the two topic lists in the follow-up request; `follow_up.md`
# refers to them by these names.
UNUSED_TOPICS_HEADING = "INDICATORS THE ANSWER DID NOT USE"
REPORTED_TOPICS_HEADING = "INDICATORS THE ANSWER REPORTED"
# Written in place of an empty topic list.
_NO_TOPICS = "none"


@dataclass(frozen=True)
class FollowUpTopics:
    """The topics that ground the follow-up questions, in two lists.

    The follow-up model writes its questions from `unused` first, so that
    they lead the reader somewhere the answer did not go, and uses
    `reported` only to fill the remaining questions.

    Attributes:
        unused: Indicators the answer did not use, such as those discovery
            left aside, or, on a turn without data, its data-gap notes.
        reported: Indicators the answer reported, with the places they were
            measured over, and the titles of the charts shown.
    """

    unused: tuple[str, ...] = ()
    reported: tuple[str, ...] = ()


def _clean_topics(topics: tuple[str, ...]) -> list[str]:
    """Returns the non-blank topics, stripped, in their order."""
    return [topic.strip() for topic in topics if topic.strip()]


def _format_topic_list(topics: list[str]) -> str:
    """Joins a topic list for the request, or names it empty."""
    return "; ".join(topics) if topics else _NO_TOPICS


async def generate_follow_up_questions(
    user_message: str,
    topics: FollowUpTopics,
    config: AgentConfig,
    token_usage: TokenUsage | None = None,
) -> list[str]:
    """Generate self-contained follow-up questions grounded in the resolved
    topics.

    Mirrors datacommons.org's related.generate_follow_up_questions: returns []
    when there are no topics (no static fallback), uses a structured Gemini
    call, and filters out any question that leaks a context-dependent pronoun.
    Also returns [] when the `follow_up` prompt slot is empty, so the model is
    never called without its system instruction.

    Args:
        user_message: The user's query.
        topics: The indicators the answer did not use and those it
            reported, sent to the model as two headed lists.
        config: The agent configuration; `prompts.follow_up` is the system
            instruction and `gemini.follow_up_model` the model.
        token_usage: Optional turn totals that receive the call's token
            counts.
    """
    unused = _clean_topics(topics.unused)
    reported = _clean_topics(topics.reported)
    if not (unused or reported) or not user_message:
        return []

    role = config.resolve_role_config(GeminiRole.FOLLOW_UP)
    system_prompt = config.prompts.follow_up
    if not system_prompt:
        logger.warning(
            "The follow_up prompt is not configured; skipping follow-up "
            "generation"
        )
        return []

    prompt = f"""The user's original research question is: {user_message}

{UNUSED_TOPICS_HEADING}: {_format_topic_list(unused)}.

{REPORTED_TOPICS_HEADING}: {_format_topic_list(reported)}.

Generate the self-contained follow-up questions now."""

    try:
        response = await async_gemini_request(
            messages=[{"role": "user", "parts": [{"text": prompt}]}],
            system_instruction=system_prompt,
            model=role.model,
            temperature=role.temperature,
            thinking_level=role.thinking_level,
            response_schema=FOLLOW_UP_SCHEMA,
            token_usage=token_usage,
            token_phase=GeminiRole.FOLLOW_UP.value,
        )
        questions: list[Any] = []
        if response.text.strip():
            loaded = json.loads(response.text)
            questions = (
                loaded.get("questions", []) if isinstance(loaded, dict) else []
            ) or []
        else:
            logger.warning(
                "Follow-up generation returned no text (finish reason: %s); "
                "returning no questions",
                response.finish_reason,
            )
    except GeminiBlockedError as error:
        logger.warning(
            "Follow-up generation blocked (%s); returning no questions",
            error.block_reason,
        )
        return []
    except GeminiError:
        # The client has already logged the redacted upstream error.
        logger.warning("Follow-up generation failed; returning no questions")
        return []
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
