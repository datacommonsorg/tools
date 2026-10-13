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
"""Tests for the MCP tool-calling loop in `mcp_loop`.

Verifies that:
1. The loop ends when the model answers without function calls.
2. The session scope is opened before any tool call, and every call of one
   model turn runs concurrently.
3. A model error, a response without candidates, an empty reply, an MCP
   transport failure, and a wall-clock timeout before any tool call
   completes end the loop with `McpLoopError` carrying a fixed, user-safe
   message.
4. Reaching `MAX_ITERATIONS` or the wall-clock timeout after a tool call has
   completed returns the completed calls, flagged truncated.
5. Tool calls in flight are bounded by `MAX_CONCURRENT_TOOL_CALLS`, and
   telemetry records only declared tool names.
6. A tool call's status is derived from the shape of its result.
7. The first request carries the verified window as alternating messages,
   with earlier answers shortened, then the scopes and the current query.
"""

import asyncio
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from narratives_agent.mcp import client as mcp_client
from narratives_agent.telemetry import TurnTelemetry
from narratives_agent.workflows import mcp_loop
from narratives_agent.workflows.transcript import (
    ConversationStateSlots,
    QueryScope,
    Transcript,
    Turn,
)

_TRANSCRIPT = Transcript(
    turns=[],
    compacted_summary=None,
    current_query="What is the population of France?",
    current_idempotency_key="key-1",
)
_TOOLS = [
    {"name": name, "description": "A tool."} for name in ("first", "second")
]
_UPSTREAM_ERROR = "HTTP 500: internal detail that must not reach the user"


def _text_turn(text: str) -> dict[str, Any]:
    """Returns a model response that answers with text alone."""
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def _tool_turn(*names: str) -> dict[str, Any]:
    """Returns a model response that calls each named tool once."""
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"functionCall": {"name": name, "args": {"q": name}}}
                        for name in names
                    ]
                }
            }
        ]
    }


@pytest.fixture
def telemetry() -> Iterator[TurnTelemetry]:
    """Yields a `TurnTelemetry` and finishes its span after the test."""
    turn_telemetry = TurnTelemetry()
    yield turn_telemetry
    turn_telemetry.finish("complete")


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Records session-scope and tool calls, in order, as they happen."""
    log: list[str] = []
    monkeypatch.setattr(
        mcp_client, "ensure_session_scope", lambda: log.append("scope")
    )

    async def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        log.append(f"tool:{name}")
        return {"content": [{"type": "text", "text": f"{name} result"}]}

    monkeypatch.setattr(mcp_client, "async_call_tool", call_tool)
    return log


@pytest.fixture
def model_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., None]:
    """Scripts the model's responses, one per loop iteration."""

    def install(*responses: dict[str, Any]) -> None:
        remaining = list(responses)

        async def request(**kwargs: Any) -> dict[str, Any]:
            return remaining.pop(0)

        monkeypatch.setattr(
            mcp_loop, "async_gemini_request_with_thought_streaming", request
        )

    return install


@pytest.mark.asyncio
async def test_text_answer_ends_the_loop(
    calls: list[str],
    model_answers: Callable[..., None],
    telemetry: TurnTelemetry,
) -> None:
    # Test: The loop terminates when the model returns text without function
    #   calls.
    # Situation: The model answers the first iteration with text alone.
    # Expectation: The loop returns after one iteration with no tool calls
    #   and no truncation.
    model_answers(_text_turn("Done."))

    result = await mcp_loop.execute_mcp_tool_loop(
        _TRANSCRIPT, {}, _TOOLS, telemetry
    )

    assert result == mcp_loop.McpLoopResult()
    assert telemetry.mcp_iterations == 1
    assert calls == ["scope"]


