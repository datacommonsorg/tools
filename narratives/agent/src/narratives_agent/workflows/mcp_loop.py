#!/usr/bin/env python3
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
"""Runs the tool-calling loop in which Gemini gathers data through MCP tools.

Each iteration sends the conversation so far to Gemini with the MCP tools
declared. When the response contains function calls, every call of that
model turn runs concurrently against the MCP server and the results are
appended to the conversation; when the response contains text alone, the
loop ends.

The loop is bounded by `MAX_ITERATIONS` and by `MCP_LOOP_TIMEOUT_SECONDS`.
When it reaches either bound, it returns the tool calls that completed and
sets `truncated` to `True`, which tells synthesis and the UI that the data
is incomplete. If the timeout expires before any tool call completes, the
loop raises `McpLoopError`.

A failed model call, an empty model reply, or an MCP transport failure ends
the loop with `McpLoopError` rather than with what was gathered so far: the
results it leaves behind have gaps that nothing flags, so synthesis would
present missing data as an answer.
"""

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from narratives_agent.config import get_gemini_model
from narratives_agent.gemini.client import (
    async_gemini_request_with_thought_streaming,
)
from narratives_agent.mcp import client as mcp_client
from narratives_agent.mcp.schema import transform_schema_for_gemini
from narratives_agent.telemetry import TurnTelemetry
from narratives_agent.workflows.transcript import (
    Transcript,
    transcript_contents,
)

logger = logging.getLogger(__name__)

# Maximum model turns in the MCP tool loop. Each entity or variable lookup uses
# up to three tool calls (search, get_variable_metadata, observations), and the
# final iteration must produce a text summary rather than a tool call.
MAX_ITERATIONS = 15

# `MCP_LOOP_TIMEOUT_SECONDS` bounds the total wall-clock duration of the loop,
# including both model calls and tool calls, so that a slow turn does not hold
# the response open. The iteration cap alone does not bound elapsed time,
# because a single tool call may wait up to the MCP client's 300-second request
# timeout.
MCP_LOOP_TIMEOUT_SECONDS = 90.0

# `MAX_CONCURRENT_TOOL_CALLS` bounds how many tool calls from a single model
# turn may run concurrently. A model turn rarely emits more than a handful of
# calls, but each in-flight call holds an MCP connection.
MAX_CONCURRENT_TOOL_CALLS = 8

# `_UNDECLARED_TOOL` is the name recorded in telemetry when a function call
# references an undeclared tool. Model output is untrusted, and the span
# attribute must not carry arbitrary model-generated strings.
_UNDECLARED_TOOL = "unknown"

_MCP_TEMPERATURE = 0.2

# `MCP_HISTORY_RESPONSE_CHARS` limits how much of each earlier answer the
# loop quotes. The loop resends its contents on every iteration, and the
# earlier questions, the summary, and the data scopes carry what resolving
# a reference needs; the full answers are reserved for synthesis.
MCP_HISTORY_RESPONSE_CHARS = 2_000


class McpLoopError(Exception):
    """Raised when the loop cannot produce results that synthesis may use.

    `error_type` is a short machine-readable reason for telemetry, and the
    message is safe to show to the user: it never carries upstream error
    text.
    """

    def __init__(self, error_type: str, message: str) -> None:
        super().__init__(message)
        self.error_type = error_type


@dataclass
class McpLoopResult:
    """Holds the tool outputs and call records from the MCP tool loop.

    `truncated` is `True` when the loop reached `MAX_ITERATIONS` or
    `MCP_LOOP_TIMEOUT_SECONDS` before the model returned a text-only
    response. Reaching a limit is not an error, because the tool calls that
    completed are returned and usable, but the flag lets callers mark the
    answer as built on partial data.
    """

    results_text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    truncated: bool = False


