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
"""Builds structured turn debug reports from telemetry and cache state.

This module models the typed server debug report and constructs it from
operational turn telemetry and cached observation tables without exposing
untyped internal maps or sensitive conversation content.
"""

import hashlib
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

from narratives_agent.analytics.digest import (
    AnalysisDigest,
    RefusalReason,
)
from narratives_agent.analytics.metrics import ScriptName
from narratives_agent.analytics.summarize import SUMMARY_PLACE_LIST_CAP
from narratives_agent.analytics.tables import ObservationTable
from narratives_agent.config_model import PROMPT_SLOTS, AgentConfig, GeminiRole
from narratives_agent.gemini.schemas import QueryPattern
from narratives_agent.json_value import JsonObject, JsonValue, json_safe
from narratives_agent.settings import DebugReportMode
from narratives_agent.telemetry import TurnTelemetry
from narratives_agent.workflows.mcp_loop import (
    RejectedSubmission,
    RejectionReason,
)
from narratives_agent.workflows.processing import (
    ProcessingDiagnostic,
    StepRefusalDiagnostic,
    TimeoutDiagnostic,
)
from narratives_agent.workflows.prompt_contracts import load_prompt_contract
from narratives_agent.workflows.specification import (
    AnalysisSpecification,
    UnavailableReport,
)
from narratives_agent.workflows.sse_frames import ThoughtPhase
from narratives_agent.workflows.turn_cache import (
    DERIVED_TABLE_PREFIX,
    CachedTable,
    TurnCache,
)

__all__ = [
    "MAX_DEBUG_TEXT_CHARS",
    "DebugCappedText",
    "DebugCoverageSummary",
    "DebugDiagnostic",
    "DebugPlaceRef",
    "DebugRejectedSpecification",
    "DebugReport",
    "DebugRoleConfig",
    "DebugSourceRecord",
    "DebugStepRefusalDiagnostic",
    "DebugTableRecord",
    "DebugTerminalState",
    "DebugThought",
    "DebugTimeoutDiagnostic",
    "DebugTokenCall",
    "DebugTokenUsage",
    "SourceSelection",
    "SpecificationOrigin",
    "build_debug_diagnostic",
    "build_debug_report",
    "should_emit_debug_report",
    "truncate_debug_text",
]

# Maximum character count preserved for debug prompt and raw output text.
MAX_DEBUG_TEXT_CHARS = 32_000

type DebugTerminalState = Literal["complete", "refused", "error"]
type SourceSelection = Literal["chosen", "server_default", "derived"]
type SpecificationOrigin = Literal["model", "default"]


@dataclass(frozen=True, kw_only=True)
class DebugCappedText:
    """Holds debug text with truncation status and original character count."""

    text: str
    truncated: bool
    total_chars: int

    def to_dict(self) -> JsonObject:
        """Serializes the capped text to a finite snake_case JSON object."""
        return {
            "text": self.text,
            "truncated": self.truncated,
            "total_chars": self.total_chars,
        }


def truncate_debug_text(
    value: str, *, max_chars: int = MAX_DEBUG_TEXT_CHARS
) -> DebugCappedText:
    """Caps text at max_chars characters if longer, preserving total count.

    Args:
        value: The string to cap.
        max_chars: Maximum characters to retain before truncation.

    Returns:
        A DebugCappedText instance with truncation metadata.
    """
    total = len(value)
    if total <= max_chars:
        return DebugCappedText(text=value, truncated=False, total_chars=total)
    return DebugCappedText(
        text=value[:max_chars], truncated=True, total_chars=total
    )


@dataclass(frozen=True, kw_only=True)
class DebugRoleConfig:
    """Snapshot of model settings for one Gemini role in the agent loop."""

    role: str
    model: str
    temperature: float
    thinking_level: str


def should_emit_debug_report(
    mode: DebugReportMode, *, request_debug: bool
) -> bool:
    """Returns whether the debug report should be emitted for a turn.

    Args:
        mode: The server's configured debug report mode.
        request_debug: Whether the client requested debug mode (?debug).

    Returns:
        False for "off", True for "on", and request_debug for "flag".
    """
    match mode:
        case "off":
            return False
        case "on":
            return True
        case "flag":
            return request_debug


@dataclass(frozen=True, kw_only=True)
class DebugTokenCall:
    """Token counts from a single model call within a turn."""

    phase: str
    model: str
    round_number: int | None
    prompt_token_count: int
    candidates_token_count: int
    thoughts_token_count: int
    total_token_count: int