@pytest.mark.asyncio
async def test_tool_calls_of_one_turn_run_concurrently_in_the_scope(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    model_answers: Callable[..., None],
    telemetry: TurnTelemetry,
) -> None:
    # Test: Tool calls from a single model turn run concurrently within the
    #   session scope.
    # Situation: The model calls two tools in one turn, then returns a text
    #   response. Each tool call waits at a two-party barrier, which only
    #   releases once both calls are in flight at the same time.
    # Expectation: The session scope is opened before either call, both
    #   calls complete, and both results reach the gathered text.
    barrier = asyncio.Barrier(2)

    async def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        calls.append(f"tool:{name}")
        async with asyncio.timeout(1):
            await barrier.wait()
        return {"content": [{"type": "text", "text": f"{name} result"}]}

    monkeypatch.setattr(mcp_client, "async_call_tool", call_tool)
    model_answers(_tool_turn("first", "second"), _text_turn("Done."))

    result = await mcp_loop.execute_mcp_tool_loop(
        _TRANSCRIPT, {}, _TOOLS, telemetry
    )

    assert calls == ["scope", "tool:first", "tool:second"]
    assert [record["name"] for record in result.tool_calls] == [
        "first",
        "second",
    ]
    assert result.results_text == (
        "Tool: first\nResult: first result\n\n"
        "Tool: second\nResult: second result"
    )
    assert telemetry.tool_calls == {"first": 1, "second": 1}
    assert not result.truncated


@pytest.mark.parametrize(
    ("response", "error_type"),
    [
        pytest.param(
            {"error": _UPSTREAM_ERROR}, "mcp_model_error", id="model-error"
        ),
        pytest.param({"candidates": []}, "mcp_no_candidates", id="empty"),
        pytest.param({}, "mcp_no_candidates", id="no-candidates-key"),
        pytest.param(
            {"candidates": [{"content": {"parts": []}}]},
            "mcp_empty_response",
            id="no-parts",
        ),
        pytest.param(_text_turn("  \n"), "mcp_empty_response", id="blank-text"),
    ],
)
@pytest.mark.asyncio
async def test_unusable_model_response_fails_closed(
    response: dict[str, Any],
    error_type: str,
    calls: list[str],
    model_answers: Callable[..., None],
    telemetry: TurnTelemetry,
) -> None:
    # Test: Fail-closed handling of an unusable model response.
    # Situation: After one successful tool turn, the model call returns an
    #   error, an empty candidate list, no candidates at all, a candidate
    #   with no parts, or a candidate whose only text is blank.
    # Expectation: The loop raises `McpLoopError` with the matching type and
    #   a message that does not carry the upstream error text, instead of
    #   returning the partial results.
    model_answers(_tool_turn("first"), response)

    with pytest.raises(mcp_loop.McpLoopError) as raised:
        await mcp_loop.execute_mcp_tool_loop(_TRANSCRIPT, {}, _TOOLS, telemetry)

    assert raised.value.error_type == error_type
    assert _UPSTREAM_ERROR not in str(raised.value)


@pytest.mark.asyncio
async def test_wall_clock_timeout_before_any_tool_call_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    telemetry: TurnTelemetry,
) -> None:
    # Test: Exceeding the loop's wall-clock timeout before any tool call has
    #   completed raises `McpLoopError`.
    # Situation: The bound is shortened to 10 ms and the first model call
    #   never returns.
    # Expectation: The loop raises `McpLoopError` of type `mcp_timeout`, and
    #   the hung model call is canceled.
    canceled = asyncio.Event()

    async def hung_request(**kwargs: Any) -> dict[str, Any]:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            canceled.set()
            raise
        raise AssertionError("unreachable")

    monkeypatch.setattr(mcp_loop, "MCP_LOOP_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(
        mcp_loop, "async_gemini_request_with_thought_streaming", hung_request
    )

    with pytest.raises(mcp_loop.McpLoopError) as raised:
        await mcp_loop.execute_mcp_tool_loop(_TRANSCRIPT, {}, _TOOLS, telemetry)

    assert raised.value.error_type == "mcp_timeout"
    assert canceled.is_set()


