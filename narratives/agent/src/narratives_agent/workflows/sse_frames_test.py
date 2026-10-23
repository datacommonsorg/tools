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
"""Tests for the SSE frame types in `sse_frames`.

Verifies that:
1. Every non-terminal frame serializes to its event name and to exactly the
   JSON `data` string the browser reads, with the same keys in the same
   order.
2. The terminal frames carry exactly the keys of their outcome: `error` and
   `reason` on an error, `reason` and `message` without `error` on a
   refusal, the signing keys with `compacted_summary` present even when it
   is `null` on a signed completion, and no signing keys on an unsigned
   completion.
"""

import json

import pytest

from narratives_agent.workflows.sse_frames import (
    ChartConfigFrame,
    DataStatusFrame,
    EventName,
    FollowUpsFrame,
    SourcesFrame,
    SseFrame,
    StatusFrame,
    TerminalCompleteFrame,
    TerminalErrorFrame,
    TerminalRefusedFrame,
    TextFrame,
    ThoughtFrame,
    ToolCallFrame,
)
from narratives_agent.workflows.transcript import (
    ConversationStateSlots,
    QueryScope,
    SignedWindow,
    Turn,
)

_IDEMPOTENCY_KEY = "key-4"
_EARLIER_HMAC = "a" * 64
_LATEST_HMAC = "b" * 64


def _serialize(frame: SseFrame) -> tuple[EventName, str]:
    """Returns the event name and `data` string the chat route sends."""
    return frame.event, json.dumps(frame.payload())


def _turn(turn_index: int, idempotency_key: str, signature: str) -> Turn:
    """Returns a signed turn whose slots hold one scope."""
    return Turn(
        turn_index=turn_index,
        idempotency_key=idempotency_key,
        user_query="What is the population of France?",
        model_response="About 68 million.",
        state_slots=ConversationStateSlots(
            scopes=[
                QueryScope(
                    places={"country/FRA": "France"},
                    variables={"Count_Person": "Total Population"},
                    date_range=("2023", "2023"),
                )
            ]
        ),
        hmac=signature,
    )


def _window(compacted_summary: str | None) -> SignedWindow:
    """Returns a two-turn window ending with the turn that just completed."""
    return SignedWindow(
        turns=[
            _turn(3, "key-3", _EARLIER_HMAC),
            _turn(4, _IDEMPOTENCY_KEY, _LATEST_HMAC),
        ],
        compacted_summary=compacted_summary,
    )


_SIGNED_FIELDS = (
    f'"turn_index": 4, "hmac": "{_LATEST_HMAC}", "state_slots": '
    '{"scopes": [{"places": {"country/FRA": "France"}, "parent_place": null, '
    '"child_place_type": null, "variables": {"Count_Person": '
    '"Total Population"}, "date_range": ["2023", "2023"]}]}'
)
_WINDOW_FIELD = (
    f'"window": [{{"turn_index": 3, "idempotency_key": "key-3", '
    f'"hmac": "{_EARLIER_HMAC}"}}, {{"turn_index": 4, '
    f'"idempotency_key": "{_IDEMPOTENCY_KEY}", "hmac": "{_LATEST_HMAC}"}}]'
)


@pytest.mark.parametrize(
    ("frame", "expected"),
    [
        pytest.param(
            StatusFrame(phase="discovery", message="Querying data tools..."),
            (
                "status",
                '{"phase": "discovery", "message": "Querying data tools..."}',
            ),
            id="status",
        ),
        pytest.param(
            ThoughtFrame(thought="Looking up France.", phase="synthesis"),
            (
                "thought",
                '{"thought": "Looking up France.", "phase": "synthesis"}',
            ),
            id="thought",
        ),
        pytest.param(
            TextFrame(text="About 68 million."),
            ("content", '{"text": "About 68 million."}'),
            id="text",
        ),
        pytest.param(
            ToolCallFrame(
                tool_call={
                    "name": "get_observations",
                    "arguments": {"place_dcid": "country/FRA"},
                    "result": '{"data": {}}',
                    "status": "success",
                }
            ),
            (
                "content",
                '{"tool_call": {"name": "get_observations", "arguments": '
                '{"place_dcid": "country/FRA"}, "result": '
                '"{\\"data\\": {}}", "status": "success"}}',
            ),
            id="tool_call",
        ),
        pytest.param(
            DataStatusFrame(data_status={"has_data": True, "truncated": False}),
            (
                "content",
                '{"data_status": {"has_data": true, "truncated": false}}',
            ),
            id="data_status",
        ),
        pytest.param(
            SourcesFrame(
                sources=[{"name": "INSEE", "url": "https://insee.fr/"}]
            ),
            (
                "content",
                '{"sources": [{"name": "INSEE", "url": "https://insee.fr/"}]}',
            ),
            id="sources",
        ),
        pytest.param(
            ChartConfigFrame(
                chart_config={"should_render": False, "hide_charts": True}
            ),
            (
                "content",
                '{"chart_config": {"should_render": false, '
                '"hide_charts": true}}',
            ),
            id="chart_config",
        ),
        pytest.param(
            FollowUpsFrame(follow_up_questions=["And Spain?"]),
            ("follow_ups", '{"follow_up_questions": ["And Spain?"]}'),
            id="follow_ups",
        ),
    ],
)
def test_a_frame_serializes_to_its_wire_form(
    frame: SseFrame, expected: tuple[EventName, str]
) -> None:
    # Test: Wire form of every non-terminal frame.
    # Situation: One frame of each status, thought, content, and follow-up
    #   type is serialized as the chat route serializes it.
    # Expectation: The event name and the JSON `data` string equal the
    #   payload the browser reads, key for key and in the same order.
    assert _serialize(frame) == expected