@dataclass(frozen=True, kw_only=True)
class DebugTokenUsage:
    """Aggregated token usage and per-call token breakdown for a turn."""

    prompt_token_count: int
    candidates_token_count: int
    thoughts_token_count: int
    total_token_count: int
    calls: tuple[DebugTokenCall, ...]


@dataclass(frozen=True, kw_only=True)
class DebugPlaceRef:
    """Reference to a place entity in an observation table."""

    dcid: str
    name: str


@dataclass(frozen=True, kw_only=True)
class DebugSourceRecord:
    """Citation and provenance record for a data source."""

    name: str
    url: str
    license: str | None = None
    dataset: str | None = None
    provider: str | None = None
    date_range: str | None = None


@dataclass(frozen=True, kw_only=True)
class DebugTableRecord:
    """Summary of a cached observation table evaluated during the turn."""

    table_id: str
    used_in_answer: bool
    variable_dcid: str
    variable_name: str
    unit: str | None
    scaling_factor: float | None
    measurement_method: str | None
    observation_period: str | None
    parent_place_dcid: str | None
    child_place_type: str | None
    places_with_data_count: int
    places: tuple[DebugPlaceRef, ...]
    facet_id: str | None
    source_selection: SourceSelection
    source: DebugSourceRecord | None
    date_range: tuple[str, str] | None
    row_count: int


@dataclass(frozen=True, kw_only=True)
class DebugThought:
    """Model reasoning thought emitted during discovery or synthesis.

    Attributes:
        phase: The pipeline phase that produced the thought.
        text: The thought text chunk.
        round_number: 1-based discovery round, or None for synthesis thoughts.
    """

    phase: ThoughtPhase
    text: str
    round_number: int | None = None


@dataclass(frozen=True, kw_only=True)
class DebugRejectedSpecification:
    """A specification rejected by validation or analytical processing.

    Attributes:
        round_number: 1-based discovery round in which submit_specification ran.
        reason: Category of the rejection.
        errors: Sanitized validation errors or diagnostic failure message.
        specification: The parsed specification when available, or None.
    """

    round_number: int
    reason: RejectionReason
    errors: tuple[str, ...]
    specification: AnalysisSpecification | None = None


@dataclass(frozen=True, kw_only=True)
class DebugCoverageSummary:
    """Summarizes target place coverage for a refused step.

    Attributes:
        contributing_places: Number of target places with valid data.
        requested_places: Total number of target places requested.
        coverage_ratio: Ratio of contributing to requested places.
        reference_date: Reference date to which observations were aligned.
        missing_places: Target place DCIDs missing data on reference date.
        mixed_vintages: Whether unaligned places had differing observation
            dates.
    """

    contributing_places: int
    requested_places: int
    coverage_ratio: float
    reference_date: str | None
    missing_places: tuple[str, ...]
    mixed_vintages: bool


@dataclass(frozen=True, kw_only=True)
class DebugStepRefusalDiagnostic:
    """Diagnostic detail for a step refused by an analytical script.

    Attributes:
        kind: Discriminator literal ("step_refusal").
        round_number: 1-based discovery round, or None for the default
            specification.
        step_id: Identifier of the refused step.
        script: Name of the analytical script.
        refusal_reason: Script-level refusal reason.
        message: Diagnostic explanation and caveats.
        input_table_ids: Table IDs read by the step.
        coverage: Optional coverage summary.
        alternative_source_count: Count of alternative sources available.
    """

    kind: Literal["step_refusal"] = "step_refusal"
    round_number: int | None
    step_id: str
    script: ScriptName
    refusal_reason: RefusalReason
    message: str
    input_table_ids: tuple[str, ...]
    coverage: DebugCoverageSummary | None
    alternative_source_count: int


@dataclass(frozen=True, kw_only=True)
class DebugTimeoutDiagnostic:
    """Diagnostic detail for a specification execution timeout.

    Attributes:
        kind: Discriminator literal ("timeout").
        round_number: 1-based discovery round, or None for the default
            specification.
        timeout_seconds: The budget exceeded in seconds.
        message: Explanation of the timeout.
    """

    kind: Literal["timeout"] = "timeout"
    round_number: int | None
    timeout_seconds: float
    message: str


type DebugDiagnostic = DebugStepRefusalDiagnostic | DebugTimeoutDiagnostic


