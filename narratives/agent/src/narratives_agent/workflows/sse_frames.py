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
"""Declares the Server-Sent Event frames that the agent loop sends.

These types are the SSE contract the browser consumes. Each frame type names
its SSE `event` and builds its JSON `data` payload in `payload`, which the
chat route serializes with `json.dumps`. Frames are constructed with keyword
arguments only, because several carry adjacent string fields whose swap would
type-check and change the wire. The serialized form must match the SSE table
in `docs/architecture.md`, including which keys a payload carries: a key that
is absent and a key that is `null` mean different things to the browser.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import ClassVar, Literal

from narratives_agent.json_value import JsonObject, JsonValue
from narratives_agent.telemetry import ErrorType
from narratives_agent.workflows.classify import RefusedReason
from narratives_agent.workflows.transcript import SignedWindow

type EventName = Literal[
    "status", "thought", "content", "terminal", "follow_ups"
]
type StatusPhase = Literal["classify", "discovery", "synthesis", "chart_config"]
type ThoughtPhase = Literal["discovery", "synthesis"]


@dataclass(frozen=True, kw_only=True)
class StatusFrame:
    """Announces the phase the turn has entered, with a status message."""

    event: ClassVar[EventName] = "status"
    phase: StatusPhase
    message: str

    def payload(self) -> JsonObject:
        """Returns the `data` payload of the frame."""
        return {"phase": self.phase, "message": self.message}


@dataclass(frozen=True, kw_only=True)
class ThoughtFrame:
    """Carries a model reasoning summary from discovery or synthesis."""

    event: ClassVar[EventName] = "thought"
    thought: str
    phase: ThoughtPhase

    def payload(self) -> JsonObject:
        """Returns the `data` payload of the frame."""
        return {"thought": self.thought, "phase": self.phase}


@dataclass(frozen=True, kw_only=True)
class TextFrame:
    """Carries one chunk of answer text, or a whole clarification question."""

    event: ClassVar[EventName] = "content"
    text: str

    def payload(self) -> JsonObject:
        """Returns the `data` payload of the frame."""
        return {"text": self.text}


@dataclass(frozen=True, kw_only=True)
class ToolCallFrame:
    """Carries the record of one MCP tool call, as the tool loop built it."""

    event: ClassVar[EventName] = "content"
    tool_call: JsonObject

    def payload(self) -> JsonObject:
        """Returns the `data` payload of the frame."""
        return {"tool_call": self.tool_call}


@dataclass(frozen=True, kw_only=True)
class DataStatusFrame:
    """Reports whether the tool results hold data and were cut short."""

    event: ClassVar[EventName] = "content"
    data_status: JsonObject

    def payload(self) -> JsonObject:
        """Returns the `data` payload of the frame."""
        return {"data_status": self.data_status}


@dataclass(frozen=True, kw_only=True)
class SourcesFrame:
    """Lists the cited sources, numbered by their position in the list.

    `sources` is a read-only sequence of mappings because the pipeline
    assigns the provenance extractor's `list[dict[str, str]]` to
    `DiscoveryPhaseResult.sources` before emitting it, and mypy narrows the
    emitted value to that type, which the invariant `list[JsonObject]`
    rejects.
    """

    event: ClassVar[EventName] = "content"
    sources: Sequence[Mapping[str, JsonValue]]

    def payload(self) -> JsonObject:
        """Returns the `data` payload of the frame."""
        return {"sources": [dict(source) for source in self.sources]}


@dataclass(frozen=True, kw_only=True)
class ChartConfigFrame:
    """Carries the chart configuration that the browser renders."""

    event: ClassVar[EventName] = "content"
    chart_config: JsonObject

    def payload(self) -> JsonObject:
        """Returns the `data` payload of the frame."""
        return {"chart_config": self.chart_config}


@dataclass(frozen=True, kw_only=True)
class FollowUpsFrame:
    """Carries the follow-up questions, sent after the terminal frame."""

    event: ClassVar[EventName] = "follow_ups"
    follow_up_questions: list[str]

    def payload(self) -> JsonObject:
        """Returns the `data` payload of the frame."""
        return {"follow_up_questions": list(self.follow_up_questions)}


@dataclass(frozen=True, kw_only=True)
class TerminalCompleteFrame:
    """Ends a turn that completed, with its signed window when it was signed.

    With a `window`, the payload adds the completed turn's `turn_index`,
    `hmac`, and `state_slots`, the window's `compacted_summary` (present even
    when it is `null`), and `window`: the `turn_index`, `idempotency_key`, and
    `hmac` of every turn the browser must send next, oldest first.
    Compaction re-signs the whole window, so the browser replaces the
    signatures it holds with these and drops any turn that `window` does not
    list. Without a window, the payload carries none of those keys, which
    marks a turn that was not signed and that the browser leaves out of later
    requests.
    """

    event: ClassVar[EventName] = "terminal"
    idempotency_key: str
    window: SignedWindow | None

    def payload(self) -> JsonObject:
        """Returns the `data` payload of the frame."""
        frame: JsonObject = {
            "state": "complete",
            "idempotency_key": self.idempotency_key,
        }
        if self.window is None:
            return frame
        turn = self.window.turn
        frame["turn_index"] = turn.turn_index
        frame["hmac"] = turn.hmac
        frame["state_slots"] = turn.state_slots.model_dump(mode="json")
        frame["compacted_summary"] = self.window.compacted_summary
        frame["window"] = [
            {
                "turn_index": signed.turn_index,
                "idempotency_key": signed.idempotency_key,
                "hmac": signed.hmac,
            }
            for signed in self.window.turns
        ]
        return frame


@dataclass(frozen=True, kw_only=True)
class TerminalRefusedFrame:
    """Ends a refused turn with a refusal reason and a user-safe message.

    The payload carries no `error` key, so the browser renders the message
    as a notice rather than as an error.
    """

    event: ClassVar[EventName] = "terminal"
    idempotency_key: str
    reason: RefusedReason
    message: str

    def payload(self) -> JsonObject:
        """Returns the `data` payload of the frame."""
        return {
            "state": "refused",
            "idempotency_key": self.idempotency_key,
            "reason": self.reason,
            "message": self.message,
        }


@dataclass(frozen=True, kw_only=True)
class TerminalErrorFrame:
    """Ends a failed turn with a user-safe error and a reason code."""

    event: ClassVar[EventName] = "terminal"
    idempotency_key: str
    error: str
    reason: ErrorType

    def payload(self) -> JsonObject:
        """Returns the `data` payload of the frame."""
        return {
            "state": "error",
            "idempotency_key": self.idempotency_key,
            "error": self.error,
            "reason": self.reason,
        }


type SseFrame = (
    StatusFrame
    | ThoughtFrame
    | TextFrame
    | ToolCallFrame
    | DataStatusFrame
    | SourcesFrame
    | ChartConfigFrame
    | FollowUpsFrame
    | TerminalCompleteFrame
    | TerminalRefusedFrame
    | TerminalErrorFrame
)
