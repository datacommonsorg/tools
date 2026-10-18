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

from narratives_agent.gemini.client import GeminiBlockedError, GeminiError
from narratives_agent.workflows import follow_up


@pytest.mark.asyncio
async def test_follow_ups_request_the_low_thinking_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: The thinking level that follow-up generation sends to Gemini.
    # Situation: The configuration carries a `follow_up` prompt, and follow-up
    #   questions are generated for a question with one related topic.
    # Expectation: The request asks for "low". `gemini-3.8-flash` rejects
    #   "minimal" with a 400 error. This call catches that error and returns
    #   no questions, so the failure would be silent.
    monkeypatch.setattr(
        follow_up,
        "load_config",
        lambda: {"prompts": {"follow_up": "Suggest follow-up questions."}},
    )
    levels: list[str | None] = []

    async def request(**kwargs: Any) -> dict[str, Any]:
        levels.append(kwargs.get("thinking_level"))
        raise GeminiError("stubbed")

    monkeypatch.setattr(follow_up, "async_gemini_request", request)

    await follow_up.generate_follow_up_questions(
        "What is the population of California?", ["California population"]
    )

    assert levels == ["low"]


@pytest.mark.asyncio
async def test_follow_ups_are_skipped_when_the_prompt_is_empty(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Test: Follow-up generation when the `follow_up` prompt slot is empty.
    # Situation: The configuration has no `prompts` section, and follow-up
    #   questions are requested for a question with one related topic.
    # Expectation: Gemini is not called, no questions are returned, and a
    #   warning names the `follow_up` prompt.
    monkeypatch.setattr(follow_up, "load_config", lambda: {})
    calls: list[dict[str, Any]] = []

    async def request(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"error": "stubbed"}

    monkeypatch.setattr(follow_up, "async_gemini_request", request)

    with caplog.at_level("WARNING"):
        questions = await follow_up.generate_follow_up_questions(
            "What is the population of California?", ["California population"]
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
    # Situation: `async_gemini_request` raises `GeminiError` or
    #   `GeminiBlockedError`.
    # Expectation: No questions are returned and the failure is logged once
    #   at WARNING, not at ERROR, because the client already logged the
    #   redacted upstream error.
    monkeypatch.setattr(follow_up, "load_config", lambda: {})

    async def request(**kwargs: Any) -> dict[str, Any]:
        raise error

    monkeypatch.setattr(follow_up, "async_gemini_request", request)

    with caplog.at_level(logging.WARNING, logger=follow_up.logger.name):
        questions = await follow_up.generate_follow_up_questions(
            "What is the population of California?",
            ["California population"],
        )

    assert questions == []
    assert [record.levelno for record in caplog.records] == [logging.WARNING]
