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

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, Literal

from narratives_agent.analytics.provenance import Source
from narratives_agent.json_value import JsonObject
from narratives_agent.telemetry import ErrorType, TerminalState
from narratives_agent.workflows.blocks import SynthesisBlock, TextBlock
from narratives_agent.workflows.charts import serialize_resolved_chart
from narratives_agent.workflows.classify import RefusedReason
from narratives_agent.workflows.transcript import SignedWindow

type EventName = Literal[
    "status", "thought", "content", "terminal", "follow_ups"
]
type StatusPhase = Literal["classify", "discovery", "processing", "synthesis"]
type ThoughtPhase = Literal["discovery", "synthesis"]


def serialize_source(source: Source) -> JsonObject:
    """Converts a `Source` into its wire payload for the `sources` SSE frame.

    Args:
        source: The domain source record to serialize.

    Returns:
        A JSON object carrying `name` and `url`, plus any non-`None` optional
        fields (`license`, `dataset`, `provider`, and `dateRange`).
    """
    entry: JsonObject = {"name": source.name, "url": source.url}
    if source.license is not None:
        entry["license"] = source.license
    if source.dataset is not None:
        entry["dataset"] = source.dataset
    if source.provider is not None:
        entry["provider"] = source.provider
    if source.date_range is not None:
        entry["dateRange"] = source.date_range
    return entry


@dataclass(frozen=True, kw_only=True)
class StatusFrame:
    """Announces the phase the turn has entered, with a status message.

    Attributes:
        phase: The pipeline phase name (`"classify"`, `"discovery"`,
            `"processing"`, or `"synthesis"`).
        message: The user-visible status message for the phase.
    """

    event: ClassVar[EventName] = "status"
    phase: StatusPhase
    message: str

    def payload(self) -> JsonObject:
        """Returns the `data` payload of the frame.

        Returns:
            A JSON object with `phase` and `message`.
        """
        return {"phase": self.phase, "message": self.message}


@dataclass(frozen=True, kw_only=True)
class ThoughtFrame:
    """Carries a model reasoning summary from discovery or synthesis.

    Attributes:
        thought: The model thought text chunk.
        phase: The phase that produced the thought (`"discovery"` or
            `"synthesis"`).
    """

    event: ClassVar[EventName] = "thought"
    thought: str
    phase: ThoughtPhase

    def payload(self) -> JsonObject:
        """Returns the `data` payload of the frame.

        Returns:
            A JSON object with `thought` and `phase`.
        """
        return {"thought": self.thought, "phase": self.phase}


@dataclass(frozen=True, kw_only=True)
class BlockContentFrame:
    """Carries one streamed synthesis block (a text paragraph or a chart).

    Attributes:
        block: The text or chart synthesis block to serialize.
    """

    event: ClassVar[EventName] = "content"
    block: SynthesisBlock

    def payload(self) -> JsonObject:
        """Returns the `data` payload of the frame.

        Returns:
            A JSON object with `block` (`index`, `type`, and either `markdown`
            or `chart`).
        """
        if isinstance(self.block, TextBlock):
            return {
                "block": {
                    "index": self.block.index,
                    "type": "text",
                    "markdown": self.block.markdown,
                }
            }
        return {
            "block": {
                "index": self.block.index,
                "type": "chart",
                "chart": serialize_resolved_chart(self.block.chart),
            }
        }


@dataclass(frozen=True, kw_only=True)
class ToolCallFrame:
    """Carries the record of one MCP tool or server function call.

    Attributes:
        tool_call: The serialized tool-call record (`name`, `arguments`,
            `result`, and `status`).
    """

    event: ClassVar[EventName] = "content"
    tool_call: JsonObject

    def payload(self) -> JsonObject:
        """Returns the `data` payload of the frame.

        Returns:
            A JSON object with `tool_call`.
        """
        return {"tool_call": self.tool_call}


@dataclass(frozen=True, kw_only=True)
class DataStatusFrame:
    """Reports whether the tool results hold data and were cut short.

    Attributes:
        data_status: The data status mapping (`has_data`, `truncated`, and
            `message`).
    """

    event: ClassVar[EventName] = "content"
    data_status: JsonObject

    def payload(self) -> JsonObject:
        """Returns the `data` payload of the frame.

        Returns:
            A JSON object with `data_status`.
        """
        return {"data_status": self.data_status}