def build_debug_diagnostic(
    diagnostic: ProcessingDiagnostic, *, round_number: int | None = None
) -> DebugDiagnostic:
    """Constructs a typed DebugDiagnostic from a ProcessingDiagnostic.

    Args:
        diagnostic: The runtime processing diagnostic to convert.
        round_number: Optional 1-based discovery round in which the diagnostic
            occurred, or None for runs outside the discovery loop.

    Returns:
        A DebugStepRefusalDiagnostic or DebugTimeoutDiagnostic.
    """
    match diagnostic:
        case StepRefusalDiagnostic():
            coverage = (
                DebugCoverageSummary(
                    contributing_places=diagnostic.coverage.contributing_places,
                    requested_places=diagnostic.coverage.requested_places,
                    coverage_ratio=diagnostic.coverage.coverage_ratio,
                    reference_date=diagnostic.coverage.reference_date,
                    missing_places=diagnostic.coverage.missing_places,
                    mixed_vintages=diagnostic.coverage.mixed_vintages,
                )
                if diagnostic.coverage is not None
                else None
            )
            return DebugStepRefusalDiagnostic(
                round_number=round_number,
                step_id=diagnostic.step_id,
                script=diagnostic.script,
                refusal_reason=diagnostic.refusal_reason,
                message=diagnostic.message,
                input_table_ids=diagnostic.input_table_ids,
                coverage=coverage,
                alternative_source_count=len(diagnostic.alternative_sources),
            )
        case TimeoutDiagnostic():
            return DebugTimeoutDiagnostic(
                round_number=round_number,
                timeout_seconds=diagnostic.timeout_seconds,
                message=diagnostic.message,
            )


