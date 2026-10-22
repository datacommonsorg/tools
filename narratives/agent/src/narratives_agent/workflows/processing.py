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
"""Bounded processing phase that executes an `AnalysisSpecification`.

Runs the steps of a validated specification in order against `TurnCache` on
a bounded thread pool under a wall-clock budget, and returns an
`AnalysisDigest` when every step succeeds or a `ProcessingDiagnostic` when a
step refuses or the run exceeds its budget.
"""

import asyncio
import logging
import math
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from narratives_agent.analytics.alignment import AlignedCohort
from narratives_agent.analytics.composition import compute_composition
from narratives_agent.analytics.derived import derive_observation_table
from narratives_agent.analytics.digest import (
    PLACE_NAME_CAP,
    AnalysisDigest,
    CoverageReport,
    RefusalReason,
    RefusedScriptResult,
    ScriptResult,
    format_place_names,
)
from narratives_agent.analytics.distribution import summarize_distribution
from narratives_agent.analytics.metrics import ScriptName
from narratives_agent.analytics.provenance import AlternativeSource
from narratives_agent.analytics.ranking import rank_cohort
from narratives_agent.analytics.relations import relate_cohorts
from narratives_agent.analytics.script_inputs import resolve_aligned_cohort
from narratives_agent.analytics.tables import ObservationTable
from narratives_agent.analytics.timeseries import analyze_timeseries
from narratives_agent.workflows.specification import (
    AlignCohortStep,
    AnalysisSpecification,
    AnalyzeTimeseriesStep,
    ComputeCompositionStep,
    ComputeDerivedMetricStep,
    RankCohortStep,
    RelateCohortsStep,
    SpecificationStep,
    SummarizeDistributionStep,
    list_step_inputs,
    validate_specification,
)
from narratives_agent.workflows.turn_cache import CachedTable, TurnCache

__all__ = [
    "ProcessingDiagnostic",
    "StepRefusalDiagnostic",
    "TimeoutDiagnostic",
    "execute_specification",
]

logger = logging.getLogger(__name__)

# A run that has not finished within this many seconds is abandoned and
# reported as a timeout, so a stuck run cannot hold the turn open.
_PROCESSING_TIMEOUT_SECONDS = 5.0
# Runs share this many worker threads across concurrent turns. A run that
# outlives its budget keeps its thread until its next step boundary, and a
# run queued behind busy workers spends its own budget waiting, so two
# abandoned runs inside long steps can make concurrent runs time out.
_PROCESSING_MAX_WORKERS = 2
# The steps whose script produces only a result. An alignment produces a
# cohort, and a derived metric produces a table as well as a result.
type _ResultStep = (
    AnalyzeTimeseriesStep
    | RankCohortStep
    | SummarizeDistributionStep
    | ComputeCompositionStep
    | RelateCohortsStep
)

_EXECUTOR = ThreadPoolExecutor(
    max_workers=_PROCESSING_MAX_WORKERS,
    thread_name_prefix="narratives-processing",
)


@dataclass(frozen=True)
class StepRefusalDiagnostic:
    """Why a specification stopped at a step whose script refused.

    Attributes:
        refusal_reason: The refused script's reason.
        message: The refused step's caveats in order, which state any
            input's qualifications before the reason.
        step_id: Identifier of the analysis step (for example, `"s1"`).
        script: The refused step's script.
        input_table_ids: The table references the step read, in the order
            of `list_step_inputs`.
        coverage: The coverage the step reported, or `None` when its refusal
            carries none.
        alternative_sources: The alternative sources of the fetched tables
            behind the step's inputs, followed through any alignment or
            derived table, so the model can refetch with `source_override`.
        completed_results: The results of the steps that succeeded before
            the refusal, in step order.
    """

    refusal_reason: RefusalReason
    message: str
    step_id: str
    script: ScriptName
    input_table_ids: tuple[str, ...]
    coverage: CoverageReport | None
    alternative_sources: tuple[AlternativeSource, ...]
    completed_results: tuple[ScriptResult, ...]

    def format_for_retry(self) -> str:
        """Renders the diagnostic as the message returned to the model.

        Returns:
            The step, its script, its input tables, the reason and caveats,
            the coverage when known, the alternative sources
            (`PLACE_NAME_CAP` of them, then a count of the rest) with how to
            use one, and the corrective actions available.
        """
        tables = format_place_names(
            self.input_table_ids, singular_noun="table", plural_noun="tables"
        )
        lines = [
            f"Processing step {self.step_id} ({self.script}) on {tables} "
            f"failed with {self.refusal_reason}: {self.message}"
        ]
        if self.coverage is not None:
            lines.append(f"Coverage: {self.coverage.describe()}.")
        if self.alternative_sources:
            described = _describe_sources(self.alternative_sources)
            lines.append(
                f"Alternative sources for {tables}: {described}. To use one, "
                "call the same fetch again with source_override=<facet_id>; "
                "the new table gets a new id."
            )
        lines.append(
            "Then submit a corrected specification, or widen the date "
            "window, lower min_coverage, or choose another table. If the "
            "data cannot answer the question, call report_unavailable."
        )
        return " ".join(lines)


