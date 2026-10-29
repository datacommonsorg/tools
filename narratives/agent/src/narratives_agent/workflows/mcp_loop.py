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
"""Runs the discovery loop in which Gemini finds data and specifies analysis.

Exposes the MCP search and metadata tools and the server functions in
`workflows/fetch.py` and `workflows/specification.py`, validates and runs
submitted specifications through `workflows/processing.py`, and returns a
`DiscoveryResult`.
"""

import asyncio
import json
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from google.genai import types
from pydantic import ValidationError

from narratives_agent.analytics.digest import AnalysisDigest
from narratives_agent.config_model import AgentConfig, GeminiRole, RoleConfig
from narratives_agent.gemini.client import (
    GeminiBlockedError,
    GeminiError,
    Message,
    async_gemini_request_with_thought_streaming,
)
from narratives_agent.gemini.response import FunctionCall, GeminiResponse
from narratives_agent.gemini.schemas import QueryClassification
from narratives_agent.json_value import JsonObject, JsonValue
from narratives_agent.mcp import client as mcp_client
from narratives_agent.mcp.capabilities import (
    TOOL_GET_VARIABLE_METADATA,
    TOOL_SEARCH_CHILD_INDICATORS,
    TOOL_SEARCH_INDICATORS,
)
from narratives_agent.mcp.schema import transform_schema_for_gemini
from narratives_agent.telemetry import ErrorType, TurnTelemetry
from narratives_agent.workflows.fetch import (
    build_fetch_declarations,
    run_fetch,
    serialize_fetch_result,
)
from narratives_agent.workflows.fetch_requests import (
    FETCH_FUNCTION_NAMES,
    FetchArgumentError,
    parse_fetch_request,
)
from narratives_agent.workflows.messages import (
    DISCOVERY_STATUS as _DISCOVERY_STATUS_MESSAGE,
)
from narratives_agent.workflows.messages import (
    MCP_LOOP_TIMEOUT,
    MCP_MODEL_ERROR,
    MCP_NO_RESPONSE,
    MCP_UNAVAILABLE,
)
from narratives_agent.workflows.messages import (
    PROCESSING_STATUS as _PROCESSING_STATUS_MESSAGE,
)
from narratives_agent.workflows.processing import (
    ProcessingDiagnostic,
    execute_specification,
)
from narratives_agent.workflows.prompt_contracts import (
    compose_system_instruction,
)
from narratives_agent.workflows.specification import (
    REPORT_UNAVAILABLE,
    SUBMIT_SPECIFICATION,
    AnalysisSpecification,
    UnavailableReport,
    build_specification_declarations,
    validate_specification,
)
from narratives_agent.workflows.transcript import (
    Transcript,
    transcript_contents,
)
from narratives_agent.workflows.turn_cache import TurnCache

logger = logging.getLogger(__name__)

# Maximum model turns in the discovery loop across searches, fetches, and
# submissions.
MAX_ITERATIONS = 15

# Wall-clock timeout in seconds across all model, tool, and processing calls.
MCP_LOOP_TIMEOUT_SECONDS = 90.0

# Maximum tool calls from a single model turn that may run concurrently.
MAX_CONCURRENT_TOOL_CALLS = 8

# Maximum reminders sent when the model replies in prose instead of a tool call.
_MAX_PROSE_REMINDERS = 2

# A rejected specification or failed processing run is returned to the model
# at most this many times before the loop falls back to a default
# specification.
MAX_PROCESSING_RETRIES = 2
# The server functions that end the discovery loop.
_TERMINAL_FUNCTION_NAMES: frozenset[str] = frozenset(
    {SUBMIT_SPECIFICATION, REPORT_UNAVAILABLE}
)
# Every function the server runs itself rather than forwarding to MCP.
SERVER_FUNCTION_NAMES: frozenset[str] = (
    FETCH_FUNCTION_NAMES | _TERMINAL_FUNCTION_NAMES
)
# The only MCP tools declared to the model for discovery.
DISCOVERY_TOOL_NAMES: frozenset[str] = frozenset(
    {
        TOOL_SEARCH_INDICATORS,
        TOOL_SEARCH_CHILD_INDICATORS,
        TOOL_GET_VARIABLE_METADATA,
    }
)

# Telemetry label recorded when the model invokes an undeclared tool name.
_UNDECLARED_TOOL = "unknown"

# Maximum characters of each earlier model answer quoted in the loop history.
MCP_HISTORY_RESPONSE_CHARS = 2_000

_PROSE_REMINDER = (
    "Do not answer in prose. Finish by calling submit_specification with the "
    "steps to run over the cached tables, or report_unavailable if Data "
    "Commons does not have the data."
)

# Number of rounds without a non-empty fetch before reminding the model.
_UNPRODUCTIVE_ROUNDS_BEFORE_REMINDER = 4

