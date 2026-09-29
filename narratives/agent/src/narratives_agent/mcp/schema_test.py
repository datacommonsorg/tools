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
"""Tests for MCP tool argument normalization and Gemini schema translation.

Verifies two groups of behaviors in `mcp.schema`:
1. `fix_tool_arguments` normalizes date-range parameters, applies the `"latest"`
   date default, strips `None` values, wraps scalar list parameters (`places`,
   `sample_child_places`, `variable_dcids`, `entity_dcids`), and avoids mutating
   the caller's input dictionary.
2. `transform_schema_for_gemini` converts MCP JSON Schemas into the OpenAPI
   3.0.3 subset accepted by Gemini function calling by collapsing nullable
   `anyOf` unions, filtering unsupported keywords, recursing through nested
   `properties` and `items`, and describing `additionalProperties` maps in
   prose.
"""

import pytest

from narratives_agent.mcp import schema


@pytest.mark.parametrize(
    "tool",
    ["get_observations", "get_child_observations"],
    ids=["get_observations", "get_child_observations (1.3.x only)"],
)
def test_date_is_forced_to_range_when_range_bounds_are_given(
    tool: str,
) -> None:
    # Test: Automatic setting of `date="range"` when range bounds are provided.
    # Situation: The model passes `date_range_start` without setting
    #   `date="range"` on `get_observations` or `get_child_observations`.
    # Expectation: `fix_tool_arguments` sets `args["date"] = "range"` so the
    #   MCP server applies the requested date range instead of returning only
    #   the single latest observation.
    args = schema.fix_tool_arguments(tool, {"date_range_start": "2000"})
    assert args["date"] == "range"


def test_scalar_places_is_coerced_to_a_list() -> None:
    # Test: Coercion of a scalar `places` argument on `search_child_indicators`.
    # Situation: The model supplies a single string for `places` instead of a
    #   list of strings.
    # Expectation: `fix_tool_arguments` wraps the string in a single-element
    #   list to match the MCP server's schema.
    args = schema.fix_tool_arguments(
        "search_child_indicators", {"places": "India"}
    )
    assert args["places"] == ["India"]


@pytest.mark.parametrize(
    ("param", "value"),
    [
        ("variable_dcids", "Count_Person"),
        ("entity_dcids", "country/IND"),
    ],
)
def test_scalar_variable_metadata_params_are_coerced_to_lists(
    param: str, value: str
) -> None:
    # Test: Coercion of scalar `variable_dcids` and `entity_dcids` arguments on
    #   `get_variable_metadata`.
    # Situation: The model supplies a single string for `variable_dcids` or
    #   `entity_dcids` instead of a list of strings.
    # Expectation: `fix_tool_arguments` wraps the string in a single-element
    #   list to match the MCP server's schema.
    args = schema.fix_tool_arguments("get_variable_metadata", {param: value})
    assert args[param] == [value]


def test_observation_call_without_date_defaults_to_latest() -> None:
    # Test: Default `date` value on observation tool calls.
    # Situation: `get_observations` is called without a `date`,
    #   `date_range_start`, or `date_range_end` argument.
    # Expectation: `fix_tool_arguments` sets `args["date"] = "latest"`.
    args = schema.fix_tool_arguments("get_observations", {"variable": "X"})
    assert args["date"] == "latest"


def test_null_arguments_are_removed_from_observation_call() -> None:
    # Test: Removal of explicit `None` argument values on observation calls.
    # Situation: `get_observations` is passed a dictionary containing a key
    #   mapped to `None` (`source_override=None`).
    # Expectation: `fix_tool_arguments` strips the `None` entry while retaining
    #   non-null arguments.
    args = schema.fix_tool_arguments(
        "get_observations",
        {"variable": "X", "date": "latest", "source_override": None},
    )
    assert args == {"variable": "X", "date": "latest"}


def test_scalar_sample_child_places_is_coerced_to_a_list() -> None:
    # Test: Coercion of a scalar `sample_child_places` argument on
    #   `search_child_indicators`.
    # Situation: The model supplies a single string for `sample_child_places`
    #   instead of a list of strings.
    # Expectation: `fix_tool_arguments` wraps the string in a single-element
    #   list.
    args = schema.fix_tool_arguments(
        "search_child_indicators", {"sample_child_places": "geoId/06"}
    )
    assert args["sample_child_places"] == ["geoId/06"]