@dataclass(frozen=True)
class TimeoutDiagnostic:
    """Why a specification did not finish within its budget.

    Attributes:
        timeout_seconds: The budget the run exceeded, in seconds.
        message: The statement of the timeout.
    """

    timeout_seconds: float
    message: str

    def format_for_retry(self) -> str:
        """Renders the diagnostic as the message returned to the model.

        Returns:
            The timeout and a request for a simpler specification.
        """
        return (
            f"Processing failed: {self.message} Submit a simpler "
            "specification with fewer steps or smaller tables."
        )


# Why a specification produced no digest: a refused step, or the budget.
ProcessingDiagnostic = StepRefusalDiagnostic | TimeoutDiagnostic


def _describe_sources(sources: tuple[AlternativeSource, ...]) -> str:
    """Lists up to `PLACE_NAME_CAP` sources and counts the rest.

    Entries are joined with semicolons, because each entry's details are
    joined with commas, so `format_place_names` does not apply.
    """
    described = "; ".join(
        _describe_source(source) for source in sources[:PLACE_NAME_CAP]
    )
    remainder = len(sources) - PLACE_NAME_CAP
    if remainder <= 0:
        return described
    noun = "other source" if remainder == 1 else "other sources"
    return f"{described}; and {remainder} {noun}"


def _describe_source(source: AlternativeSource) -> str:
    """Renders one alternative source as `facet_id (details)`."""
    details = [
        value
        for value in (
            source.measurement_method,
            source.observation_period,
            source.unit,
        )
        if value
    ]
    if source.places_found_count is not None:
        details.append(f"{source.places_found_count} places")
    return (
        f"{source.facet_id} ({', '.join(details)})"
        if details
        else source.facet_id
    )


@dataclass
class _RunState:
    """The inputs and outputs of one run, keyed by table reference.

    Attributes:
        tables: The fetched tables the specification references, and the
            tables derived by earlier steps under their step ids.
        default_focal_places: The specification's focal places, for the
            steps that name none of their own.
        cohorts: The cohorts aligned by earlier steps, by step id.
        fetched_tables: The fetched tables behind each earlier step's
            cohort or derived table, by step id.
        results: The results of the steps that succeeded, in step order.
        derived: The tables derived by earlier steps, in step order.
    """

    tables: dict[str, ObservationTable]
    default_focal_places: list[str]
    cohorts: dict[str, AlignedCohort] = field(default_factory=dict)
    fetched_tables: dict[str, tuple[ObservationTable, ...]] = field(
        default_factory=dict
    )
    results: list[ScriptResult] = field(default_factory=list)
    derived: list[CachedTable] = field(default_factory=list)

    def get_input(self, reference: str) -> ObservationTable | AlignedCohort:
        """Returns the aligned cohort or table a reference names.

        `validate_specification` guarantees that every reference names a
        fetched table or the output of an earlier step.
        """
        cohort = self.cohorts.get(reference)
        return cohort if cohort is not None else self.tables[reference]

    def resolve_fetched_tables(
        self, step: SpecificationStep
    ) -> tuple[ObservationTable, ...]:
        """Returns the fetched tables behind a step's inputs, in input order.

        A fetched input is itself; an aligned cohort or a derived table is
        the fetched tables it was produced from.
        """
        tables: list[ObservationTable] = []
        for _, reference in list_step_inputs(step):
            behind = self.fetched_tables.get(reference)
            tables.extend(
                behind if behind is not None else (self.tables[reference],)
            )
        return tuple(tables)


def _collect_alternative_sources(
    step: SpecificationStep, state: _RunState
) -> tuple[AlternativeSource, ...]:
    """Collects the alternative sources of the fetched tables a step reads.

    Every input of a two-input step is consulted, in input order, and a
    facet offered by more than one table is listed once.
    """
    sources: dict[str, AlternativeSource] = {}
    for table in state.resolve_fetched_tables(step):
        for source in table.alternative_sources:
            sources.setdefault(source.facet_id, source)
    return tuple(sources.values())


