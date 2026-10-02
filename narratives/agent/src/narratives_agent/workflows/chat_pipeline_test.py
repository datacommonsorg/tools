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
"""Tests for `run_turn` in the chat pipeline.

Verifies that:
1. A complete turn emits the final payload, then the follow-ups, and is
   recorded as `complete`.
2. Missing or timed-out MCP tools, a failed MCP loop, or a failed or empty
   synthesis stream ends the turn with an error payload and records the
   matching error type in telemetry.
3. A chart config that misses its join timeout is canceled and the turn
   completes without charts.
4. Cancellation mid-turn cancels the background chart task and is recorded
   as `canceled`; cancellation after the final payload stays `complete`.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import pytest

from narratives_agent.gemini.client import GeminiStreamError
from narratives_agent.mcp import client as mcp_client
from narratives_agent.telemetry import TerminalState, TokenUsage, TurnTelemetry
from narratives_agent.workflows import chat_pipeline
from narratives_agent.workflows.mcp_loop import McpLoopError, McpLoopResult

_QUESTION = "What is the population of France?"
_ANSWER = "About 68 million."
_CHARTS = {"should_render": True, "charts": [{"title": "Population"}]}
_FOLLOW_UPS = ["And Spain?"]
_TOOL_CALL = {
    "name": "get_observations",
    "arguments": {},
    "result": "68000000",
    "status": "success",
}


class _RecordingTelemetry(TurnTelemetry):
    """Subclasses `TurnTelemetry` to record the terminal state of the turn."""

    finished: list[tuple[TerminalState, str | None]]

    def finish(
        self, state: TerminalState, error_type: str | None = None
    ) -> None:
        self.finished.append((state, error_type))
        super().finish(state, error_type)


@dataclass
class _Turn:
    """Holds the stubbed collaborators of one turn and their recorded state."""

    payloads: list[dict[str, Any]] = field(default_factory=list)
    finished: list[tuple[TerminalState, str | None]] = field(
        default_factory=list
    )
    synthesis_calls: int = 0
    chart_canceled: asyncio.Event = field(default_factory=asyncio.Event)
    chart_release: asyncio.Event = field(default_factory=asyncio.Event)
    synthesis_release: asyncio.Event = field(default_factory=asyncio.Event)
    follow_ups_release: asyncio.Event = field(default_factory=asyncio.Event)

    def emit(self, payload: dict[str, Any]) -> None:
        self.payloads.append(payload)


@pytest.fixture
def turn(monkeypatch: pytest.MonkeyPatch) -> _Turn:
    """Stubs every external call of a turn so each stage succeeds at once."""
    stub = _Turn()
    stub.chart_release.set()
    stub.synthesis_release.set()
    stub.follow_ups_release.set()

    def telemetry() -> _RecordingTelemetry:
        recording = _RecordingTelemetry()
        recording.finished = stub.finished
        return recording

    async def get_tools() -> list[dict[str, Any]]:
        return [{"name": "get_observations"}]

    async def tool_loop(*args: Any, **kwargs: Any) -> McpLoopResult:
        return McpLoopResult(
            results_text="Tool: get_observations\nResult: 68000000",
            tool_calls=[dict(_TOOL_CALL)],
        )

    async def answer() -> AsyncIterator[str]:
        await stub.synthesis_release.wait()
        yield _ANSWER

    async def synthesis(**kwargs: Any) -> AsyncIterator[str]:
        stub.synthesis_calls += 1
        return answer()

    async def chart_config(
        results: str, question: str, usage: TokenUsage
    ) -> dict[str, Any]:
        try:
            await stub.chart_release.wait()
        except asyncio.CancelledError:
            stub.chart_canceled.set()
            raise
        return dict(_CHARTS)

    async def validate(text: str, question: str, usage: TokenUsage) -> bool:
        return True

    async def follow_ups(
        question: str, topics: list[str], usage: TokenUsage
    ) -> list[str]:
        await stub.follow_ups_release.wait()
        return list(_FOLLOW_UPS)

    monkeypatch.setattr(chat_pipeline, "TurnTelemetry", telemetry)
    monkeypatch.setattr(
        chat_pipeline, "load_config", lambda: {"mcp": {"enabled": True}}
    )
    monkeypatch.setattr(mcp_client, "ensure_session_scope", lambda: None)
    monkeypatch.setattr(mcp_client, "async_get_tools", get_tools)
    monkeypatch.setattr(chat_pipeline, "execute_mcp_tool_loop", tool_loop)
    monkeypatch.setattr(
        chat_pipeline,
        "check_data_availability",
        lambda tool_calls: {"has_data": True},
    )
    monkeypatch.setattr(
        chat_pipeline,
        "extract_provenance_from_mcp_results",
        lambda tool_calls: [{"name": "INSEE", "url": "https://insee.fr/"}],
    )
    monkeypatch.setattr(chat_pipeline, "async_gemini_stream", synthesis)
    monkeypatch.setattr(chat_pipeline, "get_chart_config", chart_config)
    monkeypatch.setattr(chat_pipeline, "validate_data_response", validate)
    monkeypatch.setattr(
        chat_pipeline, "generate_follow_up_questions", follow_ups
    )
    return stub


async def _start_and_wait_for(
    turn: _Turn, predicate_key: str
) -> asyncio.Task[None]:
    """Starts the turn and waits until it emits a payload with the key."""
    task = asyncio.create_task(chat_pipeline.run_turn(_QUESTION, [], turn.emit))
    async with asyncio.timeout(1):
        while not any(predicate_key in p for p in turn.payloads):
            await asyncio.sleep(0)
    return task


@pytest.mark.asyncio
async def test_complete_turn_emits_the_answer_then_the_follow_ups(
    turn: _Turn,
) -> None:
    # Test: The payload sequence of a turn in which every phase succeeds.
    # Situation: Tools, synthesis, chart config, and follow-ups all succeed.
    # Expectation: The answer text is emitted first, followed by the final
    #   payload with the chart config and then the follow-up questions, and
    #   the turn is recorded as `complete`.
    await chat_pipeline.run_turn(_QUESTION, [], turn.emit)

    keys = [next(iter(payload)) for payload in turn.payloads]
    assert keys.index("text") < keys.index("chart_config")
    assert keys.index("chart_config") < keys.index("follow_up_questions")
    final = next(p for p in turn.payloads if "chart_config" in p)
    assert final["chart_config"] == _CHARTS
    assert final["done"] is True
    assert turn.payloads[-1] == {"follow_up_questions": _FOLLOW_UPS}
    assert turn.finished == [("complete", None)]


@pytest.mark.asyncio
async def test_failed_tool_loop_ends_the_turn_before_synthesis(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: Fail-closed handling of an MCP loop failure.
    # Situation: The tool loop raises `McpLoopError` of type `mcp_timeout`.
    # Expectation: The turn emits one error payload with the loop's message,
    #   never calls synthesis, and is recorded as `error` with `mcp_timeout`.
    async def failing_loop(*args: Any, **kwargs: Any) -> McpLoopResult:
        raise McpLoopError("mcp_timeout", "The data request took too long.")

    monkeypatch.setattr(chat_pipeline, "execute_mcp_tool_loop", failing_loop)

    await chat_pipeline.run_turn(_QUESTION, [], turn.emit)

    assert turn.payloads[-1] == {"error": "The data request took too long."}
    assert not any("done" in payload for payload in turn.payloads)
    assert turn.synthesis_calls == 0
    assert turn.finished == [("error", "mcp_timeout")]


@pytest.mark.asyncio
async def test_slow_chart_config_is_canceled_and_charts_are_dropped(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: The chart-config join timeout.
    # Situation: The join timeout is shortened to 10 ms and chart
    #   configuration never finishes.
    # Expectation: The chart task is canceled, and the turn completes with
    #   `should_render` set to `False`.
    monkeypatch.setattr(
        chat_pipeline, "CHART_CONFIG_JOIN_TIMEOUT_SECONDS", 0.01
    )
    turn.chart_release.clear()

    await chat_pipeline.run_turn(_QUESTION, [], turn.emit)

    final = next(p for p in turn.payloads if "chart_config" in p)
    assert final["chart_config"] == {"should_render": False}
    assert turn.chart_canceled.is_set()
    assert turn.finished == [("complete", None)]


@pytest.mark.asyncio
async def test_a_failed_chart_task_leaves_the_turn_complete(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: Containment of a chart-configuration failure.
    # Situation: Chart configuration raises after the answer has streamed.
    # Expectation: The turn completes with `should_render` set to `False`
    #   rather than ending as an internal error.
    async def failing_chart_config(*args: Any) -> dict[str, Any]:
        raise RuntimeError("chart config failed")

    monkeypatch.setattr(chat_pipeline, "get_chart_config", failing_chart_config)

    await chat_pipeline.run_turn(_QUESTION, [], turn.emit)

    assert {"text": _ANSWER} in turn.payloads
    final = next(p for p in turn.payloads if "chart_config" in p)
    assert final["chart_config"] == {"should_render": False}
    assert final["done"] is True
    assert not any("error" in payload for payload in turn.payloads)
    assert turn.finished == [("complete", None)]


@pytest.mark.asyncio
async def test_a_failed_chart_validation_hides_the_charts(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: Containment of a chart-validation failure.
    # Situation: The data-validation check raises after the answer has
    #   streamed, and chart configuration succeeds.
    # Expectation: The turn completes with the charts hidden rather than
    #   ending as an internal error.
    async def failing_validate(*args: Any) -> bool:
        raise RuntimeError("validation failed")

    monkeypatch.setattr(
        chat_pipeline, "validate_data_response", failing_validate
    )

    await chat_pipeline.run_turn(_QUESTION, [], turn.emit)

    final = next(p for p in turn.payloads if "chart_config" in p)
    assert final["chart_config"] == {**_CHARTS, "hide_charts": True}
    assert final["done"] is True
    assert not any("error" in payload for payload in turn.payloads)
    assert turn.finished == [("complete", None)]


@pytest.mark.asyncio
async def test_cancel_mid_turn_cancels_the_chart_task(turn: _Turn) -> None:
    # Test: Cancellation while synthesis is streaming.
    # Situation: Synthesis and chart configuration are both held open, and
    #   the turn is canceled once synthesis has started.
    # Expectation: `CancelledError` is raised to the caller, the background
    #   chart task is canceled with the turn, and the turn is recorded as
    #   `canceled`.
    turn.synthesis_release.clear()
    turn.chart_release.clear()
    task = await _start_and_wait_for(turn, "status")
    async with asyncio.timeout(1):
        while turn.synthesis_calls == 0:
            await asyncio.sleep(0)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    async with asyncio.timeout(1):
        await turn.chart_canceled.wait()
    assert turn.finished == [("canceled", None)]


@pytest.mark.asyncio
async def test_cancel_after_the_final_payload_stays_complete(
    turn: _Turn,
) -> None:
    # Test: Cancellation while follow-ups are generated.
    # Situation: Follow-up generation is held open, and the turn is canceled
    #   after the final payload has been emitted.
    # Expectation: The turn is recorded as `complete` because the answer was
    #   already delivered.
    turn.follow_ups_release.clear()
    task = await _start_and_wait_for(turn, "done")

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert turn.finished == [("complete", None)]


@pytest.mark.asyncio
async def test_no_mcp_tools_fails_the_turn_before_synthesis(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: Fail-closed handling when no MCP tools are available.
    # Situation: MCP is enabled, but `async_get_tools` returns an empty list.
    # Expectation: The turn emits an error payload with the fixed
    #   unavailable message, never calls synthesis, and is recorded as
    #   `error` with `mcp_unavailable`.
    async def no_tools() -> list[dict[str, Any]]:
        return []

    monkeypatch.setattr(mcp_client, "async_get_tools", no_tools)

    await chat_pipeline.run_turn(_QUESTION, [], turn.emit)

    assert turn.payloads == [{"error": chat_pipeline._MCP_UNAVAILABLE}]
    assert turn.synthesis_calls == 0
    assert turn.finished == [("error", "mcp_unavailable")]


@pytest.mark.asyncio
async def test_a_slow_tool_list_fails_the_turn(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: The timeout for fetching the MCP tool list.
    # Situation: `MCP_TOOLS_TIMEOUT_SECONDS` is shortened to 10 ms and
    #   `async_get_tools` never returns.
    # Expectation: The turn emits an error payload, never calls synthesis,
    #   and is recorded as `error` with `mcp_timeout`.
    async def hung_tools() -> list[dict[str, Any]]:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    monkeypatch.setattr(chat_pipeline, "MCP_TOOLS_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(mcp_client, "async_get_tools", hung_tools)

    await chat_pipeline.run_turn(_QUESTION, [], turn.emit)

    assert turn.payloads == [{"error": chat_pipeline._MCP_TOOLS_TIMEOUT}]
    assert turn.synthesis_calls == 0
    assert turn.finished == [("error", "mcp_timeout")]


@pytest.mark.asyncio
async def test_an_empty_synthesis_fails_the_turn(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: Fail-closed handling of empty synthesis output.
    # Situation: The synthesis stream finishes after yielding only
    #   whitespace.
    # Expectation: The turn emits an error payload with the fixed synthesis
    #   error message, emits no `done` payload, and is recorded as `error`
    #   with `synthesis_empty`.
    async def blank() -> AsyncIterator[str]:
        yield " \n"

    async def blank_synthesis(**kwargs: Any) -> AsyncIterator[str]:
        return blank()

    monkeypatch.setattr(chat_pipeline, "async_gemini_stream", blank_synthesis)

    await chat_pipeline.run_turn(_QUESTION, [], turn.emit)

    assert turn.payloads[-1] == {"error": chat_pipeline._SYNTHESIS_FAILED}
    assert not any("done" in payload for payload in turn.payloads)
    assert turn.finished == [("error", "synthesis_empty")]


@pytest.mark.asyncio
async def test_a_broken_synthesis_stream_fails_the_turn(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: Fail-closed handling of a synthesis stream that fails mid-stream.
    # Situation: The synthesis stream yields part of the answer and then
    #   raises `GeminiStreamError` with upstream error text.
    # Expectation: The partial text is emitted, and the turn ends with the
    #   fixed synthesis error message rather than the upstream text and is
    #   recorded as `error` with `synthesis_stream_error`.
    upstream = "HTTP 503: upstream detail"

    async def broken() -> AsyncIterator[str]:
        yield "About "
        raise GeminiStreamError(upstream)

    async def broken_synthesis(**kwargs: Any) -> AsyncIterator[str]:
        return broken()

    monkeypatch.setattr(chat_pipeline, "async_gemini_stream", broken_synthesis)

    await chat_pipeline.run_turn(_QUESTION, [], turn.emit)

    assert {"text": "About "} in turn.payloads
    assert turn.payloads[-1] == {"error": chat_pipeline._SYNTHESIS_FAILED}
    assert turn.finished == [("error", "synthesis_stream_error")]


@pytest.mark.asyncio
async def test_an_unexpected_exception_ends_the_turn_as_internal_error(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: Catch-all handling for unexpected exceptions inside a phase.
    # Situation: `check_data_availability` raises an unexpected
    #   `RuntimeError` containing internal details.
    # Expectation: The turn emits the fixed internal-error message and is
    #   recorded as `error` with `internal_error`.
    detail = "internal detail"

    def broken_check(tool_calls: list[dict[str, Any]]) -> dict[str, Any]:
        raise RuntimeError(detail)

    monkeypatch.setattr(chat_pipeline, "check_data_availability", broken_check)

    await chat_pipeline.run_turn(_QUESTION, [], turn.emit)

    assert turn.payloads[-1] == {"error": chat_pipeline._INTERNAL_ERROR}
    assert turn.finished == [("error", "internal_error")]


@pytest.mark.asyncio
async def test_a_follow_up_failure_leaves_the_turn_complete(
    monkeypatch: pytest.MonkeyPatch, turn: _Turn
) -> None:
    # Test: Best-effort handling of follow-up question generation.
    # Situation: `generate_follow_up_questions` raises a `RuntimeError`
    #   after the final payload has been emitted.
    # Expectation: The final payload has already been emitted, no follow-ups
    #   are emitted, and the turn is recorded as `complete`.
    async def failing_follow_ups(
        question: str, topics: list[str], usage: TokenUsage
    ) -> list[str]:
        raise RuntimeError("follow-up model failed")

    monkeypatch.setattr(
        chat_pipeline, "generate_follow_up_questions", failing_follow_ups
    )

    await chat_pipeline.run_turn(_QUESTION, [], turn.emit)

    assert any(p.get("done") is True for p in turn.payloads)
    assert not any("follow_up_questions" in p for p in turn.payloads)
    assert turn.finished == [("complete", None)]


@pytest.mark.asyncio
async def test_a_failed_chart_task_is_reaped_when_the_turn_fails(
    monkeypatch: pytest.MonkeyPatch,
    turn: _Turn,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Test: Cleanup of a failed chart task when a later phase fails.
    # Situation: `get_chart_config` raises a `ValueError`, and synthesis
    #   fails after the chart task has finished.
    # Expectation: The turn emits an error payload, and the chart task's
    #   exception is retrieved and logged by type.
    chart_failed = asyncio.Event()

    async def failing_chart_config(
        results: str, question: str, usage: TokenUsage
    ) -> dict[str, Any]:
        chart_failed.set()
        raise ValueError("chart detail")

    async def late_failing_synthesis(**kwargs: Any) -> dict[str, str]:
        await chart_failed.wait()
        await asyncio.sleep(0)
        return {"error": "upstream"}

    monkeypatch.setattr(chat_pipeline, "get_chart_config", failing_chart_config)
    monkeypatch.setattr(
        chat_pipeline, "async_gemini_stream", late_failing_synthesis
    )

    with caplog.at_level(logging.WARNING, logger=chat_pipeline.__name__):
        await chat_pipeline.run_turn(_QUESTION, [], turn.emit)

    assert turn.payloads[-1] == {"error": chat_pipeline._SYNTHESIS_FAILED}
    assert "Chart config failed: ValueError" in caplog.text
