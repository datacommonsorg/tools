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
"""Tests for the follow-up question workflow."""

import logging
from pathlib import Path
from typing import Any

import pytest
from google.genai import types

from narratives_agent.config_model import AgentConfig, Prompts
from narratives_agent.gemini.client import GeminiBlockedError, GeminiError
from narratives_agent.gemini.response import GeminiResponse
from narratives_agent.workflows import follow_up

_CONFIG = AgentConfig(prompts=Prompts(follow_up="Suggest follow-up questions."))


@pytest.mark.asyncio
async def test_follow_ups_request_the_low_thinking_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: The thinking level that follow-up generation sends to Gemini.
    # Situation: The configuration carries a `follow_up` prompt, and follow-up
    #   questions are generated for a question with one related topic.
    # Expectation: The request asks for `ThinkingLevel.LOW`. `gemini-3.8-flash`
    #   rejects `MINIMAL` with a 400 error. This call catches that error and
    #   returns no questions, so the failure would be silent.
    levels: list[types.ThinkingLevel | None] = []
    phases: list[str | None] = []

    async def request(**kwargs: Any) -> GeminiResponse:
        levels.append(kwargs.get("thinking_level"))
        phases.append(kwargs.get("token_phase"))
        raise GeminiError("stubbed", is_retryable=False)

    monkeypatch.setattr(follow_up, "async_gemini_request", request)

    await follow_up.generate_follow_up_questions(
        "What is the population of California?",
        follow_up.FollowUpTopics(unused=("California population",)),
        _CONFIG,
    )

    assert levels == [types.ThinkingLevel.LOW]
    assert phases == ["follow_up"]


@pytest.mark.asyncio
async def test_follow_ups_are_skipped_when_the_prompt_is_empty(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Test: Follow-up generation when the `follow_up` prompt slot is empty.
    # Situation: The configuration carries no `follow_up` prompt, and follow-up
    #   questions are requested for a question with one related topic.
    # Expectation: Gemini is not called, no questions are returned, and a
    #   warning names the `follow_up` prompt.
    calls: list[dict[str, Any]] = []

    async def request(**kwargs: Any) -> GeminiResponse:
        calls.append(kwargs)
        raise GeminiError("stubbed", is_retryable=False)

    monkeypatch.setattr(follow_up, "async_gemini_request", request)

    with caplog.at_level("WARNING"):
        questions = await follow_up.generate_follow_up_questions(
            "What is the population of California?",
            follow_up.FollowUpTopics(unused=("California population",)),
            AgentConfig(),
        )

    assert questions == []
    assert calls == []
    assert any(
        r.levelname == "WARNING" and "follow_up prompt" in r.getMessage()
        for r in caplog.records
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        pytest.param(
            GeminiError("HTTP 500: upstream detail", is_retryable=True),
            id="error",
        ),
        pytest.param(GeminiBlockedError("SAFETY"), id="blocked"),
    ],
)
async def test_a_failed_or_blocked_call_returns_no_questions(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
) -> None:
    # Test: Fail-open handling of a failed or blocked follow-up call.
    # Situation: The configuration carries a `follow_up` prompt, and
    #   `async_gemini_request` raises `GeminiError` or `GeminiBlockedError`.
    # Expectation: No questions are returned and the failure is logged once
    #   at WARNING, not at ERROR, because the client already logged the
    #   redacted upstream error.
    async def request(**kwargs: Any) -> GeminiResponse:
        raise error

    monkeypatch.setattr(follow_up, "async_gemini_request", request)

    with caplog.at_level(logging.WARNING, logger=follow_up.logger.name):
        questions = await follow_up.generate_follow_up_questions(
            "What is the population of California?",
            follow_up.FollowUpTopics(unused=("California population",)),
            _CONFIG,
        )

    assert questions == []
    assert [record.levelno for record in caplog.records] == [logging.WARNING]
    assert "returning no questions" in caplog.records[0].getMessage()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        pytest.param(GeminiResponse(finish_reason="MAX_TOKENS"), id="empty"),
        pytest.param(GeminiResponse(text=" \n"), id="blank-text"),
    ],
)
async def test_an_empty_response_returns_no_questions(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    response: GeminiResponse,
) -> None:
    # Test: Follow-up generation when Gemini returns nothing to parse.
    # Situation: The configuration carries a `follow_up` prompt, and
    #   `async_gemini_request` returns a reply with no text, or with only
    #   whitespace.
    # Expectation: No questions are returned, and one WARNING names the
    #   finish reason; an empty reply is not a parse failure, so nothing is
    #   logged at ERROR.
    async def request(**kwargs: Any) -> GeminiResponse:
        return response

    monkeypatch.setattr(follow_up, "async_gemini_request", request)

    with caplog.at_level(logging.WARNING, logger=follow_up.logger.name):
        questions = await follow_up.generate_follow_up_questions(
            "What is the population of California?",
            follow_up.FollowUpTopics(unused=("California population",)),
            _CONFIG,
        )

    assert questions == []
    assert [record.levelno for record in caplog.records] == [logging.WARNING]
    assert f"finish reason: {response.finish_reason}" in caplog.text


