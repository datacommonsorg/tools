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
"""Typed values that the Gemini client returns to the agent loop.

`gemini/client.py` builds these from SDK responses, so the code in
`workflows/` reads a response's text and function calls as attributes and
never handles an SDK object or a REST-shaped dictionary. Nothing here is an
SDK type, so the values the workflows depend on are independent of
`google.genai`.
"""

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class FunctionCall:
    """Represents one function call the model made in a response.

    `args` is the open-ended argument object passed through to the MCP tool,
    and is `{}` when the model sent none. `thought_signature` is the opaque
    signature the SDK attached to the part that carried the call, or `None`
    when there was none; it is sent back with the call when the model turn is
    replayed, because Gemini 3 requires it to continue the turn.
    """

    name: str
    args: dict[str, Any]
    thought_signature: bytes | None = None


@dataclass(frozen=True)
class GeminiResponse:
    """Holds the first candidate of a successful Gemini call.

    `text` is the candidate's non-thought text in part order, and
    `function_calls` are its function calls in part order. Both are empty
    when the model produced neither, including when the response carried no
    candidate at all, so the defaults describe an empty reply and a caller
    constructing one names only the fields that are present. `finish_reason`
    is the SDK enum name when the response reported one.
    """

    text: str = ""
    function_calls: tuple[FunctionCall, ...] = ()
    finish_reason: str | None = None


@dataclass(frozen=True)
class StreamChunk:
    """Represents one text or thought-summary chunk of a streamed response."""

    kind: Literal["thought", "text"]
    text: str