# Number of rounds without any non-empty table before the server ends the loop.
_UNPRODUCTIVE_ROUNDS_BEFORE_GIVING_UP = 7

_PROGRESS_REMINDER = (
    "{rounds} rounds have passed without a fetched table that has rows, and "
    "{left} rounds remain. Independent calls can share one round. Fetch the "
    "most promising candidate now so that its data can be checked. If a "
    "cached table already answers the question, call submit_specification. "
    "If the searches show nothing for the places asked about, call "
    "report_unavailable with what you searched instead of searching again."
)

# Maximum search queries and candidate names a server-built report lists.
_REPORT_LIST_CAP = 6
_SERVER_REPORT = "server_report_unavailable"

type StatusPhase = Literal["discovery", "processing"]
type StatusCallback = Callable[[StatusPhase, str], None]

# Status `(phase, message)` pairs reported for discovery and processing phases.
DISCOVERY_STATUS: tuple[StatusPhase, str] = (
    "discovery",
    _DISCOVERY_STATUS_MESSAGE,
)
PROCESSING_STATUS: tuple[StatusPhase, str] = (
    "processing",
    _PROCESSING_STATUS_MESSAGE,
)


class McpLoopError(Exception):
    """Raised when the loop cannot produce results that synthesis may use.

    `error_type` is a short machine-readable reason for telemetry, and the
    message is safe to show to the user: it never carries upstream error
    text.

    Attributes:
        error_type: The machine-readable error classification for telemetry.
    """

    def __init__(self, error_type: ErrorType, message: str) -> None:
        super().__init__(message)
        self.error_type = error_type


@dataclass
class DiscoveryResult:
    """What the discovery loop produced for the rest of the turn.

    Exactly one of three things is true when the loop ends normally:
    `digest` is set because a specification was accepted and processed,
    `unavailable` is set because the model reported that the data does not
    exist, or neither is set because the loop reached a bound or exhausted
    its retries, in which case the caller builds a default specification
    over the cache.

    Attributes:
        tool_calls: The records of every tool and server function call, in
            completion order, streamed to the UI.
        truncated: True when the loop reached `MAX_ITERATIONS` or
            `MCP_LOOP_TIMEOUT_SECONDS` before the model finished.
        specification: The last specification the model submitted (valid or
            not), or `None` when the model never submitted a structurally
            valid `AnalysisSpecification`.
        digest: The digest of the accepted specification, or `None` when no
            specification was accepted.
        unavailable: The no-data report filed by the model or by the server
            after the unproductive-round limit, or `None` when the turn did
            not end via `report_unavailable`.
        processing_retries: How many validation failures and diagnostics
            were fed back to the model.
        last_diagnostic: The diagnostic of the last processing failure so
            the caller can record it when retries are exhausted, or `None`
            when no processing step failed.
    """

    tool_calls: list[JsonObject] = field(default_factory=list)
    truncated: bool = False
    specification: AnalysisSpecification | None = None
    digest: AnalysisDigest | None = None
    unavailable: UnavailableReport | None = None
    processing_retries: int = 0
    last_diagnostic: ProcessingDiagnostic | None = None


def _build_gemini_tools(
    tools: Sequence[mcp_client.McpTool],
) -> list[types.FunctionDeclaration]:
    """Builds the model's tool declarations.

    The MCP discovery tools keep the schemas the server published, rewritten
    into the subset Gemini accepts; the observation tools are withheld, and
    the five server functions are declared in their place.

    Args:
        tools: The MCP tool definitions published by the server.

    Returns:
        The Gemini `FunctionDeclaration` list for the discovery loop.

    Raises:
        pydantic.ValidationError: If a transformed MCP tool schema is not a
            valid Gemini `Schema`.
    """
    declarations = [
        types.FunctionDeclaration(
            name=tool.name,
            description=tool.description,
            parameters=types.Schema.model_validate(
                transform_schema_for_gemini(tool.input_schema)
            ),
        )
        for tool in tools
        if tool.name in DISCOVERY_TOOL_NAMES
    ]
    declarations.extend(build_fetch_declarations())
    declarations.extend(build_specification_declarations())
    return declarations


def _format_result_text(result: Mapping[str, JsonValue]) -> str:
    """Flattens an MCP tool result into the text handed back to the model.

    Args:
        result: The MCP wire result mapping returned by `async_call_tool`.

    Returns:
        The concatenated text of `"content"` blocks, or the JSON-serialized
        `result` when `"content"` is not a list.
    """
    content = result.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, Mapping) and isinstance(
                block.get("text"), str
            ):
                parts.append(str(block["text"]))
            else:
                parts.append(json.dumps(block))
        return "\n".join(parts)
    return json.dumps(result)


