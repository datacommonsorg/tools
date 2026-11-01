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
"""Parses, resolves, and serializes the charts of a synthesis answer.

Parses a chart block into a `ChartSpecification` per chart kind, resolves it
against the `TurnCache` and the `AnalysisDigest` into a `ResolvedChart` per
chart kind, and serializes a resolved chart to its wire mapping
(`serialize_resolved_chart`).
"""

import logging
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import Annotated, ClassVar, Literal, Protocol, Self, TypedDict

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    model_validator,
)

from narratives_agent.analytics.alignment import find_unit_mismatch
from narratives_agent.analytics.digest import (
    AnalysisDigest,
    ScriptResult,
)
from narratives_agent.analytics.metrics import (
    CompositionMetrics,
    DistributionMetrics,
    RankingMetrics,
    RelationMetrics,
    TimeseriesMetrics,
)
from narratives_agent.analytics.ranking import rank_cohort
from narratives_agent.analytics.tables import (
    ObservationTable,
    clean_display_name,
)
from narratives_agent.json_value import JsonObject, JsonValue
from narratives_agent.workflows.specification import (
    TABLE_REFERENCE_PATTERN,
    AnalysisSpecification,
    ComputeDerivedMetricStep,
    list_step_table_ids,
)
from narratives_agent.workflows.turn_cache import (
    DERIVED_TABLE_PREFIX,
    FETCHED_TABLE_PREFIX,
    CachedTable,
    TurnCache,
)

__all__ = [
    "INVENTORY_PLACE_CAP",
    "MAX_CHARTS_PER_TURN",
    "MIN_LINE_CHART_DATES",
    "BarChartSpecification",
    "BarSort",
    "ChartKind",
    "ChartScope",
    "ChartSpecification",
    "ChildCohort",
    "HighlightChartSpecification",
    "LineChartSpecification",
    "MapChartSpecification",
    "PlaceList",
    "RankingChartSpecification",
    "RankingEnds",
    "RankingSlice",
    "ResolvedBarChart",
    "ResolvedChart",
    "ResolvedHighlightChart",
    "ResolvedLineChart",
    "ResolvedMapChart",
    "ResolvedRankingChart",
    "ResolvedScatterChart",
    "ScatterChartSpecification",
    "TableSource",
    "find_chart_entry",
    "get_chart_cohort",
    "parse_chart_specification",
    "resolve_chart_specification",
    "serialize_resolved_chart",
]

logger = logging.getLogger(__name__)

# Maximum places a line or bar chart draws from a place list, and the
# places the synthesis inventory names per table.
INVENTORY_PLACE_CAP = 25
# Maximum chart blocks emitted in a single turn.
MAX_CHARTS_PER_TURN = 3
# Variable DCID used by chart web components for per-capita normalization.
_POPULATION_VARIABLE_DCID = "Count_Person"
# Fewest distinct dates a line chart needs to draw a series.
MIN_LINE_CHART_DATES = 2

# Keywords that select the latest observation date in chart specifications.
_LATEST_DATE_KEYWORDS = frozenset({"HIGHEST", "LATEST"})

# Chart visualization types supported by synthesis.
type ChartKind = Literal[
    "line", "bar", "map", "ranking", "scatter", "highlight"
]


# A cached table id a chart block references (`t<n>` or `s<n>`). The
# transparent form keeps the values usable wherever a `str` is expected.
_TableReference = Annotated[str, Field(pattern=TABLE_REFERENCE_PATTERN)]
# A count of at least one, for the ranked slices `top_n` and `bottom_n`.
_PositiveCount = Annotated[int, Field(ge=1)]
# Bar order a chart block may request.
type BarSort = Literal["ascending", "descending"]
# The ends of a ranking a ranking chart lists.
type RankingEnds = Literal["top", "bottom", "both"]


class _ChartSpecificationBase(BaseModel):
    """The fields every chart block carries, whatever its kind.

    Every reference is resolved against the turn cache by
    `resolve_chart_specification`. A chart is normalized per capita by
    naming a per-capita derived table, which charts as its fetched
    numerator, so its ranked slices and dates are read from the per-capita
    table itself. The components' remaining presentation attributes (zoom,
    place labels) are not part of the grammar, and a field the block's
    kind does not take rejects the block.

    Attributes:
        has_shared_axis: Whether the kind's variables share a numeric axis,
            so that their tables must agree in unit and scaling factor.
        tables: The cached table ids the chart draws, at least one.
        title: The chart title, external text cleaned before display.
        unit: The display unit; None when the component shows the data's
            own unit.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    has_shared_axis: ClassVar[bool] = False

    tables: tuple[_TableReference, ...] = Field(min_length=1)
    title: str = Field(min_length=1)
    unit: str | None = None


class _SingleDateSpecification(_ChartSpecificationBase):
    """The optional `date` of a chart kind that draws one date.

    Attributes:
        date: The observation date to draw, or the keyword `LATEST` or
            `HIGHEST` (any case); None when the date defaults to the
            digest's reference date.
    """

    date: str | None = None


@dataclass(frozen=True)
class _NamedPlaces:
    """A line or bar block's explicit `places`, each once, in its order."""

    place_dcids: tuple[str, ...]


@dataclass(frozen=True)
class _WholeCohort:
    """A line or bar block that sets `cohort` to true."""


@dataclass(frozen=True)
class _RankedPlaces:
    """A line or bar block's `top_n` or `bottom_n` slice.

    Attributes:
        count: How many places the slice holds.
        is_highest: Whether the slice takes the highest values (`top_n`)
            rather than the lowest (`bottom_n`).
    """

    count: int
    is_highest: bool


@dataclass(frozen=True)
class _DefaultPlaces:
    """A line or bar block that picks no places."""


# How a line or bar block picks its places; exactly one variant per block.
type _PlaceChoice = _NamedPlaces | _WholeCohort | _RankedPlaces | _DefaultPlaces


