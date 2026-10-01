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
"""Structured-output schemas for Gemini calls.

Each model is passed to `GenerateContentConfig(response_schema=...)`, which
constrains the model's JSON output, and can validate that output locally.
The schemas are fixed in code and are not user configurable.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ChartVizType = Literal[
    "line",
    "bar",
    "ranking",
    "pie",
    "highlight",
    "gauge",
    "scatter",
    "slider",
]


def _strip_additional_properties(schema: dict[str, Any]) -> None:
    """Removes `additionalProperties` from the generated JSON schema.

    Pydantic's `extra="forbid"` adds `additionalProperties: false`, which the
    Gemini API rejects with HTTP 400. Stripping it here keeps the schema
    compatible with Gemini while retaining strict local Pydantic validation.
    """
    schema.pop("additionalProperties", None)


_SCHEMA_CONFIG = ConfigDict(
    extra="forbid",
    json_schema_extra=_strip_additional_properties,
)


class ChartItem(BaseModel):
    """One chart configuration within a chart config response."""

    model_config = _SCHEMA_CONFIG

    viz_type: ChartVizType | None = None
    # Required to prevent blank UI headers: forces the model to always
    # generate a descriptive title rather than rendering an empty header strip.
    title: str = Field(description="Descriptive chart title")
    variable_dcids: list[str] | None = None
    place_dcids: list[str] | None = None
    parent_place: str | None = None
    child_place_type: str | None = None
    date: str | None = Field(
        default=None,
        description="Single comparison date in YYYY, YYYY-MM, or YYYY-MM-DD",
    )


class ChartConfigResponse(BaseModel):
    """Chart configurations, one per group of compatible variables."""

    model_config = _SCHEMA_CONFIG

    should_render: bool = Field(
        description="True if at least one chart should be rendered"
    )
    charts: list[ChartItem] | None = Field(
        default=None,
        description=(
            "Array of chart configurations (max 3). Group compatible "
            "variables together."
        ),
    )


class DataValidationResponse(BaseModel):
    """Verdict on whether a synthesized answer contains actual data."""

    model_config = _SCHEMA_CONFIG

    data_found: bool = Field(
        description=(
            "True if the response contains actual data/statistics that "
            "answer the query. False if data is unavailable, not found, "
            "or the response says data doesn't exist."
        )
    )


class FollowUpResponse(BaseModel):
    """Suggested follow-up questions for a completed answer."""

    model_config = _SCHEMA_CONFIG

    questions: list[str] = Field(
        description="Self-contained follow-up questions, one per related topic."
    )


# The workflows pass these names as `response_schema`.
CHART_CONFIG_SCHEMA = ChartConfigResponse
DATA_VALIDATION_SCHEMA = DataValidationResponse
FOLLOW_UP_SCHEMA = FollowUpResponse

# Default system prompt for follow-up generation. Ported from the
# datacommons.org explore feature (server/lib/nl/explore/gemini_prompts.py,
# FOLLOW_UP_QUESTIONS_PROMPT) and adapted for the Custom DC agent. Overridable
# via config["prompts"]["follow_up"] (or config/prompts/follow_up.md).
DEFAULT_FOLLOW_UP_PROMPT = """You are a dynamic, trusted, and factual UI \
copywriter for a public-data explorer.

Write related follow-up questions that the user might find interesting to \
BROADEN their research — relatable angles to explore around the original \
question, NOT continuations of it.

The follow-up questions are based on a list of RELATED TOPICS (statistical \
variables for the same place) provided in the user message.

CRUCIAL RULES:
- If no related topics are given, return an empty list.
- Generate at most one question per topic. Return at most 3 questions total.
- Each question MUST be fully SELF-CONTAINED: it must name its own subject \
explicitly and read sensibly on its own, with no prior context.
- NEVER use referential words like "this", "that", "these", "those", "it", \
or "the above". Do not reference "the previous question/answer".
- Make the questions timeless: do NOT ask for a specific year or range of years.
- Each question must be simple and focus on a single variable.
- Avoid questions about places that meet a certain condition.
- Make the questions extremely varied; use diverse phrasing. For inspiration \
draw from these angles: Ranking, Maps, Comparison, Correlation, \
Increase/Decrease over time.
- Only suggest questions that can plausibly be answered from public \
statistical data for the same place.
- Ensure correct grammar and casing."""