def _append_user_text(contents: list[Message], text: str) -> None:
    """Adds an instruction to the model as part of the next user message.

    When the last message is already the user's (the function responses of
    the previous round), the text joins its parts, so the conversation keeps
    alternating between the model and the user.

    Args:
        contents: The mutable conversation message list sent to Gemini.
        text: The user-role instruction text to append.
    """
    if (
        contents
        and isinstance(contents[-1], dict)
        and contents[-1].get("role") == "user"
    ):
        parts = contents[-1].setdefault("parts", [])
        if isinstance(parts, list):
            parts.append({"text": text})
            return
    contents.append({"role": "user", "parts": [{"text": text}]})


def _select_unique(values: list[str], cap: int) -> list[str]:
    """Returns the first `cap` distinct values, in order.

    Args:
        values: Candidate strings in appearance order.
        cap: Maximum number of distinct strings to return.

    Returns:
        Up to `cap` unique strings preserving first-appearance order.
    """
    return list(dict.fromkeys(values))[:cap]


def format_count(count: int, singular: str, plural: str | None = None) -> str:
    """Formats `count` with its grammatical singular or plural noun.

    Args:
        count: The integer count to format.
        singular: Singular noun form (for example, `"variable"`).
        plural: Optional irregular plural form; defaults to `f"{singular}s"`.

    Returns:
        A string such as `"1 variable"` or `"3 variables"`.
    """
    noun = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {noun}"


def _collect_candidate_names(result_text: str) -> list[str]:
    """Returns the variable names a search result offered.

    A 1.3.x search result maps every DCID it mentions to a display name in
    `dcidNameMappings` and lists the place DCIDs among them in
    `dcidPlaceTypeMappings`, so the variables are the names whose DCIDs are
    not places.

    Args:
        result_text: The raw JSON text returned by a search tool call.

    Returns:
        The non-place display names offered in `dcidNameMappings`.
    """
    try:
        parsed = json.loads(result_text)
    except ValueError:
        return []
    if not isinstance(parsed, dict):
        return []
    names = parsed.get("dcidNameMappings")
    places = parsed.get("dcidPlaceTypeMappings")
    if not isinstance(names, dict):
        return []
    place_dcids = set(places) if isinstance(places, dict) else set()
    return [
        name
        for dcid, name in names.items()
        if dcid not in place_dcids and isinstance(name, str) and name
    ]


def _build_server_report(
    records: Sequence[Mapping[str, JsonValue]], rounds: int
) -> UnavailableReport:
    """Builds the no-data report the server files when the model does not.

    The loop calls this only when no fetched table has rows, so every
    variable that was fetched came back empty. The report names the search
    queries and places tried, the variables the searches offered that were
    never confirmed to have data, and the variables that were fetched and
    came back empty, so that the answer can say what was looked for rather
    than only that nothing was found.

    Args:
        records: The completed tool-call records from the discovery loop.
        rounds: The number of discovery rounds executed before giving up.

    Returns:
        The server-synthesized `UnavailableReport`.
    """
    queries: list[str] = []
    places: list[str] = []
    candidates: list[str] = []
    empty: list[str] = []
    for record in records:
        raw_args = record.get("arguments")
        arguments: Mapping[str, JsonValue] = (
            raw_args if isinstance(raw_args, Mapping) else {}
        )
        name = record.get("name")
        if name in (TOOL_SEARCH_INDICATORS, TOOL_SEARCH_CHILD_INDICATORS):
            query = arguments.get("query")
            if isinstance(query, str) and query.strip():
                queries.append(query.strip())
            for key in ("places", "sample_child_places"):
                listed = arguments.get(key)
                if isinstance(listed, list):
                    places.extend(str(place) for place in listed)
            parent = arguments.get("parent_place")
            if isinstance(parent, str) and parent:
                places.append(parent)
            candidates.extend(
                _collect_candidate_names(str(record.get("result", "")))
            )
        elif name in FETCH_FUNCTION_NAMES and record.get("status") == "success":
            variable = arguments.get("variable_dcid")
            if isinstance(variable, str) and variable:
                empty.append(variable)
    if empty:
        unique_empty = list(dict.fromkeys(empty))
        fetched = unique_empty[:_REPORT_LIST_CAP]
        listed = ", ".join(fetched)
        if len(unique_empty) > len(fetched):
            extra = len(unique_empty) - len(fetched)
            listed += f", and {format_count(extra, 'other variable')}"
        tested = (
            f"the {format_count(len(unique_empty), 'variable')} fetched had "
            f"no rows for the requested entities ({listed})"
        )
    else:
        tested = "no candidate variable was fetched to confirm it has data"
    return UnavailableReport(
        searched_indicators=_select_unique(queries, _REPORT_LIST_CAP),
        searched_places=_select_unique(places, _REPORT_LIST_CAP),
        reason=(
            f"No data was found in {rounds} rounds of discovery: {tested}."
        ),
        related_available=_select_unique(candidates, _REPORT_LIST_CAP),
    )