@dataclass(frozen=True, kw_only=True)
class DebugReport:
    """Structured operational and analytical debug report for a turn."""

    turn_id: str
    terminal_state: DebugTerminalState
    terminal_reason: str | None
    is_clarification: bool
    pattern: QueryPattern | None
    duration_ms: float
    phase_durations_ms: Mapping[str, float]
    nested_phases: Mapping[str, str]
    mcp_iterations: int
    scripts: tuple[str, ...]
    processing_retries: int
    charts_emitted: int
    charts_rejected: int
    tokens: DebugTokenUsage
    tables: tuple[DebugTableRecord, ...]
    thoughts: tuple[DebugThought, ...] = ()
    tool_calls: tuple[JsonObject, ...] = ()
    rejected_specifications: tuple[DebugRejectedSpecification, ...] = ()
    diagnostics: tuple[DebugDiagnostic, ...] = ()
    specification: AnalysisSpecification | None = None
    specification_origin: SpecificationOrigin | None = None
    unavailable: UnavailableReport | None = None
    digest: AnalysisDigest | None = None
    synthesis_prompt: DebugCappedText | None = None
    synthesis_raw_output: DebugCappedText | None = None
    role_configs: tuple[DebugRoleConfig, ...] = ()
    prompt_hashes: Mapping[str, str] = field(
        default_factory=lambda: MappingProxyType({})
    )
    build_sha: str | None = None

    def to_dict(self) -> JsonObject:
        """Serializes the report to a finite snake_case JSON object."""
        return {
            "turn_id": self.turn_id,
            "terminal_state": self.terminal_state,
            "terminal_reason": self.terminal_reason,
            "is_clarification": self.is_clarification,
            "pattern": self.pattern,
            "duration_ms": self.duration_ms,
            "phase_durations_ms": dict(self.phase_durations_ms),
            "nested_phases": dict(self.nested_phases),
            "mcp_iterations": self.mcp_iterations,
            "scripts": list(self.scripts),
            "processing_retries": self.processing_retries,
            "charts_emitted": self.charts_emitted,
            "charts_rejected": self.charts_rejected,
            "tokens": {
                "prompt_token_count": self.tokens.prompt_token_count,
                "candidates_token_count": self.tokens.candidates_token_count,
                "thoughts_token_count": self.tokens.thoughts_token_count,
                "total_token_count": self.tokens.total_token_count,
                "calls": [
                    {
                        "phase": call.phase,
                        "model": call.model,
                        "round": call.round_number,
                        "prompt_token_count": call.prompt_token_count,
                        "candidates_token_count": call.candidates_token_count,
                        "thoughts_token_count": call.thoughts_token_count,
                        "total_token_count": call.total_token_count,
                    }
                    for call in self.tokens.calls
                ],
            },
            "tables": [
                {
                    "table_id": table.table_id,
                    "used_in_answer": table.used_in_answer,
                    "variable_dcid": table.variable_dcid,
                    "variable_name": table.variable_name,
                    "unit": table.unit,
                    "scaling_factor": table.scaling_factor,
                    "measurement_method": table.measurement_method,
                    "observation_period": table.observation_period,
                    "parent_place_dcid": table.parent_place_dcid,
                    "child_place_type": table.child_place_type,
                    "places_with_data_count": table.places_with_data_count,
                    "places": [
                        {"dcid": place.dcid, "name": place.name}
                        for place in table.places
                    ],
                    "facet_id": table.facet_id,
                    "source_selection": table.source_selection,
                    "source": (
                        {
                            "name": table.source.name,
                            "url": table.source.url,
                            "license": table.source.license,
                            "dataset": table.source.dataset,
                            "provider": table.source.provider,
                            "date_range": table.source.date_range,
                        }
                        if table.source is not None
                        else None
                    ),
                    "date_range": (
                        list(table.date_range)
                        if table.date_range is not None
                        else None
                    ),
                    "row_count": table.row_count,
                }
                for table in self.tables
            ],
            "thoughts": [
                {"phase": t.phase, "text": t.text, "round": t.round_number}
                for t in self.thoughts
            ],
            "tool_calls": [dict(call) for call in self.tool_calls],
            "rejected_specifications": [
                {
                    "round": item.round_number,
                    "reason": item.reason,
                    "errors": list(item.errors),
                    "specification": (
                        json_safe(item.specification.model_dump(mode="json"))
                        if item.specification is not None
                        else None
                    ),
                }
                for item in self.rejected_specifications
            ],
            "diagnostics": [
                (
                    {
                        "kind": "step_refusal",
                        "round": diag.round_number,
                        "step_id": diag.step_id,
                        "script": diag.script,
                        "refusal_reason": diag.refusal_reason,
                        "message": diag.message,
                        "input_table_ids": list(diag.input_table_ids),
                        "coverage": (
                            {
                                "contributing_places": (
                                    diag.coverage.contributing_places
                                ),
                                "requested_places": (
                                    diag.coverage.requested_places
                                ),
                                "coverage_ratio": diag.coverage.coverage_ratio,
                                "reference_date": diag.coverage.reference_date,
                                "missing_places": list(
                                    diag.coverage.missing_places
                                ),
                                "mixed_vintages": diag.coverage.mixed_vintages,
                            }
                            if diag.coverage is not None
                            else None
                        ),
                        "alternative_source_count": (
                            diag.alternative_source_count
                        ),
                    }
                    if isinstance(diag, DebugStepRefusalDiagnostic)
                    else {
                        "kind": "timeout",
                        "round": diag.round_number,
                        "timeout_seconds": diag.timeout_seconds,
                        "message": diag.message,
                    }
                )
                for diag in self.diagnostics
            ],
            "specification": (
                json_safe(self.specification.model_dump(mode="json"))
                if self.specification is not None
                else None
            ),
            "specification_origin": self.specification_origin,
            "unavailable": (
                json_safe(self.unavailable.model_dump(mode="json"))
                if self.unavailable is not None
                else None
            ),
            "digest": (
                self.digest.to_dict() if self.digest is not None else None
            ),
            "synthesis_prompt": (
                self.synthesis_prompt.to_dict()
                if self.synthesis_prompt is not None
                else None
            ),
            "synthesis_raw_output": (
                self.synthesis_raw_output.to_dict()
                if self.synthesis_raw_output is not None
                else None
            ),
            "role_configs": [
                {
                    "role": r.role,
                    "model": r.model,
                    "temperature": r.temperature,
                    "thinking_level": r.thinking_level,
                }
                for r in self.role_configs
            ],
            "prompt_hashes": dict(self.prompt_hashes),
            "build_sha": self.build_sha,
        }


def _resolve_place_name(table: ObservationTable, dcid: str) -> str:
    """Resolves place name from table place names, row place names, or dcid."""
    if name := table.place_names.get(dcid):
        return name
    for row in table.rows:
        if row.place_dcid == dcid and row.place_name:
            return row.place_name
    return dcid


