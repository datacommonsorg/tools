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
"""Tests for `execute_specification` in `processing`.

Covers the dispatch of every step type, shared cohort alignment, refusal
diagnostics with coverage and alternative sources, the enforced
preconditions, the wall-clock budget and the isolation of a run that
outlives it, derived-table replacement, and digest source numbering.
"""

import asyncio
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from narratives_agent.analytics.digest import (
    PLACE_NAME_CAP,
    AnalysisDigest,
    CoverageReport,
)
from narratives_agent.analytics.metrics import (
    CompositionMetrics,
    DistributionMetrics,
    RankingMetrics,
    RelationMetrics,
)
from narratives_agent.analytics.provenance import (
    AlternativeSource,
    Provenance,
    Source,
)
from narratives_agent.analytics.tables import ObservationRow, ObservationTable
from narratives_agent.json_value import JsonObject, JsonValue
from narratives_agent.workflows import processing
from narratives_agent.workflows.processing import (
    StepRefusalDiagnostic,
    TimeoutDiagnostic,
    execute_specification,
)
from narratives_agent.workflows.specification import (
    AnalysisSpecification,
    SpecificationStep,
)
from narratives_agent.workflows.turn_cache import CachedTable, TurnCache

_WDI = Source(name="WDI", url="https://wdi.example")
_CENSUS = Source(name="Census", url="https://census.example")
_OTHER = Source(name="Other", url="https://other.example")
# A budget short enough that a run blocked on an event exceeds it.
_SHORT_BUDGET_SECONDS = 0.01


def _build_table(
    table_id: str,
    values: dict[str, float],
    *,
    variable_dcid: str,
    source: Source,
    unit: str | None = None,
    requested: tuple[str, ...] | None = None,
    alternatives: tuple[str, ...] = (),
) -> CachedTable:
    """Builds a one-date cached state table of `values` keyed by place."""
    places = requested or tuple(values)
    table = ObservationTable(
        variable_dcid=variable_dcid,
        variable_name=variable_dcid.replace("_", " "),
        unit=unit,
        scaling_factor=None,
        provenance=Provenance(sources=(source,), facet_ids=("f1",)),
        rows=tuple(
            ObservationRow(place, place.upper(), "2023", value)
            for place, value in values.items()
        ),
        requested_places=places,
        place_names={place: place.upper() for place in places},
        facet_id="f1",
        source=source,
        alternative_sources=tuple(
            AlternativeSource(
                facet_id=item,
                measurement_method=f"import {item}",
            )
            for item in alternatives
        ),
        parent_place_dcid="country/USA",
        child_place_type="State",
    )
    return CachedTable(table_id=table_id, table=table)


def _build_specification(
    *steps: JsonObject, **extra: JsonValue
) -> AnalysisSpecification:
    """Validates a specification from step objects and top-level fields."""
    payload: JsonObject = {"steps": list(steps), **extra}
    return AnalysisSpecification.model_validate(payload)


def _build_cache(*entries: CachedTable) -> TurnCache:
    """Stores the cached tables in a fresh cache, in order."""
    cache = TurnCache()
    for entry in entries:
        cache.store_fetched(entry)
    return cache


def _build_four_state_tables(
    *, by_values: dict[str, float] | None = None
) -> TurnCache:
    """Caches diabetes (`t1`) and income (`t2`) over the same four states."""
    return _build_cache(
        _build_table(
            "t1",
            {"a": 1.0, "b": 2.0, "c": 3.0, "d": 4.0},
            variable_dcid="Percent_Diabetes",
            source=_WDI,
        ),
        _build_table(
            "t2",
            by_values or {"a": 40.0, "b": 30.0, "c": 20.0, "d": 10.0},
            variable_dcid="Median_Income",
            source=_CENSUS,
            requested=("a", "b", "c", "d"),
            alternatives=("f3",),
        ),
    )