def _build_tool_record(
    name: str, arguments: JsonObject, result_text: str, failed: bool
) -> JsonObject:
    """Builds the tool-call record streamed to the UI.

    Args:
        name: The invoked tool or function name.
        arguments: The JSON arguments supplied by the model (or synthesized by
            the server).
        result_text: The serialized result or error string.
        failed: Whether the call failed (`"error"` vs. `"success"`).

    Returns:
        A JSON object with `name`, `arguments`, `result`, and `status`.
    """
    return {
        "name": name,
        "arguments": arguments,
        "result": result_text,
        "status": "error" if failed else "success",
    }


def _format_validation_errors(
    error: ValidationError, *, default_location: str
) -> list[str]:
    """Formats Pydantic validation errors without echoing untrusted input.

    Pydantic's default `union_tag_invalid` and `literal_error` messages embed
    the raw input value inside `msg`, and `extra_forbidden` appends the raw
    extra key name to `loc`. At the model-input boundary, this helper
    replaces those messages with the expected tags or values from `ctx` and
    strips the extra key name from `loc` so an arbitrary model-supplied
    string is never echoed back. Each message is prefixed with its field
    path so the model can tell which argument to correct.

    Args:
        error: The `ValidationError` raised when validating model arguments.
        default_location: The label used when an error has no field path,
            such as a missing argument object (for example, `"report"`).

    Returns:
        A list of sanitized validation error descriptions, one per line.
    """
    formatted: list[str] = []
    for item in error.errors(include_url=False, include_input=False):
        context = item.get("ctx")
        error_type = item.get("type", "")
        if error_type == "union_tag_invalid" and isinstance(context, Mapping):
            expected = context.get("expected_tags", "")
            discriminator = context.get("discriminator", "script")
            message = f"Invalid {discriminator} tag; expected one of {expected}"
        elif error_type == "literal_error" and isinstance(context, Mapping):
            expected = context.get("expected", "")
            message = f"Input should be {expected}"
        else:
            message = item["msg"]
        loc_parts = (
            item["loc"][:-1] if error_type == "extra_forbidden" else item["loc"]
        )
        location = ".".join(str(loc) for loc in loc_parts) or default_location
        formatted.append(f"- {location}: {message}")
    return formatted


async def _run_tool(
    function_call: FunctionCall,
    declared: frozenset[str],
    limit: asyncio.Semaphore,
    fetch_lock: asyncio.Lock,
    telemetry: TurnTelemetry,
    cache: TurnCache,
) -> JsonObject:
    """Runs one model function call: an MCP tool or a fetch function.

    A call to a name that was not declared is answered with an error and
    never reaches MCP. The observation tools are withheld from the model so
    that raw rows never enter its context, and that holds only if the loop
    refuses them when the model names them anyway.

    Args:
        function_call: The model's `FunctionCall`.
        declared: Names of the tools declared to the model.
        limit: Bounds how many tool calls run at once.
        fetch_lock: Held for the whole of each fetch, so that fetches never
            overlap on `cache`.
        telemetry: The turn's telemetry, which receives the tool name.
        cache: The turn's cache, which receives fetched tables and
            metadata payloads.

    Returns:
        The tool-call record streamed to the UI: `name`, `arguments`, the
        full `result` text, and `status`.

    Raises:
        McpLoopError: If the MCP request fails below the tool layer.
    """
    name = function_call.name
    arguments: JsonObject = function_call.args
    if name not in declared:
        logger.info("Refusing a call to the undeclared tool %r", name)
        telemetry.record_tool_call(_UNDECLARED_TOOL)
        return _build_tool_record(
            name,
            arguments,
            json.dumps(
                {
                    "error": f"{name} is not an available tool. Use the "
                    "declared tools: the search and metadata tools to "
                    "discover data, the fetch functions to retrieve it, and "
                    "submit_specification or report_unavailable to finish."
                }
            ),
            True,
        )
    logger.info("Executing discovery tool: %s", name)
    try:
        if name in FETCH_FUNCTION_NAMES:
            request = parse_fetch_request(name, arguments)
            # The lock is taken before the semaphore, so a fetch waiting for
            # another fetch does not hold a slot a search could use.
            async with fetch_lock, limit:
                outcome = await run_fetch(request, cache)
            result_text = json.dumps(serialize_fetch_result(outcome))
            failed = False
        else:
            async with limit:
                result = await mcp_client.async_call_tool(name, arguments)
            result_text = _format_result_text(result)
            failed = False
            if name == TOOL_GET_VARIABLE_METADATA:
                cache.record_variable_metadata(result)
    except FetchArgumentError as error:
        result_text = json.dumps(error.build_error_response())
        failed = True
    except mcp_client.McpToolError as error:
        result_text = json.dumps({"error": error.message})
        failed = True
    except mcp_client.McpTransportError as error:
        raise McpLoopError(
            ErrorType.MCP_TRANSPORT_ERROR, MCP_UNAVAILABLE
        ) from error
    telemetry.record_tool_call(name)
    return _build_tool_record(name, arguments, result_text, failed)