class _PlaceChoiceSpecification(_ChartSpecificationBase):
    """The place choice of a line or bar chart: at most one way to pick.

    Attributes:
        places: The place DCIDs to draw; None when the places come from a
            slice, the tables' cohort, or the default.
        cohort: Whether the chart draws the tables' parent-place cohort.
        top_n: How many of the highest-valued places to draw; None when the
            chart is not sliced from the top.
        bottom_n: How many of the lowest-valued places to draw; None when
            the chart is not sliced from the bottom.
    """

    places: tuple[str, ...] | None = Field(default=None, min_length=1)
    cohort: bool = False
    top_n: _PositiveCount | None = None
    bottom_n: _PositiveCount | None = None

    def _list_place_choices(self) -> list[_PlaceChoice]:
        """Lists every way the block's fields pick its places."""
        choices: list[_PlaceChoice] = []
        if self.places is not None:
            choices.append(_NamedPlaces(tuple(dict.fromkeys(self.places))))
        if self.cohort:
            choices.append(_WholeCohort())
        if self.top_n is not None:
            choices.append(_RankedPlaces(self.top_n, is_highest=True))
        if self.bottom_n is not None:
            choices.append(_RankedPlaces(self.bottom_n, is_highest=False))
        return choices

    @model_validator(mode="after")
    def _check_single_place_choice(self) -> Self:
        """Rejects a block that picks its places in more than one way."""
        if len(self._list_place_choices()) > 1:
            raise ValueError(
                "choose at most one of places, cohort, top_n, and bottom_n"
            )
        return self

    def read_place_choice(self) -> _PlaceChoice:
        """Returns the one way the block picks its places.

        Returns:
            The named places, the whole cohort, the ranked slice, or the
            default when the block picks none.
        """
        choices = self._list_place_choices()
        return choices[0] if choices else _DefaultPlaces()


class LineChartSpecification(_PlaceChoiceSpecification):
    """A `line` chart block: a full series over time for places or a cohort.

    Takes no `date` field because a line chart draws the full time series.
    Without a place choice, the line draws every place with data, and
    rejects more than `INVENTORY_PLACE_CAP` places.

    Attributes:
        kind: Always `"line"`.
    """

    has_shared_axis: ClassVar[bool] = True

    kind: Literal["line"] = "line"


class BarChartSpecification(
    _PlaceChoiceSpecification, _SingleDateSpecification
):
    """A `bar` chart block: values compared across places or a cohort.

    Without a place choice, the bar draws the tables' cohort when they were
    fetched across one, and every place with data otherwise, and rejects
    more than `INVENTORY_PLACE_CAP` places.

    Attributes:
        kind: Always `"bar"`.
        sort: The bar order; None when the component's default applies.
    """

    has_shared_axis: ClassVar[bool] = True

    kind: Literal["bar"] = "bar"
    sort: BarSort | None = None


class RankingChartSpecification(_SingleDateSpecification):
    """A `ranking` chart block: the tables' cohort ordered by value.

    Attributes:
        kind: Always `"ranking"`.
        cohort: Always true: a ranking charts the tables' cohort, and a
            block may state so.
        top_n: How many of the highest-valued places to list; None when the
            top end is not listed on its own.
        bottom_n: How many of the lowest-valued places to list; None when
            the bottom end is not listed on its own. When both are set they
            are equal, because the chart lists one count at each end.
    """

    kind: Literal["ranking"] = "ranking"
    cohort: Literal[True] = True
    top_n: _PositiveCount | None = None
    bottom_n: _PositiveCount | None = None

    @model_validator(mode="after")
    def _check_equal_ends(self) -> Self:
        """Rejects a block that asks for different counts at each end."""
        if (
            self.top_n is not None
            and self.bottom_n is not None
            and self.top_n != self.bottom_n
        ):
            raise ValueError("top_n and bottom_n must be equal")
        return self


class MapChartSpecification(_SingleDateSpecification):
    """A `map` chart block: the tables' cohort shaded by value.

    Attributes:
        kind: Always `"map"`.
        cohort: Always true: a map charts the tables' cohort, and a
            block may state so.
    """

    kind: Literal["map"] = "map"
    cohort: Literal[True] = True


class ScatterChartSpecification(_SingleDateSpecification):
    """A `scatter` chart block: two variables plotted across a cohort.

    Attributes:
        kind: Always `"scatter"`.
        cohort: Always true: a scatter charts the tables' cohort, and a
            block may state so.
    """

    kind: Literal["scatter"] = "scatter"
    cohort: Literal[True] = True


class HighlightChartSpecification(_SingleDateSpecification):
    """A `highlight` chart block: one value for one place.

    Attributes:
        kind: Always `"highlight"`.
        places: The one place DCID to draw; None when the block names no
            place, in which case the tables must hold exactly one place
            with data.
    """

    kind: Literal["highlight"] = "highlight"
    places: tuple[str] | None = None


# One chart block as the model writes it, discriminated by `kind`. The
# transparent form lets `TypeAdapter` read the discriminator.
ChartSpecification = Annotated[
    LineChartSpecification
    | BarChartSpecification
    | RankingChartSpecification
    | MapChartSpecification
    | ScatterChartSpecification
    | HighlightChartSpecification,
    Field(discriminator="kind"),
]
# Validates chart block JSON into the specification of its kind.
_CHART_SPECIFICATION_ADAPTER: TypeAdapter[ChartSpecification] = TypeAdapter(
    ChartSpecification
)


def parse_chart_specification(text: str) -> ChartSpecification:
    """Parses the JSON body of a chart block into its kind's specification.

    Args:
        text: The JSON text between the chart fences, external model text.

    Returns:
        The specification of the block's `kind`.

    Raises:
        ValidationError: If the text is not JSON, names no known `kind`, or
            breaks that kind's grammar.
    """
    return _CHART_SPECIFICATION_ADAPTER.validate_json(text)


@dataclass(frozen=True)
class PlaceList:
    """The explicit places a line or bar chart draws.

    Attributes:
        place_dcids: The place DCIDs, at least one, in drawing order.
    """

    place_dcids: tuple[str, ...]

    def __post_init__(self) -> None:
        """Rejects an empty place list.

        Raises:
            ValueError: If `place_dcids` is empty.
        """
        if not self.place_dcids:
            raise ValueError("a place list names at least one place")


@dataclass(frozen=True)
class ChildCohort:
    """The child places of one parent place that a chart draws.

    Attributes:
        parent_place: The parent place DCID.
        child_place_type: The type of the child places drawn.
    """

    parent_place: str
    child_place_type: str

    def __post_init__(self) -> None:
        """Rejects an empty parent place or child place type.

        Raises:
            ValueError: If `parent_place` or `child_place_type` is empty.
        """
        if not self.parent_place or not self.child_place_type:
            raise ValueError(
                "a child cohort names a parent place and a child place type"
            )


# The places a line or bar chart draws.
type ChartScope = PlaceList | ChildCohort