@pytest.mark.asyncio
async def test_a_derived_ranking_cites_both_sources() -> None:
    # Test: A derived metric whose table a ranking reads.
    # Situation: Of three cached tables, the specification divides `t3`
    #   (cases, from WDI) by `t1` (population, from Census) per 100,000
    #   people and ranks the derived table; `t2` is unused.
    # Expectation: The digest holds both results; the derived table is
    #   stored as `s1`; the sources are numbered in order of first
    #   appearance (`t3` then `t1`) and the ranking cites both, so `t2`
    #   takes no number; and the missing notes reach the digest.
    cache = _build_cache(
        _build_table(
            "t1",
            {"a": 4000.0, "b": 8000.0},
            variable_dcid="Count_Person",
            source=_CENSUS,
        ),
        _build_table("t2", {"a": 1.0}, variable_dcid="Unused", source=_WDI),
        _build_table(
            "t3",
            {"a": 10.0, "b": 50.0},
            variable_dcid="Count_Case",
            source=_WDI,
        ),
    )
    specification = _build_specification(
        {
            "step_id": "s1",
            "script": "compute_derived_metric",
            "left": "t3",
            "right": "t1",
            "operation": "per_capita",
            "scale": 100000,
        },
        {"step_id": "s2", "script": "rank_cohort", "table": "s1", "n": 1},
        missing=["No county data."],
    )

    digest = await execute_specification(specification, cache)

    assert isinstance(digest, AnalysisDigest)
    assert [result.script for result in digest.results] == [
        "compute_derived_metric",
        "rank_cohort",
    ]
    assert digest.sources == (_WDI, _CENSUS)
    assert digest.citation_label(digest.results[1].provenance) == "[1, 2]"
    ranking_metrics = digest.results[1].metrics
    assert isinstance(ranking_metrics, RankingMetrics)
    assert ranking_metrics.top_n[0].place_dcid == "b"
    assert ranking_metrics.top_n[0].value == 625.0
    assert digest.missing_notes == ("No county data.",)
    derived = cache.get("s1")
    assert derived is not None
    assert (
        derived.table.variable_dcid
        == "derived_Count_Case_per_capita_Count_Person"
    )


@pytest.mark.asyncio
async def test_a_relation_step_reads_both_tables() -> None:
    # Test: The dispatch of `relate_cohorts`.
    # Situation: Diabetes (`t1`) is related to income (`t2`) over the same
    #   four states, two places per group.
    # Expectation: The digest holds one relation over both variables, citing
    #   both sources, and nothing is stored in the cache for it.
    cache = _build_four_state_tables()
    specification = _build_specification(
        {
            "step_id": "s1",
            "script": "relate_cohorts",
            "target": "t1",
            "by": "t2",
            "n": 2,
        }
    )

    digest = await execute_specification(specification, cache)

    assert isinstance(digest, AnalysisDigest)
    (result,) = digest.results
    assert result.variables == ("Percent_Diabetes", "Median_Income")
    assert digest.sources == (_WDI, _CENSUS)
    metrics = result.metrics
    assert isinstance(metrics, RelationMetrics)
    assert [entry.place_dcid for entry in metrics.highest_by] == ["a", "b"]
    assert metrics.target_mean_difference == -2.0
    assert cache.get("s1") is None


@pytest.mark.asyncio
async def test_a_refused_relation_reports_both_tables() -> None:
    # Test: The diagnostic of a refused two-input step.
    # Situation: The `by` table was requested for four states and reports
    #   one, below the default coverage.
    # Expectation: The diagnostic carries `insufficient_coverage`, the `by`
    #   side's coverage, both input tables with `t1` first, and `t2`'s
    #   alternative source; its retry message names both tables, the side,
    #   and the coverage.
    cache = _build_four_state_tables(by_values={"a": 40.0})
    specification = _build_specification(
        {
            "step_id": "s1",
            "script": "relate_cohorts",
            "target": "t1",
            "by": "t2",
        }
    )

    outcome = await execute_specification(specification, cache)

    assert isinstance(outcome, StepRefusalDiagnostic)
    assert outcome.refusal_reason == "insufficient_coverage"
    assert outcome.coverage is not None
    assert outcome.coverage.contributing_places == 1
    assert outcome.input_table_ids == ("t1", "t2")
    assert [item.facet_id for item in outcome.alternative_sources] == ["f3"]
    message = outcome.format_for_retry()
    assert message.startswith(
        "Processing step s1 (relate_cohorts) on t1 and t2 failed with "
        "insufficient_coverage:"
    )
    assert "The by cohort (Median Income) could not be aligned" in message
    assert "Coverage: 1 of 4 places on 2023." in message
    assert "Alternative sources for t1 and t2: f3 (import f3)." in message


