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
"""Tests for `workflows.fetch_requests`.

Covers the validation `parse_fetch_request` applies to the model's arguments
before any MCP call: argument types, list normalization, and the
multi-entity child expansion.
"""

import re

import pytest
from pydantic import ValidationError

from narratives_agent.json_value import JsonObject
from narratives_agent.workflows.fetch_requests import (
    FetchArgumentError,
    FetchMultiEntityRequest,
    FetchObservationsRequest,
    parse_fetch_request,
)


@pytest.mark.parametrize(
    ("name", "arguments", "message"),
    [
        (
            "fetch_observations",
            {"variable_dcid": 5, "place_dcids": ["country/FRA"]},
            "variable_dcid must be a string.",
        ),
        (
            "fetch_observations",
            {
                "variable_dcid": "X",
                "place_dcids": ["country/FRA"],
                "start_date": 2010,
            },
            "start_date must be a string.",
        ),
        (
            "fetch_observations",
            {
                "variable_dcid": "X",
                "place_dcids": ["country/FRA"],
                "date_mode": ["all"],
            },
            "date_mode must be a string.",
        ),
        (
            "fetch_observations",
            {
                "variable_dcid": "X",
                "place_dcids": ["country/FRA"],
                "source_override": 123,
            },
            "source_override must be a string.",
        ),
        (
            "fetch_observations",
            {"variable_dcid": "X", "place_dcids": {"a": "country/FRA"}},
            "place_dcids must be a list of DCID strings.",
        ),
        (
            "fetch_child_observations",
            {
                "variable_dcid": "X",
                "parent_place_dcid": "country/USA",
                "child_place_type": 3,
            },
            "child_place_type must be a string.",
        ),
        (
            "fetch_multi_entity_observations",
            {"variable_dcid": "Aid", "entities": {"donor": 7}},
            "each entities value must be a list of DCID strings.",
        ),
    ],
    ids=[
        "variable",
        "start date",
        "date mode",
        "source override",
        "place mapping",
        "child place type",
        "entity value",
    ],
)
def test_an_argument_of_the_wrong_type_is_rejected(
    name: str, arguments: JsonObject, message: str
) -> None:
    # Test: Arguments whose JSON type is wrong.
    # Situation: A number where a string is expected, a list where a mode is
    #   expected, a mapping where a list of places is expected, and a number
    #   as an entity list.
    # Expectation: Validation raises `FetchArgumentError` naming the
    #   argument and the type it needs, rather than ignoring the argument.
    with pytest.raises(FetchArgumentError, match=re.escape(message)):
        parse_fetch_request(name, arguments)


def test_arguments_that_are_not_an_object_are_rejected() -> None:
    # Test: Validation of a request whose arguments are not a JSON object.
    # Situation: A bare string is validated as a `FetchObservationsRequest`
    #   directly, so Pydantic wraps the validator's error.
    # Expectation: The wrapped error says the arguments must be a JSON
    #   object, rather than naming one missing argument.
    with pytest.raises(ValidationError, match="must be a JSON object"):
        FetchObservationsRequest.model_validate("not an object")


def test_null_and_blank_optional_arguments_are_read_as_absent() -> None:
    # Test: Optional arguments a model leaves empty.
    # Situation: `date_mode` is null, `source_override` is blank, and
    #   `place_dcids` is a bare string.
    # Expectation: The request has no mode and no override, and one place.
    request = parse_fetch_request(
        "fetch_observations",
        {
            "variable_dcid": "Count_Person",
            "place_dcids": " country/FRA ",
            "date_mode": None,
            "source_override": "  ",
        },
    )
    assert request == FetchObservationsRequest(
        variable_dcid="Count_Person", place_dcids=["country/FRA"]
    )


@pytest.mark.parametrize(
    "entities",
    [
        {"  ": ["country/ARE"]},
        {"donor": []},
        {"donor": ["country/ARE"], " donor ": ["country/USA"]},
    ],
    ids=["blank key", "empty list", "repeated key"],
)
def test_a_malformed_entities_mapping_is_rejected(entities: JsonObject) -> None:
    # Test: Keys and values of `entities`.
    # Situation: A blank property name, an empty DCID list, and two keys that
    #   name the same property once stripped.
    # Expectation: Validation raises `FetchArgumentError`, so no entity list
    #   is silently dropped or overwritten.
    with pytest.raises(FetchArgumentError, match="entities"):
        parse_fetch_request(
            "fetch_multi_entity_observations",
            {"variable_dcid": "Aid", "entities": entities},
        )


@pytest.mark.parametrize(
    "expansion",
    [
        {"parent_entity_property": "recipient"},
        {"parent_entity_property": "recipient", "parent_entity_dcid": "Earth"},
        {"child_entity_type": "Country"},
    ],
    ids=["property only", "no child type", "child type only"],
)
def test_a_partial_multi_entity_expansion_is_rejected(
    expansion: JsonObject,
) -> None:
    # Test: The expansion fields of `fetch_multi_entity_observations`.
    # Situation: Some but not all of `parent_entity_property`,
    #   `parent_entity_dcid`, and `child_entity_type` are given.
    # Expectation: Validation raises `FetchArgumentError` naming the three
    #   fields; giving all three is accepted.
    arguments: JsonObject = {
        "variable_dcid": "Aid",
        "entities": {"donor": ["country/ARE"]},
    }
    with pytest.raises(FetchArgumentError, match="must be given together"):
        parse_fetch_request(
            "fetch_multi_entity_observations", {**arguments, **expansion}
        )
    request = parse_fetch_request(
        "fetch_multi_entity_observations",
        {
            **arguments,
            "parent_entity_property": "recipient",
            "parent_entity_dcid": "Earth",
            "child_entity_type": "Country",
        },
    )
    assert isinstance(request, FetchMultiEntityRequest)
    assert request.child_entity_type == "Country"


@pytest.mark.parametrize(
    ("name", "arguments", "message"),
    [
        (
            "fetch_observations",
            {"variable_dcid": "X", "place_dcids": [123, "country/FRA"]},
            "place_dcids must be a list of DCID strings.",
        ),
        (
            "fetch_multi_entity_observations",
            {"variable_dcid": "Aid", "entities": {"donor": ["country/ARE", 7]}},
            "each entities value must be a list of DCID strings.",
        ),
    ],
    ids=["place", "entity"],
)
def test_a_non_string_dcid_is_rejected(
    name: str, arguments: JsonObject, message: str
) -> None:
    # Test: List items that are not strings.
    # Situation: A place list and an entity list each hold a number.
    # Expectation: Validation raises `FetchArgumentError` naming the
    #   argument, rather than dropping the item.
    with pytest.raises(FetchArgumentError, match=re.escape(message)):
        parse_fetch_request(name, arguments)


def test_entity_dcids_are_stripped_and_deduplicated() -> None:
    # Test: Normalization of `entities`.
    # Situation: An entity list repeats a DCID, once with spaces, and holds a
    #   blank string; another property is given as a bare string.
    # Expectation: Each list holds its distinct DCIDs in order.
    request = parse_fetch_request(
        "fetch_multi_entity_observations",
        {
            "variable_dcid": "Aid",
            "entities": {
                "donor": ["country/ARE", " country/ARE ", "", "country/USA"],
                "recipient": "country/AFG",
            },
        },
    )
    assert isinstance(request, FetchMultiEntityRequest)
    assert request.entities == {
        "donor": ["country/ARE", "country/USA"],
        "recipient": ["country/AFG"],
    }
