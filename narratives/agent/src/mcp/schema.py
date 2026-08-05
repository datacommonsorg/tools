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

    # Handle required array
    if "required" in schema:
        result["required"] = schema["required"]

    # Handle array items recursively
    if "items" in schema:
        result["items"] = transform_schema_for_gemini(schema["items"])

    return result


def fix_tool_arguments(name: str, arguments: dict) -> dict:
    """Fix common parameter mistakes made by LLMs."""
    args = arguments.copy()

    if name == "get_observations":
        # Fix 1: If date_range_start/end provided but date != 'range', fix it
        has_range_params = args.get("date_range_start") or args.get("date_range_end")
        if has_range_params and args.get("date") != "range":
            logger.info("Fixing: Setting date='range' because date_range params provided")
            args["date"] = "range"

        # Fix 2: Ensure date has a default if not provided
        if "date" not in args:
            args["date"] = "latest"

        # Fix 3: Remove null/None values that might cause issues
        args = {k: v for k, v in args.items() if v is not None}

    if name == "search_indicators":
        # Ensure places is a list
        if "places" in args and isinstance(args["places"], str):
            args["places"] = [args["places"]]

    return args