@pytest.mark.asyncio
async def test_an_alignment_is_shared_by_later_steps() -> None:
    # Test: The dispatch of `align_cohort`, and of a ranking and a
    #   distribution over its cohort.
    # Situation: One table is aligned once, then ranked and summarized from
    #   the cohort; neither step names focal places, and the specification
    #   names `c`.
    # Expectation: The digest holds the ranking and the distribution, both
    #   on the alignment's date and both reporting `c`, and the alignment
    #   stores nothing in the cache.
    cache = _build_cache(
        _build_table(
            "t1",
            {"a": 1.0, "b": 2.0, "c": 3.0},
            variable_dcid="Count_Person",
            source=_WDI,
        )
    )
    specification = _build_specification(
        {"step_id": "s1", "script": "align_cohort", "table": "t1"},
        {"step_id": "s2", "script": "rank_cohort", "table": "s1"},
        {"step_id": "s3", "script": "summarize_distribution", "table": "s1"},
        focal_places=["c"],
    )

    digest = await execute_specification(specification, cache)

    assert isinstance(digest, AnalysisDigest)
    assert [result.step_id for result in digest.results] == ["s2", "s3"]
    ranking_metrics = digest.results[0].metrics
    distribution_metrics = digest.results[1].metrics
    assert isinstance(ranking_metrics, RankingMetrics)
    assert isinstance(distribution_metrics, DistributionMetrics)
    assert ranking_metrics.reference_date == "2023"
    assert distribution_metrics.reference_date == "2023"
    assert ranking_metrics.focal_entries[0].place_dcid == "c"
    assert distribution_metrics.focal_entries[0].place_dcid == "c"
    assert cache.table_ids == ("t1",)


@pytest.mark.asyncio
async def test_a_step_with_its_own_focal_places_keeps_them() -> None:
    # Test: Step focal places over the specification's.
    # Situation: The ranking names `a`, and the specification names `c`.
    # Expectation: The ranking reports `a` only.
    cache = _build_cache(
        _build_table(
            "t1",
            {"a": 1.0, "b": 2.0, "c": 3.0},
            variable_dcid="Count_Person",
            source=_WDI,
        )
    )
    specification = _build_specification(
        {
            "step_id": "s1",
            "script": "rank_cohort",
            "table": "t1",
            "focal_places": ["a"],
        },
        focal_places=["c"],
    )

    digest = await execute_specification(specification, cache)

    assert isinstance(digest, AnalysisDigest)
    metrics = digest.results[0].metrics
    assert isinstance(metrics, RankingMetrics)
    assert [entry.place_dcid for entry in metrics.focal_entries] == ["a"]


@pytest.mark.asyncio
async def test_a_refused_alignment_becomes_a_diagnostic() -> None:
    # Test: The diagnostic of a refused `align_cohort` step.
    # Situation: `t1` was requested for four states and reports one, and the
    #   specification aligns it before ranking it.
    # Expectation: The run ends at the alignment with
    #   `insufficient_coverage`, its coverage of one of four places, and its
    #   alignment message, and no step result.
    cache = _build_cache(
        _build_table(
            "t1",
            {"a": 1.0},
            variable_dcid="Count_Person",
            source=_WDI,
            requested=("a", "b", "c", "d"),
        )
    )
    specification = _build_specification(
        {"step_id": "s1", "script": "align_cohort", "table": "t1"},
        {"step_id": "s2", "script": "rank_cohort", "table": "s1"},
    )

    diagnostic = await execute_specification(specification, cache)

    assert isinstance(diagnostic, StepRefusalDiagnostic)
    assert (diagnostic.step_id, diagnostic.script) == ("s1", "align_cohort")
    assert diagnostic.refusal_reason == "insufficient_coverage"
    assert diagnostic.coverage is not None
    assert diagnostic.coverage.describe() == "1 of 4 places on 2023"
    assert diagnostic.message.startswith("Only 1 of 4 places on 2023 has")
    assert diagnostic.completed_results == ()