@pytest.mark.asyncio
async def test_wall_clock_timeout_returns_completed_calls_flagged_truncated(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    telemetry: TurnTelemetry,
) -> None:
    # Test: Exceeding the loop's wall-clock timeout after a tool call has
    #   completed returns the completed calls with `truncated` set.
    # Situation: The bound is shortened to 50 ms. The first model call
    #   requests one tool, and the second model call never returns.
    # Expectation: The loop returns the completed tool call, and its result
    #   text, with `truncated` set, rather than raising an exception.
    responses = [_tool_turn("first")]

    async def request(**kwargs: Any) -> dict[str, Any]:
        if responses:
            return responses.pop(0)
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    monkeypatch.setattr(mcp_loop, "MCP_LOOP_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(
        mcp_loop, "async_gemini_request_with_thought_streaming", request
    )

    result = await mcp_loop.execute_mcp_tool_loop(
        _TRANSCRIPT, {}, _TOOLS, telemetry
    )

    assert result.truncated
    assert [record["name"] for record in result.tool_calls] == ["first"]
    assert result.results_text == "Tool: first\nResult: first result"
    assert telemetry.mcp_iterations == 2


@pytest.mark.asyncio
async def test_iteration_cap_returns_partial_results_flagged_truncated(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    model_answers: Callable[..., None],
    telemetry: TurnTelemetry,
) -> None:
    # Test: Reaching `MAX_ITERATIONS` returns partial results with `truncated`
    #   set to `True`.
    # Situation: The cap is lowered to two iterations and the model calls a
    #   tool on both.
    # Expectation: The loop returns both tool results with `truncated` set,
    #   rather than raising an exception.
    monkeypatch.setattr(mcp_loop, "MAX_ITERATIONS", 2)
    model_answers(_tool_turn("first"), _tool_turn("second"))

    result = await mcp_loop.execute_mcp_tool_loop(
        _TRANSCRIPT, {}, _TOOLS, telemetry
    )

    assert result.truncated
    assert [record["name"] for record in result.tool_calls] == [
        "first",
        "second",
    ]
    assert telemetry.mcp_iterations == 2


@pytest.mark.asyncio
async def test_a_transport_failure_fails_closed_and_cancels_siblings(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    model_answers: Callable[..., None],
    telemetry: TurnTelemetry,
) -> None:
    # Test: Fail-closed handling of an MCP transport failure.
    # Situation: The model calls two tools in one turn. The first raises
    #   `McpTransportError` once the second is in flight; the second never
    #   returns on its own.
    # Expectation: The loop raises `McpLoopError` of type
    #   `mcp_transport_error`, with a message that does not carry the
    #   transport detail, and the second call is canceled rather than left
    #   running.
    second_started = asyncio.Event()
    second_canceled = asyncio.Event()

    async def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "second":
            second_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                second_canceled.set()
                raise
        await second_started.wait()
        raise mcp_client.McpTransportError() from OSError(_UPSTREAM_ERROR)

    monkeypatch.setattr(mcp_client, "async_call_tool", call_tool)
    model_answers(_tool_turn("first", "second"))

    with pytest.raises(mcp_loop.McpLoopError) as raised:
        await mcp_loop.execute_mcp_tool_loop(_TRANSCRIPT, {}, _TOOLS, telemetry)

    assert raised.value.error_type == "mcp_transport_error"
    assert _UPSTREAM_ERROR not in str(raised.value)
    assert second_canceled.is_set()
    assert telemetry.tool_calls == {}


@pytest.mark.asyncio
async def test_tool_calls_in_flight_are_bounded(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    model_answers: Callable[..., None],
    telemetry: TurnTelemetry,
) -> None:
    # Test: Concurrent tool calls within a turn are bounded by
    #   `MAX_CONCURRENT_TOOL_CALLS`.
    # Situation: `MAX_CONCURRENT_TOOL_CALLS` is lowered to 2 and the model
    #   calls four tools in one turn, each of which yields to the event loop
    #   while it counts the calls in flight.
    # Expectation: All four calls complete, and no more than two were ever
    #   in flight at once.
    monkeypatch.setattr(mcp_loop, "MAX_CONCURRENT_TOOL_CALLS", 2)
    in_flight = 0
    peak = 0

    async def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0)
        in_flight -= 1
        return {"content": [{"type": "text", "text": f"{name} result"}]}

    monkeypatch.setattr(mcp_client, "async_call_tool", call_tool)
    model_answers(
        _tool_turn("first", "second", "first", "second"), _text_turn("Done.")
    )

    result = await mcp_loop.execute_mcp_tool_loop(
        _TRANSCRIPT, {}, _TOOLS, telemetry
    )

    assert len(result.tool_calls) == 4
    assert peak == 2