def _build_refusal_diagnostic(
    step: SpecificationStep, state: _RunState, result: RefusedScriptResult
) -> StepRefusalDiagnostic:
    """Builds the diagnostic of a step whose script refused.

    A diagnostic is the message returned to the model for a retry, not a
    script result, so it is built here rather than by the shared refusal
    builders, which the scripts have already applied to `result`.
    """
    return StepRefusalDiagnostic(
        refusal_reason=result.refusal_reason,
        message=" ".join(result.caveats),
        step_id=step.step_id,
        script=step.script,
        input_table_ids=tuple(
            reference for _, reference in list_step_inputs(step)
        ),
        coverage=result.coverage,
        alternative_sources=_collect_alternative_sources(step, state),
        completed_results=tuple(state.results),
    )


def _build_timeout_diagnostic(timeout_seconds: float) -> TimeoutDiagnostic:
    """Builds the diagnostic of a run that exceeded its budget."""
    return TimeoutDiagnostic(
        timeout_seconds=timeout_seconds,
        message=(
            f"The analysis did not finish within {timeout_seconds:g} seconds."
        ),
    )


def _run_alignment_step(
    step: AlignCohortStep, state: _RunState
) -> StepRefusalDiagnostic | None:
    """Aligns a table and records the cohort for later steps.

    Returns:
        The diagnostic of a refused alignment, or `None` once the cohort is
        recorded.
    """
    table = state.tables[step.table]
    aligned = resolve_aligned_cohort(
        table,
        script=step.script,
        step_id=step.step_id,
        target_date=step.target_date,
        min_coverage=step.min_coverage,
        operation="aligned",
    )
    if isinstance(aligned, RefusedScriptResult):
        return _build_refusal_diagnostic(step, state, aligned)
    state.fetched_tables[step.step_id] = state.resolve_fetched_tables(step)
    state.cohorts[step.step_id] = aligned
    return None


def _run_derived_metric_step(
    step: ComputeDerivedMetricStep, state: _RunState
) -> StepRefusalDiagnostic | None:
    """Derives a table and records it and its result for later steps.

    Returns:
        The diagnostic of a refused derivation, or `None` once the table and
        its result are recorded.
    """
    outcome = derive_observation_table(
        state.tables[step.left],
        state.tables[step.right],
        operation=step.operation,
        scale=step.scale,
        derived_variable_dcid=step.derived_variable_dcid,
        derived_variable_name=step.derived_variable_name,
        derived_unit=step.derived_unit,
        places=step.places,
        start_date=step.start_date,
        end_date=step.end_date,
        min_coverage=step.min_coverage,
        step_id=step.step_id,
    )
    if isinstance(outcome.result, RefusedScriptResult):
        return _build_refusal_diagnostic(step, state, outcome.result)
    # An `ok` outcome always carries its table.
    if outcome.table is None:
        raise RuntimeError(f"{step.step_id} derived no table.")
    state.fetched_tables[step.step_id] = state.resolve_fetched_tables(step)
    state.tables[step.step_id] = outcome.table
    state.derived.append(
        CachedTable(table_id=step.step_id, table=outcome.table)
    )
    state.results.append(outcome.result)
    return None


def _run_result_step(step: _ResultStep, state: _RunState) -> ScriptResult:
    """Runs the script of a step that produces only a result."""
    match step:
        case AnalyzeTimeseriesStep():
            return analyze_timeseries(
                state.tables[step.table],
                places=step.places,
                start_date=step.start_date,
                end_date=step.end_date,
                step_id=step.step_id,
            )
        case RankCohortStep():
            return rank_cohort(
                state.get_input(step.table),
                max_entries_per_end=step.n,
                direction=step.direction,
                focal_places=step.focal_places or state.default_focal_places,
                target_date=step.target_date,
                min_coverage=step.min_coverage,
                step_id=step.step_id,
            )
        case SummarizeDistributionStep():
            return summarize_distribution(
                state.get_input(step.table),
                weights=(
                    state.get_input(step.weights)
                    if step.weights is not None
                    else None
                ),
                focal_places=step.focal_places or state.default_focal_places,
                target_date=step.target_date,
                min_coverage=step.min_coverage,
                step_id=step.step_id,
            )
        case RelateCohortsStep():
            return relate_cohorts(
                state.get_input(step.target),
                state.get_input(step.by),
                n=step.n,
                target_date=step.target_date,
                by_date=step.by_date,
                min_coverage=step.min_coverage,
                step_id=step.step_id,
            )
        case ComputeCompositionStep():
            return compute_composition(
                [state.get_input(reference) for reference in step.components],
                total=(
                    state.get_input(step.total)
                    if step.total is not None
                    else None
                ),
                mode=step.mode,
                places=step.places,
                target_date=step.target_date,
                min_coverage=step.min_coverage,
                step_id=step.step_id,
            )


