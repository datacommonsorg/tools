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
# Refused turns always return a fixed string rather than model-generated text.
# `REFUSED_MESSAGE` answers questions the classifier marks adversarial (for
# example, subjective or demeaning questions); `SAFETY_REFUSED_MESSAGE` answers
# pre-filter matches (prompt-injection attempts), Model Armor matches, and
# Gemini safety blocks.
REFUSED_MESSAGE = (
    "Data Commons is built to explore standardized public data (such as "
    "demographics, economics, health, and education) rather than subjective "
    "or opinion-based questions."
)
SAFETY_REFUSED_MESSAGE = (
    "Data Commons is built to explore standardized public data (such as "
    "demographics, economics, health, and education) and is not able to do "
    "more than that."
)
# Format template for off-domain refusals. `{subject}` is
# `OFF_DOMAIN_NAMED_SUBJECT` with the sanitized topic premise, or
# `OFF_DOMAIN_UNNAMED_SUBJECT` when no premise is available.
OFF_DOMAIN_TEMPLATE = (
    "{subject} falls outside the public statistics Data Commons is built to "
    "explore. Try asking about a demographic, economic, health, climate, or "
    "social measure for a country, state, or city."
)
OFF_DOMAIN_NAMED_SUBJECT = 'The topic "{premise}"'
OFF_DOMAIN_UNNAMED_SUBJECT = "This topic"

# Informational and truncation messages carried on `data_status` SSE frames.
NO_DATA_MESSAGE = (
    "Data Commons does not have matching data for this question. Try asking "
    "about a broader geography, time period, or measure."
)
TRUNCATED_MESSAGE = (
    "This question covers more ground than Data Commons can match at once. "
    "Try breaking it into a simpler question about a single measure or place."
)

# Error messages carried on `terminal` SSE frames with `state == "error"`.
# Retryable (`is_retryable == True`) errors each define their own literal so
# they remain decoupled while sharing the high-traffic notice; non-retryable
# errors omit any retry prompt. The chat-disabled message is configured as
# `chat.unavailable_message` (default `DEFAULT_UNAVAILABLE_MESSAGE` in
# `config_model.py`).
CONFIG_MISSING = "Backend config not loaded"
SYNTHESIS_FAILED = (
    "Data Commons was unable to complete an answer for that prompt. Try "
    "asking a simpler or different question instead."
)
SYNTHESIS_TRANSIENT_ERROR = (
    "Data Commons is experiencing unusually high traffic right now."
)
MCP_UNAVAILABLE = (
    "Data Commons is experiencing unusually high traffic right now."
)
MCP_TOOLS_TIMEOUT = (
    "Data Commons is experiencing unusually high traffic right now."
)
MCP_MODEL_ERROR = (
    "Data Commons ran into an issue retrieving the data for that. Try "
    "rephrasing or asking about a different public statistic."
)
MCP_TRANSIENT_MODEL_ERROR = (
    "Data Commons is experiencing unusually high traffic right now."
)
MCP_NO_RESPONSE = (
    "Data Commons is experiencing unusually high traffic right now."
)
MCP_LOOP_TIMEOUT = (
    "Data Commons is experiencing unusually high traffic right now."
)
INTERNAL_ERROR = (
    "Data Commons is experiencing unusually high traffic right now."
)

# Default chart titles built by the agent loop. `{variable_name}` is the
# display name of the fetched numerator the chart normalizes by population.
PER_CAPITA_CHART_TITLE_TEMPLATE = "{variable_name} per person"

__all__ = [
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
    "OFF_DOMAIN_NAMED_SUBJECT",
    "OFF_DOMAIN_TEMPLATE",
    "OFF_DOMAIN_UNNAMED_SUBJECT",
    "PER_CAPITA_CHART_TITLE_TEMPLATE",
    "PROCESSING_STATUS",
    "REFUSED_MESSAGE",
    "SAFETY_REFUSED_MESSAGE",
    "SYNTHESIS_FAILED",
    "SYNTHESIS_STATUS",
    "SYNTHESIS_TRANSIENT_ERROR",
    "TRUNCATED_MESSAGE",
]