@dataclass(frozen=True)
class RankingSlice:
    """The ends a ranking chart lists, and how many places at each.

    Attributes:
        count: How many places each listed end shows, at least one.
        ends: Which ends are listed.
    """

    count: int
    ends: RankingEnds

    def __post_init__(self) -> None:
        """Rejects a count below one.

        Raises:
            ValueError: If `count` is below 1.
        """
        if self.count < 1:
            raise ValueError("a ranking lists at least one place per end")


@dataclass(frozen=True, kw_only=True)
class _ResolvedChartBase:
    """The fields every resolved chart carries, whatever its kind.

    Each kind declares `variable_dcids`, the charted variables in order of
    first reference, with a tuple shape that fixes how many it draws: one
    for a map, a ranking, or a highlight, two for a scatter, and one or
    more for a line or a bar.

    Attributes:
        viz_type: The chart kind, fixed per class and serialized as the
            wire `viz_type`.
        title: The cleaned chart title.
        facet_ids: `(variable_dcid, facet_id)` pairs, one per charted
            variable whose every table names the same facet; empty when no
            variable qualifies.
        unit: The display unit; None when the component shows the data's
            own unit.
        per_capita: Whether the component normalizes values by population.
    """

    viz_type: ClassVar[ChartKind]

    title: str
    facet_ids: tuple[tuple[str, str], ...] = ()
    unit: str | None = None
    per_capita: bool = False

    def __post_init__(self) -> None:
        """Rejects a variable pinned to more than one facet.

        Raises:
            ValueError: If two `facet_ids` pairs name the same variable.
        """
        variables = [variable for variable, _ in self.facet_ids]
        if len(set(variables)) != len(variables):
            raise ValueError("a chart pins each variable to one facet")


@dataclass(frozen=True, kw_only=True)
class _SingleDateChartBase(_ResolvedChartBase):
    """The optional `date` of a resolved chart that draws one date.

    Attributes:
        date: The observation date drawn; None when the component draws the
            latest date.
    """

    date: str | None = None


@dataclass(frozen=True, kw_only=True)
class ResolvedLineChart(_ResolvedChartBase):
    """A resolved `line` chart.

    Attributes:
        variable_dcids: The charted variables.
        scope: The places or the cohort the line draws.
    """

    viz_type: ClassVar[ChartKind] = "line"

    variable_dcids: tuple[str, *tuple[str, ...]]
    scope: ChartScope


@dataclass(frozen=True, kw_only=True)
class ResolvedBarChart(_SingleDateChartBase):
    """A resolved `bar` chart.

    Attributes:
        variable_dcids: The charted variables.
        scope: The places or the cohort the bar draws.
        sort: The bar order; None when the component's default applies.
    """

    viz_type: ClassVar[ChartKind] = "bar"

    variable_dcids: tuple[str, *tuple[str, ...]]
    scope: ChartScope
    sort: BarSort | None = None


@dataclass(frozen=True, kw_only=True)
class ResolvedRankingChart(_SingleDateChartBase):
    """A resolved `ranking` chart.

    Attributes:
        variable_dcids: The charted variable.
        cohort: The cohort the ranking orders.
        ranking: The ends listed; None when the component's default applies.
    """

    viz_type: ClassVar[ChartKind] = "ranking"

    variable_dcids: tuple[str]
    cohort: ChildCohort
    ranking: RankingSlice | None = None


@dataclass(frozen=True, kw_only=True)
class ResolvedMapChart(_SingleDateChartBase):
    """A resolved `map` chart.

    Attributes:
        variable_dcids: The charted variable.
        cohort: The cohort the map shades.
    """

    viz_type: ClassVar[ChartKind] = "map"

    variable_dcids: tuple[str]
    cohort: ChildCohort


@dataclass(frozen=True, kw_only=True)
class ResolvedScatterChart(_SingleDateChartBase):
    """A resolved `scatter` chart.

    Attributes:
        variable_dcids: The charted variables.
        cohort: The cohort the scatter plots.
    """

    viz_type: ClassVar[ChartKind] = "scatter"

    variable_dcids: tuple[str, str]
    cohort: ChildCohort


@dataclass(frozen=True, kw_only=True)
class ResolvedHighlightChart(_SingleDateChartBase):
    """A resolved `highlight` chart.

    Attributes:
        variable_dcids: The charted variable.
        place_dcid: The one place whose value is shown.
    """

    viz_type: ClassVar[ChartKind] = "highlight"

    variable_dcids: tuple[str]
    place_dcid: str


# One resolved chart configuration, ready for wire serialization.
type ResolvedChart = (
    ResolvedLineChart
    | ResolvedBarChart
    | ResolvedRankingChart
    | ResolvedMapChart
    | ResolvedScatterChart
    | ResolvedHighlightChart
)


def _serialize_cohort(cohort: ChildCohort) -> dict[str, JsonValue]:
    """Returns the wire keys of a cohort."""
    return {
        "parent_place": cohort.parent_place,
        "child_place_type": cohort.child_place_type,
    }


def _serialize_scope(scope: ChartScope) -> dict[str, JsonValue]:
    """Returns the wire keys of a line or bar chart's places or cohort."""
    match scope:
        case PlaceList():
            return {"place_dcids": list(scope.place_dcids)}
        case ChildCohort():
            return _serialize_cohort(scope)


def _serialize_ranking(ranking: RankingSlice) -> dict[str, JsonValue]:
    """Returns the wire keys of the ends a ranking chart lists."""
    return {
        "ranking_count": ranking.count,
        "show_highest_lowest": ranking.ends == "both",
        "show_lowest": ranking.ends == "bottom",
    }


def _serialize_kind_fields(chart: ResolvedChart) -> dict[str, JsonValue]:
    """Returns the wire keys that depend on the chart's kind."""
    match chart:
        case ResolvedLineChart():
            return _serialize_scope(chart.scope)
        case ResolvedBarChart():
            sort: dict[str, JsonValue] = (
                {"sort": chart.sort} if chart.sort is not None else {}
            )
            return {**_serialize_scope(chart.scope), **sort}
        case ResolvedRankingChart():
            ranking = (
                _serialize_ranking(chart.ranking)
                if chart.ranking is not None
                else {}
            )
            return {**_serialize_cohort(chart.cohort), **ranking}
        case ResolvedMapChart() | ResolvedScatterChart():
            return _serialize_cohort(chart.cohort)
        case ResolvedHighlightChart():
            return {"place_dcids": [chart.place_dcid]}