def _build_debug_table_record(
    entry: CachedTable, *, used_in_answer: bool
) -> DebugTableRecord:
    """Builds a DebugTableRecord from a cached table entry."""
    table = entry.table
    dates = [row.date for row in table.rows]
    date_range = (min(dates), max(dates)) if dates else None

    # Derive source selection: derived for s-prefixed tables, chosen if
    # explicit source override was requested, else server default.
    if entry.table_id.startswith(DERIVED_TABLE_PREFIX):
        source_selection: SourceSelection = "derived"
    elif entry.source_selected_explicitly:
        source_selection = "chosen"
    else:
        source_selection = "server_default"

    # Places with rows, ordered with requested places first, then remaining
    # places in sorted order, capped at SUMMARY_PLACE_LIST_CAP.
    with_data = set(table.places_with_data)
    seen: set[str] = set()
    places_ordered: list[str] = []
    for dcid in table.requested_places:
        if dcid in with_data and dcid not in seen:
            seen.add(dcid)
            places_ordered.append(dcid)
    for dcid in table.places_with_data:
        if dcid not in seen:
            seen.add(dcid)
            places_ordered.append(dcid)

    places = tuple(
        DebugPlaceRef(
            dcid=dcid,
            name=_resolve_place_name(table, dcid),
        )
        for dcid in places_ordered[:SUMMARY_PLACE_LIST_CAP]
    )

    source = (
        DebugSourceRecord(
            name=table.source.name,
            url=table.source.url,
            license=table.source.license,
            dataset=table.source.dataset,
            provider=table.source.provider,
            date_range=table.source.date_range,
        )
        if table.source is not None
        else None
    )

    return DebugTableRecord(
        table_id=entry.table_id,
        used_in_answer=used_in_answer,
        variable_dcid=table.variable_dcid,
        variable_name=table.variable_name,
        unit=table.unit,
        scaling_factor=table.scaling_factor,
        measurement_method=table.measurement_method,
        observation_period=table.observation_period,
        parent_place_dcid=table.parent_place_dcid,
        child_place_type=table.child_place_type,
        places_with_data_count=len(table.places_with_data),
        places=places,
        facet_id=table.facet_id,
        source_selection=source_selection,
        source=source,
        date_range=date_range,
        row_count=len(table.rows),
    )


def _build_role_configs(config: AgentConfig) -> tuple[DebugRoleConfig, ...]:
    """Extracts model settings for each Gemini role in the agent loop.

    Never reads config.gemini.api_key to prevent secret leakage.
    """
    configs: list[DebugRoleConfig] = []
    for role in GeminiRole:
        resolved = config.resolve_role_config(role)
        configs.append(
            DebugRoleConfig(
                role=role.value,
                model=resolved.model,
                temperature=resolved.temperature,
                thinking_level=resolved.thinking_level.value.lower(),
            )
        )
    return tuple(configs)


def _build_prompt_hashes(config: AgentConfig) -> Mapping[str, str]:
    """Computes SHA-256 digests for configured prompt slots and contracts."""
    hashes: dict[str, str] = {}
    for slot in PROMPT_SLOTS:
        text = getattr(config.prompts, slot)
        hashes[slot] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    hashes["discovery_contract"] = hashlib.sha256(
        load_prompt_contract("discovery").encode("utf-8")
    ).hexdigest()
    hashes["synthesis_contract"] = hashlib.sha256(
        load_prompt_contract("synthesis").encode("utf-8")
    ).hexdigest()
    return MappingProxyType(hashes)