@dataclass(frozen=True, kw_only=True)
class SourcesFrame:
    """Lists the cited `Source` entries, numbered by position in the list.

    Attributes:
        sources: The ordered sequence of cited `Source` records.
    """

    event: ClassVar[EventName] = "content"
    sources: Sequence[Source]

    def payload(self) -> JsonObject:
        """Returns the `data` payload of the frame.

        Returns:
            A JSON object with `sources` serialized in citation order.
        """
        return {
            "sources": [serialize_source(source) for source in self.sources]
        }


@dataclass(frozen=True, kw_only=True)
class FollowUpsFrame:
    """Carries the follow-up questions, sent after the terminal frame.

    Attributes:
        follow_up_questions: The suggested follow-up question strings.
    """

    event: ClassVar[EventName] = "follow_ups"
    follow_up_questions: list[str]

    def payload(self) -> JsonObject:
        """Returns the `data` payload of the frame.

        Returns:
            A JSON object with `follow_up_questions`.
        """
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

    Attributes:
        idempotency_key: The client-supplied idempotency key for the turn.
        window: The signed conversation window ending with the completed turn,
            or `None` when the turn completed unsigned (for example, when the
            answer exceeded `MAX_RESPONSE_CHARS` or signing failed).
    """

    event: ClassVar[EventName] = "terminal"
    idempotency_key: str
    window: SignedWindow | None

    def payload(self) -> JsonObject:
        """Returns the `data` payload of the frame.

        Returns:
            A JSON object with `state: "complete"` and `idempotency_key`, plus
            `turn_index`, `hmac`, `state_slots`, `compacted_summary`, and
            `window` when `window` is not `None`.
        """
        frame: JsonObject = {
            "state": TerminalState.COMPLETE,
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

    Attributes:
        idempotency_key: The client-supplied idempotency key for the turn.
        reason: The refusal reason code (`"adversarial"`, `"off_domain"`,
            `"safety_blocked"`, or `"chat_disabled"`).
        message: The user-visible refusal explanation.
    """

    event: ClassVar[EventName] = "terminal"
    idempotency_key: str
    reason: RefusedReason
    message: str

    def payload(self) -> JsonObject:
        """Returns the `data` payload of the frame.

        Returns:
            A JSON object with `state: "refused"`, `idempotency_key`, `reason`,
            and `message` (and no `error` key).
        """
        return {
            "state": TerminalState.REFUSED,
            "idempotency_key": self.idempotency_key,
            "reason": self.reason,
            "message": self.message,
        }


@dataclass(frozen=True, kw_only=True)
class TerminalErrorFrame:
    """Ends a failed turn with a user-safe error and a reason code.

    Attributes:
        idempotency_key: The client-supplied idempotency key for the turn.
        error: The user-safe error message.
        reason: The machine-readable error code.
    """

    event: ClassVar[EventName] = "terminal"
    idempotency_key: str
    error: str
    reason: ErrorType

    def payload(self) -> JsonObject:
        """Returns the `data` payload of the frame.

        Returns:
            A JSON object with `state: "error"`, `idempotency_key`, `error`,
            and `reason`.
        """
        return {
            "state": TerminalState.ERROR,
            "idempotency_key": self.idempotency_key,
            "error": self.error,
            "reason": self.reason,
        }


type SseFrame = (
    StatusFrame
    | ThoughtFrame
    | BlockContentFrame
    | ToolCallFrame
    | DataStatusFrame
    | SourcesFrame
    | FollowUpsFrame
    | TerminalCompleteFrame
    | TerminalRefusedFrame
    | TerminalErrorFrame
)

__all__ = [
    "BlockContentFrame",
    "DataStatusFrame",
    "EventName",
    "FollowUpsFrame",
    "SourcesFrame",
    "SseFrame",
    "StatusFrame",
    "StatusPhase",
    "TerminalCompleteFrame",
    "TerminalErrorFrame",
    "TerminalRefusedFrame",
    "ThoughtFrame",
    "ThoughtPhase",
    "ToolCallFrame",
    "serialize_source",
]
