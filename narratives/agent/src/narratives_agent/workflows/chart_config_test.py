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
"""Tests for the chart configuration workflow.

Verifies that `validate_data_response` fails closed (returns `False`) when the
Gemini validation call returns an error dict, invalid JSON, or a JSON object
without a boolean `data_found` field, and returns the model's boolean verdict
when `data_found` is present. Verifies that `get_chart_config` returns a dict
whatever JSON value the model produces, and that both calls request a thinking
level that `gemini-3.8-flash` accepts.
"""

import json
from collections.abc import Callable, Coroutine
from typing import Any

import pytest

from narratives_agent.workflows import chart_config

_SYNTHESIS = "Population reached 39,538,223 in 2020."
_QUESTION = "What is the population of California?"
_RESULTS = "Tool: get_observations\nResult: 39538223"


def _candidates(text: str) -> dict[str, Any]:
    """Wrap model output text in the Gemini REST API response envelope."""
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


@pytest.fixture
def gemini_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[dict[str, Any]], None]:
    """Stub `chart_config.async_gemini_request` to return a fixed response."""
    monkeypatch.setattr(chart_config, "load_config", lambda: {})

    def install(response: dict[str, Any]) -> None:
        async def request(**kwargs: Any) -> dict[str, Any]:
            return response

        monkeypatch.setattr(chart_config, "async_gemini_request", request)

    return install


@pytest.mark.asyncio
async def test_an_api_error_hides_the_charts(
    gemini_answers: Callable[[dict[str, Any]], None],
) -> None:
    # Test: Chart suppression when the Gemini validation call returns an error.
    # Situation: async_gemini_request returns an error dict without a
    #   "candidates" key.
    # Expectation: validate_data_response returns False so charts are hidden
    #   when validation fails.
    gemini_answers({"error": "HTTP 404: model not found"})

    assert (
        await chart_config.validate_data_response(_SYNTHESIS, _QUESTION)
        is False
    )


@pytest.mark.asyncio
async def test_a_response_that_is_not_json_hides_the_charts(
    gemini_answers: Callable[[dict[str, Any]], None],
) -> None:
    # Test: Chart suppression when the validation response text is not valid
    #   JSON.
    # Situation: The candidate envelope contains unparseable prose instead of a
    #   JSON object.
    # Expectation: validate_data_response catches the parse error and returns
    #   False.
    gemini_answers(_candidates("I think so, yes."))

    assert (
        await chart_config.validate_data_response(_SYNTHESIS, _QUESTION)
        is False
    )


@pytest.mark.asyncio
async def test_a_verdict_missing_the_field_hides_the_charts(
    gemini_answers: Callable[[dict[str, Any]], None],
) -> None:
    # Test: Chart suppression when the parsed JSON omits `data_found`.
    # Situation: The model returns a valid JSON object without the required
    #   boolean `data_found` property.
    # Expectation: validate_data_response returns False instead of defaulting
    #   a missing field to True.
    gemini_answers(_candidates(json.dumps({"reason": "unsure"})))

    assert (
        await chart_config.validate_data_response(_SYNTHESIS, _QUESTION)
        is False
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", ["null", "[]", "false", "123"])
async def test_a_non_object_json_payload_hides_the_charts(
    gemini_answers: Callable[[dict[str, Any]], None], payload: str
) -> None:
    # Test: Chart suppression when the validation response is valid non-object
    #   JSON.
    # Situation: json.loads succeeds and returns None, a list, a bool, or an
    #   int rather than a dict.
    # Expectation: validate_data_response returns False without raising
    #   AttributeError.
    gemini_answers(_candidates(payload))

    assert (
        await chart_config.validate_data_response(_SYNTHESIS, _QUESTION)
        is False
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("data_found", [True, False])
async def test_a_clear_verdict_is_passed_through(
    gemini_answers: Callable[[dict[str, Any]], None], data_found: bool
) -> None:
    # Test: Pass-through of a valid boolean `data_found` verdict.
    # Situation: The model returns a JSON object with `data_found` set to True
    #   or False.
    # Expectation: validate_data_response returns the exact boolean value from
    #   the response.
    gemini_answers(_candidates(json.dumps({"data_found": data_found})))

    assert (
        await chart_config.validate_data_response(_SYNTHESIS, _QUESTION)
        is data_found
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", ["null", "[]", "false", "123"])
async def test_a_non_object_chart_config_is_replaced_by_no_charts(
    gemini_answers: Callable[[dict[str, Any]], None], payload: str
) -> None:
    # Test: `get_chart_config` never returns a value that is not a dict.
    # Situation: The chart-config response is valid JSON that is None, a
    #   list, a bool, or an int rather than an object.
    # Expectation: `get_chart_config` returns `{"should_render": False}`
    #   rather than the parsed value, so the caller can index the result.
    gemini_answers(_candidates(payload))

    assert await chart_config.get_chart_config(_RESULTS, _QUESTION) == {
        "should_render": False
    }


@pytest.mark.asyncio
async def test_an_object_chart_config_is_passed_through(
    gemini_answers: Callable[[dict[str, Any]], None],
) -> None:
    # Test: Pass-through of a well-formed chart configuration.
    # Situation: The chart-config response is a JSON object.
    # Expectation: `get_chart_config` returns that object unchanged.
    config = {"should_render": True, "charts": [{"title": "Population"}]}
    gemini_answers(_candidates(json.dumps(config)))

    assert await chart_config.get_chart_config(_RESULTS, _QUESTION) == config


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "call",
    [
        lambda: chart_config.get_chart_config(_RESULTS, _QUESTION),
        lambda: chart_config.validate_data_response(_SYNTHESIS, _QUESTION),
    ],
    ids=["get_chart_config", "validate_data_response"],
)
async def test_chart_calls_request_the_low_thinking_level(
    monkeypatch: pytest.MonkeyPatch,
    call: Callable[[], Coroutine[Any, Any, object]],
) -> None:
    # Test: The thinking level that the chart calls send to Gemini.
    # Situation: The chart configuration and chart validation calls run.
    # Expectation: Each requests "low". `gemini-3.8-flash` rejects "minimal"
    #   with a 400 error. These calls catch that error and return no charts,
    #   so the failure would be silent.
    monkeypatch.setattr(chart_config, "load_config", lambda: {})
    levels: list[str | None] = []

    async def request(**kwargs: Any) -> dict[str, Any]:
        levels.append(kwargs.get("thinking_level"))
        return {"error": "stubbed"}

    monkeypatch.setattr(chart_config, "async_gemini_request", request)

    await call()

    assert levels == ["low"]