@pytest.mark.asyncio
async def test_a_refusal_reports_alternatives_and_completed_steps() -> None:
    # Test: The diagnostic of a refused single-table step.
    # Situation: A series summary of `t1` succeeds, then a ranking of `t2`
    #   refuses because one of four requested places has a value; `t2` lists
    #   two alternative sources.
    # Expectation: The diagnostic names the step, the script, the table, the
    #   reason, the coverage, both alternative sources, and the one
    #   completed result; the retry message names the facets and the
    #   corrective actions.
    cache = _build_cache(
        _build_table(
            "t1", {"a": 1.0}, variable_dcid="Count_Person", source=_WDI
        ),
        _build_table(
            "t2",
            {"a": 1.0},
            variable_dcid="Median_Income",
            source=_CENSUS,
            requested=("a", "b", "c", "d"),
            alternatives=("f2", "f3"),
        ),
    )
    specification = _build_specification(
        {"step_id": "s1", "script": "analyze_timeseries", "table": "t1"},
        {"step_id": "s2", "script": "rank_cohort", "table": "t2"},
    )

    diagnostic = await execute_specification(specification, cache)

    assert isinstance(diagnostic, StepRefusalDiagnostic)
    assert (
        diagnostic.step_id,
        diagnostic.script,
        diagnostic.input_table_ids,
    ) == ("s2", "rank_cohort", ("t2",))
    assert diagnostic.refusal_reason == "insufficient_coverage"
    assert diagnostic.coverage == CoverageReport(
        contributing_places=1,
        requested_places=4,
        coverage_ratio=0.25,
        reference_date="2023",
        missing_places=("b", "c", "d"),
    )
    assert [item.facet_id for item in diagnostic.alternative_sources] == [
        "f2",
        "f3",
    ]
    assert [item.script for item in diagnostic.completed_results] == [
        "analyze_timeseries"
    ]
    message = diagnostic.format_for_retry()
    assert message.startswith(
        "Processing step s2 (rank_cohort) on t2 failed with "
        "insufficient_coverage: Only 1 of 4 places on 2023 has a value"
    )
    assert "Coverage: 1 of 4 places on 2023." in message
    assert "f2 (import f2); f3 (import f3)" in message
    assert "source_override=<facet_id>" in message
    assert "report_unavailable" in message


@pytest.mark.asyncio
async def test_alternatives_are_traced_through_an_aligned_cohort() -> None:
    # Test: Alternative sources of a step that reads an aligned cohort.
    # Situation: `s1` aligns `t1`, which offers `f2`, and a composition of
    #   `s1` and `t2`, which offers `f3`, refuses on their different units.
    # Expectation: The diagnostic traces `s1` back to `t1` and lists `f2`
    #   and then `f3`.
    cache = _build_cache(
        _build_table(
            "t1",
            {"a": 1.0, "b": 2.0},
            variable_dcid="Count_Person",
            source=_WDI,
            unit="Person",
            alternatives=("f2",),
        ),
        _build_table(
            "t2",
            {"a": 1.0, "b": 2.0},
            variable_dcid="Median_Income",
            source=_CENSUS,
            unit="USDollar",
            alternatives=("f3",),
        ),
    )
    specification = _build_specification(
        {"step_id": "s1", "script": "align_cohort", "table": "t1"},
        {
            "step_id": "s2",
            "script": "compute_composition",
            "components": ["s1", "t2"],
        },
    )

    diagnostic = await execute_specification(specification, cache)

    assert isinstance(diagnostic, StepRefusalDiagnostic)
    assert diagnostic.step_id == "s2"
    assert diagnostic.refusal_reason == "unit_mismatch"
    assert [item.facet_id for item in diagnostic.alternative_sources] == [
        "f2",
        "f3",
    ]