def test_fix_tool_arguments_does_not_mutate_caller_dict() -> None:
    # Test: Immutability of the caller's argument dictionary in
    #   `fix_tool_arguments`.
    # Situation: `fix_tool_arguments` normalizes an observation argument
    #   dictionary by adding `date="range"`.
    # Expectation: The returned dictionary reflects the normalized arguments
    #   while the caller's original dictionary remains unmodified.
    original = {"date_range_start": "2000"}
    schema.fix_tool_arguments("get_observations", original)
    assert original == {"date_range_start": "2000"}


def test_nullable_any_of_union_collapses_to_non_null_type() -> None:
    # Test: Translation of nullable `anyOf` unions in
    #   `transform_schema_for_gemini`.
    # Situation: An MCP parameter schema uses `anyOf: [{"type": "string"},
    #   {"type": "null"}]` with top-level `default` and `description` fields.
    # Expectation: `transform_schema_for_gemini` collapses the union to its
    #   non-null branch (`type: "string"`) and preserves `default` and
    #   `description`.
    result = schema.transform_schema_for_gemini(
        {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "default": "latest",
            "description": "Observation date.",
        }
    )
    assert result == {
        "type": "string",
        "default": "latest",
        "description": "Observation date.",
    }


def test_unsupported_json_schema_keywords_are_filtered_out() -> None:
    # Test: Filtering of JSON Schema keywords unsupported by Gemini function
    #   calling.
    # Situation: A parameter schema includes `title`, `minimum`, and
    #   `exclusiveMaximum` alongside `type` and `description`.
    # Expectation: `transform_schema_for_gemini` retains only supported OpenAPI
    #   subset keys (`type` and `description`).
    result = schema.transform_schema_for_gemini(
        {
            "type": "integer",
            "description": "How many.",
            "title": "Count",
            "minimum": 1,
            "exclusiveMaximum": 100,
        }
    )
    assert result == {"type": "integer", "description": "How many."}


def test_nested_properties_and_array_items_are_transformed() -> None:
    # Test: Recursive schema translation across object `properties` and array
    #   `items`.
    # Situation: An object schema contains an array property whose `items`
    #   schema uses a nullable `anyOf` union.
    # Expectation: `transform_schema_for_gemini` recursively transforms the
    #   nested `items` union and preserves the `required` list.
    result = schema.transform_schema_for_gemini(
        {
            "type": "object",
            "properties": {
                "places": {
                    "type": "array",
                    "items": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                }
            },
            "required": ["places"],
        }
    )
    assert result == {
        "type": "object",
        "properties": {
            "places": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["places"],
    }


def test_map_valued_object_is_described_in_prose() -> None:
    # Test: Prose description synthesis for `additionalProperties` map schemas.
    # Situation: An object schema defines `additionalProperties` (an array of
    #   strings) without fixed `properties`.
    # Expectation: `transform_schema_for_gemini` emits `"type": "object"` with
    #   a `description` stating that keys are caller-defined and values are
    #   arrays of string values.
    result = schema.transform_schema_for_gemini(
        {
            "type": "object",
            "additionalProperties": {
                "type": "array",
                "items": {"type": "string"},
            },
        }
    )
    assert result == {
        "type": "object",
        "description": (
            "A JSON object whose keys are caller-defined and whose values "
            "are arrays of string values."
        ),
    }


def test_map_description_is_appended_to_existing_description() -> None:
    # Test: Appending the `additionalProperties` shape note to an existing
    #   `description`.
    # Situation: A map-valued object schema already has a `description` string.
    # Expectation: `transform_schema_for_gemini` preserves the existing
    #   description and appends the caller-defined key/value shape note.
    result = schema.transform_schema_for_gemini(
        {
            "type": "object",
            "description": "Entities to fetch.",
            "additionalProperties": {"type": "string"},
        }
    )
    assert result["description"] == (
        "Entities to fetch. A JSON object whose keys are caller-defined and "
        "whose values are string values."
    )
