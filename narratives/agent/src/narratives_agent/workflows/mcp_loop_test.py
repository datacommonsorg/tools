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
3. A model error, a reply with neither a tool call nor text, an MCP
   transport failure, and a wall-clock timeout before any tool call
   completes end the loop with `McpLoopError` carrying a fixed, user-safe
   message; an empty reply is logged with its finish reason.
4. Reaching `MAX_ITERATIONS` or the wall-clock timeout after a tool call has
   completed returns the completed calls, flagged truncated.
5. Tool calls in flight are bounded by `MAX_CONCURRENT_TOOL_CALLS`, and
   telemetry records only declared tool names.
6. A tool call that raises `McpToolError` is recorded with status `error`
   and the JSON text of `{"error": <message>}` as its result, a successful
   result is recorded as a success whatever its text says, and telemetry
   counts both calls.
7. The first request carries the verified window as alternating messages,
   with earlier answers shortened, then the scopes and the current query;
   the next request replays the model's response and the tool results.
8. A classification appends its pattern directive to the system instruction,
   and a prompt that Gemini blocks propagates out of the loop as the client's
   `GeminiBlockedError`.
9. Each tool is declared to Gemini with its name, its description, and its
   transformed input schema, and a schema that Gemini's `Schema` rejects ends
   the loop as a model error before any request is sent.
