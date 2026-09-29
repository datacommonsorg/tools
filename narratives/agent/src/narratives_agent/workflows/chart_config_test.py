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
"""Tests for `validate_data_response` in the chart configuration workflow.

Verifies that `validate_data_response` fails closed (returns `False`) when the
Gemini validation call returns an error dict, invalid JSON, or a JSON object
without a boolean `data_found` field, and returns the model's boolean verdict
when `data_found` is present.
"""

import json
from collections.abc import Callable
from typing import Any

import pytest

from narratives_agent.workflows import chart_config

_SYNTHESIS = "Population reached 39,538,223 in 2020."
_QUESTION = "What is the population of California?"


def _candidates(text: str) -> dict[str, Any]:
    """Wrap model output text in the Gemini REST API response envelope."""
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


@pytest.fixture
def gemini_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[dict[str, Any]], None]:
    """Stub `chart_config.gemini_request` to return a fixed response dict."""
    monkeypatch.setattr(chart_config, "load_config", lambda: {})

    def install(response: dict[str, Any]) -> None:
        def request(**kwargs: Any) -> dict[str, Any]:
            return response

        monkeypatch.setattr(chart_config, "gemini_request", request)

    return install


def test_an_api_error_hides_the_charts(
    gemini_answers: Callable[[dict[str, Any]], None],
) -> None:
    # Test: Chart suppression when the Gemini validation call returns an error.
    # Situation: gemini_request returns an error dict without a "candidates"
    #   key.
    # Expectation: validate_data_response returns False so charts are hidden
    #   when validation fails.
    gemini_answers({"error": "HTTP 404: model not found"})

    assert chart_config.validate_data_response(_SYNTHESIS, _QUESTION) is False


def test_a_response_that_is_not_json_hides_the_charts(
    gemini_answers: Callable[[dict[str, Any]], None],
) -> None:
    # Test: Chart suppression when the validation response text is not valid
    #   JSON.
    # Situation: The candidate envelope contains unparseable prose instead of a
    #   JSON object.
    # Expectation: validate_data_response catches the parse error and returns
    #   False.
    gemini_answers(_candidates("I think so, yes."))

    assert chart_config.validate_data_response(_SYNTHESIS, _QUESTION) is False


def test_a_verdict_missing_the_field_hides_the_charts(
    gemini_answers: Callable[[dict[str, Any]], None],
) -> None:
    # Test: Chart suppression when the parsed JSON omits `data_found`.
    # Situation: The model returns a valid JSON object without the required
    #   boolean `data_found` property.
    # Expectation: validate_data_response returns False instead of defaulting
    #   a missing field to True.
    gemini_answers(_candidates(json.dumps({"reason": "unsure"})))

    assert chart_config.validate_data_response(_SYNTHESIS, _QUESTION) is False


@pytest.mark.parametrize("payload", ["null", "[]", "false", "123"])
def test_a_non_object_json_payload_hides_the_charts(
    gemini_answers: Callable[[dict[str, Any]], None], payload: str
) -> None:
    # Test: Chart suppression when the validation response is valid non-object
    #   JSON.
    # Situation: json.loads succeeds and returns None, a list, a bool, or an
    #   int rather than a dict.
    # Expectation: validate_data_response returns False without raising
    #   AttributeError.
    gemini_answers(_candidates(payload))

    assert chart_config.validate_data_response(_SYNTHESIS, _QUESTION) is False


@pytest.mark.parametrize("data_found", [True, False])
def test_a_clear_verdict_is_passed_through(
    gemini_answers: Callable[[dict[str, Any]], None], data_found: bool
) -> None:
    # Test: Pass-through of a valid boolean `data_found` verdict.
    # Situation: The model returns a JSON object with `data_found` set to True
    #   or False.
    # Expectation: validate_data_response returns the exact boolean value from
    #   the response.
    gemini_answers(_candidates(json.dumps({"data_found": data_found})))

    assert (
        chart_config.validate_data_response(_SYNTHESIS, _QUESTION) is data_found
    )
