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
"""Builds the default chart of an answer that holds no chart block.

`build_default_charts` projects one chart directly from the primary script
result of an `AnalysisDigest` when that result defines a chart slice without
inventing one (`analyze_timeseries`, `rank_cohort`, `compute_composition`, or
a cohort `relate_cohorts`), and resolves it through
`resolve_chart_specification` so that a default chart passes the same checks
as a chart the model writes.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypeIs

from narratives_agent.analytics.digest import (
    AnalysisDigest,
    ScriptResult,
)
from narratives_agent.analytics.metrics import (
    CompositionMetrics,
    RankingMetrics,
    RelationMetrics,
    ScriptMetrics,
    TimeseriesMetrics,
)
from narratives_agent.analytics.tables import clean_display_name
from narratives_agent.workflows.charts import (
    INVENTORY_PLACE_CAP,
    MIN_LINE_CHART_DATES,
    BarChartSpecification,
    ChartSpecification,
    ChildCohort,
    HighlightChartSpecification,
    LineChartSpecification,
    RankingChartSpecification,
    ResolvedChart,
    ScatterChartSpecification,
    TableSource,
    find_chart_entry,
    get_chart_cohort,
    resolve_chart_specification,
)
from narratives_agent.workflows.messages import PER_CAPITA_CHART_TITLE_TEMPLATE
from narratives_agent.workflows.specification import (
    AnalysisSpecification,
    SpecificationStep,
    list_reference_table_ids,
    list_step_inputs,
)
from narratives_agent.workflows.turn_cache import TurnCache

__all__ = ["build_default_charts"]

logger = logging.getLogger(__name__)

# Step input field on `compute_composition` that is not a charted component.
_AUXILIARY_STEP_INPUTS = frozenset({"total"})
# Maximum ranked places included in a default bar chart for non-cohort tables.
_DEFAULT_RANKED_PLACE_CAP = 10
# Fewest places a single-date default chart compares as a bar chart; a
# single place is shown as a highlight instead.
_MIN_BAR_CHART_PLACES = 2
# Number of input tables a scatter chart pairs.
_SCATTER_TABLE_COUNT = 2
# Date keyword that leaves a multi-vintage scatter unpinned to a single date.
_LATEST_DATE = "LATEST"
# Default chart priorities: `relate_cohorts` results are considered before
# every other result.
_RELATION_PRIORITY = 0
_DEFAULT_PRIORITY = 1


@dataclass(frozen=True)
class _FloorContext:
    """The turn state the default chart floor reads and resolves against.

    Attributes:
        cache: The turn cache holding fetched and derived tables.
        digest: The digest whose results the floor projects.
        analysis: The specification that produced the digest; None when
            the turn ran no specification.
    """

    cache: TurnCache
    digest: AnalysisDigest
    analysis: AnalysisSpecification | None

    def resolve(self, spec: ChartSpecification) -> ResolvedChart | None:
        """Resolves a specification the floor built, or returns None."""
        return resolve_chart_specification(
            spec, self.cache, self.digest, self.analysis
        )

    def has_shared_chart_cohort(self, table_ids: Sequence[str]) -> bool:
        """Returns whether every table in `table_ids` draws the same cohort.

        A per-capita table is drawn as its fetched numerator, so its cohort
        is read from the numerator, as the resolver reads it. A per-capita
        table can hold its population input's cohort when its numerator
        holds none.
        """
        if not table_ids:
            return False
        cohorts: list[ChildCohort | None] = []
        for table_id in table_ids:
            entry = find_chart_entry(table_id, self.analysis, self.cache)
            if entry is None:
                return False
            cohorts.append(get_chart_cohort(entry.table))
        first = cohorts[0]
        return first is not None and all(cohort == first for cohort in cohorts)


def _is_chartable_table_id(
    analysis: AnalysisSpecification, table_id: str, tables: TableSource
) -> bool:
    """Returns whether `table_id` names a non-empty chartable cached table.

    Both the cached table and the table the resolver draws (`find_chart_entry`)
    must hold rows, matching `_resolve_tables` in `workflows.charts`.
    """
    cached = tables.get(table_id)
    entry = find_chart_entry(table_id, analysis, tables)
    return (
        cached is not None
        and bool(cached.table.rows)
        and entry is not None
        and bool(entry.table.rows)
    )


def _collect_chart_table_ids(
    analysis: AnalysisSpecification,
    step: SpecificationStep,
    tables: TableSource,
) -> list[str]:
    """Returns the chartable table IDs a step's charted inputs read.

    Every input except an auxiliary `total` must resolve to non-empty fetched
    or per-capita cached tables; if any charted input cannot be charted,
    returns `[]` so a multi-input step is never partially charted.
    """
    collected: list[str] = []
    for input_name, reference in list_step_inputs(step):
        if input_name in _AUXILIARY_STEP_INPUTS:
            continue
        resolved = list_reference_table_ids(analysis, reference, step)
        if not resolved or not all(
            _is_chartable_table_id(analysis, table_id, tables)
            for table_id in resolved
        ):
            return []
        collected.extend(resolved)
    return list(dict.fromkeys(collected))


def _format_table_title(
    table_id: str,
    result: ScriptResult,
    context: _FloorContext,
) -> str | None:
    """Formats the display title of one charted table."""
    entry = find_chart_entry(table_id, context.analysis, context.cache)
    if entry is None:
        return None
    dcid = entry.table.variable_dcid
    cleaned_dcid = clean_display_name(dcid, "")
    if entry.table_id != table_id:
        variable_name = clean_display_name(
            entry.table.variable_name, cleaned_dcid
        )
        if not variable_name:
            return None
        return PER_CAPITA_CHART_TITLE_TEMPLATE.format(
            variable_name=variable_name
        )
    name = clean_display_name(result.variable_names.get(dcid, ""), "")
    return (
        name
        or clean_display_name(entry.table.variable_name, cleaned_dcid)
        or None
    )


def _build_default_title(
    result: ScriptResult,
    table_ids: Sequence[str],
    context: _FloorContext,
) -> str:
    """Builds the default chart title from the charted tables."""
    names = [
        title
        for table_id in table_ids
        if (title := _format_table_title(table_id, result, context)) is not None
    ]
    return ", ".join(dict.fromkeys(names))


def _build_ranking_specification(
    metrics: RankingMetrics,
    table_ids: Sequence[str],
    has_cohort: bool,
    title: str,
) -> RankingChartSpecification | BarChartSpecification | None:
    """Builds the chart of a `rank_cohort` result from its own slice and date.

    A cohort table is charted as a `ranking` at `metrics.reference_date`,
    pinned to `bottom_n` for an ascending ranking and to `top_n` when the
    result slices a larger cohort. Any other table is a `bar` of the places
    `metrics.top_n` lists first (up to `_DEFAULT_RANKED_PLACE_CAP`) at
    `metrics.reference_date`, passed directly so resolution does not scan
    earlier digest results.
    """
    if not metrics.top_n:
        return None
    # `rank_cohort` orders `top_n` from the leading end of `direction`, so
    # `top_n` lists the smallest values first when `direction == "asc"`.
    count = len(metrics.top_n)
    if has_cohort:
        if metrics.direction == "asc":
            return RankingChartSpecification(
                tables=tuple(table_ids),
                title=title,
                date=metrics.reference_date,
                bottom_n=count,
            )
        top_n = count if count < metrics.cohort_size else None
        return RankingChartSpecification(
            tables=tuple(table_ids),
            title=title,
            date=metrics.reference_date,
            top_n=top_n,
        )
    places = tuple(
        entry.place_dcid for entry in metrics.top_n[:_DEFAULT_RANKED_PLACE_CAP]
    )
    return BarChartSpecification(
        tables=tuple(table_ids),
        title=title,
        places=places,
        date=metrics.reference_date,
    )


def _build_series_specification(
    metrics: TimeseriesMetrics,
    table_ids: Sequence[str],
    has_cohort: bool,
    title: str,
) -> ChartSpecification | None:
    """Builds the chart of an `analyze_timeseries` result from its summaries.

    A result where at least one charted place spans two or more observations
    is a `line` over `metrics.series` (or over the cohort above
    `INVENTORY_PLACE_CAP`). When every charted place holds one observation,
    the chart is a `bar` (or `highlight` for one place) pinned to their shared
    date, or to `"LATEST"` when their single observations fall on different
    dates.
    """
    if not metrics.series:
        return None
    uses_cohort = has_cohort and len(metrics.series) > INVENTORY_PLACE_CAP
    charted = (
        metrics.series if uses_cohort else metrics.series[:INVENTORY_PLACE_CAP]
    )
    places = tuple(entry.place_dcid for entry in charted)
    if any(entry.point_count >= MIN_LINE_CHART_DATES for entry in charted):
        if uses_cohort:
            return LineChartSpecification(
                tables=tuple(table_ids), title=title, cohort=True
            )
        return LineChartSpecification(
            tables=tuple(table_ids), title=title, places=places
        )
    series_dates = {entry.end_date for entry in charted}
    date = next(iter(series_dates)) if len(series_dates) == 1 else _LATEST_DATE
    if uses_cohort:
        return BarChartSpecification(
            tables=tuple(table_ids), title=title, cohort=True, date=date
        )
    if len(places) >= _MIN_BAR_CHART_PLACES:
        return BarChartSpecification(
            tables=tuple(table_ids), title=title, places=places, date=date
        )
    return HighlightChartSpecification(
        tables=tuple(table_ids), title=title, places=(places[0],), date=date
    )


def _build_composition_specification(
    metrics: CompositionMetrics,
    table_ids: Sequence[str],
    has_cohort: bool,
    title: str,
) -> BarChartSpecification | None:
    """Builds the bar chart of a `compute_composition` result at its date."""
    if not metrics.places:
        return None
    charted = [entry.place_dcid for entry in metrics.places]
    if has_cohort and len(charted) > INVENTORY_PLACE_CAP:
        return BarChartSpecification(
            tables=tuple(table_ids),
            title=title,
            cohort=True,
            date=metrics.reference_date,
        )
    return BarChartSpecification(
        tables=tuple(table_ids),
        title=title,
        places=tuple(charted[:INVENTORY_PLACE_CAP]),
        date=metrics.reference_date,
    )


def _build_relation_specification(
    metrics: RelationMetrics,
    table_ids: Sequence[str],
    has_cohort: bool,
    title: str,
) -> ScatterChartSpecification | None:
    """Builds the cohort scatter chart of a `relate_cohorts` result.

    Requires two chartable tables drawn across the same cohort. When both
    variables were aligned on the same date, the scatter is pinned to that
    date; otherwise `"LATEST"` leaves the resolved date unset so the
    component plots each variable at its own latest date rather than pinning
    `target`'s date onto `by`.
    """
    if len(table_ids) != _SCATTER_TABLE_COUNT or not has_cohort:
        return None
    date = (
        metrics.target_reference_date
        if metrics.target_reference_date == metrics.by_reference_date
        else _LATEST_DATE
    )
    return ScatterChartSpecification(
        tables=tuple(table_ids),
        title=title,
        date=date,
    )


# Metrics types that directly define a default chart slice without invention.
type _ChartableMetrics = (
    TimeseriesMetrics | RankingMetrics | CompositionMetrics | RelationMetrics
)


def _is_chartable_metrics(
    metrics: ScriptMetrics | None,
) -> TypeIs[_ChartableMetrics]:
    """Returns whether a result's metrics project directly to a chart."""
    return isinstance(
        metrics,
        (
            TimeseriesMetrics,
            RankingMetrics,
            CompositionMetrics,
            RelationMetrics,
        ),
    )


