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

import json
import logging
from typing import Optional

from src.config import get_gemini_model, load_config
from src.gemini.client import gemini_request_with_thought_streaming
from src.mcp.client import call_tool, get_tools
from src.mcp.schema import transform_schema_for_gemini
from src.session_logger import SessionLogger

logger = logging.getLogger(__name__)


def execute_mcp_tool_loop(
    user_message: str,
    history: list,
    # Each iteration is one model turn, and the last one has to carry the text
    # answer rather than a tool call. A broad question re-searches before it
    # settles — "compare X across European countries" spent four turns on
    # search/observe/search/observe — and exhausting the budget returns whatever
    # was gathered with no synthesis, so leave headroom.
    #
    # Raised from 7 for the 1.3.0 tool surface: the recommended flow is now
    # three steps (search → get_variable_metadata → observations) rather than
    # two, and a bilateral question was observed spending all seven turns on
    # search alone and returning no data at all.
    max_iterations: int = 15,
    session_logger: Optional[SessionLogger] = None,
    effective_config: dict = None,
    thought_callback: callable = None,
    demo_mode: bool = False
) -> tuple:
    """Execute the MCP tool calling loop with optional thought streaming.

    Args:
        user_message: The user's query
        history: Conversation history
        max_iterations: Maximum tool calling iterations
        session_logger: Optional SessionLogger for comprehensive logging
        effective_config: Optional config dict with query param overrides applied
        thought_callback: Optional callback for streaming thought chunks.
                         Signature: callback(thought_text: str) -> None
        demo_mode: If True, uses demo API keys reserved for internal demos.

    Returns:
        tuple: (tool_results_text, tool_calls_list, final_response_text,
               truncated)

        `truncated` is True when the loop ran out of iterations before the model
        chose to stop. That is not an error -- whatever was gathered is still
        returned and still usable -- but the answer is built on less data than
        the model intended to collect, and callers have no other way to tell.
    """
    config = effective_config if effective_config else load_config()
    mcp_prompt = config.get("prompts", {}).get("mcp", "")
    mcp_model = get_gemini_model(config)
    thinking_level = config.get("thinking", {}).get("mcp_level", "low")
    max_iterations = config.get("mcp", {}).get("max_iterations", max_iterations)

    # Get MCP tools
    tools = get_tools()
    if not tools:
        if session_logger:
            session_logger.log_error("MCP_TOOLS_UNAVAILABLE", "No MCP tools available")
        return "", [], "MCP tools not available", False

    # Convert tools to Gemini format (transform schema to remove unsupported constructs)
    gemini_tools = [{
        "name": t.get("name", ""),
        "description": t.get("description", ""),
        "parameters": transform_schema_for_gemini(
            t.get("inputSchema", {"type": "object", "properties": {}})
        )
    } for t in tools]

    # Build conversation - NO history for MCP calls (fresh search every time)
    # History is only used in synthesis phase for context
    contents = []
    contents.append({"role": "user", "parts": [{"text": user_message}]})

    tool_calls_list = []
    all_tool_results = []

    for iteration in range(max_iterations):
        logger.info(f"MCP Tool Loop - Iteration {iteration + 1}/{max_iterations}")

        if session_logger:
            session_logger.log("MCP_LOOP_ITERATION", {"iteration": iteration + 1, "max": max_iterations})

        response = gemini_request_with_thought_streaming(
            messages=contents,
            system_instruction=mcp_prompt,
            model=mcp_model,
            tools=gemini_tools,
            temperature=0.2,
            thinking_level=thinking_level,
            session_logger=session_logger,
            thought_callback=thought_callback,
            demo_mode=demo_mode
        )

        if "error" in response:
            if session_logger:
                session_logger.log_error("MCP_LOOP_ERROR", response['error'])
            return "", tool_calls_list, f"Error: {response['error']}", False

        # Check for function calls
        candidates = response.get("candidates", [])
        if not candidates:
            if session_logger:
                session_logger.log_error("MCP_NO_CANDIDATES", "No response from model")
            return "", tool_calls_list, "No response from model", False

        candidate = candidates[0]
        content = candidate.get("content", {})
        parts = content.get("parts", [])

        function_calls = []
        text_response = ""

        for part in parts:
            if "functionCall" in part:
                function_calls.append(part["functionCall"])
            elif "text" in part:
                text_response += part["text"]

        # If no function calls, we're done
        if not function_calls:
            tool_results_text = "\n\n".join(all_tool_results)
            if session_logger:
                session_logger.log("MCP_LOOP_COMPLETE", {
                    "iterations_used": iteration + 1,
                    "tools_called": len(tool_calls_list),
                    "has_text_response": bool(text_response)
                })
            return tool_results_text, tool_calls_list, text_response, False

        # Execute function calls
        contents.append({"role": "model", "parts": parts})
        function_responses = []

        for fc in function_calls:
            tool_name = fc.get("name", "")
            tool_args = fc.get("args", {})

            logger.info(f"Executing MCP tool: {tool_name}")
            result = call_tool(tool_name, tool_args, session_logger=session_logger)

            # Convert result to string
            if isinstance(result, dict):
                if "content" in result and isinstance(result["content"], list):
                    result_text = "\n".join([
                        c.get("text", json.dumps(c)) for c in result["content"]
                    ])
                else:
                    result_text = json.dumps(result)
            else:
                result_text = str(result)

            tool_call_info = {
                "name": tool_name,
                "arguments": tool_args,
                "result": result_text,  # No truncation - full result for source extraction
                "status": "error" if "error" in result_text.lower() else "success"
            }
            tool_calls_list.append(tool_call_info)
            all_tool_results.append(f"Tool: {tool_name}\nResult: {result_text}")

            function_responses.append({
                "functionResponse": {
                    "name": tool_name,
                    "response": {"result": result_text}
                }
            })

        contents.append({"role": "user", "parts": function_responses})

    # Max iterations reached. The session log is a file inside the container and
    # does not survive the instance, so warn as well -- that is what reaches
    # Cloud Logging and lets this be counted across real traffic.
    tool_results_text = "\n\n".join(all_tool_results)
    logger.warning(
        "MCP loop hit max_iterations=%d after %d tool calls; the answer "
        "will be built on partial data",
        max_iterations,
        len(tool_calls_list),
    )
    if session_logger:
        session_logger.log("MCP_LOOP_MAX_ITERATIONS", {
            "tools_called": len(tool_calls_list),
            "max_iterations": max_iterations,
        })
    return (tool_results_text, tool_calls_list,
            "Max tool iterations reached", True)