@pytest.mark.asyncio
async def test_a_composition_step_computes_shares_of_its_total() -> None:
    # Test: The dispatch of `compute_composition`.
    # Situation: Two component tables and a total table in one unit over
    #   two states, with each place's components summing to its total.
    # Expectation: The digest holds one composition over both places with
    #   an explicit total.
    cache = _build_cache(
        _build_table(
            "t1",
            {"a": 40.0, "b": 30.0},
            variable_dcid="Count_Person_Male",
            source=_WDI,
            unit="Person",
        ),
        _build_table(
            "t2",
            {"a": 60.0, "b": 50.0},
            variable_dcid="Count_Person_Female",
            source=_WDI,
            unit="Person",
        ),
        _build_table(
            "t3",
            {"a": 100.0, "b": 80.0},
            variable_dcid="Count_Person",
            source=_WDI,
            unit="Person",
        ),
    )
    specification = _build_specification(
        {
            "step_id": "s1",
            "script": "compute_composition",
            "components": ["t1", "t2"],
            "total": "t3",
        }
    )

    digest = await execute_specification(specification, cache)

    assert isinstance(digest, AnalysisDigest)
    metrics = digest.results[0].metrics
    assert isinstance(metrics, CompositionMetrics)
    assert metrics.place_count == 2
    assert metrics.has_explicit_total


@pytest.mark.asyncio
async def test_a_refused_derived_metric_reports_both_tables_sources() -> None:
    # Test: The diagnostic of a refused `compute_derived_metric`.
    # Situation: Two tables whose places never overlap, each offering its
    #   own alternative source.
    # Expectation: The diagnostic reports `no_observations` on both inputs
    #   with `t1` first, lists both alternative sources, and no derived
    #   table is stored.
    cache = _build_cache(
        _build_table(
            "t1",
            {"a": 1.0},
            variable_dcid="Count_Case",
            source=_WDI,
            alternatives=("f2",),
        ),
        _build_table(
            "t2",
            {"b": 1.0},
            variable_dcid="Count_Person",
            source=_CENSUS,
            alternatives=("f3",),
        ),
    )
    specification = _build_specification(
        {
            "step_id": "s1",
            "script": "compute_derived_metric",
            "left": "t1",
            "right": "t2",
        }
    )

    diagnostic = await execute_specification(specification, cache)

    assert isinstance(diagnostic, StepRefusalDiagnostic)
    assert diagnostic.refusal_reason == "no_observations"
    assert diagnostic.input_table_ids == ("t1", "t2")
    assert [item.facet_id for item in diagnostic.alternative_sources] == [
        "f2",
        "f3",
    ]
    assert diagnostic.completed_results == ()
    assert cache.get("s1") is None


@pytest.mark.asyncio
async def test_a_derived_metric_of_one_variable_is_refused() -> None:
    # Test: Two inputs that measure one variable.
    # Situation: `t1` and `t2` are two fetches of `Count_Person`, divided one
    #   by the other.
    # Expectation: The script's `invalid_parameters` refusal becomes the
    #   diagnostic, which has no coverage, so its retry message states none.
    cache = _build_cache(
        _build_table(
            "t1", {"a": 4.0}, variable_dcid="Count_Person", source=_WDI
        ),
        _build_table(
            "t2", {"a": 8.0}, variable_dcid="Count_Person", source=_CENSUS
        ),
    )
    specification = _build_specification(
        {
            "step_id": "s1",
            "script": "compute_derived_metric",
            "left": "t1",
            "right": "t2",
        }
    )

    diagnostic = await execute_specification(specification, cache)

    assert isinstance(diagnostic, StepRefusalDiagnostic)
    assert diagnostic.refusal_reason == "invalid_parameters"
    assert diagnostic.coverage is None
    assert "Coverage:" not in diagnostic.format_for_retry()


@pytest.mark.asyncio
async def test_a_specification_the_cache_does_not_hold_raises() -> None:
    # Test: The validation precondition of `execute_specification`.
    # Situation: The specification ranks `t2`, which is not cached.
    # Expectation: `ValueError` names the problem, and the run never starts.
    cache = _build_cache(
        _build_table(
            "t1", {"a": 1.0}, variable_dcid="Count_Person", source=_WDI
        )
    )
    specification = _build_specification(
        {"step_id": "s1", "script": "rank_cohort", "table": "t2"}
    )

    with pytest.raises(ValueError, match=r"s1\.table references t2"):
        await execute_specification(specification, cache)


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout_seconds", [0.0, -1.0, float("inf")])
async def test_a_budget_that_is_not_a_positive_duration_raises(
    timeout_seconds: float,
) -> None:
    # Test: The budget precondition of `execute_specification`.
    # Situation: A budget of zero, a negative budget, and an infinite one.
    # Expectation: Each raises `ValueError`.
    cache = _build_cache(
        _build_table(
            "t1", {"a": 1.0}, variable_dcid="Count_Person", source=_WDI
        )
    )
    specification = _build_specification(
        {"step_id": "s1", "script": "analyze_timeseries", "table": "t1"}
    )

    with pytest.raises(ValueError, match="processing budget"):
        await execute_specification(
            specification, cache, timeout_seconds=timeout_seconds
        )


