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

# Chart config schema for Gemini structured output (hardcoded - not user configurable)
# Supports multiple charts for variables with different units/scales
CHART_CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "should_render": {
            "type": "boolean",
            "description": "True if at least one chart should be rendered"
        },
        "charts": {
            "type": "array",
            "description": "Array of chart configurations (max 3). Group compatible variables together.",
            "items": {
                "type": "object",
                "properties": {
                    "viz_type": {
                        "type": "string",
                        "enum": ["line", "bar", "ranking", "pie", "highlight", "gauge", "scatter", "slider"]
                    },
                    "title": {"type": "string", "description": "Descriptive chart title"},
                    "variable_dcids": {"type": "array", "items": {"type": "string"}},
                    "place_dcids": {"type": "array", "items": {"type": "string"}},
                    "parent_place": {"type": "string"},
                    "child_place_type": {"type": "string"},
                    "date": {
                        "type": "string",
                        "description": "Single comparison date in YYYY, YYYY-MM, or YYYY-MM-DD"
                    }
                }
            }
        }
    },
    "required": ["should_render"]
}


# Schema for validating if synthesis response contains actual data
DATA_VALIDATION_SCHEMA = {
    "type": "object",
    "properties": {
        "data_found": {
            "type": "boolean",
            "description": "True if the response contains actual data/statistics that answer the query. False if data is unavailable, not found, or the response says data doesn't exist."
        }
    },
    "required": ["data_found"]
}


# Schema for structured follow-up question generation.
FOLLOW_UP_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Self-contained follow-up questions, one per related topic."
        }
    },
    "required": ["questions"]
}

# Default system prompt for follow-up generation. Ported from the
# datacommons.org explore feature (server/lib/nl/explore/gemini_prompts.py,
# FOLLOW_UP_QUESTIONS_PROMPT) and adapted for the Custom DC agent. Overridable
# via config["prompts"]["follow_up"] (or config/prompts/follow_up.md).
DEFAULT_FOLLOW_UP_PROMPT = """You are a dynamic, trusted, and factual UI copywriter for a public-data explorer.

Write related follow-up questions that the user might find interesting to BROADEN their research — relatable angles to explore around the original question, NOT continuations of it.

The follow-up questions are based on a list of RELATED TOPICS (statistical variables for the same place) provided in the user message.

CRUCIAL RULES:
- If no related topics are given, return an empty list.
- Generate at most one question per topic. Return at most 3 questions total.
- Each question MUST be fully SELF-CONTAINED: it must name its own subject explicitly and read sensibly on its own, with no prior context.
- NEVER use referential words like "this", "that", "these", "those", "it", or "the above". Do not reference "the previous question/answer".
- Make the questions timeless: do NOT ask for a specific year or range of years.
- Each question must be simple and focus on a single variable.
- Avoid questions about places that meet a certain condition.
- Make the questions extremely varied; use diverse phrasing. For inspiration draw from these angles: Ranking, Maps, Comparison, Correlation, Increase/Decrease over time.
- Only suggest questions that can plausibly be answered from public statistical data for the same place.
- Ensure correct grammar and casing."""