def _build_default_specification(
    metrics: _ChartableMetrics,
    table_ids: Sequence[str],
    has_cohort: bool,
    title: str,
) -> ChartSpecification | None:
    """Projects a script result's metrics to its default chart specification."""
    match metrics:
        case TimeseriesMetrics():
            return _build_series_specification(
                metrics, table_ids, has_cohort, title
            )
        case RankingMetrics():
            return _build_ranking_specification(
                metrics, table_ids, has_cohort, title
            )
        case CompositionMetrics():
            return _build_composition_specification(
                metrics, table_ids, has_cohort, title
            )
        case RelationMetrics():
            return _build_relation_specification(
                metrics, table_ids, has_cohort, title
            )


def _rank_default_candidate(result: ScriptResult) -> int:
    """Returns a result's default chart priority; lower is considered first."""
    if isinstance(result.metrics, RelationMetrics):
        return _RELATION_PRIORITY
    return _DEFAULT_PRIORITY


def _order_default_candidates(
    results: Sequence[ScriptResult],
) -> list[ScriptResult]:
    """Orders `ok` results for the default chart floor, first to last.

    `relate_cohorts` results come first so a two-variable cohort relation
    charts as a scatter ahead of a single-table supporting step; `sorted` is
    stable, so the digest's order holds otherwise.
    """
    return sorted(results, key=_rank_default_candidate)