async def _run_tools(
    function_calls: Sequence[FunctionCall],
    declared: frozenset[str],
    limit: asyncio.Semaphore,
    telemetry: TurnTelemetry,
    cache: TurnCache,
) -> list[JsonObject]:
    """Runs the calls of one model turn in a task group.

    The search and metadata calls run concurrently. The fetches run one at a
    time, in the order of `function_calls`, because `TurnCache` requires
    that fetches never overlap: each fetch reads the facet a variable is
    locked to before it calls MCP. Running them in call order also stores
    their tables as `t1`, `t2`, ... in the order the model asked for them.

    The calls share the turn's MCP session because the caller opened its
    scope before this task spawned them. The first failure cancels the
    calls still running, so none outlives the turn.

    Args:
        function_calls: Non-terminal function calls from one model turn.
        declared: Names of the tools and functions declared to the model.
        limit: Semaphore bounding concurrent tool calls.
        telemetry: The turn's telemetry collector.
        cache: The turn's table and metadata cache.

    Returns:
        The tool-call records, in the order of `function_calls`.

    Raises:
        McpLoopError: If any call fails below the tool layer.
    """
    # `asyncio.Lock` wakes waiters in the order they blocked, and each task
    # reaches the lock without awaiting anything earlier, so the fetches
    # acquire it in the order the tasks are created.
    fetch_lock = asyncio.Lock()
    try:
        async with asyncio.TaskGroup() as group:
            tasks = [
                group.create_task(
                    _run_tool(
                        call, declared, limit, fetch_lock, telemetry, cache
                    )
                )
                for call in function_calls
            ]
    except BaseExceptionGroup as failures:
        # Unwrap McpLoopError so callers handle one exception type.
        loop_errors, _ = failures.split(McpLoopError)
        if loop_errors is not None:
            raise loop_errors.exceptions[0] from failures
        raise
    return [task.result() for task in tasks]


def _build_function_response(record: Mapping[str, JsonValue]) -> JsonObject:
    """Wraps a tool-call record as the `functionResponse` part for the model.

    Args:
        record: The completed tool-call record mapping.

    Returns:
        A Gemini `functionResponse` part dictionary.
    """
    return {
        "functionResponse": {
            "name": record["name"],
            "response": {"result": record["result"]},
        }
    }