def serialize_resolved_chart(chart: ResolvedChart) -> JsonObject:
    """Serializes a resolved chart to the wire `ChartItem` mapping.

    Args:
        chart: The resolved chart.

    Returns:
        The wire `ChartItem` mapping: `parent_place` and
        `child_place_type` for a cohort chart and `place_dcids` otherwise,
        `ranking_count`, `show_highest_lowest`, and `show_lowest` for a
        sliced ranking, `sort` for a sorted bar, and each other optional
        field present only when it is set.
    """
    wire: dict[str, JsonValue] = {
        "viz_type": chart.viz_type,
        "title": chart.title,
        "variable_dcids": list(chart.variable_dcids),
        **_serialize_kind_fields(chart),
    }
    if isinstance(chart, _SingleDateChartBase) and chart.date is not None:
        wire["date"] = chart.date
    if chart.facet_ids:
        wire["facet_ids"] = dict(chart.facet_ids)
    if chart.unit:
        wire["unit"] = chart.unit
    if chart.per_capita:
        wire["per_capita"] = True
    return wire


class TableSource(Protocol):
    """Looks up a cached table by id, as `TurnCache` and a mapping do."""

    def get(self, table_id: str, /) -> CachedTable | None:
        """Returns the cached table stored under `table_id`, or None."""
        ...


def _find_per_capita_numerator(
    step: ComputeDerivedMetricStep, tables: TableSource
) -> CachedTable | None:
    """Returns the fetched count a per-capita step divided by population.

    The chart components normalize a variable by `Count_Person` natively, so
    a per-capita table whose numerator and population denominator are fetched
    tables renders as the numerator with `perCapita` set. Other derived
    tables have no series the components could fetch.
    """
    if step.operation != "per_capita":
        return None
    if not (
        step.left.startswith(FETCHED_TABLE_PREFIX)
        and step.right.startswith(FETCHED_TABLE_PREFIX)
    ):
        return None
    denominator = tables.get(step.right)
    if (
        denominator is None
        or denominator.table.variable_dcid != _POPULATION_VARIABLE_DCID
    ):
        return None
    return tables.get(step.left)


def find_chart_entry(
    table_id: str,
    analysis: AnalysisSpecification | None,
    tables: TableSource,
) -> CachedTable | None:
    """Returns the cached table a chart naming `table_id` draws.

    A fetched table is drawn as it is, and a per-capita table as its fetched
    numerator (`_find_per_capita_numerator`), so its variable, unit, facet,
    and cohort come from the numerator while its places, dates, and slices
    come from the per-capita table.

    Args:
        table_id: The cached table id a chart names.
        analysis: The specification whose steps derived the `s<n>` tables;
            None when the turn ran no specification.
        tables: The cached tables to look the table and its inputs up in.

    Returns:
        The cached table the chart draws, or None when `table_id` names no
        cached table or a derived table that cannot be charted.
    """
    entry = tables.get(table_id)
    if entry is None:
        return None
    if not table_id.startswith(DERIVED_TABLE_PREFIX):
        return entry
    step = analysis.find_step(table_id) if analysis is not None else None
    if not isinstance(step, ComputeDerivedMetricStep):
        return None
    return _find_per_capita_numerator(step, tables)


def get_chart_cohort(table: ObservationTable) -> ChildCohort | None:
    """Returns the cohort a table was fetched across, if it was.

    Args:
        table: The observation table.

    Returns:
        The table's parent place and child place type, or None when it was
        not fetched across a cohort.
    """
    if table.parent_place_dcid and table.child_place_type:
        return ChildCohort(table.parent_place_dcid, table.child_place_type)
    return None


class _ChartRejectedError(Exception):
    """Raised inside resolution when a specification fails a check."""


@dataclass(frozen=True)
class _ResolvedTable:
    """A cached table a chart block names, with the table its results describe.

    `chart_entry` is the fetched cached table the chart renders.
    `analysis_entry` is the cached table the digest and inventory describe:
    the same table, or the per-capita derived table that `chart_entry`
    stands in for.
    """

    chart_entry: CachedTable
    analysis_entry: CachedTable

    @property
    def chart_table(self) -> ObservationTable:
        """The `ObservationTable` the chart renders."""
        return self.chart_entry.table

    @property
    def analysis_table(self) -> ObservationTable:
        """The `ObservationTable` the digest and inventory describe."""
        return self.analysis_entry.table


@dataclass(frozen=True)
class _ChartContext:
    """The turn state a chart block is resolved against.

    Attributes:
        cache: The turn cache holding fetched and derived tables.
        digest: The digest providing reference dates and ranked slices.
        analysis: The specification that produced the digest; None when
            the turn ran no specification.
        result_tables: Maps the step id of each successful result to the
            cached table ids its step read; empty without a specification.
    """

    cache: TurnCache
    digest: AnalysisDigest
    analysis: AnalysisSpecification | None
    result_tables: Mapping[str, frozenset[str]]


def _build_chart_context(
    cache: TurnCache,
    digest: AnalysisDigest,
    analysis: AnalysisSpecification | None,
) -> _ChartContext:
    """Collects the turn state and binds each result to the tables it read.

    A result is bound to a table through its specification step, not
    through its variable, so that a result over another table of the same
    variable (another cohort, or a subset of the places) is never read for
    the charted one.
    """
    result_tables: dict[str, frozenset[str]] = {}
    if analysis is not None:
        for result in digest.results:
            step = analysis.find_step(result.step_id)
            if result.status == "ok" and step is not None:
                result_tables[result.step_id] = frozenset(
                    list_step_table_ids(analysis, step)
                )
    return _ChartContext(cache, digest, analysis, result_tables)


def _list_bound_results(
    table_id: str, context: _ChartContext
) -> list[ScriptResult]:
    """Returns the successful results computed over a cached table."""
    return [
        result
        for result in context.digest.results
        if table_id in context.result_tables.get(result.step_id, frozenset())
    ]


def _resolve_tables(
    spec: ChartSpecification, context: _ChartContext
) -> tuple[list[_ResolvedTable], bool]:
    """Resolves the table ids of a specification to cached tables.

    Returns:
        The resolved tables in order of first reference and whether the
        chart is normalized per capita.

    Raises:
        _ChartRejectedError: If an id names no cached table with rows, names a
            derived table that cannot be charted, or mixes per-capita and
            raw tables, including a per-capita table with its own numerator.
    """
    resolved: list[_ResolvedTable] = []
    mapped = 0
    raw = 0
    for table_id in dict.fromkeys(spec.tables):
        analysis_entry = context.cache.get(table_id)
        if analysis_entry is None or not analysis_entry.table.rows:
            raise _ChartRejectedError(
                f"{table_id} is not a cached table with rows"
            )
        chart_entry = find_chart_entry(
            table_id, context.analysis, context.cache
        )
        if chart_entry is None or not chart_entry.table.rows:
            raise _ChartRejectedError(
                f"{table_id} is derived and not chartable"
            )
        if chart_entry.table_id == table_id:
            raw += 1
        else:
            mapped += 1
        resolved.append(_ResolvedTable(chart_entry, analysis_entry))
    if mapped and raw:
        raise _ChartRejectedError(
            "per-capita and raw tables cannot share a chart"
        )
    return resolved, mapped > 0


