#!/usr/bin/env python3
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

import logging

logger = logging.getLogger(__name__)


def _describe_value_shape(schema: dict) -> str:
    """Names the shape a sub-schema describes, for use in prose.

    Used only to explain map-valued objects, which Gemini's schema subset has no
    way to represent structurally.
    """
    if not isinstance(schema, dict):
        return "values"
    if schema.get("type") == "array":
        return f"arrays of {_describe_value_shape(schema.get('items') or {})}"
    value_type = schema.get("type")
    return f"{value_type} values" if value_type else "values"


def transform_schema_for_gemini(schema: dict) -> dict:
    """Transform MCP inputSchema to Gemini-compatible format.

    Gemini function calling only supports a subset of OpenAPI 3.0.3 schema.
    This removes unsupported constructs like 'anyOf' for nullable types.

    Args:
        schema: The MCP inputSchema dictionary

    Returns:
        dict: Gemini-compatible schema
    """
    if not isinstance(schema, dict):
        return schema

    result = {}

    # Handle anyOf (union types) - common for nullable fields in MCP schemas
    # e.g., {"anyOf": [{"type": "string"}, {"type": "null"}], "default": null}
    if "anyOf" in schema:
        # Find the non-null type and use that
        for option in schema["anyOf"]:
            if option.get("type") != "null":
                result = transform_schema_for_gemini(option)
                break
        # Preserve default if present at the anyOf level
        if "default" in schema:
            result["default"] = schema["default"]
        # Preserve description if present at the anyOf level
        if "description" in schema:
            result["description"] = schema["description"]
        return result

    # Copy supported fields
    for key in ["type", "description", "default", "enum"]:
        if key in schema:
            result[key] = schema[key]

    # Handle object properties recursively
    if "properties" in schema:
        result["properties"] = {
            k: transform_schema_for_gemini(v)
            for k, v in schema["properties"].items()
        }
    elif isinstance(schema.get("additionalProperties"), dict):
        # A map-valued object -- {"type": "object", "additionalProperties":
        # {"type": "array", "items": {"type": "string"}}} -- has no `properties`
        # to recurse into, and Gemini's schema subset cannot express one.
        # Dropping the key leaves a bare {"type": "object"}: the model then has
        # to guess the shape and gets it wrong (get_multi_entity_observations'
        # `entities` is the live example, where a guessed list is rejected).
        # Describe the shape in prose instead, which is how the model learns
        # every other constraint in here.
        note = (
            "A JSON object whose keys are caller-defined and whose values are "
            f"{_describe_value_shape(schema['additionalProperties'])}."
        )
        existing = result.get("description", "").strip()
        result["description"] = (
            f"{existing} {note}".strip() if existing else note
        )

    # Handle required array
    if "required" in schema:
        result["required"] = schema["required"]

    # Handle array items recursively
    if "items" in schema:
        result["items"] = transform_schema_for_gemini(schema["items"])

    return result


# Tools that take the date / date_range_start / date_range_end trio. Server
# 1.3.0 split the single fat observations tool into these three; they share the
# date handling, so the fix below has to cover all of them or a range request
# against child places silently collapses to one date.
_OBSERVATION_TOOLS = (
    "get_observations",
    "get_child_observations",
    "get_multi_entity_observations",
)


def fix_tool_arguments(name: str, arguments: dict) -> dict:
    """Fix common parameter mistakes made by LLMs."""
    args = arguments.copy()

    if name in _OBSERVATION_TOOLS:
        # Fix 1: If date_range_start/end provided but date != 'range', fix it.
        # Load-bearing, not cosmetic: the server ignores the range bounds unless
        # date is exactly "range" and returns a single latest value instead.
        has_range_params = args.get("date_range_start") or args.get("date_range_end")
        if has_range_params and args.get("date") != "range":
            logger.info("Fixing: Setting date='range' because date_range params provided")
            args["date"] = "range"

        # Fix 2: Ensure date has a default if not provided
        if "date" not in args:
            args["date"] = "latest"

        # Fix 3: Remove null/None values that might cause issues
        args = {k: v for k, v in args.items() if v is not None}

    if name in ("search_indicators", "search_child_indicators"):
        # Ensure places is a list
        if "places" in args and isinstance(args["places"], str):
            args["places"] = [args["places"]]

    if name == "search_child_indicators":
        # sample_child_places is required and must be a list. A model naming one
        # example place tends to pass a bare string, which the server rejects.
        if isinstance(args.get("sample_child_places"), str):
            logger.info("Fixing: wrapping sample_child_places in a list")
            args["sample_child_places"] = [args["sample_child_places"]]

    if name == "get_variable_metadata":
        # Both arguments are required and must be lists. A model asking about a
        # single variable or place tends to pass a bare string, which the server
        # rejects outright rather than coercing.
        for key in ("variable_dcids", "entity_dcids"):
            if isinstance(args.get(key), str):
                logger.info(f"Fixing: wrapping {key} in a list")
                args[key] = [args[key]]

    return args
