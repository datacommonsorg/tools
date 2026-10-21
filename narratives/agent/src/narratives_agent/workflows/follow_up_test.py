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

    async def request(**kwargs: Any) -> GeminiResponse:
        levels.append(kwargs.get("thinking_level"))
        raise GeminiError("stubbed")

    monkeypatch.setattr(follow_up, "async_gemini_request", request)

    await follow_up.generate_follow_up_questions(
        "What is the population of California?",
        ["California population"],
        _CONFIG,
    )

    assert levels == [types.ThinkingLevel.LOW]


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
        raise GeminiError("stubbed")

    monkeypatch.setattr(follow_up, "async_gemini_request", request)

    with caplog.at_level("WARNING"):
        questions = await follow_up.generate_follow_up_questions(
            "What is the population of California?",
            ["California population"],
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
        pytest.param(GeminiError("HTTP 500: upstream detail"), id="error"),
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
            ["California population"],
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
            ["California population"],
            _CONFIG,
        )

    assert questions == []
    assert [record.levelno for record in caplog.records] == [logging.WARNING]
    assert f"finish reason: {response.finish_reason}" in caplog.text
