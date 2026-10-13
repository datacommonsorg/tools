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
    ChartConfigResponse,
    ChartItem,
    ChartVizType,
    DataValidationResponse,
    FollowUpResponse,
)

_MODELS: list[type[BaseModel]] = [
    ChartItem,
    ChartConfigResponse,
    DataValidationResponse,
    FollowUpResponse,
]

# Holds the smallest valid payload for each schema model.
_MINIMAL_PAYLOADS: dict[type[BaseModel], dict[str, Any]] = {
    ChartItem: {"title": "Population of California"},
    ChartConfigResponse: {"should_render": False},
    DataValidationResponse: {"data_found": True},
    FollowUpResponse: {"questions": []},
}


def test_a_chart_config_response_parses_nested_charts() -> None:
    # Test: Parsing a complete chart config response.
    # Situation: The model returns JSON with one fully populated chart.
    # Expectation: The JSON parses into a ChartConfigResponse with all
    #   provided chart fields populated and omitted optional fields set to
    #   None.
    response = ChartConfigResponse.model_validate_json(
        """{
            "should_render": true,
            "charts": [{
                "viz_type": "line",
                "title": "Population over time",
                "variable_dcids": ["Count_Person"],
                "place_dcids": ["geoId/06"],
                "date": "2020"
            }]
        }"""
    )

    assert response.should_render is True
    assert response.charts is not None
    chart = response.charts[0]
    assert chart.viz_type == "line"
    assert chart.title == "Population over time"
    assert chart.variable_dcids == ["Count_Person"]
    assert chart.place_dcids == ["geoId/06"]
    assert chart.date == "2020"
    assert chart.parent_place is None
    assert chart.child_place_type is None


@pytest.mark.parametrize(
    ("model", "required_field"),
    [
        (ChartItem, "title"),
        (ChartConfigResponse, "should_render"),
        (DataValidationResponse, "data_found"),
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


@pytest.mark.parametrize("viz_type", get_args(ChartVizType))
def test_every_supported_viz_type_is_accepted(viz_type: str) -> None:
    # Test: Accepted chart types.
    # Situation: ChartItem is validated with each visualization type in
    #   ChartVizType.
    # Expectation: Validation succeeds and preserves viz_type for every
    #   supported value.
    chart = ChartItem.model_validate({"title": "t", "viz_type": viz_type})

    assert chart.viz_type == viz_type


def test_an_unsupported_viz_type_is_rejected() -> None:
    # Test: Chart type enforcement.
    # Situation: ChartItem is given a visualization type ("histogram") that
    #   the Data Commons web components do not support.
    # Expectation: Validation fails on viz_type, and the JSON schema
    #   enumerates only the supported types.
    with pytest.raises(ValidationError) as raised:
        ChartItem.model_validate({"title": "t", "viz_type": "histogram"})

    assert raised.value.errors()[0]["loc"] == ("viz_type",)
    viz_schema = ChartItem.model_json_schema()["properties"]["viz_type"]
    enums = [option.get("enum") for option in viz_schema["anyOf"]]
    assert list(get_args(ChartVizType)) in enums


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