@dataclass
class _Loop:
    """The mutable state of one discovery loop run.

    Attributes:
        cache: The per-turn table and metadata cache.
        telemetry: The per-turn telemetry collector.
        status_callback: Optional callback invoked when the loop moves between
            discovery and processing, or `None` when status updates are not
            subscribed to.
        result: The `DiscoveryResult` populated as the loop runs.
    """

    cache: TurnCache
    telemetry: TurnTelemetry
    status_callback: StatusCallback | None
    result: DiscoveryResult

    def emit_status(self, phase_and_message: tuple[StatusPhase, str]) -> None:
        """Reports a phase change to the UI, when a callback is installed.

        Args:
            phase_and_message: The `(phase, message)` pair to emit.
        """
        if self.status_callback is not None:
            self.status_callback(*phase_and_message)

    def has_failures_remaining(self) -> bool:
        """Returns True while another failed submission may be fed back.

        Returns:
            `True` when `processing_retries` is below `MAX_PROCESSING_RETRIES`.
        """
        return self.result.processing_retries < MAX_PROCESSING_RETRIES

    async def submit_specification(
        self, arguments: Mapping[str, JsonValue]
    ) -> tuple[str, bool]:
        """Validates and processes a submitted specification.

        Args:
            arguments: Raw `submit_specification` arguments from the model.

        Returns:
            The text the model receives as the tool's response, and whether
            the loop ends. The loop ends when the specification produced a
            digest, and also when a failure exhausted the retries, in which
            case the caller falls back to a default specification.
        """
        try:
            specification = AnalysisSpecification.model_validate(arguments)
        except ValidationError as error:
            return self._record_failed_submission(
                "The specification is invalid:\n"
                + "\n".join(
                    _format_validation_errors(
                        error, default_location="specification"
                    )
                )
            )
        self.result.specification = specification
        problems = validate_specification(specification, self.cache)
        if problems is not None:
            return self._record_failed_submission(
                f"The specification references are invalid:\n{problems}"
            )
        self.emit_status(PROCESSING_STATUS)
        with self.telemetry.phase("processing"):
            outcome = await execute_specification(specification, self.cache)
        if isinstance(outcome, ProcessingDiagnostic):
            self.result.last_diagnostic = outcome
            return self._record_failed_submission(outcome.format_for_retry())
        self.result.digest = outcome
        return (
            json.dumps(
                {
                    "status": "accepted",
                    "scripts": specification.list_script_names(),
                    "has_data": outcome.has_data,
                }
            ),
            True,
        )

    def _record_failed_submission(self, message: str) -> tuple[str, bool]:
        """Records a failed submission and decides whether to continue.

        `processing_retries` counts the failures fed back to the model, so
        a failure that arrives with the budget spent ends the loop without
        being counted.

        Args:
            message: The diagnostic message to return to the model.

        Returns:
            `(message, finished)`, where `finished` is `False` while retries
            remain and `True` once the retry budget is exhausted.
        """
        if self.has_failures_remaining():
            self.result.processing_retries += 1
            logger.info(
                "Specification rejected; returning to discovery (retry %d "
                "of %d)",
                self.result.processing_retries,
                MAX_PROCESSING_RETRIES,
            )
            self.emit_status(DISCOVERY_STATUS)
            return message, False
        logger.warning(
            "Specification rejected after %d retries; falling back to the "
            "default specification",
            self.result.processing_retries,
        )
        return message, True

    def report_unavailable(
        self, arguments: Mapping[str, JsonValue]
    ) -> tuple[str, bool]:
        """Records the model's no-data report.

        Args:
            arguments: Raw `report_unavailable` arguments from the model.

        Returns:
            The tool response text and whether the loop ends, which it does
            unless the report itself is malformed.
        """
        try:
            self.result.unavailable = UnavailableReport.model_validate(
                arguments
            )
        except ValidationError as error:
            return (
                "The report is invalid:\n"
                + "\n".join(
                    _format_validation_errors(error, default_location="report")
                ),
                False,
            )
        return json.dumps({"status": "recorded"}), True

    def give_up(self, rounds: int) -> None:
        """Ends the loop with a no-data report the server builds itself.

        Called after `_UNPRODUCTIVE_ROUNDS_BEFORE_GIVING_UP` rounds in which
        no fetch stored a table with rows and no earlier fetch did either.
        The report is recorded like a model's `report_unavailable` call, so
        the turn answers through the same no-data path, and it is streamed
        to the UI as a tool-call record that says the server filed it.

        Args:
            rounds: Number of discovery rounds executed before giving up.
        """
        report = _build_server_report(self.result.tool_calls, rounds)
        logger.warning(
            "Discovery loop ended by the server after %d rounds without a "
            "table that has rows: %s",
            rounds,
            report.reason,
        )
        self.telemetry.record_tool_call(_SERVER_REPORT)
        self.result.unavailable = report
        self.result.tool_calls.append(
            _build_tool_record(
                REPORT_UNAVAILABLE,
                report.model_dump(mode="json"),
                json.dumps({"status": "recorded", "filed_by": "server"}),
                False,
            )
        )

    async def execute_turn_calls(
        self,
        function_calls: Sequence[FunctionCall],
        declared: frozenset[str],
        limit: asyncio.Semaphore,
    ) -> tuple[list[JsonObject], bool]:
        """Executes the non-terminal and terminal calls of one model turn.

        Non-terminal calls run concurrently first so any fetch in the same
        turn populates `cache` before `submit_specification` validates against
        it. Only the first terminal call is handled if the model emits more
        than one.

        Args:
            function_calls: All function calls returned by the model turn.
            declared: Names of the tools and functions declared to the model.
            limit: Semaphore bounding concurrent non-terminal calls.

        Returns:
            `(records, finished)`, where `records` are the tool-call records
            from this turn and `finished` is `True` when a terminal call ended
            the loop.
        """
        terminal = [
            call
            for call in function_calls
            if call.name in _TERMINAL_FUNCTION_NAMES
        ]
        others = [
            call
            for call in function_calls
            if call.name not in _TERMINAL_FUNCTION_NAMES
        ]
        records = await _run_tools(
            others, declared, limit, self.telemetry, self.cache
        )
        self.result.tool_calls.extend(records)
        finished = False
        # Handle only the first terminal call if the model submits more than 1.
        for index, call in enumerate(terminal):
            name = call.name
            arguments: JsonObject = call.args
            self.telemetry.record_tool_call(name)
            if index > 0:
                text = "Ignored: only the first terminal call is handled."
                failed = True
            elif name == SUBMIT_SPECIFICATION:
                text, finished = await self.submit_specification(arguments)
                failed = self.result.digest is None
            else:
                text, finished = self.report_unavailable(arguments)
                failed = self.result.unavailable is None
            record = _build_tool_record(name, arguments, text, failed)
            self.result.tool_calls.append(record)
            records.append(record)
        return records, finished


