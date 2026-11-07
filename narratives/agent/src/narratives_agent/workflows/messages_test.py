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
"""Tests for the user-visible error messages in `messages`."""

import pytest

from narratives_agent.workflows import messages

# Messages carried on `terminal` SSE frames that end a turn in an error.
TERMINAL_ERROR_MESSAGES = [
    messages.CHAT_DISABLED,
    messages.SYNTHESIS_FAILED,
    messages.MCP_UNAVAILABLE,
    messages.MCP_TOOLS_TIMEOUT,
    messages.MCP_MODEL_ERROR,
    messages.MCP_NO_RESPONSE,
    messages.MCP_LOOP_TIMEOUT,
    messages.INTERNAL_ERROR,
]


@pytest.mark.parametrize("message", TERMINAL_ERROR_MESSAGES)
def test_terminal_error_message_contains_retry_phrase(message: str) -> None:
    # Test: The wording of each terminal error message.
    # Situation: The UI makes the "try again" phrase of an error message the
    #            link that retries the turn (`ErrorNotice` in
    #            ui/src/components/data_agent.tsx).
    # Expectation: Every terminal error message contains "try again", so a
    #              rewording that drops it fails here instead of moving the
    #              link to a trailing "Try again".
    assert "try again" in message.lower()
