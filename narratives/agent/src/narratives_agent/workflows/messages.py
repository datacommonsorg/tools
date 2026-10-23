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
"""User-visible status, refusal, and error messages for the agent loop."""

# Status messages carried on `status` SSE frames for each phase of a turn.
CLASSIFY_STATUS = "Understanding the question..."
DISCOVERY_STATUS = "Querying data tools..."
SYNTHESIS_STATUS = "Generating response..."
CHART_CONFIG_STATUS = "Preparing charts..."

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

# Error messages carried on `terminal` SSE frames with `state == "error"`.
SYNTHESIS_FAILED = "The response could not be generated. Please try again."
MCP_UNAVAILABLE = "The data service is unavailable. Please try again."
MCP_TOOLS_TIMEOUT = "The data service did not respond. Please try again."
MCP_MODEL_ERROR = "The data request failed. Please try again."
MCP_NO_RESPONSE = "The model returned no response. Please try again."
MCP_LOOP_TIMEOUT = "The data request took too long. Please try again."
INTERNAL_ERROR = "An internal error occurred. Please try again."