def _check_shared_axis(
    spec: ChartSpecification, tables: Sequence[ObservationTable]
) -> None:
    """Checks that charted tables that share an axis agree in unit.

    The tables of one variable always share its axis. The tables of
    different variables share one only when the kind draws them on one.

    Raises:
        _ChartRejectedError: If tables that share an axis differ in unit or
            scaling factor.
    """
    by_variable: dict[str, list[ObservationTable]] = {}
    for table in tables:
        by_variable.setdefault(table.variable_dcid, []).append(table)
    groups = [tables] if spec.has_shared_axis else list(by_variable.values())
    for group in groups:
        mismatch = find_unit_mismatch(*group) if len(group) > 1 else None
        if mismatch is not None:
            raise _ChartRejectedError(mismatch.message)


def _get_result_reference_date(
    result: ScriptResult, variable_dcid: str
) -> str | None:
    """Returns the date a result's figures for a variable are aligned to.

    A relation aligns each of its variables on its own date, so its date is
    read per variable from the metrics rather than from one coverage date.
    """
    metrics = result.metrics
    if isinstance(metrics, RelationMetrics):
        if variable_dcid == metrics.target_variable_dcid:
            return metrics.target_reference_date
        if variable_dcid == metrics.by_variable_dcid:
            return metrics.by_reference_date
        return None
    if result.coverage is not None and result.coverage.reference_date:
        return result.coverage.reference_date
    if isinstance(
        metrics, (RankingMetrics, DistributionMetrics, CompositionMetrics)
    ):
        return metrics.reference_date
    if (
        isinstance(metrics, TimeseriesMetrics)
        and metrics.cross_place_comparison is not None
    ):
        return metrics.cross_place_comparison.reference_date
    return None


def _find_reference_date(
    entry: CachedTable, context: _ChartContext
) -> str | None:
    """Returns the aligned date of the first result over a table, if any."""
    variable_dcid = entry.table.variable_dcid
    for result in _list_bound_results(entry.table_id, context):
        if variable_dcid in result.variables:
            reference = _get_result_reference_date(result, variable_dcid)
            if reference is not None:
                return reference
    return None


def _extract_ranked_places(
    result: ScriptResult, variable_dcid: str, is_highest: bool
) -> list[str] | None:
    """Returns the places a result ranks by a variable at one end, if any.

    A ranking of the variable supplies its leading or trailing tail. A
    relation ranks only its `by` variable, so its highest or lowest group is
    a ranked tail of that variable and of no other.
    """
    metrics = result.metrics
    # The returned order is the source module's and is not re-sorted:
    # `rank_cohort` orders `top_n` from the leading end of `direction` and
    # `bottom_n` from the opposite end (`bottom_n` runs from the smallest
    # value up when `direction == "desc"`), and `relate_cohorts` orders
    # `highest_by` descending and `lowest_by` ascending by the `by` variable.
    if isinstance(metrics, RankingMetrics) and result.variables == (
        variable_dcid,
    ):
        is_descending = metrics.direction == "desc"
        ranked = (
            metrics.top_n if is_highest == is_descending else metrics.bottom_n
        )
        return [entry.place_dcid for entry in ranked]
    if (
        isinstance(metrics, RelationMetrics)
        and metrics.by_variable_dcid == variable_dcid
    ):
        group = metrics.highest_by if is_highest else metrics.lowest_by
        return [entry.place_dcid for entry in group]
    return None


def _find_digest_slice(
    entry: CachedTable,
    context: _ChartContext,
    count: int,
    is_highest: bool,
    date: str | None,
) -> tuple[list[str], str | None] | None:
    """Returns a top or bottom slice of a table that the digest ranks.

    The slice is read from a result computed over this table that ranks
    its variable with enough entries at `date`, so that the chart shows
    the places the prose ranks, at the date they were ranked. A ranking
    of the variable takes precedence over a relation's group, because the
    group holds only the places the relation's other variable also covers.

    Args:
        entry: The cached table the slice is taken from.
        context: The turn state the chart is resolved against.
        count: How many places the slice holds.
        is_highest: Whether the slice takes the highest values.
        date: The date the chart is drawn at; None when any ranking's date
            may be drawn.

    Returns:
        The slice's places and the date its ranking was aligned to, or
        None when no result ranks the table at `date`.
    """
    variable_dcid = entry.table.variable_dcid
    ordered = sorted(
        _list_bound_results(entry.table_id, context),
        key=lambda result: not isinstance(result.metrics, RankingMetrics),
    )
    for result in ordered:
        places = _extract_ranked_places(result, variable_dcid, is_highest)
        if places is None or len(places) < count:
            continue
        ranked_at = _get_result_reference_date(result, variable_dcid)
        if date is None or ranked_at == date:
            return places[:count], ranked_at
    return None


def _select_ranked_slice(
    entry: CachedTable,
    context: _ChartContext,
    slice_choice: _RankedPlaces,
    date: str | None,
    *,
    use_latest: bool = False,
) -> tuple[list[str], str | None]:
    """Returns a top or bottom slice of a cached table and its ranked date.

    The slice is read from the digest when a result ranks the table at the
    target date (`_find_digest_slice`), and is otherwise computed by ranking
    the table again. When `use_latest` is true, the target date is the latest
    date `rank_cohort` selects rather than an earlier digest date.

    Args:
        entry: The cached table the slice is taken from.
        context: The turn state the chart is resolved against.
        slice_choice: How many places the slice holds, and from which end.
        date: Explicit date to rank at; None when no literal date was given.
        use_latest: Whether a latest-date keyword requires ranking at the
            table's latest covered date instead of any digest date.

    Returns:
        The slice's places and the date they were ranked at; no places and
        None when the table cannot be ranked at the target date.
    """
    count, is_highest = slice_choice.count, slice_choice.is_highest
    if not use_latest:
        found = _find_digest_slice(entry, context, count, is_highest, date)
        if found is not None:
            return found
    # `rank_cohort` orders `top_n` from the leading end of `direction`, so
    # an ascending ranking's `top_n` starts at the smallest value.
    ranked = rank_cohort(
        entry.table,
        max_entries_per_end=count,
        direction="desc" if is_highest else "asc",
        target_date=None if use_latest else date,
    ).metrics
    if not isinstance(ranked, RankingMetrics):
        return [], None
    if use_latest:
        found = _find_digest_slice(
            entry, context, count, is_highest, ranked.reference_date
        )
        if found is not None:
            return found
    return [item.place_dcid for item in ranked.top_n], ranked.reference_date