def test_an_error_frame_carries_the_error_and_the_reason() -> None:
    # Test: Wire form of the `error` terminal frame.
    # Situation: A turn ends with a user-safe message and a reason code.
    # Expectation: The payload holds `state`, `idempotency_key`, `error`,
    #   and `reason`, and no signing or refusal keys.
    frame = TerminalErrorFrame(
        idempotency_key=_IDEMPOTENCY_KEY,
        error="The data request took too long.",
        reason="mcp_timeout",
    )

    assert _serialize(frame) == (
        "terminal",
        '{"state": "error", "idempotency_key": "key-4", '
        '"error": "The data request took too long.", "reason": "mcp_timeout"}',
    )


def test_a_refused_frame_carries_no_error_key() -> None:
    # Test: Wire form of the `refused` terminal frame.
    # Situation: A turn is refused as adversarial.
    # Expectation: The payload holds `state`, `idempotency_key`, `reason`,
    #   and `message`, and no `error` key, so the browser renders a notice.
    frame = TerminalRefusedFrame(
        idempotency_key=_IDEMPOTENCY_KEY,
        reason="adversarial",
        message="We cannot service that request.",
    )

    assert _serialize(frame) == (
        "terminal",
        '{"state": "refused", "idempotency_key": "key-4", '
        '"reason": "adversarial", '
        '"message": "We cannot service that request."}',
    )


def test_a_signed_complete_frame_carries_the_summary_and_the_window() -> None:
    # Test: Wire form of a signed `complete` frame after compaction.
    # Situation: The completed turn is the second of a window that carries a
    #   compacted summary.
    # Expectation: The payload adds the latest turn's index, signature, and
    #   slots, the summary, and every turn of the window, oldest first.
    frame = TerminalCompleteFrame(
        idempotency_key=_IDEMPOTENCY_KEY, window=_window("Earlier turns.")
    )

    assert _serialize(frame) == (
        "terminal",
        '{"state": "complete", "idempotency_key": "key-4", '
        f'{_SIGNED_FIELDS}, "compacted_summary": "Earlier turns.", '
        f"{_WINDOW_FIELD}}}",
    )


def test_a_signed_complete_frame_keeps_a_null_summary_key() -> None:
    # Test: Key presence of `compacted_summary` in a signed `complete` frame.
    # Situation: The signed window carries no compacted summary.
    # Expectation: `compacted_summary` is present with the value `null`
    #   rather than omitted.
    frame = TerminalCompleteFrame(
        idempotency_key=_IDEMPOTENCY_KEY, window=_window(None)
    )

    assert _serialize(frame) == (
        "terminal",
        '{"state": "complete", "idempotency_key": "key-4", '
        f'{_SIGNED_FIELDS}, "compacted_summary": null, {_WINDOW_FIELD}}}',
    )


def test_an_unsigned_complete_frame_carries_no_window_keys() -> None:
    # Test: Wire form of a `complete` frame for a turn that was not signed.
    # Situation: The turn completed without a signed window.
    # Expectation: The payload holds only `state` and `idempotency_key`, so
    #   the browser leaves the turn out of later requests.
    frame = TerminalCompleteFrame(idempotency_key=_IDEMPOTENCY_KEY, window=None)

    assert _serialize(frame) == (
        "terminal",
        '{"state": "complete", "idempotency_key": "key-4"}',
    )
