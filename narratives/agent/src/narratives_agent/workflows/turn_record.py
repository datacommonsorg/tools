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
"""Collects what one chat turn did in a single in-memory record.

The agent loop creates one `TurnRecord` per turn and discards it with the
turn. Each phase records its results on the record once, and the outputs
that describe the turn are built from it.
"""

from dataclasses import dataclass, field
from typing import Literal

from narratives_agent.analytics.digest import AnalysisDigest
from narratives_agent.telemetry import ErrorType, TerminalState, TurnTelemetry
from narratives_agent.workflows.charts import ResolvedChart
from narratives_agent.workflows.classify import RefusedReason
from narratives_agent.workflows.mcp_loop import DiscoveryResult
from narratives_agent.workflows.processing import ProcessingDiagnostic
from narratives_agent.workflows.specification import AnalysisSpecification
from narratives_agent.workflows.turn_cache import TurnCache

__all__ = [
    "ChartOrigin",
    "SpecificationOrigin",
    "ThoughtPhase",
    "TurnRecord",
    "TurnThought",
]

type SpecificationOrigin = Literal["model", "default"]
type ChartOrigin = Literal["model", "default"]
type ThoughtPhase = Literal["discovery", "synthesis"]


@dataclass(frozen=True, kw_only=True)
class TurnThought:
    """Model reasoning thought emitted during discovery or synthesis.

    Attributes:
        phase: The pipeline phase that produced the thought.
        text: The thought text chunk.
        round_number: 1-based discovery round, or None for synthesis thoughts.
    """

    phase: ThoughtPhase
    text: str
    round_number: int | None = None


@dataclass(kw_only=True)
class TurnRecord:
    """Holds what one chat turn did, by reference to the turn's own objects.

    A turn can end in any phase, so every field except `telemetry` starts at
    the value that means the phase that records it was not reached, and only
    the agent loop assigns it. `cache` is created with the record and
    discarded with it, so nothing is shared across turns or requests.

    Some fields hold text from the conversation or the model. `thoughts`,
    `synthesis_prompt`, and `synthesis_raw_output` hold only text and are
    only used by the debug report. `loop_result`, `default_diagnostics`,
    `specification`, `specification_diagnostic`, `digest`, `cache`, and
    `charts` hold text alongside identifiers, codes, and counts. For
    example, a tool's name and its arguments and result are next to each
    other in a tool call record, and a chart's title is next to its kind.
    The `chat_turn` log line must not contain any text from the
    conversation, so anything written to it from these fields has to be an
    identifier, a code, or a count.

    Attributes:
        telemetry: The turn's timings, token counts, and counters.
        cache: The turn's fetched and derived observation tables and its
            variable metadata.
        loop_result: What the discovery loop produced, including the calls
            that completed before a loop that failed.
        default_diagnostics: The diagnostics of the default specification's
            runs, in run order.
        specification: The specification that answered the turn, or `None`
            when the turn was answered without one.
        specification_origin: Whether the model or the server wrote
            `specification`, or `None` when there is none.
        specification_diagnostic: The diagnostic of the run of
            `specification` when that run failed, or `None` when the run
            succeeded or the record does not hold a specification. The
            agent loop keeps only a default specification after its run
            fails.
        digest: The digest the turn was answered from, or `None` when the
            turn ended before one was resolved.
        used_table_ids: The IDs of the cached tables the answer used.
        thoughts: The model's reasoning thoughts, in emission order.
        synthesis_prompt: The rendered synthesis user message, or `None`
            when the turn ended before synthesis rendered it.
        synthesis_raw_output: The synthesis output as the model wrote it,
            chart fences included, or `None` when the synthesis stream did
            not open.
        charts: The resolved charts emitted in the answer (including any
            default chart), in emission order.
        chart_origins: Whether the model or the server supplied each chart
            of `charts`, in the same order.
        is_clarification: Whether the turn was answered with a clarification
            question.
        is_signed: Whether the server signed the turn into the conversation.
            It is `False` for a turn that did not reach signing.
        was_compacted: Whether signing the turn compacted older turns into a
            summary. It is `False` for a turn that was not signed.
        terminal_state: The state the turn ended in, or `None` while the
            turn is running.
        terminal_reason: The machine-readable reason of a turn that ended
            `error` or `refused`, or `None` otherwise.
    """

    telemetry: TurnTelemetry
    cache: TurnCache = field(default_factory=TurnCache, init=False)
    loop_result: DiscoveryResult = field(
        default_factory=DiscoveryResult, init=False
    )
    default_diagnostics: list[ProcessingDiagnostic] = field(
        default_factory=list, init=False
    )
    specification: AnalysisSpecification | None = field(
        default=None, init=False
    )
    specification_origin: SpecificationOrigin | None = field(
        default=None, init=False
    )
    specification_diagnostic: ProcessingDiagnostic | None = field(
        default=None, init=False
    )
    digest: AnalysisDigest | None = field(default=None, init=False)
    used_table_ids: frozenset[str] = field(default=frozenset(), init=False)
    thoughts: list[TurnThought] = field(default_factory=list, init=False)
    synthesis_prompt: str | None = field(default=None, init=False)
    synthesis_raw_output: str | None = field(default=None, init=False)
    charts: tuple[ResolvedChart, ...] = field(default=(), init=False)
    chart_origins: tuple[ChartOrigin, ...] = field(default=(), init=False)
    is_clarification: bool = field(default=False, init=False)
    is_signed: bool = field(default=False, init=False)
    was_compacted: bool = field(default=False, init=False)
    terminal_state: TerminalState | None = field(default=None, init=False)
    terminal_reason: ErrorType | RefusedReason | None = field(
        default=None, init=False
    )
