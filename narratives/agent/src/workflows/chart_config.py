#!/usr/bin/env python3
# Copyright 2024 Google LLC
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

import json
import logging

from src.config import load_config
from src.gemini.client import gemini_request
from src.gemini.schemas import CHART_CONFIG_SCHEMA, DATA_VALIDATION_SCHEMA

logger = logging.getLogger(__name__)


def get_chart_config(mcp_results: str, user_message: str) -> dict:
    """Get chart configuration using structured output.

    Supports multiple charts for variables with different units/scales.
    """
    config = load_config()
    mcp_model = config.get("gemini", {}).get("mcp_model", "gemini-3-flash-preview")

    prompt = f"""Based on the data query and results, determine chart configurations.

User Query: {user_message}

Data Results:
{mcp_results if mcp_results else 'No data results'}

Instructions:
1. Extract variable DCIDs and place DCIDs from the results
2. Analyze variable units from source_metadata and data scales from the values
3. Group variables that can be meaningfully compared on the same Y-axis:
   - Same unit type (e.g., both INR, both counts, both percentages)
   - Similar magnitude (within ~100x of each other)
4. Create SEPARATE charts for incompatible variable groups:
   - Different unit types should be separate (e.g., "Count" vs "INR" vs "Percentage")
   - Vastly different scales should be separate (e.g., millions vs trillions)
5. MAXIMUM 3 charts - if more groups exist, prioritize most relevant to the query
6. Choose appropriate viz_type for each chart (line for time series, bar for comparison)
7. Give each chart a descriptive title related to data it is showing but do NOT include year/date in the title.
8. For ALL bar charts, ALWAYS include a date field:
   - date can be in formats YYYY, YYYY-MM, or YYYY-MM-DD (e.g., "2021", "2022", "2021-01", "2022-01-01")
   - prefer explicit date from user query or tool result context
   - if no reliable explicit date is available, omit date

Set should_render to false if no meaningful data for visualization."""

    response = gemini_request(
        messages=[{"role": "user", "parts": [{"text": prompt}]}],
        system_instruction="You are a data visualization expert. Extract chart configurations from data results, grouping compatible variables together and separating incompatible ones into multiple charts.",
        model=mcp_model,
        temperature=0.2,
        thinking_level="minimal",  # Fastest for simple extraction
        response_schema=CHART_CONFIG_SCHEMA,
        stream=False
    )

    try:
        if "candidates" in response:
            text = response["candidates"][0]["content"]["parts"][0].get("text", "{}")
            chart_config = json.loads(text)
            logger.info(f"📊 Chart config result: {json.dumps(chart_config, indent=2)}")
            return chart_config
    except Exception as e:
        logger.error(f"Chart config parse error: {e}")

    return {"should_render": False}


def validate_data_response(synthesis_text: str, user_message: str) -> bool:
    """Quick validation: did synthesis actually answer with data?

    Called after synthesis completes to determine if charts should be shown.
    Uses fast model with no thinking for minimal latency.
    """
    config = load_config()
    model = config.get("gemini", {}).get("mcp_model", "gemini-2.0-flash")

    prompt = f"""User asked: {user_message}

Response given:
{synthesis_text[:2000]}

Did this response contain actual data/statistics that answer the user's question?
Return false if the response says data is "not available", "not found", "doesn't exist", or similar."""

    response = gemini_request(
        messages=[{"role": "user", "parts": [{"text": prompt}]}],
        system_instruction="You validate if a response contains actual data.",
        model=model,
        temperature=0,
        thinking_level="none",  # Fastest - no thinking needed
        response_schema=DATA_VALIDATION_SCHEMA,
        stream=False
    )

    try:
        if "candidates" in response:
            text = response["candidates"][0]["content"]["parts"][0].get("text", "{}")
            result = json.loads(text)
            return result.get("data_found", True)
    except Exception as e:
        logger.error(f"Data validation parse error: {e}")

    return True  # Default to showing charts on error