def _resolve_cohort(
    kind: ChartKind, tables: Sequence[_ResolvedTable]
) -> ChildCohort:
    """Returns the one cohort every table of a cohort chart shares.

    Raises:
        _ChartRejectedError: If the primary table has no cohort, or the
            tables are not one cohort.
    """
    cohort = get_chart_cohort(tables[0].chart_table)
    if cohort is None:
        raise _ChartRejectedError(f"a {kind} chart needs a cohort")
    for item in tables:
        if get_chart_cohort(item.chart_table) != cohort:
            raise _ChartRejectedError("the tables are not one cohort")
    return cohort


def _list_available_places(tables: Sequence[_ResolvedTable]) -> list[str]:
    """Returns every place with data in the charted tables, sorted."""
    return sorted(
        {
            place
            for item in tables
            for place in item.analysis_table.places_with_data
        }
    )


def _check_known_places(
    places: Sequence[str], available: AbstractSet[str]
) -> None:
    """Checks that every named place has data in the charted tables.

    Raises:
        _ChartRejectedError: If a place has no data in the tables.
    """
    unknown = [place for place in places if place not in available]
    if unknown:
        raise _ChartRejectedError(
            f"named places not in the tables: {len(unknown)}"
        )


def _build_place_list(kind: ChartKind, places: Sequence[str]) -> PlaceList:
    """Builds the place list of a line or bar chart within the place cap.

    Raises:
        _ChartRejectedError: If the list is empty or longer than
            `INVENTORY_PLACE_CAP`.
    """
    if not 1 <= len(places) <= INVENTORY_PLACE_CAP:
        raise _ChartRejectedError(
            f"a {kind} chart shows between 1 and {INVENTORY_PLACE_CAP} "
            f"places, not {len(places)}"
        )
    return PlaceList(tuple(places))


def _list_shared_dates(tables: Sequence[_ResolvedTable]) -> set[str]:
    """Returns the observation dates every charted table holds."""
    return set.intersection(
        *({row.date for row in item.analysis_table.rows} for item in tables)
    )


def _has_line_series(
    table: ObservationTable, places: AbstractSet[str] | None
) -> bool:
    """Returns whether at least one charted place spans two or more dates."""
    dates_by_place: dict[str, set[str]] = {}
    for row in table.rows:
        if places is None or row.place_dcid in places:
            dates_by_place.setdefault(row.place_dcid, set()).add(row.date)
    return any(
        len(dates) >= MIN_LINE_CHART_DATES for dates in dates_by_place.values()
    )


def _check_line_dates(
    tables: Sequence[_ResolvedTable], scope: ChartScope
) -> None:
    """Checks that each table of a line chart has a multi-date series.

    Raises:
        _ChartRejectedError: If a charted table has no place within `scope`
            with at least `MIN_LINE_CHART_DATES` dates.
    """
    places = set(scope.place_dcids) if isinstance(scope, PlaceList) else None
    if any(
        not _has_line_series(item.analysis_table, places) for item in tables
    ):
        raise _ChartRejectedError(
            "each table of a line chart needs a place with at least "
            f"{MIN_LINE_CHART_DATES} dates"
        )


def _resolve_places_date(
    places: AbstractSet[str],
    tables: Sequence[_ResolvedTable],
    date: str | None,
    *,
    has_explicit_date: bool,
) -> str | None:
    """Checks that at least one charted place holds a value at `date`.

    An explicit date with no value for any named place rejects the chart; a
    default reference date with no value for any named place is dropped so
    the component shows the places' latest observations instead of an empty
    chart.
    """
    if date is None or any(
        row.place_dcid in places and row.date == date
        for item in tables
        for row in item.analysis_table.rows
    ):
        return date
    if has_explicit_date:
        raise _ChartRejectedError("no named place has a value at the date")
    return None


def _has_place_value(
    table: ObservationTable, places: AbstractSet[str], date: str | None
) -> bool:
    """Returns whether a named place holds a value at `date`, or at all."""
    return any(
        row.place_dcid in places and (date is None or row.date == date)
        for row in table.rows
    )


def _resolve_bar_places_date(
    places: AbstractSet[str],
    tables: Sequence[_ResolvedTable],
    date: str | None,
    *,
    has_explicit_date: bool,
) -> str | None:
    """Checks that each table of a named-place bar chart holds a value.

    A bar chart draws a series per table, so a table without a value for any
    named place would draw an empty series, which `_check_line_dates` also
    rejects for a line. Every table must hold a value for a named place at
    `date`: an explicit date that a table lacks rejects the chart, and a
    default reference date that a table lacks is dropped so the component
    shows the places' latest observations. Every table must then hold a
    value for a named place at some date.

    Raises:
        _ChartRejectedError: If a table has no value for a named place at
            an explicit date, or at any date.
    """
    if date is not None and not all(
        _has_place_value(item.analysis_table, places, date) for item in tables
    ):
        if has_explicit_date:
            raise _ChartRejectedError(
                "a charted table has no value for a named place at the date"
            )
        date = None
    if not all(
        _has_place_value(item.analysis_table, places, None) for item in tables
    ):
        raise _ChartRejectedError(
            "each table of a bar chart needs a value for a named place"
        )
    return date


def _resolve_bar_slice(
    spec: BarChartSpecification,
    tables: Sequence[_ResolvedTable],
    context: _ChartContext,
    slice_choice: _RankedPlaces,
    date: str | None,
    shared_dates: AbstractSet[str],
) -> tuple[PlaceList, str | None]:
    """Resolves a bar chart's `top_n` or `bottom_n` slice and drawn date.

    A sliced bar chart is drawn at the date its slice was ranked at: the
    block's literal date when it names one, the table's latest covered date
    when `date` names a latest keyword, or else the date of the digest's
    ranking or of the table ranked again. That date must be one of
    `shared_dates`, the dates every charted table holds.

    Raises:
        _ChartRejectedError: If the slice selects no place or more than
            `INVENTORY_PLACE_CAP`, or was ranked at a date that not every
            charted table holds.
    """
    use_latest = (
        spec.date is not None and spec.date.upper() in _LATEST_DATE_KEYWORDS
    )
    requested = date if spec.date is not None and not use_latest else None
    places, ranked_at = _select_ranked_slice(
        tables[0].analysis_entry,
        context,
        slice_choice,
        requested,
        use_latest=use_latest,
    )
    if not places:
        raise _ChartRejectedError("the ranked slice selected no place")
    scope = _build_place_list(spec.kind, places)
    if ranked_at not in shared_dates:
        raise _ChartRejectedError(
            "the ranked slice's date is not in every table"
        )
    return scope, ranked_at


