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
"""User-visible status, refusal, error, and chart title text.

The agent loop sends these strings to the reader.
"""

# Status messages carried on `status` SSE frames for each phase of a turn.
CLASSIFY_STATUS = "Understanding the question..."
DISCOVERY_STATUS = "Querying data tools..."
PROCESSING_STATUS = "Analyzing data..."
SYNTHESIS_STATUS = "Generating response..."

# Refusal messages carried on `terminal` SSE frames with `state == "refused"`.
# Adversarial and safety-blocked turns always return a fixed string rather
# than model-generated text.
REFUSED_MESSAGE = "We cannot service that request."
# Format template for off-domain refusals; `{premise}` is `" (<topic>)"` or
# `""` when no sanitized topic premise is available.
OFF_DOMAIN_TEMPLATE = (
    "That request is outside the public statistical data this service "
    "covers{premise}. Ask about a demographic, economic, health, climate, "
    "or social indicator for a place."
)

# Informational and truncation messages carried on `data_status` SSE frames.
NO_DATA_MESSAGE = "We didn't find data for your query."
TRUNCATED_MESSAGE = (
    "We ran out of research steps before finding data for your query. Try "
    "asking something narrower."
)

# Error messages carried on `terminal` SSE frames with `state == "error"`.
# Retryable (`is_retryable == True`) errors each define their own literal so
# they remain decoupled while sharing the high-traffic notice;
# non-retryable errors omit any retry prompt (except `CHAT_DISABLED`, which
# notes later availability without rendering a retry button).
CHAT_DISABLED = "Chat is temporarily unavailable. Please try again later."
CONFIG_MISSING = "Backend config not loaded"
SYNTHESIS_FAILED = "The response could not be generated."
SYNTHESIS_TRANSIENT_ERROR = "We are experiencing unusually high traffic."
MCP_UNAVAILABLE = "We are experiencing unusually high traffic."
MCP_TOOLS_TIMEOUT = "We are experiencing unusually high traffic."
MCP_MODEL_ERROR = "The data request failed."
MCP_TRANSIENT_MODEL_ERROR = "We are experiencing unusually high traffic."
MCP_NO_RESPONSE = "We are experiencing unusually high traffic."
MCP_LOOP_TIMEOUT = "We are experiencing unusually high traffic."
INTERNAL_ERROR = "We are experiencing unusually high traffic."

# Default chart titles built by the agent loop. `{variable_name}` is the
# display name of the fetched numerator the chart normalizes by population.
PER_CAPITA_CHART_TITLE_TEMPLATE = "{variable_name} per person"

__all__ = [
    "CHAT_DISABLED",
    "CLASSIFY_STATUS",
    "CONFIG_MISSING",
    "DISCOVERY_STATUS",
    "INTERNAL_ERROR",
    "MCP_LOOP_TIMEOUT",
    "MCP_MODEL_ERROR",
    "MCP_NO_RESPONSE",
    "MCP_TOOLS_TIMEOUT",
    "MCP_TRANSIENT_MODEL_ERROR",
    "MCP_UNAVAILABLE",
    "NO_DATA_MESSAGE",
    "OFF_DOMAIN_TEMPLATE",
    "PER_CAPITA_CHART_TITLE_TEMPLATE",
    "PROCESSING_STATUS",
    "REFUSED_MESSAGE",
    "SYNTHESIS_FAILED",
    "SYNTHESIS_STATUS",
    "SYNTHESIS_TRANSIENT_ERROR",
    "TRUNCATED_MESSAGE",
]