"""

import asyncio
import json
import logging
from collections.abc import Callable, Iterator, Sequence
from typing import Any

import pytest
from google.genai import types

from narratives_agent.config_model import AgentConfig, Prompts
from narratives_agent.gemini.client import GeminiBlockedError, GeminiError
from narratives_agent.gemini.response import FunctionCall, GeminiResponse
from narratives_agent.gemini.schemas import QueryClassification
from narratives_agent.json_value import JsonObject
from narratives_agent.mcp import client as mcp_client
from narratives_agent.telemetry import ErrorType, TurnTelemetry
from narratives_agent.workflows import mcp_loop
from narratives_agent.workflows.pattern_guidance import pattern_directive
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
_CONFIG = AgentConfig()
_TOOLS = [
    mcp_client.McpTool(
        name=name,
        description="A tool.",
        input_schema={"type": "object", "properties": {}},
    )
    for name in ("first", "second")
]
_UPSTREAM_ERROR = "HTTP 500: internal detail that must not reach the user"


def _text_turn(text: str) -> GeminiResponse:
    """Returns a model response that answers with text alone."""
    return GeminiResponse(text=text)


def _tool_turn(*names: str) -> GeminiResponse:
    """Returns a model response that calls each named tool once."""
    return GeminiResponse(
        function_calls=tuple(FunctionCall(name, {"q": name}) for name in names)
    )


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

    async def call_tool(name: str, arguments: JsonObject) -> JsonObject:
        log.append(f"tool:{name}")
        return {"content": [{"type": "text", "text": f"{name} result"}]}

    monkeypatch.setattr(mcp_client, "async_call_tool", call_tool)
    return log


@pytest.fixture
def model_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., None]:
    """Scripts the model's responses, one per loop iteration.

    An exception in the script is raised by that iteration's call, as the
    Gemini client raises on a failed or blocked request.
    """

    def install(*responses: GeminiResponse | Exception) -> None:
        remaining = list(responses)

        async def request(**kwargs: Any) -> GeminiResponse:
            response = remaining.pop(0)
            if isinstance(response, Exception):
                raise response
            return response

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
        _TRANSCRIPT, _CONFIG, _TOOLS, telemetry
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

    async def call_tool(name: str, arguments: JsonObject) -> JsonObject:
        calls.append(f"tool:{name}")
        async with asyncio.timeout(1):
            await barrier.wait()
        return {"content": [{"type": "text", "text": f"{name} result"}]}

    monkeypatch.setattr(mcp_client, "async_call_tool", call_tool)
    model_answers(_tool_turn("first", "second"), _text_turn("Done."))

    result = await mcp_loop.execute_mcp_tool_loop(
        _TRANSCRIPT, _CONFIG, _TOOLS, telemetry
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
            GeminiError(_UPSTREAM_ERROR),
            ErrorType.MCP_MODEL_ERROR,
            id="model-error",
        ),
        pytest.param(
            GeminiResponse(), ErrorType.MCP_EMPTY_RESPONSE, id="empty"
        ),
        pytest.param(
            GeminiResponse(finish_reason="MALFORMED_FUNCTION_CALL"),
            ErrorType.MCP_EMPTY_RESPONSE,
            id="empty-with-finish-reason",
        ),
        pytest.param(
            _text_turn("  \n"), ErrorType.MCP_EMPTY_RESPONSE, id="blank-text"
        ),
    ],
)
@pytest.mark.asyncio
async def test_unusable_model_response_fails_closed(
    response: GeminiResponse | Exception,
    error_type: ErrorType,
    calls: list[str],
    model_answers: Callable[..., None],
    telemetry: TurnTelemetry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Test: Fail-closed handling of an unusable model response.
    # Situation: After one successful tool turn, the model call raises
    #   `GeminiError`, or returns a reply with neither a tool call nor text:
    #   with no finish reason, with `MALFORMED_FUNCTION_CALL`, or with only
    #   blank text.
    # Expectation: The loop raises `McpLoopError` with the matching type and
    #   a message that does not carry the upstream error text, instead of
    #   returning the partial results. An empty reply is logged at WARNING
    #   with its finish reason, so that the log says why the model produced
    #   nothing.
    model_answers(_tool_turn("first"), response)

    with (
        caplog.at_level(logging.WARNING, logger=mcp_loop.logger.name),
        pytest.raises(mcp_loop.McpLoopError) as raised,
    ):
        await mcp_loop.execute_mcp_tool_loop(
            _TRANSCRIPT, _CONFIG, _TOOLS, telemetry
        )

    assert raised.value.error_type == error_type
    assert _UPSTREAM_ERROR not in str(raised.value)
    if isinstance(response, GeminiResponse):
        assert f"finish reason: {response.finish_reason}" in caplog.text


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

    async def hung_request(**kwargs: Any) -> GeminiResponse:
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
        await mcp_loop.execute_mcp_tool_loop(
            _TRANSCRIPT, _CONFIG, _TOOLS, telemetry
        )

    assert raised.value.error_type == ErrorType.MCP_TIMEOUT
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

    async def request(**kwargs: Any) -> GeminiResponse:
        if responses:
            return responses.pop(0)
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    monkeypatch.setattr(mcp_loop, "MCP_LOOP_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(
        mcp_loop, "async_gemini_request_with_thought_streaming", request
    )

    result = await mcp_loop.execute_mcp_tool_loop(
        _TRANSCRIPT, _CONFIG, _TOOLS, telemetry
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
        _TRANSCRIPT, _CONFIG, _TOOLS, telemetry
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

    async def call_tool(name: str, arguments: JsonObject) -> JsonObject:
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
        await mcp_loop.execute_mcp_tool_loop(
            _TRANSCRIPT, _CONFIG, _TOOLS, telemetry
        )

    assert raised.value.error_type == ErrorType.MCP_TRANSPORT_ERROR
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

    async def call_tool(name: str, arguments: JsonObject) -> JsonObject:
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
        _TRANSCRIPT, _CONFIG, _TOOLS, telemetry
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

    await mcp_loop.execute_mcp_tool_loop(
        _TRANSCRIPT, _CONFIG, _TOOLS, telemetry
    )

    assert calls == ["scope", "tool:first", "tool:invented_tool"]
    assert telemetry.tool_calls == {"first": 1, "unknown": 1}


@pytest.mark.parametrize(
    ("outcome", "status", "result_text"),
    [
        pytest.param(
            mcp_client.McpToolError("first", "Unknown place."),
            "error",
            json.dumps({"error": "Unknown place."}),
            id="tool-error",
        ),
        pytest.param(
            {"content": [{"type": "text", "text": "Standard error: 0.4"}]},
            "success",
            "Standard error: 0.4",
            id="data-mentioning-error",
        ),
    ],
)
@pytest.mark.asyncio
async def test_tool_status_follows_the_call_outcome(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    model_answers: Callable[..., None],
    telemetry: TurnTelemetry,
    outcome: JsonObject | mcp_client.McpToolError,
    status: str,
    result_text: str,
) -> None:
    # Test: A tool call's record follows whether the call raised a tool error.
    # Situation: The tool call raises `McpToolError`, or returns a successful
    #   result whose text contains the word "error".
    # Expectation: Only the tool error is recorded with status `error`, and
    #   its result text is the JSON of `{"error": <message>}`. The success is
    #   recorded with its text. Telemetry counts the call in both cases.
    async def call_tool(name: str, arguments: JsonObject) -> JsonObject:
        if isinstance(outcome, mcp_client.McpToolError):
            raise outcome
        return outcome

    monkeypatch.setattr(mcp_client, "async_call_tool", call_tool)
    model_answers(_tool_turn("first"), _text_turn("Done."))

    result = await mcp_loop.execute_mcp_tool_loop(
        _TRANSCRIPT, _CONFIG, _TOOLS, telemetry
    )

    (record,) = result.tool_calls
    assert record["status"] == status
    assert record["result"] == result_text
    assert telemetry.tool_calls == {"first": 1}


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

    async def request(**kwargs: Any) -> GeminiResponse:
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

    await mcp_loop.execute_mcp_tool_loop(transcript, _CONFIG, _TOOLS, telemetry)

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


@pytest.mark.asyncio
async def test_the_next_request_replays_the_response_and_the_results(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    telemetry: TurnTelemetry,
) -> None:
    # Test: The conversation sent after a tool turn.
    # Situation: The model calls one tool, then answers with text.
    # Expectation: The second request carries the first request's messages,
    #   then the model's `GeminiResponse` itself as the model turn, then a
    #   user message holding the tool result as a functionResponse.
    sent: list[list[Any]] = []
    tool_turn = _tool_turn("first")

    async def request(**kwargs: Any) -> GeminiResponse:
        sent.append(list(kwargs["messages"]))
        return tool_turn if len(sent) == 1 else _text_turn("Done.")

    monkeypatch.setattr(
        mcp_loop, "async_gemini_request_with_thought_streaming", request
    )

    await mcp_loop.execute_mcp_tool_loop(
        _TRANSCRIPT, _CONFIG, _TOOLS, telemetry
    )

    first, second = sent
    assert second == [
        *first,
        tool_turn,
        {
            "role": "user",
            "parts": [
                {
                    "functionResponse": {
                        "name": "first",
                        "response": {"result": "first result"},
                    }
                }
            ],
        },
    ]


_CLASSIFICATION = QueryClassification.model_validate(
    {
        "serviceable": True,
        "pattern": "top_n_ranking",
        "geographic_shape": "comparison",
        "requires_computation": True,
    }
)


@pytest.mark.asyncio
async def test_the_classification_directive_is_appended_to_the_prompt(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    telemetry: TurnTelemetry,
) -> None:
    # Test: Pattern guidance in the discovery loop system instruction.
    # Situation: The loop runs once with a `top_n_ranking` classification of
    #   comparison shape, and once with `classification=None`.
    # Expectation: With the classification, the system instruction is the
    #   `discovery` prompt followed by the pattern directive and comparison
    #   sentence; without it, the system instruction is the base prompt alone.
    instructions: list[str] = []

    async def request(**kwargs: Any) -> GeminiResponse:
        instructions.append(kwargs["system_instruction"])
        return _text_turn("Done.")

    monkeypatch.setattr(
        mcp_loop, "async_gemini_request_with_thought_streaming", request
    )
    config = AgentConfig(prompts=Prompts(discovery="Be an analyst."))

    await mcp_loop.execute_mcp_tool_loop(
        _TRANSCRIPT, config, _TOOLS, telemetry, classification=_CLASSIFICATION
    )
    await mcp_loop.execute_mcp_tool_loop(_TRANSCRIPT, config, _TOOLS, telemetry)

    guided, plain = instructions
    assert guided.startswith("Be an analyst.")
    assert guided.endswith(pattern_directive(_CLASSIFICATION))
    assert plain == "Be an analyst."


@pytest.mark.asyncio
async def test_a_blocked_prompt_propagates_out_of_the_loop(
    calls: list[str],
    model_answers: Callable[..., None],
    telemetry: TurnTelemetry,
) -> None:
    # Test: Blocked prompt handling in `execute_mcp_tool_loop`.
    # Situation: `async_gemini_request_with_thought_streaming` raises
    #   `GeminiBlockedError("PROHIBITED_CONTENT")`.
    # Expectation: The same `GeminiBlockedError` propagates out of
    #   `execute_mcp_tool_loop` with its block reason, rather than being
    #   converted to `McpLoopError`.
    model_answers(GeminiBlockedError("PROHIBITED_CONTENT"))

    with pytest.raises(GeminiBlockedError) as raised:
        await mcp_loop.execute_mcp_tool_loop(
            _TRANSCRIPT, _CONFIG, _TOOLS, telemetry
        )

    assert raised.value.block_reason == "PROHIBITED_CONTENT"


@pytest.mark.asyncio
async def test_each_tool_is_declared_with_its_transformed_schema(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    telemetry: TurnTelemetry,
) -> None:
    # Test: Conversion of `McpTool` values into the declarations sent to
    #   Gemini.
    # Situation: The loop runs once with one tool whose input schema holds a
    #   `title`, a nullable `anyOf` property with a default, and a map-valued
    #   object property.
    # Expectation: The request declares the tool with its name, its
    #   description, and the schema `transform_schema_for_gemini` produces:
    #   `title` dropped, the union collapsed to its non-null type, and the map
    #   described in prose.
    declarations: list[Sequence[types.FunctionDeclaration]] = []

    async def request(
        *,
        tools: Sequence[types.FunctionDeclaration],
        **_: object,
    ) -> GeminiResponse:
        declarations.append(tools)
        return _text_turn("Done.")

    monkeypatch.setattr(
        mcp_loop, "async_gemini_request_with_thought_streaming", request
    )
    tool = mcp_client.McpTool(
        name="get_observations",
        description="Fetches observations.",
        input_schema={
            "type": "object",
            "title": "GetObservations",
            "properties": {
                "place": {"type": "string", "title": "Place"},
                "date": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "default": "latest",
                },
                "entities": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": ["place"],
        },
    )

    await mcp_loop.execute_mcp_tool_loop(
        _TRANSCRIPT, _CONFIG, [tool], telemetry
    )

    ((declaration,),) = declarations
    assert declaration.model_dump(mode="json", exclude_none=True) == {
        "name": "get_observations",
        "description": "Fetches observations.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "place": {"type": "STRING"},
                "date": {"type": "STRING", "default": "latest"},
                "entities": {
                    "type": "OBJECT",
                    "description": (
                        "A JSON object whose keys are caller-defined and "
                        "whose values are string values."
                    ),
                },
            },
            "required": ["place"],
        },
    }


@pytest.mark.asyncio
async def test_an_invalid_tool_schema_ends_the_loop_as_a_model_error(
    calls: list[str],
    model_answers: Callable[..., None],
    telemetry: TurnTelemetry,
) -> None:
    # Test: A tool schema that is not a valid Gemini schema.
    # Situation: The tool's input schema gives `required` as a string, which
    #   Gemini's `Schema` rejects.
    # Expectation: The loop raises `McpLoopError` with type
    #   `mcp_model_error`, as a failed model call does, and sends no model
    #   request.
    model_answers()
    tool = mcp_client.McpTool(
        name="first",
        description="A tool.",
        input_schema={"type": "object", "required": "place"},
    )

    with pytest.raises(mcp_loop.McpLoopError) as raised:
        await mcp_loop.execute_mcp_tool_loop(
            _TRANSCRIPT, _CONFIG, [tool], telemetry
        )

    assert raised.value.error_type == ErrorType.MCP_MODEL_ERROR
    assert telemetry.mcp_iterations == 0