async def _request_discovery_turn(
    contents: Sequence[Message],
    system_instruction: str,
    role: RoleConfig,
    gemini_tools: Sequence[types.FunctionDeclaration],
    telemetry: TurnTelemetry,
    thought_callback: Callable[[str], None] | None,
) -> GeminiResponse:
    """Requests one discovery turn from Gemini and checks for content.

    Args:
        contents: Conversation messages sent to the model.
        system_instruction: The discovery system prompt with pattern guidance.
        role: Resolved model, temperature, and thinking level for discovery.
        gemini_tools: Tool and server-function declarations for the loop.
        telemetry: The turn's telemetry collector.
        thought_callback: Optional callback invoked with streamed thoughts.

    Returns:
        The model's `GeminiResponse`, guaranteed to carry either function
        calls or non-blank text.

    Raises:
        GeminiBlockedError: If Gemini blocks the prompt or candidate.
        McpLoopError: If the model call fails or returns neither function
            calls nor non-blank text.
    """
    try:
        response = await async_gemini_request_with_thought_streaming(
            messages=contents,
            system_instruction=system_instruction,
            model=role.model,
            tools=gemini_tools,
            temperature=role.temperature,
            thinking_level=role.thinking_level,
            token_usage=telemetry.tokens,
            thought_callback=thought_callback,
        )
    except GeminiBlockedError:
        raise
    except GeminiError as error:
        raise McpLoopError(
            ErrorType.MCP_MODEL_ERROR, MCP_MODEL_ERROR
        ) from error
    if not response.function_calls and not response.text.strip():
        logger.warning(
            "MCP model turn produced neither a tool call nor text "
            "(finish reason: %s)",
            response.finish_reason,
        )
        raise McpLoopError(ErrorType.MCP_EMPTY_RESPONSE, MCP_NO_RESPONSE)
    return response


async def _iterate(
    transcript: Transcript,
    config: AgentConfig,
    tools: Sequence[mcp_client.McpTool],
    loop: _Loop,
    thought_callback: Callable[[str], None] | None,
    classification: QueryClassification | None,
) -> None:
    """Runs model turns until the model ends the loop or a bound is reached.

    The records of each model turn's tool calls are added to the result
    once all of that turn's calls have completed, so that the result holds
    the completed calls if the caller's timeout cancels this coroutine.

    Args:
        transcript: The verified conversation transcript for the turn.
        config: The loaded agent configuration.
        tools: The MCP tool definitions published by the server.
        loop: The mutable `_Loop` state for this discovery run.
        thought_callback: Optional callback invoked with each thought chunk.
        classification: Optional query classification from the classify phase.

    Raises:
        GeminiBlockedError: If Gemini blocks a discovery prompt or candidate.
        McpLoopError: If tool schemas are invalid, a model call fails or is
            empty, or an MCP transport error occurs.
    """
    discovery_prompt = compose_system_instruction(
        config.prompts.discovery, "discovery", classification
    )
    role = config.resolve_role_config(GeminiRole.DISCOVERY)
    try:
        gemini_tools = _build_gemini_tools(tools)
    except ValidationError as error:
        logger.error(
            "MCP tool schemas are not valid Gemini declarations: "
            "%d error(s) at %s",
            error.error_count(),
            [
                ".".join(str(step) for step in detail["loc"])
                for detail in error.errors()
            ],
        )
        raise McpLoopError(
            ErrorType.MCP_MODEL_ERROR, MCP_MODEL_ERROR
        ) from error
    declared = frozenset(
        tool.name for tool in gemini_tools if tool.name is not None
    )
    limit = asyncio.Semaphore(MAX_CONCURRENT_TOOL_CALLS)
    result = loop.result

    # Put the verified window first so follow-ups resolve prior scopes.
    contents: list[Message] = list(
        transcript_contents(
            transcript,
            transcript.current_query,
            max_response_chars=MCP_HISTORY_RESPONSE_CHARS,
        )
    )
    reminders = 0
    unproductive = 0

    for iteration in range(MAX_ITERATIONS):
        loop.telemetry.mcp_iterations = iteration + 1
        logger.info(
            "Discovery loop iteration %d/%d", iteration + 1, MAX_ITERATIONS
        )
        if unproductive == _UNPRODUCTIVE_ROUNDS_BEFORE_REMINDER:
            _append_user_text(
                contents,
                _PROGRESS_REMINDER.format(
                    rounds=unproductive, left=MAX_ITERATIONS - iteration
                ),
            )
        rows_before = loop.cache.total_rows_fetched
        response = await _request_discovery_turn(
            contents,
            discovery_prompt,
            role,
            gemini_tools,
            loop.telemetry,
            thought_callback,
        )
        if not response.function_calls:
            # Remind the model to finish through a tool call up to the cap.
            if reminders >= _MAX_PROSE_REMINDERS:
                logger.warning(
                    "Discovery loop ended with a prose reply after %d "
                    "reminders; the answer will be built from the cached "
                    "tables",
                    reminders,
                )
                result.truncated = True
                return
            reminders += 1
            unproductive += 1
            contents.append(response)
            contents.append(
                {"role": "user", "parts": [{"text": _PROSE_REMINDER}]}
            )
            continue

        contents.append(response)
        records, finished = await loop.execute_turn_calls(
            response.function_calls, declared, limit
        )
        contents.append(
            {
                "role": "user",
                "parts": [
                    _build_function_response(record) for record in records
                ],
            }
        )
        if finished:
            return
        if loop.cache.total_rows_fetched > rows_before:
            unproductive = 0
            continue
        unproductive += 1
        if (
            unproductive >= _UNPRODUCTIVE_ROUNDS_BEFORE_GIVING_UP
            and loop.cache.total_rows_fetched == 0
        ):
            loop.give_up(iteration + 1)
            return

    # Log a warning when the iteration cap is reached so logs record it.
    logger.warning(
        "Discovery loop hit its iteration cap of %d after %d tool calls; the "
        "answer will be built from the cached tables",
        MAX_ITERATIONS,
        len(result.tool_calls),
    )
    result.truncated = True


