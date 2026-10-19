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

"""Generates chart configurations and validates whether to display charts."""

import json
import logging
from typing import Any

from narratives_agent.config_model import AgentConfig
from narratives_agent.gemini.client import (
    LIGHTWEIGHT_THINKING_LEVEL,
    GeminiBlockedError,
    GeminiError,
    async_gemini_request,
)
from narratives_agent.gemini.schemas import (
    CHART_CONFIG_SCHEMA,
    DATA_VALIDATION_SCHEMA,
)
from narratives_agent.telemetry import TokenUsage

logger = logging.getLogger(__name__)

# Max characters of the synthesis text sent to the data-validation check.
SYNTHESIS_PREVIEW_LENGTH = 2000

# Max characters of a parsed payload quoted in error logs.
_LOG_EXCERPT_LENGTH = 300


async def get_chart_config(
    mcp_results: str,
    user_message: str,
    config: AgentConfig,
    token_usage: TokenUsage | None = None,
) -> dict[str, Any]:
    """Get chart configuration using structured output.

    Supports multiple charts for variables with different units/scales.

    Args:
        mcp_results: The gathered tool results to chart.
        user_message: The user's query.
        config: The agent configuration; the request runs on
            `gemini.mcp_model`.
        token_usage: Optional turn totals that receive the call's token
            counts.

    Returns:
        The parsed chart configuration, or `{"should_render": False}` if the
        request fails or its response cannot be parsed.
    """
    mcp_model = config.gemini.mcp_model

    prompt = f"""Based on the data query and results, determine chart \
configurations.

User Query: {user_message}

Data Results:
{mcp_results if mcp_results else "No data results"}

Instructions:
1. Extract variable DCIDs and place DCIDs from the results
2. Analyze variable units from source_metadata and data scales from the values
3. Group variables that can be meaningfully compared on the same Y-axis:
   - Same unit type (e.g., both INR, both counts, both percentages)
   - Similar magnitude (within ~100x of each other)
4. Create SEPARATE charts for incompatible variable groups:
   - Different unit types should be separate (e.g., "Count" vs "INR" vs \
"Percentage")
   - Vastly different scales should be separate (e.g., millions vs trillions)
5. MAXIMUM 3 charts - if more groups exist, prioritize most relevant to the \
query
6. Choose appropriate viz_type for each chart (line for time series, bar for \
comparison)
7. Give each chart a descriptive title related to data it is showing but do \
NOT include year/date in the title.
8. For ALL bar charts, ALWAYS include a date field:
   - date can be in formats YYYY, YYYY-MM, or YYYY-MM-DD (e.g., "2021", \
"2022", "2021-01", "2022-01-01")
   - prefer explicit date from user query or tool result context
   - if no reliable explicit date is available, omit date

Set should_render to false if no meaningful data for visualization."""

    try:
        response = await async_gemini_request(
            messages=[{"role": "user", "parts": [{"text": prompt}]}],
            system_instruction=(
                "You are a data visualization expert. Extract chart "
                "configurations from data results, grouping compatible "
                "variables together and separating incompatible ones into "
                "multiple charts."
            ),
            model=mcp_model,
            temperature=0.2,
            thinking_level=LIGHTWEIGHT_THINKING_LEVEL,
            response_schema=CHART_CONFIG_SCHEMA,
            token_usage=token_usage,
        )
    except GeminiBlockedError as error:
        logger.warning(
            "Chart config blocked (%s); rendering without charts",
            error.block_reason,
        )
        return {"should_render": False}
    except GeminiError:
        # The client has already logged the redacted upstream error.
        logger.warning("Chart config request failed; rendering without charts")
        return {"should_render": False}

    try:
        if response.text.strip():
            chart_config = json.loads(response.text)
            # The model can return valid JSON that is not an object, such as
            # `null` or `[]`. The caller expects a dict, so anything else is
            # treated as "no charts".
            if not isinstance(chart_config, dict):
                logger.error(
                    "Chart config returned %s instead of an object",
                    type(chart_config).__name__,
                )
                return {"should_render": False}
            # The configuration is derived from the user's query, so it is
            # logged only at DEBUG, below the agent's INFO log level.
            logger.debug(
                "Chart config result: %s", json.dumps(chart_config, indent=2)
            )
            return chart_config
        logger.warning(
            "Chart config returned no text (finish reason: %s); rendering "
            "without charts",
            response.finish_reason,
        )
    except Exception as error:
        logger.error("Chart config parse error: %s", error)

    return {"should_render": False}


async def validate_data_response(
    synthesis_text: str,
    user_message: str,
    config: AgentConfig,
    token_usage: TokenUsage | None = None,
) -> bool:
    """Validate via Gemini whether the synthesis text contains chartable data.

    Returns False so that charts are suppressed unless explicitly confirmed:
    with a warning if the validation request fails or is blocked (the client
    has already logged the upstream failure), and with an error if the
    response is malformed JSON or omits the boolean `data_found` field.

    Args:
        synthesis_text: The streamed answer to judge.
        user_message: The user's query.
        config: The agent configuration; the request runs on
            `gemini.mcp_model`.
        token_usage: Optional turn totals that receive the call's token
            counts.
    """
    model = config.gemini.mcp_model

    prompt = f"""User asked: {user_message}

Response given:
{synthesis_text[:SYNTHESIS_PREVIEW_LENGTH]}

Did this response contain actual data/statistics that answer the user's \
question?
Return false if the response says data is "not available", "not found", \
"doesn't exist", or similar."""

    try:
        response = await async_gemini_request(
            messages=[{"role": "user", "parts": [{"text": prompt}]}],
            system_instruction=(
                "You validate if a response contains actual data."
            ),
            model=model,
            temperature=0,
            thinking_level=LIGHTWEIGHT_THINKING_LEVEL,
            response_schema=DATA_VALIDATION_SCHEMA,
            token_usage=token_usage,
        )
    except GeminiBlockedError as error:
        logger.warning(
            "Data validation blocked (%s) on %s, hiding charts.",
            error.block_reason,
            model,
        )
        return False
    except GeminiError:
        # The client has already logged the redacted upstream error.
        logger.warning(
            "Data validation request to %s failed, hiding charts.", model
        )
        return False
    if not response.text.strip():
        logger.error(
            "Data validation got no text from %s (finish reason: %s), hiding "
            "charts.",
            model,
            response.finish_reason,
        )
        return False

    try:
        result = json.loads(response.text)
    except Exception as error:
        logger.error("Data validation parse error, hiding charts: %s", error)
        return False

    verdict = result.get("data_found") if isinstance(result, dict) else None
    if not isinstance(verdict, bool):
        logger.error(
            "Data validation returned no data_found boolean, hiding charts. "
            "Parsed: %s",
            str(result)[:_LOG_EXCERPT_LENGTH],
        )
        return False
    return verdict
