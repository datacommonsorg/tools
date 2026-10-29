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
"""Tests for `workflows.charts`.

Covers `parse_chart_specification`, `resolve_chart_specification`,
`serialize_resolved_chart`, and the construction
invariants of `PlaceList`, `RankingSlice`, and the resolved charts' facets.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import get_args

import pytest
from pydantic import ValidationError

from narratives_agent.analytics.derived import derive_observation_table
from narratives_agent.analytics.digest import AnalysisDigest, ScriptResult
from narratives_agent.analytics.provenance import Provenance
from narratives_agent.analytics.ranking import rank_cohort
from narratives_agent.analytics.relations import relate_cohorts
from narratives_agent.analytics.tables import ObservationRow, ObservationTable
from narratives_agent.analytics.timeseries import analyze_timeseries
from narratives_agent.json_value import JsonObject
from narratives_agent.workflows.charts import (
    BarChartSpecification,
    ChartKind,
    ChartSpecification,
    ChildCohort,
    HighlightChartSpecification,
    LineChartSpecification,
    MapChartSpecification,
    PlaceList,
    RankingChartSpecification,
    RankingSlice,
    ResolvedBarChart,
    ResolvedChart,
    ResolvedHighlightChart,
    ResolvedLineChart,
    ResolvedMapChart,
    ResolvedRankingChart,
    ResolvedScatterChart,
    ScatterChartSpecification,
    find_chart_entry,
    parse_chart_specification,
    resolve_chart_specification,
    serialize_resolved_chart,
)
from narratives_agent.workflows.specification import AnalysisSpecification
from narratives_agent.workflows.turn_cache import (
    FETCHED_TABLE_PREFIX,
    CachedTable,
    TurnCache,
)

# Thirty counties of one state, more than an explicit place list allows.
_COUNTIES = tuple(f"geoId/{number:05d}" for number in range(30))
_STATES = tuple(f"geoId/{number:02d}" for number in range(1, 7))


def _make_table(
    table_id: str,
    variable_dcid: str = "Count_Person",
    *,
    name: str = "Total Population",
    unit: str | None = "Person",
    scaling_factor: float | None = None,
    places: Sequence[str] = ("country/FRA", "country/DEU"),
    dates: Sequence[str] = ("2022", "2023"),
    values: Mapping[str, float] | None = None,
    parent: str | None = None,
    child_type: str | None = None,
    facet_id: str | None = None,
) -> CachedTable:
    """Builds a cached table with one value per place and date."""
    names = {place: place.rsplit("/", 1)[-1] for place in places}
    rows = tuple(
        ObservationRow(
            place,
            names[place],
            date,
            (values or {}).get(place, float(index + 1) * 10.0),
        )
        for index, place in enumerate(places)
        for date in dates
    )
    table = ObservationTable(
        variable_dcid=variable_dcid,
        variable_name=name,
        unit=unit,
        scaling_factor=scaling_factor,
        provenance=Provenance(),
        rows=rows,
        requested_places=tuple(places),
        place_names=names,
        parent_place_dcid=parent,
        child_place_type=child_type,
        facet_id=facet_id,
    )
    return CachedTable(table_id=table_id, table=table)


def _make_cohort(
    table_id: str = "t1",
    *,
    variable_dcid: str = "Count_Person",
    name: str = "Total Population",
    facet_id: str | None = None,
) -> CachedTable:
    """Builds a table of six states of one parent at one date."""
    return _make_table(
        table_id,
        variable_dcid,
        name=name,
        places=_STATES,
        dates=("2023",),
        parent="country/USA",
        child_type="State",
        facet_id=facet_id,
    )


def _make_cache(*tables: CachedTable) -> TurnCache:
    """Caches fetched tables, then derived ones, in the order given."""
    cache = TurnCache()
    for entry in tables:
        if entry.table_id.startswith(FETCHED_TABLE_PREFIX):
            cache.store_fetched(entry)
        else:
            cache.store_derived(entry)
    return cache


def _make_spec(**fields: object) -> AnalysisSpecification:
    """Builds a one-step specification with the given step fields."""
    return AnalysisSpecification.model_validate({"steps": [fields]})


def _make_digest(*results: ScriptResult) -> AnalysisDigest:
    """Builds a digest from script results that cite nothing."""
    return AnalysisDigest.from_results(results)


def _make_series_digest(entry: CachedTable) -> AnalysisDigest:
    """Builds a digest of one time-series summary of `entry` as `s1`."""
    return _make_digest(analyze_timeseries(entry.table, step_id="s1"))


def _resolve_chart_wire(
    kind: str,
    tables: Sequence[str],
    cache: TurnCache,
    digest: AnalysisDigest | None = None,
    analysis: AnalysisSpecification | None = None,
    **fields: object,
) -> JsonObject | None:
    """Resolves a specification built from keyword fields to wire format."""
    payload: dict[str, object] = {
        "kind": kind,
        "tables": list(tables),
        "title": fields.pop("title", "A chart"),
        **fields,
    }
    spec = parse_chart_specification(json.dumps(payload))
    resolved = resolve_chart_specification(
        spec, cache, digest or AnalysisDigest((), ()), analysis
    )
    return serialize_resolved_chart(resolved) if resolved is not None else None


def test_a_subset_of_places_resolves_to_a_line_chart() -> None:
    # Test: Resolution of explicit places.
    # Situation: A table holds three countries over two years and the
    #   specification names two of them, one twice.
    # Expectation: The chart names the two places once each, no date, and
    #   the table's variable in the wire shape.
    table = _make_table(
        "t1", places=("country/FRA", "country/DEU", "country/ITA")
    )

    chart = _resolve_chart_wire(
        "line",
        ["t1"],
        _make_cache(table),
        _make_series_digest(table),
        places=["country/FRA", "country/DEU", "country/FRA"],
        title="  GDP,  France and Germany ",
    )

    assert chart == {
        "viz_type": "line",
        "title": "GDP, France and Germany",
        "variable_dcids": ["Count_Person"],
        "place_dcids": ["country/FRA", "country/DEU"],
    }


def test_the_same_variable_across_two_tables_is_charted_once() -> None:
    # Test: Two single-place tables of one variable.
    # Situation: The model fetched France and Germany in separate calls.
    # Expectation: The chart lists the variable once and both places.
    france = _make_table("t1", places=("country/FRA",))
    germany = _make_table("t2", places=("country/DEU",))

    chart = _resolve_chart_wire(
        "bar", ["t1", "t2"], _make_cache(france, germany), date="2023"
    )

    assert chart is not None
    assert chart["variable_dcids"] == ["Count_Person"]
    assert chart["place_dcids"] == ["country/DEU", "country/FRA"]
    assert chart["date"] == "2023"


def test_a_cohort_resolves_to_a_ranking_at_the_reference_date() -> None:
    # Test: Resolution of a cohort with a top and bottom slice.
    # Situation: A cohort of states was ranked at 2023, and the
    #   specification asks for a ranking with `top_n` and `bottom_n`.
    # Expectation: The chart carries the parent place and child type rather
    #   than places, the ranking count and both-ends flag, and the aligned
    #   reference date.
    table = _make_cohort()
    digest = _make_digest(rank_cohort(table.table, step_id="s1"))

    analysis = _make_spec(step_id="s1", script="rank_cohort", table="t1")

    chart = _resolve_chart_wire(
        "ranking",
        ["t1"],
        _make_cache(table),
        digest,
        analysis,
        top_n=3,
        bottom_n=3,
    )

    assert chart == {
        "viz_type": "ranking",
        "title": "A chart",
        "variable_dcids": ["Count_Person"],
        "parent_place": "country/USA",
        "child_place_type": "State",
        "date": "2023",
        "ranking_count": 3,
        "show_highest_lowest": True,
        "show_lowest": False,
    }


def test_a_top_n_slice_takes_the_ranked_places() -> None:
    # Test: A bar chart of a ranked slice.
    # Situation: The digest ranks a version of the cohort whose values run
    #   the other way, and the specification asks for a bar of the two
    #   highest places of the cohort table.
    # Expectation: The places are the digest's two highest, not the two
    #   highest of the table, so the slice is read from the digest.
    table = _make_cohort()
    reversed_values = {
        place: float(len(_STATES) - index) * 10.0
        for index, place in enumerate(_STATES)
    }
    ranked = _make_table(
        "t1",
        places=_STATES,
        dates=("2023",),
        values=reversed_values,
        parent="country/USA",
        child_type="State",
    )
    digest = _make_digest(rank_cohort(ranked.table, step_id="s1"))
    analysis = _make_spec(step_id="s1", script="rank_cohort", table="t1")

    chart = _resolve_chart_wire(
        "bar", ["t1"], _make_cache(table), digest, analysis, top_n=2
    )

    assert chart is not None
    assert chart["place_dcids"] == ["geoId/01", "geoId/02"]
    assert chart["date"] == "2023"
    assert "parent_place" not in chart


def _make_crossing_table() -> CachedTable:
    """Builds six states whose order in 2022 is reversed in 2023."""
    rows = tuple(
        ObservationRow(place, place.rsplit("/", 1)[-1], date, value)
        for number, place in enumerate(_STATES, start=1)
        for date, value in (
            ("2022", 70.0 - 10.0 * number),
            ("2023", 10.0 * number),
        )
    )
    table = ObservationTable(
        variable_dcid="Count_Person",
        variable_name="Total Population",
        unit="Person",
        scaling_factor=None,
        provenance=Provenance(),
        rows=rows,
        requested_places=_STATES,
        place_names={place: place.rsplit("/", 1)[-1] for place in _STATES},
        parent_place_dcid="country/USA",
        child_place_type="State",
    )
    return CachedTable(table_id="t1", table=table)


@pytest.mark.parametrize(
    ("has_digest", "date", "expected_places", "expected_date"),
    [
        (True, None, _STATES[:2], "2022"),
        (True, "2023", (_STATES[5], _STATES[4]), "2023"),
        (True, "LATEST", (_STATES[5], _STATES[4]), "2023"),
        (False, "2022", _STATES[:2], "2022"),
    ],
    ids=[
        "no_date_draws_the_ranking_date",
        "explicit_date_reranks_at_that_date",
        "latest_keyword_reranks_at_the_latest_covered_date",
        "no_ranking_ranks_at_the_explicit_date",
    ],
)
def test_a_slice_is_ranked_at_the_date_it_is_drawn(
    has_digest: bool,
    date: str | None,
    expected_places: tuple[str, ...],
    expected_date: str,
) -> None:
    # Test: The agreement of a ranked slice and its drawn date.
    # Situation: Six states lead in reverse order in 2022 and 2023; the
    #   digest summarizes the series and ranks the states at 2022, or the
    #   turn has no digest. A bar asks for the top two, with no date or
    #   with an explicit one.
    # Expectation: The bar draws the leaders of the date it is drawn at:
    #   without a date, the ranking's date and its leaders; with a date,
    #   the leaders at that date, ranked again when the digest ranked
    #   another date or nothing.
    table = _make_crossing_table()
    analysis = AnalysisSpecification.model_validate(
        {
            "steps": [
                {
                    "step_id": "s1",
                    "script": "analyze_timeseries",
                    "table": "t1",
                },
                {"step_id": "s2", "script": "rank_cohort", "table": "t1"},
            ]
        }
    )
    digest = _make_digest(
        analyze_timeseries(table.table, step_id="s1"),
        rank_cohort(table.table, target_date="2022", step_id="s2"),
    )
    fields: dict[str, object] = {"top_n": 2}
    if date is not None:
        fields["date"] = date

    chart = _resolve_chart_wire(
        "bar",
        ["t1"],
        _make_cache(table),
        digest if has_digest else None,
        analysis if has_digest else None,
        **fields,
    )

    assert chart is not None
    assert chart["place_dcids"] == list(expected_places)
    assert chart["date"] == expected_date


def test_a_slice_ranked_at_a_date_not_every_table_holds_is_rejected() -> None:
    # Test: A one-date chart whose slice date is missing from a table.
    # Situation: The digest ranks the crossing states at 2022, and the bar
    #   also charts a table holding only 2023.
    # Expectation: The bar is rejected rather than drawing the 2022
    #   leaders at another date.
    table = _make_crossing_table()
    other = _make_table("t2", places=("geoId/07",), dates=("2023",))
    analysis = _make_spec(step_id="s1", script="rank_cohort", table="t1")
    digest = _make_digest(
        rank_cohort(table.table, target_date="2022", step_id="s1")
    )

    chart = _resolve_chart_wire(
        "bar",
        ["t1", "t2"],
        _make_cache(table, other),
        digest,
        analysis,
        top_n=2,
    )

    assert chart is None


@pytest.mark.parametrize("date", [None, "LATEST"], ids=["no_date", "latest"])
def test_a_slice_ranked_again_is_drawn_at_its_ranked_date(
    date: str | None,
) -> None:
    # Test: The drawn date of a slice the digest does not supply.
    # Situation: Six states report in 2022, but only one reports in 2023,
    #   so the table is ranked at 2022, the latest date with coverage; the
    #   bar asks for the top two with no date or with `LATEST`.
    # Expectation: The bar shows the 2022 leaders and is drawn at 2022,
    #   not at the latest date.
    rows = (
        *(
            ObservationRow(place, place, "2022", float(number))
            for number, place in enumerate(_STATES)
        ),
        ObservationRow(_STATES[0], _STATES[0], "2023", 1000.0),
    )
    table = CachedTable(
        "t1",
        ObservationTable(
            variable_dcid="Count_Person",
            variable_name="Total Population",
            unit="Person",
            scaling_factor=None,
            provenance=Provenance(),
            rows=rows,
            requested_places=_STATES,
            place_names={place: place for place in _STATES},
            parent_place_dcid="country/USA",
            child_place_type="State",
        ),
    )
    fields: dict[str, object] = {"top_n": 2}
    if date is not None:
        fields["date"] = date

    chart = _resolve_chart_wire(
        "bar", ["t1"], _make_cache(table), None, None, **fields
    )

    assert chart is not None
    assert chart["place_dcids"] == [_STATES[5], _STATES[4]]
    assert chart["date"] == "2022"


def test_tables_of_one_variable_agree_in_unit_for_every_kind() -> None:
    # Test: The unit check across tables of one variable.
    # Situation: Two cohort tables of one variable report in different
    #   units, and each kind that draws one variable charts both.
    # Expectation: Every kind rejects the chart, as a bar does.
    persons = _make_cohort("t1")
    thousands = CachedTable(
        "t2",
        replace(
            _make_cohort("t2").table,
            unit="ThousandPersons",
            scaling_factor=1000.0,
        ),
    )
    cache = _make_cache(persons, thousands)

    for kind in ("bar", "map", "ranking"):
        assert _resolve_chart_wire(kind, ["t1", "t2"], cache) is None, kind


def test_a_bottom_n_slice_without_a_ranking_result_is_computed() -> None:
    # Test: A slice when the digest holds no ranking of the table.
    # Situation: The digest is empty.
    # Expectation: The slice is computed from the table.
    table = _make_cohort()

    chart = _resolve_chart_wire("bar", ["t1"], _make_cache(table), bottom_n=2)

    assert chart is not None
    assert chart["place_dcids"] == ["geoId/01", "geoId/02"]


def test_a_slice_ignores_a_ranking_of_another_table_of_the_variable() -> None:
    # Test: The table binding of a ranked slice.
    # Situation: `t1` holds the population of six states and `t2` the
    #   population of two countries; the specification ranks `t1`, and a
    #   bar asks for the top two of `t2`.
    # Expectation: The slice is ranked from `t2`, so the chart names its
    #   countries rather than the states the digest ranks.
    states = _make_cohort("t1")
    countries = _make_table("t2", values={"country/DEU": 90.0})
    digest = _make_digest(rank_cohort(states.table, step_id="s1"))
    analysis = _make_spec(step_id="s1", script="rank_cohort", table="t1")

    chart = _resolve_chart_wire(
        "bar",
        ["t2"],
        _make_cache(states, countries),
        digest,
        analysis,
        top_n=2,
    )

    assert chart is not None
    assert chart["place_dcids"] == ["country/DEU", "country/FRA"]


def test_a_slice_ignores_a_ranking_of_a_subset_of_the_places() -> None:
    # Test: The table binding of a ranked slice when the places overlap.
    # Situation: `t1` holds six states and `t2` the first three of them for
    #   the same variable; the specification ranks `t2`, and a bar asks for
    #   the top two of `t1`.
    # Expectation: The slice is ranked from `t1`, so the chart names its two
    #   highest states, which `t2` does not hold.
    states = _make_cohort("t1")
    subset = _make_table(
        "t2",
        places=_STATES[:3],
        dates=("2023",),
        parent="country/USA",
        child_type="State",
    )
    digest = _make_digest(rank_cohort(subset.table, step_id="s1"))
    analysis = _make_spec(step_id="s1", script="rank_cohort", table="t2")

    chart = _resolve_chart_wire(
        "bar",
        ["t1"],
        _make_cache(states, subset),
        digest,
        analysis,
        top_n=2,
    )

    assert chart is not None
    assert chart["place_dcids"] == ["geoId/06", "geoId/05"]


def test_a_ranking_of_the_bottom_end_lists_only_the_lowest() -> None:
    # Test: The display flags of a ranking sliced from the bottom.
    # Situation: A ranking of a cohort asks for `bottom_n` only.
    # Expectation: The chart lists two places at the lowest end only.
    chart = _resolve_chart_wire(
        "ranking", ["t1"], _make_cache(_make_cohort()), bottom_n=2
    )

    assert chart is not None
    assert chart["ranking_count"] == 2
    assert chart["show_highest_lowest"] is False
    assert chart["show_lowest"] is True


def test_a_per_capita_derived_table_resolves_to_its_numerator() -> None:
    # Test: The per-capita mapping.
    # Situation: `s1` divides a fetched count by `Count_Person`, both
    #   cohorts, and the specification charts `s1` as a map.
    # Expectation: The chart shows the count with `per_capita` set.
    population = _make_cohort("t1")
    crimes = _make_cohort("t2", variable_dcid="Count_Crime", name="Crimes")
    analysis = _make_spec(
        step_id="s1",
        script="compute_derived_metric",
        left="t2",
        right="t1",
        operation="per_capita",
    )
    derived = derive_observation_table(
        crimes.table, population.table, operation="per_capita", step_id="s1"
    )
    assert derived.table is not None
    cache = _make_cache(population, crimes, CachedTable("s1", derived.table))

    chart = _resolve_chart_wire(
        "map", ["s1"], cache, _make_digest(derived.result), analysis
    )

    assert chart == {
        "viz_type": "map",
        "title": "A chart",
        "variable_dcids": ["Count_Crime"],
        "parent_place": "country/USA",
        "child_place_type": "State",
        "per_capita": True,
    }


def _make_rejection_cache() -> tuple[TurnCache, AnalysisSpecification]:
    """Caches the tables the rejection tests reference.

    `t1` is a two-country population table, `t2` a GDP table in dollars,
    `t3` a single-date table, `t4` a cohort of six states, `s1` a ratio
    derived from `t2` and `t1`, `s2` a per-capita table derived from `t2`
    and `t1`, `s3` a derived table labeled `Count_Person`, and `s4` a
    per-capita table dividing `t2` by the derived `s3`.
    """
    population = _make_table("t1")
    gdp = _make_table("t2", "Amount_GDP", name="GDP", unit="USDollar")
    single = _make_table("t3", "Count_Household", dates=("2023",))
    male = _make_table("t5", "Count_Person_Male")
    female = _make_table("t6", "Count_Person_Female")
    analysis = AnalysisSpecification.model_validate(
        {
            "steps": [
                {
                    "step_id": "s1",
                    "script": "compute_derived_metric",
                    "left": "t2",
                    "right": "t1",
                },
                {
                    "step_id": "s2",
                    "script": "compute_derived_metric",
                    "left": "t2",
                    "right": "t1",
                    "operation": "per_capita",
                },
                {
                    "step_id": "s3",
                    "script": "compute_derived_metric",
                    "left": "t5",
                    "right": "t6",
                    "operation": "sum",
                    "derived_variable_dcid": "Count_Person",
                },
                {
                    "step_id": "s4",
                    "script": "compute_derived_metric",
                    "left": "t2",
                    "right": "s3",
                    "operation": "per_capita",
                },
            ]
        }
    )
    ratio = derive_observation_table(gdp.table, population.table, step_id="s1")
    per_capita = derive_observation_table(
        gdp.table, population.table, operation="per_capita", step_id="s2"
    )
    derived_pop = derive_observation_table(
        male.table,
        female.table,
        operation="sum",
        derived_variable_dcid="Count_Person",
        step_id="s3",
    )
    assert derived_pop.table is not None
    derived_denom_pc = derive_observation_table(
        gdp.table,
        derived_pop.table,
        operation="per_capita",
        step_id="s4",
    )
    assert (
        ratio.table is not None
        and per_capita.table is not None
        and derived_denom_pc.table is not None
    )
    cache = _make_cache(
        population,
        gdp,
        single,
        _make_cohort("t4"),
        male,
        female,
        CachedTable("s1", ratio.table),
        CachedTable("s2", per_capita.table),
        CachedTable("s3", derived_pop.table),
        CachedTable("s4", derived_denom_pc.table),
    )
    return cache, analysis


@pytest.mark.parametrize(
    ("kind", "tables", "fields"),
    [
        ("line", ["t9"], {}),
        ("line", ["t1"], {"places": ["country/FRA", "country/ESP"]}),
        ("bar", ["t1"], {"date": "1999"}),
        ("bar", ["t1", "t2"], {}),
        ("map", ["t1"], {}),
        ("scatter", ["t1", "t2"], {}),
        ("highlight", ["t1"], {}),
        ("line", ["t3"], {}),
        ("bar", ["s1"], {}),
        ("bar", ["s4"], {}),
        ("line", ["s2", "t1"], {}),
        ("line", ["t2", "s2"], {}),
        ("bar", ["t1"], {"title": " "}),
        ("highlight", ["t1"], {"places": ["country/ESP"]}),
        ("bar", ["t1", "t3"], {"date": "2022"}),
        ("line", ["t1", "t3"], {}),
    ],
    ids=[
        "unknown_table",
        "place_not_in_table",
        "date_not_in_table",
        "unit_mismatch",
        "map_without_cohort",
        "scatter_without_cohort",
        "highlight_with_two_places",
        "line_with_one_date",
        "ratio_derived_table",
        "per_capita_over_derived_denominator",
        "per_capita_with_raw_table",
        "per_capita_with_its_numerator",
        "blank_title",
        "highlight_of_a_place_not_in_table",
        "date_not_in_every_table",
        "line_with_a_single_date_table",
    ],
)
def test_a_specification_that_fails_resolution_is_rejected(
    kind: str, tables: list[str], fields: dict[str, object]
) -> None:
    # Test: The rejection rules of chart resolution.
    # Situation: Each specification is valid grammar but breaks one rule
    #   against `_make_rejection_cache`: a reference the cache cannot
    #   satisfy, a shape the kind cannot show, a per-capita table mixed
    #   with a raw one or using a derived denominator, a title that is blank
    #   once cleaned, a date only one of two tables has, or a line over a
    #   table with a single date.
    # Expectation: Resolution returns None for every case.
    cache, analysis = _make_rejection_cache()

    chart = _resolve_chart_wire(kind, tables, cache, None, analysis, **fields)

    assert chart is None


@pytest.mark.parametrize(
    ("table_id", "has_analysis", "expected"),
    [
        ("t1", True, "t1"),
        ("s2", True, "t2"),
        ("s1", True, None),
        ("s4", True, None),
        ("t9", True, None),
        ("s2", False, None),
    ],
    ids=[
        "fetched",
        "per_capita_numerator",
        "ratio",
        "per_capita_over_derived_denominator",
        "unknown",
        "derived_without_specification",
    ],
)
def test_find_chart_entry_returns_the_table_a_chart_draws(
    table_id: str, has_analysis: bool, expected: str | None
) -> None:
    # Test: The cached table a chart naming a table id draws.
    # Situation: `_make_rejection_cache` holds population `t1`, GDP `t2`,
    #   the ratio `s1`, the per-capita table `s2` of `t2` by `t1`, and `s4`
    #   dividing `t2` by a derived `s3` labeled `Count_Person`.
    # Expectation: A fetched table is drawn as it is, a per-capita table
    #   over fetched `Count_Person` as its numerator, and a ratio, a
    #   per-capita table over a derived denominator, an unknown id, or a
    #   derived table without the specification that derived it draws
    #   nothing.
    cache, analysis = _make_rejection_cache()

    entry = find_chart_entry(
        table_id, analysis if has_analysis else None, cache
    )

    assert (entry.table_id if entry is not None else None) == expected


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"date": "2023"}, None),
        (
            {},
            {
                "viz_type": "highlight",
                "title": "A chart",
                "variable_dcids": ["Count_Person"],
                "place_dcids": ["country/DEU"],
            },
        ),
    ],
    ids=["named_date_rejected", "reference_date_dropped"],
)
def test_a_highlight_is_not_drawn_at_a_date_its_place_lacks(
    fields: dict[str, object], expected: JsonObject | None
) -> None:
    # Test: The date a highlight chart is drawn at.
    # Situation: `t1` holds France in 2022 and 2023 but Germany only in
    #   2022, and the digest's series result, over France and Spain, is
    #   aligned at 2023. A highlight of Germany names 2023, or names no date.
    # Expectation: The named date is rejected. Without a date, the
    #   reference date is dropped, so the chart shows Germany's latest
    #   value rather than an empty point at 2023.
    full = _make_table("t1")
    table = replace(
        full.table,
        rows=tuple(
            row
            for row in full.table.rows
            if (row.place_dcid, row.date) != ("country/DEU", "2023")
        ),
    )
    aligned = _make_table("t1", places=("country/FRA", "country/ESP"))
    digest = _make_digest(analyze_timeseries(aligned.table, step_id="s1"))
    analysis = _make_spec(step_id="s1", script="analyze_timeseries", table="t1")

    chart = _resolve_chart_wire(
        "highlight",
        ["t1"],
        _make_cache(CachedTable("t1", table)),
        digest,
        analysis,
        places=["country/DEU"],
        **fields,
    )

    assert chart == expected


def test_a_per_capita_slice_takes_the_places_ranked_per_capita() -> None:
    # Test: A ranked slice of a per-capita chart.
    # Situation: The state with the most crimes is not the one with the
    #   most crimes per person, and the per-capita table `s1` was ranked.
    # Expectation: A bar of the top state of `s1` shows the state ranked
    #   first per person, at the ranking's date, as the count normalized
    #   per capita.
    population = _make_table(
        "t1",
        places=_STATES[:3],
        dates=("2023",),
        values={_STATES[0]: 1000.0, _STATES[1]: 10.0, _STATES[2]: 100.0},
    )
    crimes = _make_table(
        "t2",
        "Count_Crime",
        name="Crimes",
        unit="Count",
        places=_STATES[:3],
        dates=("2023",),
        values={_STATES[0]: 100.0, _STATES[1]: 5.0, _STATES[2]: 20.0},
    )
    derived = derive_observation_table(
        crimes.table, population.table, operation="per_capita", step_id="s1"
    )
    assert derived.table is not None
    per_capita = CachedTable("s1", derived.table)
    analysis = AnalysisSpecification.model_validate(
        {
            "steps": [
                {
                    "step_id": "s1",
                    "script": "compute_derived_metric",
                    "left": "t2",
                    "right": "t1",
                    "operation": "per_capita",
                },
                {"step_id": "s2", "script": "rank_cohort", "table": "s1"},
            ]
        }
    )
    digest = _make_digest(
        derived.result, rank_cohort(per_capita.table, step_id="s2")
    )

    chart = _resolve_chart_wire(
        "bar",
        ["s1"],
        _make_cache(population, crimes, per_capita),
        digest,
        analysis,
        top_n=1,
    )

    assert chart is not None
    assert chart["place_dcids"] == [_STATES[1]]
    assert chart["variable_dcids"] == ["Count_Crime"]
    assert chart["per_capita"] is True
    assert chart["date"] == "2023"


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "ranking", "tables": ["t1"], "title": "x", "top_n": 0},
        {"kind": "pie", "tables": ["t1"], "title": "x"},
        {"kind": "gauge", "tables": ["t1"], "title": "x"},
        {"kind": "bar", "tables": ["t1"], "title": "x", "donut": True},
        {"kind": "bar", "tables": [], "title": "x"},
        {"kind": "bar", "tables": ["x1"], "title": "x"},
        {"tables": ["t1"], "title": "x"},
        {"kind": "bar", "tables": ["t1"], "title": "x", "places": []},
        {
            "kind": "bar",
            "tables": ["t1"],
            "title": "x",
            "top_n": 1,
            "bottom_n": 1,
        },
        {
            "kind": "line",
            "tables": ["t1"],
            "title": "x",
            "places": ["geoId/01"],
            "top_n": 1,
        },
        {
            "kind": "bar",
            "tables": ["t1"],
            "title": "x",
            "places": ["geoId/01"],
            "cohort": True,
        },
        {"kind": "line", "tables": ["t1"], "title": "x", "sort": "ascending"},
        {
            "kind": "ranking",
            "tables": ["t1"],
            "title": "x",
            "top_n": 3,
            "bottom_n": 2,
        },
        {
            "kind": "ranking",
            "tables": ["t1"],
            "title": "x",
            "places": ["geoId/01"],
        },
        {"kind": "map", "tables": ["t1"], "title": "x", "top_n": 1},
        {"kind": "map", "tables": ["t1"], "title": "x", "cohort": False},
        {
            "kind": "scatter",
            "tables": ["t1"],
            "title": "x",
            "places": ["geoId/01"],
        },
        {"kind": "highlight", "tables": ["t1"], "title": "x", "cohort": True},
        {
            "kind": "highlight",
            "tables": ["t1"],
            "title": "x",
            "places": ["geoId/01", "geoId/02"],
        },
        {"kind": "bar", "tables": ["t1"], "title": "x", "per_capita": True},
        {"kind": "line", "tables": ["t1"], "title": "x", "date": "2023"},
        {"kind": "line", "tables": ["t1"], "title": "x", "date": "LATEST"},
    ],
    ids=[
        "zero_top_n",
        "pie_is_not_a_kind",
        "gauge_is_not_a_kind",
        "unknown_field",
        "no_tables",
        "malformed_table_id",
        "no_kind",
        "empty_places",
        "both_ends_outside_a_ranking",
        "places_with_a_slice",
        "places_with_a_cohort",
        "sort_on_a_line",
        "unequal_ranking_ends",
        "places_on_a_ranking",
        "sliced_map",
        "map_without_its_cohort",
        "places_on_a_scatter",
        "highlight_of_a_cohort",
        "highlight_of_two_places",
        "per_capita_is_charted_by_its_table",
        "date_on_a_line",
        "latest_date_on_a_line",
    ],
)
def test_a_specification_outside_the_grammar_fails_validation(
    payload: dict[str, object],
) -> None:
    # Test: The chart block grammar of each kind.
    # Situation: Each payload breaks the grammar: a zero count, a missing or
    #   unknown kind, an unknown field, an empty table list, a malformed
    #   table id, an empty place list, a field the kind does not take, more
    #   than one way to pick a line's or bar's places, unequal ranking ends,
    #   a cohort kind told not to chart its cohort, or two highlight places.
    # Expectation: `parse_chart_specification` raises `ValidationError`.
    with pytest.raises(ValidationError):
        parse_chart_specification(json.dumps(payload))


@pytest.mark.parametrize(
    ("payload", "expected_type"),
    [
        ({"kind": "line"}, LineChartSpecification),
        ({"kind": "bar", "sort": "ascending"}, BarChartSpecification),
        ({"kind": "ranking", "cohort": True}, RankingChartSpecification),
        ({"kind": "map"}, MapChartSpecification),
        ({"kind": "scatter"}, ScatterChartSpecification),
        ({"kind": "highlight"}, HighlightChartSpecification),
    ],
    ids=["line", "bar", "ranking", "map", "scatter", "highlight"],
)
def test_a_chart_block_parses_into_the_specification_of_its_kind(
    payload: dict[str, object], expected_type: type[object]
) -> None:
    # Test: Discrimination of chart blocks by `kind`.
    # Situation: A minimal valid block of each kind; the ranking repeats the
    #   `cohort` it always charts, which the grammar accepts.
    # Expectation: Each parses into the specification class of its kind.
    spec = parse_chart_specification(
        json.dumps({"tables": ["t1"], "title": "x", **payload})
    )

    assert isinstance(spec, expected_type)


_STATE_COHORT = ChildCohort("country/USA", "State")


def test_the_chart_kinds_match_their_classes() -> None:
    # Test: The chart kind vocabulary against the chart classes.
    # Situation: `ChartKind` names the kinds, each specification class
    #   fixes its `kind`, and each resolved class its `viz_type`.
    # Expectation: The three sets are equal, so no kind is named that the
    #   parser or the serializer lacks.
    kinds = set(get_args(ChartKind.__value__))
    union = get_args(ChartSpecification)[0]
    spec_kinds = {cls.model_fields["kind"].default for cls in get_args(union)}
    viz_types = {cls.viz_type for cls in get_args(ResolvedChart.__value__)}

    assert spec_kinds == kinds
    assert viz_types == kinds


@pytest.mark.parametrize(
    ("chart", "expected"),
    [
        (
            ResolvedLineChart(
                title="x",
                variable_dcids=("v",),
                scope=PlaceList(("geoId/01", "geoId/02")),
            ),
            {"viz_type": "line", "place_dcids": ["geoId/01", "geoId/02"]},
        ),
        (
            ResolvedBarChart(
                title="x",
                variable_dcids=("v",),
                scope=_STATE_COHORT,
                sort="descending",
            ),
            {
                "viz_type": "bar",
                "parent_place": "country/USA",
                "child_place_type": "State",
                "sort": "descending",
            },
        ),
        (
            ResolvedRankingChart(
                title="x",
                variable_dcids=("v",),
                cohort=_STATE_COHORT,
                ranking=RankingSlice(3, "both"),
            ),
            {
                "viz_type": "ranking",
                "parent_place": "country/USA",
                "child_place_type": "State",
                "ranking_count": 3,
                "show_highest_lowest": True,
                "show_lowest": False,
            },
        ),
        (
            ResolvedRankingChart(
                title="x",
                variable_dcids=("v",),
                cohort=_STATE_COHORT,
                ranking=RankingSlice(2, "bottom"),
            ),
            {
                "viz_type": "ranking",
                "parent_place": "country/USA",
                "child_place_type": "State",
                "ranking_count": 2,
                "show_highest_lowest": False,
                "show_lowest": True,
            },
        ),
        (
            ResolvedRankingChart(
                title="x",
                variable_dcids=("v",),
                cohort=_STATE_COHORT,
                ranking=RankingSlice(4, "top"),
            ),
            {
                "viz_type": "ranking",
                "parent_place": "country/USA",
                "child_place_type": "State",
                "ranking_count": 4,
                "show_highest_lowest": False,
                "show_lowest": False,
            },
        ),
        (
            ResolvedRankingChart(
                title="x", variable_dcids=("v",), cohort=_STATE_COHORT
            ),
            {
                "viz_type": "ranking",
                "parent_place": "country/USA",
                "child_place_type": "State",
            },
        ),
        (
            ResolvedMapChart(
                title="x",
                variable_dcids=("v",),
                cohort=_STATE_COHORT,
                date="2023",
                facet_ids=(("v", "f1"),),
                unit="people",
                per_capita=True,
            ),
            {
                "viz_type": "map",
                "parent_place": "country/USA",
                "child_place_type": "State",
                "date": "2023",
                "facet_ids": {"v": "f1"},
                "unit": "people",
                "per_capita": True,
            },
        ),
        (
            ResolvedScatterChart(
                title="x", variable_dcids=("v", "w"), cohort=_STATE_COHORT
            ),
            {
                "viz_type": "scatter",
                "parent_place": "country/USA",
                "child_place_type": "State",
            },
        ),
        (
            ResolvedHighlightChart(
                title="x", variable_dcids=("v",), place_dcid="geoId/06"
            ),
            {"viz_type": "highlight", "place_dcids": ["geoId/06"]},
        ),
    ],
    ids=[
        "line_of_places",
        "sorted_bar_of_a_cohort",
        "ranking_of_both_ends",
        "ranking_of_the_bottom_end",
        "ranking_of_the_top_end",
        "unsliced_ranking",
        "map_with_every_optional_field",
        "scatter",
        "highlight",
    ],
)
def test_each_resolved_chart_kind_serializes_to_its_wire_mapping(
    chart: ResolvedChart, expected: dict[str, object]
) -> None:
    # Test: The wire mapping of each resolved chart kind.
    # Situation: One resolved chart per kind and per ranking slice, and a
    #   map that sets every shared optional field.
    # Expectation: The mapping holds the kind's `viz_type`, title, and
    #   variables, the place or cohort keys of its scope, the three ranking
    #   keys only for a sliced ranking, `sort` only for a sorted bar, and
    #   each shared optional field only when it is set.
    wire = serialize_resolved_chart(chart)

    assert wire == {
        "title": "x",
        "variable_dcids": list(chart.variable_dcids),
        **expected,
    }


def test_a_place_list_names_at_least_one_place() -> None:
    # Test: The construction invariant of `PlaceList`.
    # Situation: A place list with no places.
    # Expectation: The construction raises `ValueError`.
    with pytest.raises(ValueError, match="at least one place"):
        PlaceList(())


@pytest.mark.parametrize(
    ("parent_place", "child_place_type"),
    [("", "State"), ("country/USA", "")],
)
def test_a_child_cohort_names_a_parent_place_and_a_child_type(
    parent_place: str, child_place_type: str
) -> None:
    # Test: The construction invariant of `ChildCohort`.
    # Situation: A child cohort with an empty parent place or child place type.
    # Expectation: The construction raises `ValueError`.
    with pytest.raises(
        ValueError, match="a parent place and a child place type"
    ):
        ChildCohort(parent_place, child_place_type)


def test_a_ranking_slice_lists_at_least_one_place() -> None:
    # Test: The construction invariant of `RankingSlice`.
    # Situation: A slice with a count of zero.
    # Expectation: The construction raises `ValueError`.
    with pytest.raises(ValueError, match="at least one place"):
        RankingSlice(0, "both")


def test_a_scatter_takes_two_variables_of_one_cohort() -> None:
    # Test: Resolution of a scatter chart.
    # Situation: Three tables of different variables cover the same cohort
    #   of states, and another covers the counties of one state.
    # Expectation: A scatter of the first two carries both variables and
    #   the cohort; a scatter that mixes cohorts, a scatter of three
    #   variables, and a ranking or map of two variables are rejected.
    population = _make_cohort("t1")
    crimes = _make_cohort("t2", variable_dcid="Count_Crime", name="Crimes")
    households = _make_cohort(
        "t4", variable_dcid="Count_Household", name="Households"
    )
    counties = _make_table(
        "t3",
        "Count_Crime",
        places=("geoId/06001", "geoId/06003"),
        dates=("2023",),
        parent="geoId/06",
        child_type="County",
    )
    cache = _make_cache(population, crimes, counties, households)

    chart = _resolve_chart_wire("scatter", ["t1", "t2"], cache)

    assert chart == {
        "viz_type": "scatter",
        "title": "A chart",
        "variable_dcids": ["Count_Person", "Count_Crime"],
        "parent_place": "country/USA",
        "child_place_type": "State",
    }
    assert _resolve_chart_wire("scatter", ["t1", "t3"], cache) is None
    assert _resolve_chart_wire("scatter", ["t1", "t2", "t4"], cache) is None
    assert _resolve_chart_wire("ranking", ["t1", "t2"], cache) is None
    assert _resolve_chart_wire("map", ["t1", "t2"], cache) is None


def _make_relation_cache() -> tuple[
    TurnCache, AnalysisDigest, AnalysisSpecification
]:
    """Income for six states on 2023 and diabetes for five of them on 2021.

    The relation step summarizes diabetes (`t2`) over the states ordered by
    income (`t1`), with groups of two.
    """
    income = _make_cohort("t1", variable_dcid="Median_Income", name="Income")
    diabetes = _make_table(
        "t2",
        "Percent_Diabetes",
        name="Diabetes",
        unit="Percent",
        places=_STATES[:5],
        dates=("2021",),
        values={
            "geoId/01": 50.0,
            "geoId/02": 40.0,
            "geoId/03": 30.0,
            "geoId/04": 20.0,
            "geoId/05": 10.0,
        },
        parent="country/USA",
        child_type="State",
    )
    analysis = _make_spec(
        step_id="s1", script="relate_cohorts", target="t2", by="t1", n=2
    )
    digest = _make_digest(
        relate_cohorts(diabetes.table, income.table, n=2, step_id="s1")
    )
    return _make_cache(income, diabetes), digest, analysis


def test_a_relation_supplies_each_table_its_date_and_the_by_tail() -> None:
    # Test: Chart resolution against a `relate_cohorts` result.
    # Situation: The digest's only result relates diabetes on 2021 to
    #   income on 2023 over the five states both cover; the state with the
    #   highest income has no diabetes value.
    # Expectation: A ranking of each table is drawn at that table's own
    #   reference date; a bar of the two highest-income states reads the
    #   relation's highest group, which leaves out the uncovered state; and
    #   a bar of the two highest diabetes rates is ranked from the diabetes
    #   table itself, because the relation does not rank its target.
    cache, digest, analysis = _make_relation_cache()

    income_ranking = _resolve_chart_wire(
        "ranking", ["t1"], cache, digest, analysis
    )
    diabetes_ranking = _resolve_chart_wire(
        "ranking", ["t2"], cache, digest, analysis
    )
    income_bar = _resolve_chart_wire(
        "bar", ["t1"], cache, digest, analysis, top_n=2
    )
    diabetes_bar = _resolve_chart_wire(
        "bar", ["t2"], cache, digest, analysis, top_n=2
    )

    assert income_ranking is not None and diabetes_ranking is not None
    assert income_ranking["date"] == "2023"
    assert diabetes_ranking["date"] == "2021"
    assert income_bar is not None and diabetes_bar is not None
    assert income_bar["place_dcids"] == ["geoId/05", "geoId/04"]
    assert diabetes_bar["place_dcids"] == ["geoId/01", "geoId/02"]


def test_a_ranking_of_the_variable_slices_before_a_relation() -> None:
    # Test: The precedence of results for a ranked slice.
    # Situation: The digest holds the relation first and then a ranking of
    #   income across all six states, and a bar asks for the two
    #   highest-income states.
    # Expectation: The ranking supplies the slice, so the state the
    #   relation leaves out for lack of diabetes data is shown.
    cache, digest, _ = _make_relation_cache()
    income = cache.get("t1")
    assert income is not None
    both = _make_digest(
        *digest.results, rank_cohort(income.table, step_id="s2")
    )
    analysis = AnalysisSpecification.model_validate(
        {
            "steps": [
                {
                    "step_id": "s1",
                    "script": "relate_cohorts",
                    "target": "t2",
                    "by": "t1",
                    "n": 2,
                },
                {"step_id": "s2", "script": "rank_cohort", "table": "t1"},
            ]
        }
    )

    bar = _resolve_chart_wire("bar", ["t1"], cache, both, analysis, top_n=2)

    assert bar is not None
    assert bar["place_dcids"] == ["geoId/06", "geoId/05"]


def test_a_latest_date_keyword_leaves_the_date_to_the_component() -> None:
    # Test: The date keywords the components understand.
    # Situation: Two bar specifications over a two-year table ask for the
    #   dates `LATEST` and `highest`.
    # Expectation: Both resolve and neither carries a date, so the
    #   component shows its latest observation.
    table = _make_table("t1")
    cache = _make_cache(table)

    latest = _resolve_chart_wire("bar", ["t1"], cache, date="LATEST")
    highest = _resolve_chart_wire("bar", ["t1"], cache, date="highest")

    assert latest is not None and "date" not in latest
    assert highest is not None and "date" not in highest


def test_a_chart_pins_the_facet_that_served_each_table() -> None:
    # Test: Facet pinning.
    # Situation: A GDP table served by a Eurostat facet and a population
    #   table served by a Census facet are charted together as a scatter,
    #   two tables of one variable were served by different facets, and a
    #   third table names no facet.
    # Expectation: The scatter maps each variable to its facet; a variable
    #   whose tables name different facets, or a facet and none, is left
    #   unpinned; a chart of the facetless table carries no mapping.
    gdp = _make_cohort(
        "t1", variable_dcid="Amount_GDP", name="GDP", facet_id="eu"
    )
    population = _make_cohort("t2", facet_id="census")
    france = _make_table("t3", places=("country/FRA",), facet_id="insee")
    germany = _make_table("t4", places=("country/DEU",), facet_id="destatis")
    unknown = _make_table("t5", places=("country/ITA",))
    cache = _make_cache(gdp, population, france, germany, unknown)

    scatter = _resolve_chart_wire("scatter", ["t1", "t2"], cache)
    shared = _resolve_chart_wire("bar", ["t3", "t4"], cache, date="2023")
    facetless = _resolve_chart_wire("bar", ["t5"], cache, date="2023")
    mixed = _resolve_chart_wire("bar", ["t3", "t5"], cache, date="2023")

    assert scatter is not None
    assert scatter["facet_ids"] == {
        "Amount_GDP": "eu",
        "Count_Person": "census",
    }
    assert shared is not None
    assert "facet_ids" not in shared
    assert facetless is not None
    assert "facet_ids" not in facetless
    assert mixed is not None
    assert "facet_ids" not in mixed


def test_display_hints_reach_the_wire_for_their_kind() -> None:
    # Test: The optional display fields.
    # Situation: A bar of two components asks for a sort and a display
    #   unit, and a line asks for a display unit only (a line takes no
    #   sort).
    # Expectation: The bar carries `sort` and `unit` with both variables,
    #   and the line carries `unit` and no `sort`.
    male = _make_table("t1", "Count_Person_Male", places=("country/FRA",))
    female = _make_table("t2", "Count_Person_Female", places=("country/FRA",))
    cache = _make_cache(male, female)

    bar = _resolve_chart_wire(
        "bar", ["t1", "t2"], cache, sort="descending", unit="people"
    )
    line = _resolve_chart_wire("line", ["t1"], cache, unit="people")

    assert bar is not None
    assert bar["variable_dcids"] == ["Count_Person_Male", "Count_Person_Female"]
    assert bar["sort"] == "descending"
    assert bar["unit"] == "people"
    assert line is not None and line["unit"] == "people"
    assert "sort" not in line


def test_a_line_over_too_many_places_is_rejected_unless_the_cohort() -> None:
    # Test: The place cap on explicit places.
    # Situation: A cohort table holds more places than the cap; one
    #   specification leaves the places to default and another asks for
    #   the cohort.
    # Expectation: The default is rejected, and the cohort line carries the
    #   parent place and child type.
    places = _COUNTIES
    table = _make_table(
        "t1", places=places, parent="geoId/06", child_type="County"
    )
    cache = _make_cache(table)

    assert _resolve_chart_wire("line", ["t1"], cache) is None
    cohort = _resolve_chart_wire("line", ["t1"], cache, cohort=True)

    assert cohort is not None
    assert cohort["parent_place"] == "geoId/06"
    assert cohort["child_place_type"] == "County"


def test_a_bar_without_a_place_choice_draws_its_cohort() -> None:
    # Test: The default place choice of a bar versus a line.
    # Situation: A cohort table of six states over two years, under the
    #   place cap, is charted as a bar and as a line, neither naming a
    #   place choice.
    # Expectation: The bar draws the cohort by its parent place and child
    #   type; the line lists the six places.
    table = _make_table(
        "t1", places=_STATES, parent="country/USA", child_type="State"
    )
    cache = _make_cache(table)

    bar = _resolve_chart_wire("bar", ["t1"], cache)
    line = _resolve_chart_wire("line", ["t1"], cache)

    assert bar is not None and line is not None
    assert bar["parent_place"] == "country/USA"
    assert bar["child_place_type"] == "State"
    assert "place_dcids" not in bar
    assert line["place_dcids"] == sorted(_STATES)
    assert "parent_place" not in line


def test_a_chart_pins_each_variable_to_one_facet() -> None:
    # Test: The facet invariant of a resolved chart.
    # Situation: A resolved line chart is built with two facets for one
    #   variable.
    # Expectation: `ValueError`.
    with pytest.raises(ValueError, match="one facet"):
        ResolvedLineChart(
            title="Population",
            facet_ids=(("Count_Person", "1"), ("Count_Person", "2")),
            variable_dcids=("Count_Person",),
            scope=PlaceList(("country/FRA",)),
        )


@pytest.mark.parametrize(
    ("kind", "fields", "expected_places"),
    [
        ("line", {}, None),
        ("bar", {"date": "2023"}, None),
        ("bar", {"places": ["country/DEU"]}, None),
        ("highlight", {"date": "2023"}, None),
        ("bar", {}, ["country/FRA"]),
        ("highlight", {}, ["country/FRA"]),
    ],
    ids=[
        "line_needs_two_per_capita_dates",
        "bar_rejects_numerator_only_date",
        "bar_rejects_numerator_only_place",
        "highlight_rejects_numerator_only_date",
        "bar_defaults_to_per_capita_places",
        "highlight_defaults_to_single_per_capita_place",
    ],
)
def test_a_per_capita_chart_reads_places_and_dates_from_the_derived_table(
    kind: str,
    fields: dict[str, object],
    expected_places: list[str] | None,
) -> None:
    # Test: Place and date checks on a per-capita derived table.
    # Situation: Numerator `t2` holds France and Germany in 2022 and 2023,
    #   while `Count_Person` `t1` holds only France in 2022, so `s1` holds
    #   only `(country/FRA, 2022)`.
    # Expectation: Line, 2023, and Germany specifications are rejected, while
    #   default bar and highlight specifications resolve to France alone.
    population = _make_table("t1", places=("country/FRA",), dates=("2022",))
    crimes = _make_table(
        "t2",
        "Count_Crime",
        name="Crimes",
        unit="Count",
        places=("country/FRA", "country/DEU"),
        dates=("2022", "2023"),
    )
    derived = derive_observation_table(
        crimes.table, population.table, operation="per_capita", step_id="s1"
    )
    assert derived.table is not None
    per_capita = CachedTable("s1", derived.table)
    analysis = _make_spec(
        step_id="s1",
        script="compute_derived_metric",
        left="t2",
        right="t1",
        operation="per_capita",
    )
    cache = _make_cache(population, crimes, per_capita)
    digest = _make_digest(derived.result)

    chart = _resolve_chart_wire(kind, ["s1"], cache, digest, analysis, **fields)

    if expected_places is None:
        assert chart is None
    else:
        assert chart is not None
        assert chart["place_dcids"] == expected_places
        assert chart["per_capita"] is True


def test_two_per_capita_tables_sharing_a_numerator_keep_both_tables() -> None:
    # Test: Multiple per-capita derived tables sharing one numerator table.
    # Situation: `s1` divides `t3` (France and Germany) by France's population
    #   `t1`, and `s2` divides `t3` by Germany's population `t2`.
    # Expectation: A bar over `["s1", "s2"]` keeps both derived tables rather
    #   than collapsing them by numerator ID, drawing both places.
    pop_fra = _make_table("t1", places=("country/FRA",), dates=("2023",))
    pop_deu = _make_table("t2", places=("country/DEU",), dates=("2023",))
    crimes = _make_table(
        "t3",
        "Count_Crime",
        name="Crimes",
        unit="Count",
        places=("country/FRA", "country/DEU"),
        dates=("2023",),
    )
    s1 = derive_observation_table(
        crimes.table, pop_fra.table, operation="per_capita", step_id="s1"
    )
    s2 = derive_observation_table(
        crimes.table, pop_deu.table, operation="per_capita", step_id="s2"
    )
    assert s1.table is not None and s2.table is not None
    analysis = AnalysisSpecification.model_validate(
        {
            "steps": [
                {
                    "step_id": "s1",
                    "script": "compute_derived_metric",
                    "left": "t3",
                    "right": "t1",
                    "operation": "per_capita",
                },
                {
                    "step_id": "s2",
                    "script": "compute_derived_metric",
                    "left": "t3",
                    "right": "t2",
                    "operation": "per_capita",
                },
            ]
        }
    )
    cache = _make_cache(
        pop_fra,
        pop_deu,
        crimes,
        CachedTable("s1", s1.table),
        CachedTable("s2", s2.table),
    )

    chart = _resolve_chart_wire(
        "bar",
        ["s1", "s2"],
        cache,
        _make_digest(s1.result, s2.result),
        analysis,
    )

    assert chart is not None
    assert chart["place_dcids"] == ["country/DEU", "country/FRA"]
    assert chart["variable_dcids"] == ["Count_Crime"]
    assert chart["per_capita"] is True


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"date": "2023"}, None),
        (
            {},
            {
                "viz_type": "bar",
                "title": "A chart",
                "variable_dcids": ["Count_Person"],
                "place_dcids": ["country/DEU"],
            },
        ),
    ],
    ids=["named_date_rejected", "reference_date_dropped"],
)
def test_a_bar_of_named_places_is_not_drawn_at_a_date_none_of_them_has(
    fields: dict[str, object], expected: JsonObject | None
) -> None:
    # Test: Date validation for a bar chart of named places.
    # Situation: `t1` holds France in 2022 and 2023 and Germany only in 2022,
    #   and the digest's series result over France and Spain is aligned at
    #   2023. A bar of Germany names 2023, or names no date.
    # Expectation: Naming 2023 is rejected because Germany has no 2023 value;
    #   omitting `date` drops the 2023 reference date so the component draws
    #   Germany's latest observation instead of an empty chart.
    full = _make_table("t1")
    table = replace(
        full.table,
        rows=tuple(
            row
            for row in full.table.rows
            if (row.place_dcid, row.date) != ("country/DEU", "2023")
        ),
    )
    aligned = _make_table("t1", places=("country/FRA", "country/ESP"))
    digest = _make_digest(analyze_timeseries(aligned.table, step_id="s1"))
    analysis = _make_spec(step_id="s1", script="analyze_timeseries", table="t1")

    chart = _resolve_chart_wire(
        "bar",
        ["t1"],
        _make_cache(CachedTable("t1", table)),
        digest,
        analysis,
        places=["country/DEU"],
        **fields,
    )

    assert chart == expected


def test_a_line_needs_a_charted_place_with_at_least_two_dates() -> None:
    # Test: Multi-date series check per charted place on a line chart.
    # Situation: In `staggered`, France reports only in 2022 and Germany only
    #   in 2023 (two dates in the table, one per place); in `partial`, France
    #   reports in 2022 and 2023 while Germany reports only in 2022.
    # Expectation: A line over `staggered` is rejected, a line over Germany
    #   alone in `partial` is rejected, and a line over both places in
    #   `partial` resolves because France spans two dates.
    staggered = CachedTable(
        "t1",
        ObservationTable(
            variable_dcid="Count_Person",
            variable_name="Total Population",
            unit="Person",
            scaling_factor=None,
            provenance=Provenance(),
            rows=(
                ObservationRow("country/FRA", "France", "2022", 68.0),
                ObservationRow("country/DEU", "Germany", "2023", 84.0),
            ),
            requested_places=("country/FRA", "country/DEU"),
            place_names={"country/FRA": "France", "country/DEU": "Germany"},
        ),
    )
    full = _make_table("t1")
    partial = CachedTable(
        "t1",
        replace(
            full.table,
            rows=tuple(
                row
                for row in full.table.rows
                if (row.place_dcid, row.date) != ("country/DEU", "2023")
            ),
        ),
    )

    assert _resolve_chart_wire("line", ["t1"], _make_cache(staggered)) is None
    assert (
        _resolve_chart_wire(
            "line",
            ["t1"],
            _make_cache(partial),
            places=["country/DEU"],
        )
        is None
    )
    resolved = _resolve_chart_wire(
        "line",
        ["t1"],
        _make_cache(partial),
        places=["country/FRA", "country/DEU"],
    )
    assert resolved is not None
    assert resolved["place_dcids"] == ["country/FRA", "country/DEU"]