@pytest.mark.asyncio
async def test_the_request_lists_unused_and_reported_indicators_apart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: How the two topic lists reach the follow-up model.
    # Situation: Follow-up questions are requested with two indicators the
    #   answer did not use and one it reported.
    # Expectation: The request names each list under its own heading, in
    #   order, so the model can tell which indicators the answer covered.
    prompts: list[str] = []

    async def request(**kwargs: Any) -> GeminiResponse:
        prompts.append(kwargs["messages"][0]["parts"][0]["text"])
        return GeminiResponse(text='{"questions": []}')

    monkeypatch.setattr(follow_up, "async_gemini_request", request)

    await follow_up.generate_follow_up_questions(
        "What is women's access to healthcare like in India?",
        follow_up.FollowUpTopics(
            unused=(
                "fertility rate in India",
                "female life expectancy in India",
            ),
            reported=("Maternal mortality ratio in India",),
        ),
        _CONFIG,
    )

    (prompt,) = prompts
    assert (
        f"{follow_up.UNUSED_TOPICS_HEADING}: fertility rate in India; "
        "female life expectancy in India."
    ) in prompt
    assert (
        f"{follow_up.REPORTED_TOPICS_HEADING}: Maternal mortality ratio in "
        "India."
    ) in prompt


@pytest.mark.asyncio
async def test_an_empty_list_is_named_as_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: A request with only reported indicators.
    # Situation: Follow-up questions are requested with no unused indicator
    #   and one reported indicator.
    # Expectation: The model is still called, and the unused list reads
    #   "none" rather than being left blank.
    prompts: list[str] = []

    async def request(**kwargs: Any) -> GeminiResponse:
        prompts.append(kwargs["messages"][0]["parts"][0]["text"])
        return GeminiResponse(text='{"questions": []}')

    monkeypatch.setattr(follow_up, "async_gemini_request", request)

    await follow_up.generate_follow_up_questions(
        "What is the population of California?",
        follow_up.FollowUpTopics(reported=("Total population in California",)),
        _CONFIG,
    )

    (prompt,) = prompts
    assert f"{follow_up.UNUSED_TOPICS_HEADING}: none." in prompt


def test_the_follow_up_prompt_names_both_lists() -> None:
    # Test: Agreement between the request and the default prompt.
    # Situation: The shipped `defaults/prompts/follow_up.md` is read.
    # Expectation: It names both list headings the request uses and tells
    #   the model to start with the indicators the answer did not use.
    prompt = (
        Path(__file__).resolve().parents[4]
        / "defaults"
        / "prompts"
        / "follow_up.md"
    ).read_text(encoding="utf-8")

    assert follow_up.UNUSED_TOPICS_HEADING in prompt
    assert follow_up.REPORTED_TOPICS_HEADING in prompt
    assert (
        "Write one question for each indicator the answer did not use"
    ) in prompt