def _gemini_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Converts MCP tool definitions into Gemini function declarations.

    The input schemas are transformed to remove constructs Gemini does not
    support.
    """
    return [
        {
            "name": tool.get("name", ""),
            "description": tool.get("description", ""),
            "parameters": transform_schema_for_gemini(
                tool.get("inputSchema", {"type": "object", "properties": {}})
            ),
        }
        for tool in tools
    ]


def _result_text(result: dict[str, Any]) -> str:
    """Flattens an MCP tool result into the text handed back to the model."""
    content = result.get("content")
    if isinstance(content, list):
        return "\n".join(
            block.get("text", json.dumps(block)) for block in content
        )
    return json.dumps(result)


async def _run_tool(
    function_call: dict[str, Any],
    declared: frozenset[str],
    limit: asyncio.Semaphore,
    telemetry: TurnTelemetry,
) -> dict[str, Any]:
    """Runs one model function call against the MCP server.

    Args:
        function_call: The model's `functionCall` part.
        declared: Names of the tools declared to the model.
        limit: Bounds how many tool calls run at once.
        telemetry: The turn's telemetry, which receives the tool name.

    Returns:
        The tool-call record streamed to the UI and used for provenance:
        `name`, `arguments`, the full `result` text (not truncated, so
        sources can be extracted from it), and `status`.

    Raises:
        McpLoopError: If the MCP request fails below the tool layer.
    """
    name = str(function_call.get("name", ""))
    arguments = function_call.get("args") or {}
    logger.info("Executing MCP tool: %s", name)
    try:
        async with limit:
            result = await mcp_client.async_call_tool(name, arguments)
    except mcp_client.McpTransportError as error:
        # The client has already logged the underlying failure.
        raise McpLoopError(
            "mcp_transport_error",
            "The data service is unavailable. Please try again.",
        ) from error
    telemetry.record_tool_call(name if name in declared else _UNDECLARED_TOOL)
    result_text = _result_text(result)
    return {
        "name": name,
        "arguments": arguments,
        "result": result_text,
        "status": "error" if "error" in result else "success",
    }


async def _run_tools(
    function_calls: list[dict[str, Any]],
    declared: frozenset[str],
    limit: asyncio.Semaphore,
    telemetry: TurnTelemetry,
) -> list[dict[str, Any]]:
    """Runs every call of one model turn concurrently, in a task group.

    The calls share the turn's MCP session because the caller opened its
    scope before this task spawned them. The first failure cancels the
    calls still running, so none outlives the turn.

    Returns:
        The tool-call records, in the order of `function_calls`.

    Raises:
        McpLoopError: If any call fails below the tool layer.
    """
    try:
        async with asyncio.TaskGroup() as group:
            tasks = [
                group.create_task(_run_tool(call, declared, limit, telemetry))
                for call in function_calls
            ]
    except BaseExceptionGroup as failures:
        # Re-raise the loop's own error unwrapped so that callers handle
        # one exception type; anything else is a bug and propagates as is.
        loop_errors, _ = failures.split(McpLoopError)
        if loop_errors is not None:
            raise loop_errors.exceptions[0] from failures
        raise
    return [task.result() for task in tasks]


async def _iterate(
    transcript: Transcript,
    config: dict[str, Any],
    tools: list[dict[str, Any]],
    telemetry: TurnTelemetry,
    thought_callback: Callable[[str], None] | None,
    result: McpLoopResult,
) -> None:
    """Runs model turns until the model stops calling tools.

    The records of each model turn's tool calls are added to `result` once
    all of that turn's calls have completed, so that `result` holds the
    completed calls if the caller's timeout cancels this coroutine.
    """
    mcp_prompt = config.get("prompts", {}).get("mcp", "")
    mcp_model = get_gemini_model(config)
    thinking_level = config.get("thinking", {}).get("mcp_level", "low")
    gemini_tools = _gemini_tools(tools)
    declared = frozenset(tool["name"] for tool in gemini_tools)
    limit = asyncio.Semaphore(MAX_CONCURRENT_TOOL_CALLS)

    # The verified window comes first so that a follow-up such as "and for
    # Texas?" is resolved against the places and variables already queried.
    contents = transcript_contents(
        transcript,
        transcript.current_query,
        max_response_chars=MCP_HISTORY_RESPONSE_CHARS,
    )

    for iteration in range(MAX_ITERATIONS):
        telemetry.mcp_iterations = iteration + 1
        logger.info(
            "MCP tool loop iteration %d/%d", iteration + 1, MAX_ITERATIONS
        )
        response = await async_gemini_request_with_thought_streaming(
            messages=contents,
            system_instruction=mcp_prompt,
            model=mcp_model,
            tools=gemini_tools,
            temperature=_MCP_TEMPERATURE,
            thinking_level=thinking_level,
            token_usage=telemetry.tokens,
            thought_callback=thought_callback,
        )
        if "error" in response:
            # The client has already logged the redacted upstream error.
            raise McpLoopError(
                "mcp_model_error",
                "The data request failed. Please try again.",
            )
        candidates = response.get("candidates") or []
        if not candidates:
            raise McpLoopError(
                "mcp_no_candidates",
                "The model returned no response. Please try again.",
            )

        parts = candidates[0].get("content", {}).get("parts", [])
        function_calls = [
            part["functionCall"] for part in parts if "functionCall" in part
        ]
        if not function_calls:
            if not any(str(part.get("text", "")).strip() for part in parts):
                # A reply with neither a tool call nor text is an empty
                # response rather than a completed answer; continuing would
                # run synthesis without gathered data.
                raise McpLoopError(
                    "mcp_empty_response",
                    "The model returned no response. Please try again.",
                )
            return

        contents.append({"role": "model", "parts": parts})
        records = await _run_tools(function_calls, declared, limit, telemetry)
        result.tool_calls.extend(records)
        contents.append(
            {
                "role": "user",
                "parts": [
                    {
                        "functionResponse": {
                            "name": record["name"],
                            "response": {"result": record["result"]},
                        }
                    }
                    for record in records
                ],
            }
        )

    # Log a warning as well as setting `truncated`, so that Cloud Logging
    # records each turn that reaches the iteration cap. The logs then show how
    # often production turns stop with partial data.
    logger.warning(
        "MCP loop hit its iteration cap of %d after %d tool calls; the answer "
        "will be built on partial data",
        MAX_ITERATIONS,
        len(result.tool_calls),
    )
    result.truncated = True


async def execute_mcp_tool_loop(
    transcript: Transcript,
    config: dict[str, Any],
    tools: list[dict[str, Any]],
    telemetry: TurnTelemetry,
    thought_callback: Callable[[str], None] | None = None,
) -> McpLoopResult:
    """Runs the MCP tool-calling loop for one user query.

    Args:
        transcript: The verified transcript, holding the user's query and
            the conversation context it is resolved against.
        config: Agent configuration, for prompts, model, and thinking level.
        tools: MCP tool definitions available to the model.
        telemetry: The turn's telemetry, which receives token counts, the
            iteration count, and tool names.
        thought_callback: Optional callable invoked with each thought chunk
            as the model streams it.

    Returns:
        The gathered tool results, tool-call records, and truncation flag.

    Raises:
        McpLoopError: If a model call fails, the model returns no
            candidates or an empty reply, an MCP request fails below the
            tool layer, or the loop exceeds `MCP_LOOP_TIMEOUT_SECONDS`
            before any tool call completes.
    """
    # Open the turn's MCP session scope in this task, before any tool call
    # is spawned, so that concurrent calls share one session.
    mcp_client.ensure_session_scope()
    result = McpLoopResult()
    try:
        async with asyncio.timeout(MCP_LOOP_TIMEOUT_SECONDS):
            await _iterate(
                transcript,
                config,
                tools,
                telemetry,
                thought_callback,
                result,
            )
    except TimeoutError as error:
        if not result.tool_calls:
            logger.warning(
                "MCP loop exceeded %.0f seconds before any tool call completed",
                MCP_LOOP_TIMEOUT_SECONDS,
            )
            raise McpLoopError(
                "mcp_timeout",
                "The data request took too long. Please try again.",
            ) from error
        logger.warning(
            "MCP loop exceeded %.0f seconds after %d iterations and %d tool "
            "calls; the answer will be built on partial data",
            MCP_LOOP_TIMEOUT_SECONDS,
            telemetry.mcp_iterations,
            len(result.tool_calls),
        )
        result.truncated = True
    result.results_text = "\n\n".join(
        f"Tool: {record['name']}\nResult: {record['result']}"
        for record in result.tool_calls
    )
    return result