@pytest.fixture
def use_isolated_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[ThreadPoolExecutor]:
    """Runs the test's specifications on a single-worker pool of its own.

    A run that the test leaves blocked past its budget would otherwise hold
    one of the module pool's workers for the rest of the session.
    """
    pool = ThreadPoolExecutor(max_workers=1)
    monkeypatch.setattr(processing, "_EXECUTOR", pool)
    yield pool
    pool.shutdown(wait=False, cancel_futures=True)


@pytest.mark.asyncio
@pytest.mark.usefixtures("use_isolated_executor")
async def test_a_run_over_budget_ends_with_a_timeout_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: The wall-clock budget.
    # Situation: The run is replaced by one that blocks on an event the test
    #   sets only after `execute_specification` returns, under a short
    #   budget.
    # Expectation: `execute_specification` returns a `TimeoutDiagnostic`
    #   carrying the budget and asking for a simpler specification, without
    #   waiting for the blocked run.
    released = asyncio.Event()
    loop = asyncio.get_running_loop()

    def run_blocked(
        specification: AnalysisSpecification,
        cache: TurnCache,
        cancel: threading.Event,
        timeout_seconds: float,
    ) -> tuple[TimeoutDiagnostic, tuple[CachedTable, ...]]:
        asyncio.run_coroutine_threadsafe(released.wait(), loop).result()
        return processing._build_timeout_diagnostic(timeout_seconds), ()

    monkeypatch.setattr(processing, "_run_specification", run_blocked)
    cache = _build_cache(
        _build_table(
            "t1", {"a": 1.0}, variable_dcid="Count_Person", source=_WDI
        )
    )
    specification = _build_specification(
        {"step_id": "s1", "script": "analyze_timeseries", "table": "t1"}
    )

    try:
        diagnostic = await execute_specification(
            specification, cache, timeout_seconds=_SHORT_BUDGET_SECONDS
        )
    finally:
        released.set()

    assert isinstance(diagnostic, TimeoutDiagnostic)
    assert diagnostic.timeout_seconds == _SHORT_BUDGET_SECONDS
    assert diagnostic.format_for_retry() == (
        "Processing failed: The analysis did not finish within 0.01 seconds. "
        "Submit a simpler specification with fewer steps or smaller tables."
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("use_isolated_executor")
async def test_a_run_that_finishes_after_its_budget_stores_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Isolation of a run that outlives its budget.
    # Situation: Every step records its id, and the first step of a
    #   derived-metric specification blocks on an event until the test sets
    #   it after the timeout; a quick specification then runs over the same
    #   cache.
    # Expectation: The timed-out run never starts its second step, its
    #   derived table never enters the cache, and the cache holds only what
    #   the quick run produced.
    released = threading.Event()
    run_step = processing._run_step
    steps_run: list[str] = []

    def run_step_when_released(
        step: SpecificationStep, state: processing._RunState
    ) -> StepRefusalDiagnostic | None:
        steps_run.append(step.step_id)
        released.wait()
        return run_step(step, state)

    monkeypatch.setattr(processing, "_run_step", run_step_when_released)
    cache = _build_cache(
        _build_table(
            "t1", {"a": 10.0}, variable_dcid="Count_Case", source=_WDI
        ),
        _build_table(
            "t2", {"a": 1000.0}, variable_dcid="Count_Person", source=_WDI
        ),
    )
    slow = _build_specification(
        {
            "step_id": "s1",
            "script": "compute_derived_metric",
            "left": "t1",
            "right": "t2",
        },
        {"step_id": "s2", "script": "analyze_timeseries", "table": "s1"},
    )

    diagnostic = await execute_specification(
        slow, cache, timeout_seconds=_SHORT_BUDGET_SECONDS
    )
    released.set()
    quick = _build_specification(
        {"step_id": "s1", "script": "analyze_timeseries", "table": "t1"}
    )
    # The pool has one worker, so the quick run starts only after the
    # timed-out run reaches its next step boundary and returns.
    digest = await execute_specification(quick, cache)

    assert isinstance(diagnostic, TimeoutDiagnostic)
    assert isinstance(digest, AnalysisDigest)
    # The timed-out run may still have been queued when its budget expired,
    # in which case it never started; either way it never reached `s2`.
    assert "s2" not in steps_run
    assert steps_run[-1] == "s1"
    assert cache.table_ids == ("t1", "t2")


@pytest.mark.asyncio
async def test_a_cancelled_run_stops_at_its_next_step_boundary(
    monkeypatch: pytest.MonkeyPatch,
    use_isolated_executor: ThreadPoolExecutor,
) -> None:
    # Test: Cancellation of the task awaiting a run.
    # Situation: The first step of a two-step specification blocks on an
    #   event; the awaiting task is cancelled while it blocks, and the event
    #   is then set.
    # Expectation: The task raises `CancelledError`, the run never starts
    #   its second step, and the cache holds no derived table.
    started = threading.Event()
    released = threading.Event()
    run_step = processing._run_step
    steps_run: list[str] = []

    def run_step_when_released(
        step: SpecificationStep, state: processing._RunState
    ) -> StepRefusalDiagnostic | None:
        steps_run.append(step.step_id)
        started.set()
        released.wait()
        return run_step(step, state)

    monkeypatch.setattr(processing, "_run_step", run_step_when_released)
    cache = _build_cache(
        _build_table(
            "t1", {"a": 10.0}, variable_dcid="Count_Case", source=_WDI
        ),
        _build_table(
            "t2", {"a": 1000.0}, variable_dcid="Count_Person", source=_WDI
        ),
    )
    specification = _build_specification(
        {
            "step_id": "s1",
            "script": "compute_derived_metric",
            "left": "t1",
            "right": "t2",
        },
        {"step_id": "s2", "script": "analyze_timeseries", "table": "s1"},
    )
    loop = asyncio.get_running_loop()

    task = asyncio.create_task(execute_specification(specification, cache))
    await loop.run_in_executor(None, started.wait)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    released.set()
    # The pool has one worker, so this no-op runs only after the cancelled
    # run has returned.
    await loop.run_in_executor(use_isolated_executor, lambda: None)

    assert steps_run == ["s1"]
    assert cache.table_ids == ("t1", "t2")


@pytest.mark.asyncio
async def test_citations_are_numbered_over_the_results_produced() -> None:
    # Test: Citation numbering when a referenced table is never cited.
    # Situation: `t1` is summarized with `t2` as weights, but `t2` covers one
    #   of three places, so no weighted mean is computed and `t2`'s source is
    #   not cited; a series summary of `t3` follows.
    # Expectation: The sources of `t1` and `t3` are numbered 1 and 2, the
    #   distribution cites `[1]`, and the series summary cites `[2]`.
    cache = _build_cache(
        _build_table(
            "t1",
            {"a": 1.0, "b": 2.0, "c": 3.0},
            variable_dcid="Median_Income",
            source=_WDI,
        ),
        _build_table(
            "t2",
            {"a": 100.0},
            variable_dcid="Count_Person",
            source=_CENSUS,
            requested=("a", "b", "c"),
        ),
        _build_table(
            "t3",
            {"a": 5.0},
            variable_dcid="Count_Household",
            source=_OTHER,
        ),
    )
    specification = _build_specification(
        {
            "step_id": "s1",
            "script": "summarize_distribution",
            "table": "t1",
            "weights": "t2",
        },
        {"step_id": "s2", "script": "analyze_timeseries", "table": "t3"},
    )

    digest = await execute_specification(specification, cache)

    assert isinstance(digest, AnalysisDigest)
    assert digest.sources == (_WDI, _OTHER)
    assert [
        digest.citation_label(result.provenance) for result in digest.results
    ] == ["[1]", "[2]"]
    distribution_metrics = digest.results[0].metrics
    assert isinstance(distribution_metrics, DistributionMetrics)
    assert distribution_metrics.weighted_mean is None


@pytest.mark.asyncio
async def test_each_run_replaces_the_derived_tables_of_the_last() -> None:
    # Test: Derived tables across runs.
    # Situation: A first specification derives `s1` from `t1` and `t2`; a
    #   second over the same cache has a result-only `s1`.
    # Expectation: After the second run the cache holds no derived table,
    #   so the first run's `s1` cannot be read as the second run's step.
    cache = _build_cache(
        _build_table(
            "t1", {"a": 10.0}, variable_dcid="Count_Case", source=_WDI
        ),
        _build_table(
            "t2", {"a": 1000.0}, variable_dcid="Count_Person", source=_WDI
        ),
    )
    first = _build_specification(
        {
            "step_id": "s1",
            "script": "compute_derived_metric",
            "left": "t1",
            "right": "t2",
        }
    )
    second = _build_specification(
        {"step_id": "s1", "script": "analyze_timeseries", "table": "t1"}
    )

    await execute_specification(first, cache)
    after_first = cache.table_ids
    await execute_specification(second, cache)

    assert after_first == ("t1", "t2", "s1")
    assert cache.table_ids == ("t1", "t2")


@pytest.mark.asyncio
async def test_a_long_list_of_alternatives_is_capped_and_counted() -> None:
    # Test: The alternative sources of a retry message.
    # Situation: A ranking refuses on a table that offers seven alternative
    #   sources: one with a place count, one with no details, and five with
    #   a measurement method.
    # Expectation: The retry message describes the first `PLACE_NAME_CAP`
    #   sources (a place count as "N places", a source without details by
    #   its facet alone) and counts the other two.
    alternatives = (
        AlternativeSource(facet_id="f1", places_found_count=3),
        AlternativeSource(facet_id="f2"),
        *(
            AlternativeSource(facet_id=f"f{index}", measurement_method="survey")
            for index in range(3, 8)
        ),
    )
    entry = _build_table(
        "t1",
        {"a": 1.0},
        variable_dcid="Median_Income",
        source=_CENSUS,
        requested=("a", "b", "c", "d"),
    )
    cache = _build_cache(
        replace(
            entry,
            table=replace(entry.table, alternative_sources=alternatives),
        )
    )
    specification = _build_specification(
        {"step_id": "s1", "script": "rank_cohort", "table": "t1"}
    )

    diagnostic = await execute_specification(specification, cache)

    assert isinstance(diagnostic, StepRefusalDiagnostic)
    assert len(diagnostic.alternative_sources) == len(alternatives)
    assert PLACE_NAME_CAP == 5
    assert (
        "Alternative sources for t1: f1 (3 places); f2; f3 (survey); "
        "f4 (survey); f5 (survey); and 2 other sources."
    ) in diagnostic.format_for_retry()


@pytest.mark.asyncio
async def test_alternatives_are_traced_through_a_derived_table() -> None:
    # Test: Alternative sources of a step that reads a derived table.
    # Situation: `s1` divides `t1`, which offers `f2`, by `t2`, which offers
    #   `f3`; a ranking of `s1` then refuses because one of four requested
    #   places has a value.
    # Expectation: The diagnostic lists the alternatives of both fetched
    #   tables behind `s1`, `f2` and then `f3`, and the retry message names
    #   `s1` as the input.
    cache = _build_cache(
        _build_table(
            "t1",
            {"a": 10.0},
            variable_dcid="Count_Case",
            source=_WDI,
            requested=("a", "b", "c", "d"),
            alternatives=("f2",),
        ),
        _build_table(
            "t2",
            {"a": 1000.0},
            variable_dcid="Count_Person",
            source=_CENSUS,
            requested=("a", "b", "c", "d"),
            alternatives=("f3",),
        ),
    )
    specification = _build_specification(
        {
            "step_id": "s1",
            "script": "compute_derived_metric",
            "left": "t1",
            "right": "t2",
        },
        {"step_id": "s2", "script": "rank_cohort", "table": "s1"},
    )

    diagnostic = await execute_specification(specification, cache)

    assert isinstance(diagnostic, StepRefusalDiagnostic)
    assert diagnostic.step_id == "s2"
    assert diagnostic.input_table_ids == ("s1",)
    assert [item.facet_id for item in diagnostic.alternative_sources] == [
        "f2",
        "f3",
    ]