def _run_step(
    step: SpecificationStep, state: _RunState
) -> StepRefusalDiagnostic | None:
    """Runs one step and records what it makes available.

    Returns:
        The diagnostic of a refused step, or `None` once its result and any
        cohort or table it produces are recorded.
    """
    match step:
        case AlignCohortStep():
            return _run_alignment_step(step, state)
        case ComputeDerivedMetricStep():
            return _run_derived_metric_step(step, state)
        case _:
            result = _run_result_step(step, state)
            if isinstance(result, RefusedScriptResult):
                return _build_refusal_diagnostic(step, state, result)
            state.results.append(result)
            return None


def _run_specification(
    specification: AnalysisSpecification,
    cache: TurnCache,
    cancel: threading.Event,
    timeout_seconds: float,
) -> tuple[AnalysisDigest | ProcessingDiagnostic, tuple[CachedTable, ...]]:
    """Runs every step in order on the calling thread.

    The cache is only read here. The derived tables are returned beside the
    outcome for the caller to store, and the run stops at the next step
    boundary once `cancel` is set, which the caller does when the budget
    expires.

    Args:
        specification: A specification `validate_specification` accepted.
        cache: The turn's cache, read for the referenced fetched tables.
        cancel: Set by the caller when the run's budget has expired.
        timeout_seconds: The budget, stated in a timeout diagnostic.

    Returns:
        The digest or diagnostic, and the derived `CachedTable` entries in
        step order.
    """
    state = _RunState(
        tables={
            table_id: entry.table
            for table_id in specification.list_referenced_table_ids()
            if (entry := cache.get(table_id)) is not None
        },
        default_focal_places=specification.focal_places,
    )
    for step in specification.steps:
        if cancel.is_set():
            return _build_timeout_diagnostic(timeout_seconds), tuple(
                state.derived
            )
        diagnostic = _run_step(step, state)
        if diagnostic is not None:
            return diagnostic, tuple(state.derived)
    digest = AnalysisDigest.from_results(
        tuple(state.results), missing_notes=tuple(specification.missing)
    )
    return digest, tuple(state.derived)


def _validate_run_preconditions(
    specification: AnalysisSpecification,
    cache: TurnCache,
    timeout_seconds: float,
) -> None:
    """Raises `ValueError` when `execute_specification` cannot run."""
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError(
            "The processing budget must be a finite number of seconds above "
            f"zero, not {timeout_seconds}."
        )
    problems = validate_specification(specification, cache)
    if problems is not None:
        raise ValueError(
            f"The specification does not match the cache:\n{problems}"
        )


async def execute_specification(
    specification: AnalysisSpecification,
    cache: TurnCache,
    *,
    timeout_seconds: float = _PROCESSING_TIMEOUT_SECONDS,
) -> AnalysisDigest | ProcessingDiagnostic:
    """Resolves a specification into a digest, off the event loop.

    The steps run on the module's bounded thread pool so that a long
    reduction never blocks concurrent streams, and under `timeout_seconds`
    so that a stuck run ends the phase with a diagnostic rather than holding
    the turn open. The cache's derived tables are cleared before the run
    and replaced by the ones the run produced once it returns in time. A
    run that exceeds the budget, or whose awaiting task is cancelled, is
    signaled to stop at its next step boundary and stores nothing; until it
    stops, it holds one of the pool's `_PROCESSING_MAX_WORKERS` threads.

    Args:
        specification: A specification that `validate_specification`
            accepts against `cache`.
        cache: The turn's cache, which receives the derived tables.
        timeout_seconds: The wall-clock budget of the run, in seconds.

    Returns:
        The digest, or the diagnostic of the first step that refused or of
        the timeout.

    Raises:
        ValueError: If `timeout_seconds` is not a finite number above zero,
            or `validate_specification` reports a problem.
    """
    _validate_run_preconditions(specification, cache, timeout_seconds)
    cache.clear_derived()
    cancel = threading.Event()
    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(
        _EXECUTOR,
        _run_specification,
        specification,
        cache,
        cancel,
        timeout_seconds,
    )
    try:
        outcome, derived = await asyncio.wait_for(
            future, timeout=timeout_seconds
        )
    except TimeoutError:
        logger.warning(
            "Processing exceeded %g seconds for %d steps",
            timeout_seconds,
            len(specification.steps),
        )
        return _build_timeout_diagnostic(timeout_seconds)
    finally:
        # Stops a run that was abandoned, on a timeout or on cancellation of
        # the awaiting task, at its next step boundary; once the run has
        # returned, the event is no longer read.
        cancel.set()
    for entry in derived:
        cache.store_derived(entry)
    return outcome