async def execute_discovery_loop(
    transcript: Transcript,
    config: AgentConfig,
    tools: Sequence[mcp_client.McpTool],
    telemetry: TurnTelemetry,
    cache: TurnCache,
    *,
    thought_callback: Callable[[str], None] | None = None,
    status_callback: StatusCallback | None = None,
    classification: QueryClassification | None = None,
) -> DiscoveryResult:
    """Runs the discovery loop for one user query.

    Args:
        transcript: The verified transcript, holding the user's query and
            the conversation context it is resolved against.
        config: The agent configuration; `prompts.discovery` is the system
            instruction, `gemini.discovery_model` the model, and
            `thinking.discovery_level` the thinking level.
        tools: The MCP tool definitions the server published; only the
            discovery tools are declared to the model.
        telemetry: The turn's telemetry, which receives token counts, the
            iteration count, tool names, and the processing phase.
        cache: The turn's cache, which receives every fetched table.
        thought_callback: Optional callable invoked with each thought chunk
            as the model streams it.
        status_callback: Optional callable invoked with a phase name and a
            message when the loop moves between discovery and processing.
        classification: The classify phase's verdict, whose pattern
            directive is appended to the system instruction, or `None` when
            the classifier failed.

    Returns:
        The tool-call records, the truncation flag, and the digest, the
        no-data report, or neither.

    Raises:
        McpLoopError: If a tool schema is not a valid Gemini schema, a model
            call fails, the model returns an empty reply, an MCP request fails
            below the tool layer, or the loop exceeds `MCP_LOOP_TIMEOUT_SECONDS`
            before any tool call completes.
        GeminiBlockedError: If Gemini blocks the prompt or the candidate of
            an iteration.
    """
    # Open the turn's MCP session scope here so concurrent calls share it.
    mcp_client.ensure_session_scope()
    result = DiscoveryResult()
    loop = _Loop(cache, telemetry, status_callback, result)
    try:
        async with asyncio.timeout(MCP_LOOP_TIMEOUT_SECONDS):
            await _iterate(
                transcript,
                config,
                tools,
                loop,
                thought_callback,
                classification,
            )
    except TimeoutError as error:
        if not result.tool_calls:
            logger.warning(
                "Discovery loop exceeded %.0f seconds before any tool call "
                "completed",
                MCP_LOOP_TIMEOUT_SECONDS,
            )
            raise McpLoopError(
                ErrorType.MCP_TIMEOUT, MCP_LOOP_TIMEOUT
            ) from error
        logger.warning(
            "Discovery loop exceeded %.0f seconds after %d iterations and %d "
            "tool calls; the answer will be built from the cached tables",
            MCP_LOOP_TIMEOUT_SECONDS,
            telemetry.mcp_iterations,
            len(result.tool_calls),
        )
        result.truncated = True
    return result


__all__ = [
    "DISCOVERY_STATUS",
    "DISCOVERY_TOOL_NAMES",
    "MAX_CONCURRENT_TOOL_CALLS",
    "MAX_ITERATIONS",
    "MAX_PROCESSING_RETRIES",
    "MCP_HISTORY_RESPONSE_CHARS",
    "MCP_LOOP_TIMEOUT_SECONDS",
    "PROCESSING_STATUS",
    "SERVER_FUNCTION_NAMES",
    "DiscoveryResult",
    "McpLoopError",
    "StatusCallback",
    "execute_discovery_loop",
    "format_count",
]
