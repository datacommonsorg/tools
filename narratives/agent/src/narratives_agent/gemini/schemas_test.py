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
"""Tests for the Gemini structured-output schemas."""

from typing import Any, get_args

import pytest
from pydantic import BaseModel, ValidationError

from narratives_agent.gemini.schemas import (
    FollowUpResponse,
    GeographicShape,
    QueryClassification,
    QueryPattern,
    RefusalReason,
)

_MODELS: list[type[BaseModel]] = [
    QueryClassification,
    FollowUpResponse,
]

# Holds the smallest valid payload for each schema model.
_MINIMAL_PAYLOADS: dict[type[BaseModel], dict[str, Any]] = {
    QueryClassification: {"serviceable": True},
    FollowUpResponse: {"questions": []},
}


@pytest.mark.parametrize(
    ("model", "required_field"),
    [
        (QueryClassification, "serviceable"),
        (FollowUpResponse, "questions"),
    ],
)
def test_a_missing_required_field_is_rejected(
    model: type[BaseModel], required_field: str
) -> None:
    # Test: Required-field enforcement.
    # Situation: A payload omits the model's one required field.
    # Expectation: Validation fails on that field, and the generated JSON
    #   schema lists it as the only required field, so Gemini is constrained
    #   to emit it.
    payload = dict(_MINIMAL_PAYLOADS[model])
    del payload[required_field]

    with pytest.raises(ValidationError) as raised:
        model.model_validate(payload)

    assert raised.value.errors()[0]["loc"] == (required_field,)
    assert model.model_json_schema()["required"] == [required_field]


def test_query_classification_populates_defaults() -> None:
    # Test: Default values on `QueryClassification` when only `serviceable` is
    #   supplied.
    # Situation: `QueryClassification` is validated with
    #   `{"serviceable": True}`.
    # Expectation: Optional fields default to `refusal_reason=None`,
    #   `clarification=None`, `pattern="exploratory"`,
    #   `geographic_shape="single_place"`, `requires_computation=False`, and
    #   `off_topic_premise=""`.
    parsed = QueryClassification.model_validate({"serviceable": True})

    assert parsed.serviceable is True
    assert parsed.refusal_reason is None
    assert parsed.clarification is None
    assert parsed.pattern == "exploratory"
    assert parsed.geographic_shape == "single_place"
    assert parsed.requires_computation is False
    assert parsed.off_topic_premise == ""


@pytest.mark.parametrize("pattern", get_args(QueryPattern))
def test_every_query_pattern_is_accepted(pattern: str) -> None:
    # Test: Accepted analytical pattern values on `QueryClassification`.
    # Situation: `QueryClassification` is validated with each value in
    #   `QueryPattern`.
    # Expectation: Validation succeeds and preserves `pattern`.
    parsed = QueryClassification.model_validate(
        {"serviceable": True, "pattern": pattern}
    )

    assert parsed.pattern == pattern


@pytest.mark.parametrize("shape", get_args(GeographicShape))
def test_every_geographic_shape_is_accepted(shape: str) -> None:
    # Test: Accepted geographic shape values on `QueryClassification`.
    # Situation: `QueryClassification` is validated with each value in
    #   `GeographicShape`.
    # Expectation: Validation succeeds and preserves `geographic_shape`.
    parsed = QueryClassification.model_validate(
        {"serviceable": True, "geographic_shape": shape}
    )

    assert parsed.geographic_shape == shape


@pytest.mark.parametrize("reason", get_args(RefusalReason))
def test_every_refusal_reason_is_accepted(reason: str) -> None:
    # Test: Accepted refusal reason values on `QueryClassification`.
    # Situation: `QueryClassification` is validated with `serviceable=False`
    #   and each value in `RefusalReason`.
    # Expectation: Validation succeeds and preserves `refusal_reason`.
    parsed = QueryClassification.model_validate(
        {"serviceable": False, "refusal_reason": reason}
    )

    assert parsed.refusal_reason == reason


def test_invalid_query_classification_enums_are_rejected() -> None:
    # Test: Rejection of unknown enum values on `QueryClassification`.
    # Situation: `QueryClassification` is given an unknown `pattern`,
    #   `geographic_shape`, or `refusal_reason`.
    # Expectation: Each invalid value raises `ValidationError` on the
    #   corresponding field.
    for field, bad_value in (
        ("pattern", "unknown_pattern"),
        ("geographic_shape", "planet"),
        ("refusal_reason", "safety_blocked"),
    ):
        with pytest.raises(ValidationError) as raised:
            QueryClassification.model_validate(
                {"serviceable": True, field: bad_value}
            )
        assert raised.value.errors()[0]["loc"] == (field,)


@pytest.mark.parametrize(
    "payload",
    [
        {"serviceable": False, "refusal_reason": None},
        {"serviceable": True, "refusal_reason": "adversarial"},
        {"serviceable": True, "refusal_reason": "off_domain"},
    ],
)
def test_inconsistent_refusal_fields_are_rejected(
    payload: dict[str, Any],
) -> None:
    # Test: Consistency check between `serviceable` and `refusal_reason`.
    # Situation: `QueryClassification` is validated with `serviceable=False`
    #   and no `refusal_reason`, or `serviceable=True` with a `refusal_reason`.
    # Expectation: Validation fails with `ValidationError`.
    with pytest.raises(ValidationError):
        QueryClassification.model_validate(payload)


@pytest.mark.parametrize("model", _MODELS)
def test_an_unknown_field_is_rejected(model: type[BaseModel]) -> None:
    # Test: Unknown-field rejection.
    # Situation: A payload that is otherwise valid carries an extra field.
    # Expectation: Validation fails locally with extra_forbidden, while the
    #   generated JSON schema omits additionalProperties so the Gemini
    #   Developer API accepts the request.
    payload = {**_MINIMAL_PAYLOADS[model], "unexpected": 1}

    with pytest.raises(ValidationError) as raised:
        model.model_validate(payload)

    assert raised.value.errors()[0]["type"] == "extra_forbidden"
    assert "additionalProperties" not in model.model_json_schema()