def _require_one_variable(
    kind: ChartKind, variable_dcids: Sequence[str]
) -> tuple[str]:
    """Returns the one variable of a single-variable chart.

    Raises:
        _ChartRejectedError: If the tables hold another number of variables.
    """
    match tuple(variable_dcids):
        case (only,):
            return (only,)
        case _:
            raise _ChartRejectedError(
                f"a {kind} chart shows one variable, not {len(variable_dcids)}"
            )


def _require_two_variables(
    kind: ChartKind, variable_dcids: Sequence[str]
) -> tuple[str, str]:
    """Returns the two variables of a scatter chart.

    Raises:
        _ChartRejectedError: If the tables hold another number of variables.
    """
    match tuple(variable_dcids):
        case (first, second):
            return (first, second)
        case _:
            raise _ChartRejectedError(
                f"a {kind} chart shows two variables, not {len(variable_dcids)}"
            )


def _require_variables(
    variable_dcids: Sequence[str],
) -> tuple[str, *tuple[str, ...]]:
    """Returns the variables of a line or bar chart, at least one.

    Raises:
        _ChartRejectedError: If the tables hold no variable.
    """
    match tuple(variable_dcids):
        case (first, *rest):
            return (first, *rest)
        case _:
            raise _ChartRejectedError("a chart shows at least one variable")


def _resolve_line_scope(
    spec: LineChartSpecification,
    tables: Sequence[_ResolvedTable],
    context: _ChartContext,
) -> ChartScope:
    """Resolves the places or cohort of a line chart and checks its series.

    Named places must have data in at least one charted table: the places
    are the union of the tables', so that a line of two tables of one
    variable (such as one country per table) can draw them all, and a
    variable a table does not cover is drawn without a value for the place.
    A slice is taken from a ranking at any date, and without a place choice
    the line draws every place with data up to `INVENTORY_PLACE_CAP`.

    Raises:
        _ChartRejectedError: If a named place has no data, a slice selects
            no place, a cohort is requested and the tables are not one
            cohort, the place count is outside 1 to `INVENTORY_PLACE_CAP`,
            or any table lacks a charted place with at least two dates.
    """
    available = _list_available_places(tables)
    match spec.read_place_choice():
        case _NamedPlaces(place_dcids=places):
            _check_known_places(places, set(available))
            scope: ChartScope = _build_place_list(spec.kind, places)
        case _WholeCohort():
            scope = _resolve_cohort(spec.kind, tables)
        case _RankedPlaces() as slice_choice:
            ranked_places, _ = _select_ranked_slice(
                tables[0].analysis_entry, context, slice_choice, None
            )
            if not ranked_places:
                raise _ChartRejectedError("the ranked slice selected no place")
            scope = _build_place_list(spec.kind, ranked_places)
        case _DefaultPlaces():
            scope = _build_place_list(spec.kind, available)
    _check_line_dates(tables, scope)
    return scope


def _resolve_bar_scope(
    spec: BarChartSpecification,
    tables: Sequence[_ResolvedTable],
    context: _ChartContext,
    date: str | None,
    shared_dates: AbstractSet[str],
) -> tuple[ChartScope, str | None]:
    """Resolves the places or cohort a bar chart draws, and its date.

    Named places must have data in at least one charted table, and every
    charted table must hold a value for a named place, at `date` when it is
    set (`_resolve_bar_places_date`). A slice is ranked from the digest or
    the primary table and drawn at the date it was ranked at, which must be
    one of `shared_dates`. Without a place choice, the bar draws the tables'
    cohort when they were fetched across one, and otherwise every place with
    data.

    Returns:
        The places or the cohort, and the chart's date.

    Raises:
        _ChartRejectedError: If a named place has no data, a table has no
            value for a named place (at an explicit date, or at any date),
            a slice selects no place or was ranked at a date not every
            table holds, a cohort is required and the tables are not one
            cohort, or the place count is outside 1 to
            `INVENTORY_PLACE_CAP`.
    """
    available = _list_available_places(tables)
    match spec.read_place_choice():
        case _NamedPlaces(place_dcids=places):
            _check_known_places(places, set(available))
            resolved_date = _resolve_bar_places_date(
                set(places),
                tables,
                date,
                has_explicit_date=spec.date is not None,
            )
            return _build_place_list(spec.kind, places), resolved_date
        case _WholeCohort():
            return _resolve_cohort(spec.kind, tables), date
        case _RankedPlaces() as slice_choice:
            return _resolve_bar_slice(
                spec, tables, context, slice_choice, date, shared_dates
            )
        case _DefaultPlaces():
            if get_chart_cohort(tables[0].chart_table) is not None:
                return _resolve_cohort(spec.kind, tables), date
            return _build_place_list(spec.kind, available), date


def _resolve_highlight(
    spec: HighlightChartSpecification,
    tables: Sequence[_ResolvedTable],
    date: str | None,
) -> tuple[str, str | None]:
    """Resolves the one place a highlight chart shows, and its date.

    The place must hold a value at the date the chart is drawn at. A date
    the block names is rejected when the place has no value at it; the
    default reference date is dropped instead, so that the chart shows the
    place's latest value.

    Args:
        spec: The highlight specification.
        tables: The charted tables.
        date: The date `_resolve_date` resolved; None for the latest.

    Returns:
        The place, and the date the chart is drawn at.

    Raises:
        _ChartRejectedError: If the named place has no data, no place is
            named and the tables do not hold exactly one place with data,
            or the place has no value at the date the block names.
    """
    available = _list_available_places(tables)
    if spec.places is not None:
        _check_known_places(spec.places, set(available))
        place = spec.places[0]
    elif len(available) == 1:
        place = available[0]
    else:
        raise _ChartRejectedError(
            f"a highlight chart shows one place, not {len(available)}"
        )
    resolved_date = _resolve_places_date(
        {place},
        tables,
        date,
        has_explicit_date=spec.date is not None,
    )
    return place, resolved_date