@pytest.mark.asyncio
async def test_telemetry_records_undeclared_tool_names_as_unknown(
    calls: list[str],
    model_answers: Callable[..., None],
    telemetry: TurnTelemetry,
) -> None:
    # Test: Telemetry records undeclared tool names as "unknown".
    # Situation: The model calls one declared tool and one name that was
    #   never declared.
    # Expectation: Both calls run, and telemetry counts the declared name
    #   and records the other as "unknown".
    model_answers(_tool_turn("first", "invented_tool"), _text_turn("Done."))

    await mcp_loop.execute_mcp_tool_loop(_TRANSCRIPT, {}, _TOOLS, telemetry)

    assert calls == ["scope", "tool:first", "tool:invented_tool"]
    assert telemetry.tool_calls == {"first": 1, "unknown": 1}


@pytest.mark.parametrize(
    ("tool_result", "status"),
    [
        pytest.param({"error": "Unknown place."}, "error", id="error-result"),
        pytest.param(
            {"content": [{"type": "text", "text": "Standard error: 0.4"}]},
            "success",
            id="data-mentioning-error",
        ),
    ],
)
@pytest.mark.asyncio
async def test_tool_status_follows_the_result_shape(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    model_answers: Callable[..., None],
    telemetry: TurnTelemetry,
    tool_result: dict[str, Any],
    status: str,
) -> None:
    # Test: A tool call's status is derived from the shape of its result.
    # Situation: The tool returns either the client's `{"error": ...}`
    #   failure result or a successful result whose text contains the word
    #   "error".
    # Expectation: Only the failure result is recorded with status `error`.
    async def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return tool_result

    monkeypatch.setattr(mcp_client, "async_call_tool", call_tool)
    model_answers(_tool_turn("first"), _text_turn("Done."))

    result = await mcp_loop.execute_mcp_tool_loop(
        _TRANSCRIPT, {}, _TOOLS, telemetry
    )

    (record,) = result.tool_calls
    assert record["status"] == status


@pytest.mark.asyncio
async def test_the_first_request_carries_the_transcript(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    telemetry: TurnTelemetry,
) -> None:
    # Test: Multi-turn context reaches the tool loop.
    # Situation: A window has one earlier turn with a long answer and one
    #   data scope, followed by a query that refers back to it.
    # Expectation: The first request alternates user and model messages,
    #   quotes at most MCP_HISTORY_RESPONSE_CHARS of the earlier answer, and
    #   ends with a user message holding the scope and the current query.
    sent: list[list[dict[str, Any]]] = []

    async def request(**kwargs: Any) -> dict[str, Any]:
        sent.append(list(kwargs["messages"]))
        return _text_turn("Done.")

    monkeypatch.setattr(
        mcp_loop, "async_gemini_request_with_thought_streaming", request
    )
    earlier = Turn(
        turn_index=0,
        idempotency_key="key-0",
        user_query="Population of France?",
        model_response="x" * (mcp_loop.MCP_HISTORY_RESPONSE_CHARS + 500),
        state_slots=ConversationStateSlots(
            scopes=[
                QueryScope(
                    places={"country/FRA": "France"},
                    variables={"Count_Person": "Total Population"},
                )
            ]
        ),
        hmac="0" * 64,
    )
    transcript = Transcript(
        turns=[earlier],
        compacted_summary=None,
        current_query="And for Germany?",
        current_idempotency_key="key-1",
    )

    await mcp_loop.execute_mcp_tool_loop(transcript, {}, _TOOLS, telemetry)

    (contents,) = sent
    assert [message["role"] for message in contents] == [
        "user",
        "model",
        "user",
    ]
    assert contents[0]["parts"] == [{"text": "Population of France?"}]
    answer = contents[1]["parts"][0]["text"]
    assert len(answer) <= mcp_loop.MCP_HISTORY_RESPONSE_CHARS + 3
    final = contents[2]["parts"][0]["text"]
    assert "Turn 1: places: France (country/FRA)" in final
    assert final.endswith(
        "<current_request>\nAnd for Germany?\n</current_request>"
    )