def _resolve_candidate_charts(
    candidate: ScriptResult, context: _FloorContext
) -> tuple[ResolvedChart, ...]:
    """Resolves the default chart of one result, or returns `()`."""
    if not _is_chartable_metrics(candidate.metrics):
        return ()
    analysis = context.analysis
    if analysis is None:
        return ()
    step = analysis.find_step(candidate.step_id)
    if step is None:
        return ()
    table_ids = _collect_chart_table_ids(analysis, step, context.cache)
    if not table_ids:
        return ()
    title = _build_default_title(candidate, table_ids, context)
    if not title:
        return ()
    spec = _build_default_specification(
        candidate.metrics,
        table_ids,
        context.has_shared_chart_cohort(table_ids),
        title,
    )
    if spec is None:
        return ()
    resolved = context.resolve(spec)
    return () if resolved is None else (resolved,)


def build_default_charts(
    digest: AnalysisDigest,
    analysis: AnalysisSpecification | None,
    cache: TurnCache,
) -> tuple[ResolvedChart, ...]:
    """Builds the fallback chart from the primary script result of a digest.

    The first `ok` result that yields a resolved chart supplies the floor,
    with `relate_cohorts` results considered before supporting single-table
    steps. Only results whose metrics directly define the chart
    (`analyze_timeseries`, `rank_cohort`, `compute_composition`, and cohort
    `relate_cohorts`) supply a default chart; distributions, standalone
    derivations, and non-cohort relations produce none.

    Args:
        digest: Analysis digest for the turn.
        analysis: Specification that produced the digest; None when the
            turn ran no specification, in which case no chart is built.
        cache: Turn cache holding fetched and derived tables.

    Returns:
        A single-element tuple holding the resolved chart, or `()` when no
        result yields a valid default chart.
    """
    context = _FloorContext(cache, digest, analysis)
    ok_results = [result for result in digest.results if result.status == "ok"]
    for candidate in _order_default_candidates(ok_results):
        charts = _resolve_candidate_charts(candidate, context)
        if charts:
            return charts
    logger.info("No default chart: no result yielded a valid default chart")
    return ()
