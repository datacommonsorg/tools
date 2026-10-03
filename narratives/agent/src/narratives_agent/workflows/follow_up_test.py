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

from typing import Any

import pytest

from narratives_agent.workflows import follow_up


@pytest.mark.asyncio
async def test_follow_ups_request_the_low_thinking_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: The thinking level that follow-up generation sends to Gemini.
    # Situation: Follow-up questions are generated for a question with one
    #   related topic.
    # Expectation: The request asks for "low". `gemini-3.8-flash` rejects
    #   "minimal" with a 400 error. This call catches that error and returns
    #   no questions, so the failure would be silent.
    monkeypatch.setattr(follow_up, "load_config", lambda: {})
    levels: list[str | None] = []

    async def request(**kwargs: Any) -> dict[str, Any]:
        levels.append(kwargs.get("thinking_level"))
        return {"error": "stubbed"}

    monkeypatch.setattr(follow_up, "async_gemini_request", request)

    await follow_up.generate_follow_up_questions(
        "What is the population of California?", ["California population"]
    )

    assert levels == ["low"]