def build_debug_report(
    *,
    telemetry: TurnTelemetry,
    terminal_state: DebugTerminalState,
    terminal_reason: str | None = None,
    is_clarification: bool = False,
    cache: TurnCache | None = None,
    used_table_ids: AbstractSet[str] = frozenset(),
    thoughts: Sequence[DebugThought] = (),
    tool_calls: Sequence[Mapping[str, JsonValue]] = (),
    rejected_submissions: Sequence[RejectedSubmission] = (),
    diagnostics: Sequence[tuple[int | None, ProcessingDiagnostic]] = (),
    specification: AnalysisSpecification | None = None,
    specification_origin: SpecificationOrigin | None = None,
    unavailable: UnavailableReport | None = None,
    digest: AnalysisDigest | None = None,
    synthesis_prompt: str | None = None,
    synthesis_raw_output: str | None = None,
    config: AgentConfig | None = None,
    build_sha: str | None = None,
) -> DebugReport:
    """Builds a structured TurnDebugReport from telemetry and cache state.

    Args:
        telemetry: Operational telemetry collected during the turn.
        terminal_state: Terminal outcome state ('complete', 'refused', 'error').
        terminal_reason: Optional terminal failure or refusal reason code.
        is_clarification: Whether the turn was answered with a clarification.
        cache: Optional turn cache holding fetched and derived tables.
        used_table_ids: Table IDs incorporated into the synthesis response.
        thoughts: Model reasoning thoughts emitted during the turn.
        tool_calls: Tool and server-function records emitted during discovery.
        rejected_submissions: Specifications rejected during the turn.
        diagnostics: Processing diagnostics and their optional discovery
            rounds.
        specification: The final analysis specification executed, if any.
        specification_origin: Origin of the specification ('model' or
            'default').
        unavailable: The no-data report filed for the turn, if any.
        digest: Analytical digest produced by the processed specification.
        synthesis_prompt: Rendered prompt supplied to the synthesis model.
        synthesis_raw_output: Raw text returned by the synthesis model.
        config: Loaded agent configuration used to snapshot roles and prompts.
        build_sha: Build or commit SHA identifying the running image.

    Returns:
        The validated DebugReport dataclass.
    """
    phase_durations_ms = dict(telemetry.phase_durations_ms)
    nested_phases = (
        {"processing": "discovery"}
        if "processing" in phase_durations_ms
        else {}
    )

    tokens = DebugTokenUsage(
        prompt_token_count=telemetry.tokens.prompt_token_count,
        candidates_token_count=telemetry.tokens.candidates_token_count,
        thoughts_token_count=telemetry.tokens.thoughts_token_count,
        total_token_count=telemetry.tokens.total_token_count,
        calls=tuple(
            DebugTokenCall(
                phase=call.phase,
                model=call.model,
                round_number=call.round_number,
                prompt_token_count=call.counts.prompt,
                candidates_token_count=call.counts.candidates,
                thoughts_token_count=call.counts.thoughts,
                total_token_count=call.counts.total,
            )
            for call in telemetry.tokens.calls
        ),
    )

    pattern = None if terminal_state == "refused" else telemetry.pattern

    tables: list[DebugTableRecord] = []
    if cache is not None:
        for table_id in cache.table_ids:
            entry = cache.get(table_id)
            if entry is not None:
                tables.append(
                    _build_debug_table_record(
                        entry,
                        used_in_answer=table_id in used_table_ids,
                    )
                )

    resolved_specification_origin: SpecificationOrigin | None
    if specification is None:
        resolved_specification_origin = None
    elif specification_origin is not None:
        resolved_specification_origin = specification_origin
    else:
        resolved_specification_origin = "model"

    rejected_specs = tuple(
        DebugRejectedSpecification(
            round_number=sub.round_number,
            reason=sub.reason,
            errors=sub.errors,
            specification=sub.specification,
        )
        for sub in rejected_submissions
    )

    debug_diagnostics = tuple(
        build_debug_diagnostic(diag, round_number=round_num)
        for round_num, diag in diagnostics
    )

    capped_synthesis_prompt = (
        truncate_debug_text(synthesis_prompt)
        if synthesis_prompt is not None
        else None
    )
    capped_synthesis_raw_output = (
        truncate_debug_text(synthesis_raw_output)
        if synthesis_raw_output is not None
        else None
    )
    role_configs = _build_role_configs(config) if config is not None else ()
    prompt_hashes = (
        _build_prompt_hashes(config)
        if config is not None
        else MappingProxyType({})
    )

    return DebugReport(
        turn_id=telemetry.turn_id,
        terminal_state=terminal_state,
        terminal_reason=terminal_reason,
        is_clarification=is_clarification,
        pattern=pattern,
        duration_ms=telemetry.elapsed_ms(),
        phase_durations_ms=phase_durations_ms,
        nested_phases=nested_phases,
        mcp_iterations=telemetry.mcp_iterations,
        scripts=tuple(telemetry.scripts),
        processing_retries=telemetry.processing_retries,
        charts_emitted=telemetry.charts_emitted,
        charts_rejected=telemetry.charts_rejected,
        tokens=tokens,
        tables=tuple(tables),
        thoughts=tuple(thoughts),
        tool_calls=tuple(dict(call) for call in tool_calls),
        rejected_specifications=rejected_specs,
        diagnostics=debug_diagnostics,
        specification=specification,
        specification_origin=resolved_specification_origin,
        unavailable=unavailable,
        digest=digest,
        synthesis_prompt=capped_synthesis_prompt,
        synthesis_raw_output=capped_synthesis_raw_output,
        role_configs=role_configs,
        prompt_hashes=prompt_hashes,
        build_sha=build_sha,
    )