def _build_ranking_slice(
    spec: RankingChartSpecification,
) -> RankingSlice | None:
    """Returns the ends a ranking block lists; None when it names none."""
    if spec.top_n is not None and spec.bottom_n is not None:
        return RankingSlice(spec.top_n, "both")
    if spec.top_n is not None:
        return RankingSlice(spec.top_n, "top")
    if spec.bottom_n is not None:
        return RankingSlice(spec.bottom_n, "bottom")
    return None


def _resolve_date(
    spec: _SingleDateSpecification,
    tables: Sequence[_ResolvedTable],
    context: _ChartContext,
    shared_dates: AbstractSet[str],
) -> str | None:
    """Resolves the observation date a single-date chart is drawn at.

    A date is drawn only when every charted table has it (`shared_dates`),
    so that no table is empty at the drawn date and no two precisions
    (`2023` and `2023-06`) are mixed at it. Without an explicit date, the
    chart defaults to the aligned reference date of the first result over
    the primary table when every table has that date, and otherwise to None,
    which the web components read as the latest date. A ranked bar slice
    replaces this default with the date it was ranked at
    (`_resolve_bar_slice`).

    Raises:
        _ChartRejectedError: If an explicit literal date is not in every
            charted table.
    """
    if spec.date is not None:
        if spec.date.upper() in _LATEST_DATE_KEYWORDS:
            return None
        if spec.date not in shared_dates:
            raise _ChartRejectedError("the date is not in every table")
        return spec.date
    reference = _find_reference_date(tables[0].analysis_entry, context)
    return reference if reference in shared_dates else None


def _collect_facet_ids(
    tables: Sequence[ObservationTable],
) -> tuple[tuple[str, str], ...]:
    """Pairs each charted variable with the facet ID that served its tables.

    A variable is pinned only when every table of it names the same facet.
    When its tables name different facets, or one names none, no single
    facet served every place, so the variable is left unpinned rather than
    drawn for some places from a facet that did not serve them.
    """
    served: dict[str, set[str | None]] = {}
    for table in tables:
        served.setdefault(table.variable_dcid, set()).add(
            table.facet_id or None
        )
    pinned: list[tuple[str, str]] = []
    for variable_dcid, facet_ids in served.items():
        match tuple(facet_ids):
            case (str() as facet_id,):
                pinned.append((variable_dcid, facet_id))
    return tuple(pinned)


class _SharedChartFields(TypedDict):
    """The resolved fields every chart kind shares, as constructor keywords."""

    title: str
    facet_ids: tuple[tuple[str, str], ...]
    unit: str | None
    per_capita: bool


def _resolve_basics(
    spec: ChartSpecification,
    tables: Sequence[_ResolvedTable],
    per_capita: bool,
) -> _SharedChartFields:
    """Resolves the title, facets, unit, and per-capita flag of a chart.

    Raises:
        _ChartRejectedError: If the title is empty once cleaned, or the
            tables that share an axis differ in unit or scaling factor.
    """
    title = clean_display_name(spec.title, "")
    if not title:
        raise _ChartRejectedError("the title is empty")
    chart_tables = [item.chart_table for item in tables]
    _check_shared_axis(spec, chart_tables)
    unit = clean_display_name(spec.unit, "") if spec.unit else ""
    return _SharedChartFields(
        title=title,
        facet_ids=_collect_facet_ids(chart_tables),
        unit=unit or None,
        per_capita=per_capita,
    )


def _resolve(spec: ChartSpecification, context: _ChartContext) -> ResolvedChart:
    """Resolves a specification, or raises `_ChartRejectedError`."""
    tables, per_capita = _resolve_tables(spec, context)
    variables = tuple(
        dict.fromkeys(item.chart_table.variable_dcid for item in tables)
    )
    kind = spec.kind
    shared = _resolve_basics(spec, tables, per_capita)
    if isinstance(spec, LineChartSpecification):
        return ResolvedLineChart(
            **shared,
            variable_dcids=_require_variables(variables),
            scope=_resolve_line_scope(spec, tables, context),
        )
    shared_dates = _list_shared_dates(tables)
    date = _resolve_date(spec, tables, context, shared_dates)
    match spec:
        case BarChartSpecification():
            scope, bar_date = _resolve_bar_scope(
                spec, tables, context, date, shared_dates
            )
            return ResolvedBarChart(
                **shared,
                date=bar_date,
                variable_dcids=_require_variables(variables),
                scope=scope,
                sort=spec.sort,
            )
        case RankingChartSpecification():
            return ResolvedRankingChart(
                **shared,
                date=date,
                variable_dcids=_require_one_variable(kind, variables),
                cohort=_resolve_cohort(kind, tables),
                ranking=_build_ranking_slice(spec),
            )
        case MapChartSpecification():
            return ResolvedMapChart(
                **shared,
                date=date,
                variable_dcids=_require_one_variable(kind, variables),
                cohort=_resolve_cohort(kind, tables),
            )
        case ScatterChartSpecification():
            return ResolvedScatterChart(
                **shared,
                date=date,
                variable_dcids=_require_two_variables(kind, variables),
                cohort=_resolve_cohort(kind, tables),
            )
        case HighlightChartSpecification():
            place, highlight_date = _resolve_highlight(spec, tables, date)
            return ResolvedHighlightChart(
                **shared,
                date=highlight_date,
                variable_dcids=_require_one_variable(kind, variables),
                place_dcid=place,
            )


def _resolve_or_reject(
    spec: ChartSpecification, context: _ChartContext
) -> ResolvedChart | None:
    """Resolves a specification, or logs the reason and returns None."""
    try:
        return _resolve(spec, context)
    except _ChartRejectedError as rejection:
        logger.info("Chart block rejected: %s", rejection)
        return None


def resolve_chart_specification(
    spec: ChartSpecification,
    cache: TurnCache,
    digest: AnalysisDigest,
    analysis: AnalysisSpecification | None,
) -> ResolvedChart | None:
    """Resolves a chart specification against the turn cache.

    Args:
        spec: Parsed chart specification from a synthesis block.
        cache: Turn cache holding fetched and derived tables.
        digest: Analysis digest providing reference dates and ranked slices.
        analysis: Specification that produced the digest; None when the
            turn ran no specification, in which case no digest result
            supplies a date or a slice.

    Returns:
        The resolved chart of the specification's kind, or None if a check
        fails; the reason is logged.
    """
    return _resolve_or_reject(
        spec, _build_chart_context(cache, digest, analysis)
    )
