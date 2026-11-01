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
"""Tests for `workflows.chart_defaults`.

Covers `build_default_charts`.
"""

from collections.abc import Mapping, Sequence
from typing import cast

import pytest

from narratives_agent.analytics.composition import compute_composition
from narratives_agent.analytics.derived import derive_observation_table
from narratives_agent.analytics.digest import AnalysisDigest, ScriptResult
from narratives_agent.analytics.distribution import summarize_distribution
from narratives_agent.analytics.provenance import Provenance
from narratives_agent.analytics.ranking import rank_cohort
from narratives_agent.analytics.relations import relate_cohorts
from narratives_agent.analytics.tables import ObservationRow, ObservationTable
from narratives_agent.analytics.timeseries import analyze_timeseries
from narratives_agent.json_value import JsonObject
from narratives_agent.workflows.chart_defaults import build_default_charts
from narratives_agent.workflows.charts import (
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
    dates: Sequence[str] = ("2023",),
    facet_id: str | None = None,
) -> CachedTable:
    """Builds a table of six states of one parent."""
    return _make_table(
        table_id,
        variable_dcid,
        name=name,
        places=_STATES,
        dates=dates,
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


def _resolve_default_wire(
    digest: AnalysisDigest,
    analysis: AnalysisSpecification | None,
    cache: TurnCache,
) -> JsonObject | None:
    """Returns the one default chart for a digest, as wire, or None."""
    charts = build_default_charts(digest, analysis, cache)
    assert len(charts) <= 1
    return serialize_resolved_chart(charts[0]) if charts else None


def _make_relation_cache() -> tuple[
    TurnCache, AnalysisDigest, AnalysisSpecification
]:
    """Income for six states over 2021 and 2023 and diabetes on 2021.

    Income (`t1`) holds both 2021 and 2023 and aligns on 2023, while
    diabetes (`t2`) holds only 2021 and aligns on 2021. The relation step
    summarizes diabetes (`t2`) over the states ordered by income (`t1`),
    with groups of two.
    """
    income = _make_cohort(
        "t1",
        variable_dcid="Median_Income",
        name="Income",
        dates=("2021", "2023"),
    )
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


def _make_per_capita_case(
    *, is_cohort: bool
) -> tuple[TurnCache, CachedTable, ScriptResult]:
    """Caches population `t1`, crimes `t2`, and their per-capita table `s1`.

    With `is_cohort`, the tables cover a cohort of six states over two
    years; otherwise two countries over two years.
    """
    if is_cohort:
        population = _make_table(
            "t1", places=_STATES, parent="country/USA", child_type="State"
        )
        crimes = _make_table(
            "t2",
            "Count_Crime",
            name="Crimes",
            unit="Count",
            places=_STATES,
            parent="country/USA",
            child_type="State",
        )
    else:
        population = _make_table("t1")
        crimes = _make_table("t2", "Count_Crime", name="Crimes", unit="Count")
    derived = derive_observation_table(
        crimes.table, population.table, operation="per_capita", step_id="s1"
    )
    assert derived.table is not None
    per_capita = CachedTable("s1", derived.table)
    cache = _make_cache(population, crimes, per_capita)
    return cache, per_capita, derived.result


_PER_CAPITA_STEP: dict[str, object] = {
    "step_id": "s1",
    "script": "compute_derived_metric",
    "left": "t2",
    "right": "t1",
    "operation": "per_capita",
}


def _make_ratio_case() -> tuple[TurnCache, CachedTable, ScriptResult]:
    """Caches GDP `t1`, population `t2`, and their ratio `s1`."""
    gdp = _make_table("t1", "Amount_GDP", name="GDP", unit="USDollar")
    population = _make_table("t2")
    ratio = derive_observation_table(gdp.table, population.table, step_id="s1")
    assert ratio.table is not None
    cache = _make_cache(gdp, population, CachedTable("s1", ratio.table))
    return cache, gdp, ratio.result


def test_the_default_chart_is_a_line_for_a_series() -> None:
    # Test: The default chart of a time-series result.
    # Situation: The primary result summarizes two countries over two
    #   years.
    # Expectation: A line chart over the summarized places.
    table = _make_table("t1")
    analysis = _make_spec(step_id="s1", script="analyze_timeseries", table="t1")

    chart = _resolve_default_wire(
        _make_series_digest(table), analysis, _make_cache(table)
    )

    assert chart == {
        "viz_type": "line",
        "title": "Total Population",
        "variable_dcids": ["Count_Person"],
        "place_dcids": ["country/FRA", "country/DEU"],
    }


@pytest.mark.parametrize("raw_name", ["", "   ", "\u200b"])
def test_an_unnamed_variable_is_titled_by_its_dcid(raw_name: str) -> None:
    # Test: The default title when a variable has no usable display name.
    # Situation: The primary result summarizes a table whose variable name
    #   is empty, whitespace-only, or zero-width format characters.
    # Expectation: The line chart is titled by the variable's DCID.
    table = _make_table("t1", name=raw_name)
    analysis = _make_spec(step_id="s1", script="analyze_timeseries", table="t1")

    chart = _resolve_default_wire(
        _make_series_digest(table), analysis, _make_cache(table)
    )

    assert chart is not None
    assert chart["title"] == "Count_Person"


def test_no_default_chart_for_a_table_without_rows() -> None:
    # Test: The default floor over a cached table that has no rows.
    # Situation: A ranking result was computed over `t1`, and the cached
    #   `t1` holds no rows.
    # Expectation: No default chart, and nothing is raised.
    ranked = _make_table("t1", places=_COUNTIES[:3])
    empty = _make_table("t1", places=())
    analysis = _make_spec(step_id="s1", script="rank_cohort", table="t1")
    digest = _make_digest(rank_cohort(ranked.table, step_id="s1"))

    assert build_default_charts(digest, analysis, _make_cache(empty)) == ()


def test_the_default_chart_is_a_highlight_for_a_single_point() -> None:
    # Test: The default chart of a single observation.
    # Situation: The primary result covers one place on one date.
    # Expectation: A highlight of that place at that date.
    table = _make_table("t1", places=("country/FRA",), dates=("2023",))
    analysis = _make_spec(step_id="s1", script="analyze_timeseries", table="t1")

    chart = _resolve_default_wire(
        _make_series_digest(table), analysis, _make_cache(table)
    )

    assert chart is not None
    assert chart["viz_type"] == "highlight"
    assert chart["place_dcids"] == ["country/FRA"]
    assert chart["date"] == "2023"


def test_a_single_date_series_window_charts_at_its_summarized_date() -> None:
    # Test: The default chart of a bounded single-date time-series window.
    # Situation: Cached `t1` holds two years (`2022` and `2023`) for one
    #   country, while `analyze_timeseries` bounded the window to `2022`.
    # Expectation: A highlight at `2022`, matching the summarized window
    #   rather than a multi-year line over the cached table.
    table = _make_table("t1", places=("country/FRA",), dates=("2022", "2023"))
    analysis = _make_spec(
        step_id="s1",
        script="analyze_timeseries",
        table="t1",
        start_date="2022",
        end_date="2022",
    )
    digest = _make_digest(
        analyze_timeseries(
            table.table, start_date="2022", end_date="2022", step_id="s1"
        )
    )

    chart = _resolve_default_wire(digest, analysis, _make_cache(table))

    assert chart == {
        "viz_type": "highlight",
        "title": "Total Population",
        "variable_dcids": ["Count_Person"],
        "place_dcids": ["country/FRA"],
        "date": "2022",
    }


def test_the_default_chart_is_a_ranking_for_an_aligned_cohort() -> None:
    # Test: The default chart of a ranking over an aligned cohort.
    # Situation: The specification aligns the cohort in `s1` and ranks all
    #   six states in `s2`, so the primary result's input is a cohort step.
    # Expectation: A ranking of the full cohort at the reference date.
    table = _make_cohort()
    analysis = AnalysisSpecification.model_validate(
        {
            "steps": [
                {"step_id": "s1", "script": "align_cohort", "table": "t1"},
                {"step_id": "s2", "script": "rank_cohort", "table": "s1"},
            ]
        }
    )
    digest = _make_digest(rank_cohort(table.table, step_id="s2"))

    chart = _resolve_default_wire(digest, analysis, _make_cache(table))

    assert chart == {
        "viz_type": "ranking",
        "title": "Total Population",
        "variable_dcids": ["Count_Person"],
        "parent_place": "country/USA",
        "child_place_type": "State",
        "date": "2023",
    }


def test_a_sliced_cohort_ranking_pins_its_top_count_and_date() -> None:
    # Test: The default chart of a cohort ranking that slices a larger
    #   cohort at a non-latest date.
    # Situation: `s1` summarizes the cohort's distribution on `2023`, and
    #   `s2` ranks the top five of thirty counties at `2022`.
    # Expectation: The distribution supplies no chart, and `s2` projects a
    #   cohort ranking with `ranking_count == 5` at `2022` rather than
    #   inheriting `s1`'s `2023` reference date.
    table = _make_table(
        "t1",
        places=_COUNTIES,
        dates=("2022", "2023"),
        parent="geoId/06",
        child_type="County",
    )
    analysis = AnalysisSpecification.model_validate(
        {
            "steps": [
                {
                    "step_id": "s1",
                    "script": "summarize_distribution",
                    "table": "t1",
                },
                {
                    "step_id": "s2",
                    "script": "rank_cohort",
                    "table": "t1",
                    "n": 5,
                    "target_date": "2022",
                },
            ]
        }
    )
    digest = _make_digest(
        summarize_distribution(table.table, step_id="s1"),
        rank_cohort(
            table.table,
            max_entries_per_end=5,
            target_date="2022",
            step_id="s2",
        ),
    )

    chart = _resolve_default_wire(digest, analysis, _make_cache(table))

    assert chart == {
        "viz_type": "ranking",
        "title": "Total Population",
        "variable_dcids": ["Count_Person"],
        "parent_place": "geoId/06",
        "child_place_type": "County",
        "ranking_count": 5,
        "show_highest_lowest": False,
        "show_lowest": False,
        "date": "2022",
    }


def test_an_ascending_cohort_ranking_pins_its_bottom_count() -> None:
    # Test: The default chart of an ascending ranking over a cohort.
    # Situation: Six states are ranked ascending (`direction == "asc"`) with
    #   four entries per end.
    # Expectation: A cohort ranking with `show_lowest` set and
    #   `ranking_count == 4` at the ranking's reference date.
    table = _make_cohort()
    analysis = _make_spec(
        step_id="s1", script="rank_cohort", table="t1", direction="asc", n=4
    )
    digest = _make_digest(
        rank_cohort(
            table.table, max_entries_per_end=4, direction="asc", step_id="s1"
        )
    )

    chart = _resolve_default_wire(digest, analysis, _make_cache(table))

    assert chart == {
        "viz_type": "ranking",
        "title": "Total Population",
        "variable_dcids": ["Count_Person"],
        "parent_place": "country/USA",
        "child_place_type": "State",
        "ranking_count": 4,
        "show_highest_lowest": False,
        "show_lowest": True,
        "date": "2023",
    }


def test_the_default_chart_is_a_bar_for_a_single_place_composition() -> None:
    # Test: The default chart of a composition at its own reference date.
    # Situation: `s1` summarizes `t1`'s distribution at `2023`, and `s2`
    #   computes a composition of two component tables at `2022`.
    # Expectation: A bar over both components at `2022`, using the
    #   composition's own reference date rather than `s1`'s `2023`.
    male = _make_table("t1", "Count_Person_Male", places=("country/FRA",))
    female = _make_table("t2", "Count_Person_Female", places=("country/FRA",))
    analysis = AnalysisSpecification.model_validate(
        {
            "steps": [
                {
                    "step_id": "s1",
                    "script": "summarize_distribution",
                    "table": "t1",
                },
                {
                    "step_id": "s2",
                    "script": "compute_composition",
                    "components": ["t1", "t2"],
                    "target_date": "2022",
                },
            ]
        }
    )
    digest = _make_digest(
        summarize_distribution(male.table, step_id="s1"),
        compute_composition(
            [male.table, female.table], target_date="2022", step_id="s2"
        ),
    )

    chart = _resolve_default_wire(digest, analysis, _make_cache(male, female))

    assert chart == {
        "viz_type": "bar",
        "title": "Total Population",
        "variable_dcids": [
            "Count_Person_Male",
            "Count_Person_Female",
        ],
        "place_dcids": ["country/FRA"],
        "date": "2022",
    }


def test_no_default_chart_for_a_standalone_per_capita_derivation() -> None:
    # Test: The default floor for a standalone per-capita derivation.
    # Situation: A `compute_derived_metric` `per_capita` step is the only
    #   step in the digest, with no ranking or time-series summary over it.
    # Expectation: No default chart.
    cache, _, result = _make_per_capita_case(is_cohort=False)
    analysis = _make_spec(**_PER_CAPITA_STEP)

    assert build_default_charts(_make_digest(result), analysis, cache) == ()


@pytest.mark.parametrize("raw_name", ["", "   ", "\u200b"])
def test_the_per_capita_title_of_an_unnamed_numerator_is_its_dcid(
    raw_name: str,
) -> None:
    # Test: The default per-capita title when the numerator has no usable name.
    # Situation: A per-capita derivation divides a count with an empty,
    #   whitespace-only, or zero-width variable name by population, and `s2`
    #   ranks the derived table.
    # Expectation: The chart is titled with the numerator's DCID per person.
    population = _make_table("t1")
    crimes = _make_table("t2", "Count_Crime", name=raw_name, unit="Count")
    derived = derive_observation_table(
        crimes.table, population.table, operation="per_capita", step_id="s1"
    )
    assert derived.table is not None
    cache = _make_cache(population, crimes, CachedTable("s1", derived.table))
    ranked = rank_cohort(derived.table, step_id="s2")
    analysis = AnalysisSpecification.model_validate(
        {
            "steps": [
                _PER_CAPITA_STEP,
                {"step_id": "s2", "script": "rank_cohort", "table": "s1"},
            ]
        }
    )

    chart = _resolve_default_wire(
        AnalysisDigest(results=(derived.result, ranked), sources=()),
        analysis,
        cache,
    )

    assert chart is not None
    assert chart["title"] == "Count_Crime per person"


def test_the_default_chart_follows_a_per_capita_table_to_its_ranking() -> None:
    # Test: The default chart when a ranking consumes a per-capita table.
    # Situation: A per-capita derivation over a cohort of states, followed
    #   by a `rank_cohort` step that ranks `s1`.
    # Expectation: A per-capita cohort ranking from the downstream ranking
    #   step, drawn at its reference date.
    cache, per_capita, result = _make_per_capita_case(is_cohort=True)
    ranked = rank_cohort(per_capita.table, step_id="s2")
    analysis = AnalysisSpecification.model_validate(
        {
            "steps": [
                _PER_CAPITA_STEP,
                {"step_id": "s2", "script": "rank_cohort", "table": "s1"},
            ]
        }
    )

    chart = _resolve_default_wire(
        AnalysisDigest(results=(result, ranked), sources=()), analysis, cache
    )

    assert chart == {
        "viz_type": "ranking",
        "title": "Crimes per person",
        "variable_dcids": ["Count_Crime"],
        "parent_place": "country/USA",
        "child_place_type": "State",
        "date": "2023",
        "per_capita": True,
    }


def test_a_per_capita_ranking_without_a_numerator_cohort_is_a_bar() -> None:
    # Test: The default chart of a ranked per-capita table whose numerator
    #   was not fetched across a cohort.
    # Situation: Population is a cohort of six states, and crimes were
    #   fetched for the same six states by name, so the per-capita table
    #   holds the population's cohort while its numerator holds none. A
    #   `rank_cohort` step ranks the per-capita table.
    # Expectation: A per-capita bar of the six ranked states, as the
    #   resolver draws the numerator, which has no cohort to rank.
    population = _make_table(
        "t1", places=_STATES, parent="country/USA", child_type="State"
    )
    crimes = _make_table(
        "t2", "Count_Crime", name="Crimes", unit="Count", places=_STATES
    )
    derived = derive_observation_table(
        crimes.table, population.table, operation="per_capita", step_id="s1"
    )
    assert derived.table is not None
    assert derived.table.child_place_type == "State"
    cache = _make_cache(population, crimes, CachedTable("s1", derived.table))
    analysis = AnalysisSpecification.model_validate(
        {
            "steps": [
                _PER_CAPITA_STEP,
                {"step_id": "s2", "script": "rank_cohort", "table": "s1"},
            ]
        }
    )
    ranked = rank_cohort(derived.table, step_id="s2")

    chart = _resolve_default_wire(
        AnalysisDigest(results=(derived.result, ranked), sources=()),
        analysis,
        cache,
    )

    assert chart is not None
    assert chart["viz_type"] == "bar"
    assert chart["variable_dcids"] == ["Count_Crime"]
    assert chart["per_capita"] is True
    assert sorted(cast(list[str], chart["place_dcids"])) == sorted(_STATES)


def test_no_default_chart_for_a_distribution() -> None:
    # Test: The default floor for a `summarize_distribution` result.
    # Situation: A `summarize_distribution` step summarizes income across a
    #   cohort of states with population weights.
    # Expectation: No default chart, because distribution quantiles do not
    #   define a ranked slice or series.
    income = _make_table(
        "t1",
        "Median_Income_Person",
        name="Median income",
        unit="USDollar",
        places=_STATES,
        parent="country/USA",
        child_type="State",
    )
    weights = _make_table(
        "t2",
        "Count_Person",
        name="Population",
        places=_STATES,
        parent="country/USA",
        child_type="State",
    )
    result = summarize_distribution(
        income.table, weights=weights.table, step_id="s1"
    )
    analysis = _make_spec(
        step_id="s1",
        script="summarize_distribution",
        table="t1",
        weights="t2",
    )

    assert (
        build_default_charts(
            _make_digest(result), analysis, _make_cache(income, weights)
        )
        == ()
    )


def test_a_composition_with_an_unchartable_component_falls_through() -> None:
    # Test: The default floor's all-inputs-chartable rule for a composition.
    # Situation: A composition combines crimes `t1` with `s1`, crimes per
    #   household, a per-capita derivation whose denominator is not
    #   population, alone or followed by a series step over `t1`.
    # Expectation: Rather than charting `t1` alone as an incomplete
    #   composition, the composition produces no default chart on its own and
    #   falls through to the later series step when one is present.
    crimes = _make_table(
        "t1", "Count_Crime", name="Crimes", unit=None, dates=("2022", "2023")
    )
    homes = _make_table(
        "t2",
        "Count_Household",
        name="Households",
        unit=None,
        dates=("2022", "2023"),
    )
    derived = derive_observation_table(
        crimes.table, homes.table, operation="per_capita", step_id="s1"
    )
    assert derived.table is not None
    per_household = CachedTable("s1", derived.table)
    composition_only = AnalysisSpecification.model_validate(
        {
            "steps": [
                {
                    "step_id": "s1",
                    "script": "compute_derived_metric",
                    "left": "t1",
                    "right": "t2",
                    "operation": "per_capita",
                },
                {
                    "step_id": "s2",
                    "script": "compute_composition",
                    "components": ["s1", "t1"],
                },
            ]
        }
    )
    composition_result = compute_composition(
        (per_household.table, crimes.table), step_id="s2"
    )
    cache = _make_cache(crimes, homes, per_household)

    assert (
        build_default_charts(
            _make_digest(composition_result), composition_only, cache
        )
        == ()
    )

    with_fallback = AnalysisSpecification.model_validate(
        {
            "steps": [
                *composition_only.model_dump()["steps"],
                {
                    "step_id": "s3",
                    "script": "analyze_timeseries",
                    "table": "t1",
                },
            ]
        }
    )
    series_result = analyze_timeseries(crimes.table, step_id="s3")

    chart = _resolve_default_wire(
        _make_digest(composition_result, series_result), with_fallback, cache
    )

    assert chart is not None
    assert chart["viz_type"] == "line"
    assert chart["variable_dcids"] == ["Count_Crime"]


def test_the_default_chart_leaves_out_a_composition_total() -> None:
    # Test: Default chart table selection for a composition with a total.
    # Situation: A `compute_composition` step over two components with an
    #   explicit total table.
    # Expectation: The total table is in neither the chart's
    #   `variable_dcids` nor its title.
    solar = _make_table("t1", "Count_Solar", name="Solar", dates=("2023",))
    wind = _make_table("t2", "Count_Wind", name="Wind", dates=("2023",))
    total = _make_table(
        "t3",
        "Count_Total",
        name="Total generation",
        dates=("2023",),
        values={"country/FRA": 500.0, "country/DEU": 500.0},
    )
    result = compute_composition(
        (solar.table, wind.table), total=total.table, step_id="s1"
    )
    analysis = _make_spec(
        step_id="s1",
        script="compute_composition",
        components=["t1", "t2"],
        total="t3",
    )

    chart = _resolve_default_wire(
        _make_digest(result), analysis, _make_cache(solar, wind, total)
    )

    assert chart == {
        "viz_type": "bar",
        "title": "Solar, Wind",
        "variable_dcids": ["Count_Solar", "Count_Wind"],
        "place_dcids": ["country/FRA", "country/DEU"],
        "date": "2023",
    }


def test_no_default_chart_without_results() -> None:
    # Test: The floor of a digest without results.
    # Situation: The digest is empty and there is no specification.
    # Expectation: No charts.
    cache, _, _ = _make_ratio_case()

    assert build_default_charts(AnalysisDigest((), ()), None, cache) == ()


def test_no_default_chart_for_a_ratio_of_two_tables() -> None:
    # Test: The floor when the only result is unchartable.
    # Situation: The digest's only result is a ratio of two tables, which
    #   is not a Data Commons variable.
    # Expectation: No charts.
    cache, _, result = _make_ratio_case()
    analysis = _make_spec(
        step_id="s1", script="compute_derived_metric", left="t1", right="t2"
    )

    assert build_default_charts(_make_digest(result), analysis, cache) == ()


def test_the_default_chart_skips_an_unchartable_first_result() -> None:
    # Test: Advancing past an unchartable result.
    # Situation: The ratio result is followed by a `rank_cohort` result over
    #   the fetched GDP table.
    # Expectation: The chart comes from the ranking: a bar of the leading
    #   places at its reference date.
    cache, gdp, result = _make_ratio_case()
    ranked = rank_cohort(gdp.table, step_id="s2")
    analysis = AnalysisSpecification.model_validate(
        {
            "steps": [
                {
                    "step_id": "s1",
                    "script": "compute_derived_metric",
                    "left": "t1",
                    "right": "t2",
                },
                {"step_id": "s2", "script": "rank_cohort", "table": "t1"},
            ]
        }
    )

    chart = _resolve_default_wire(
        AnalysisDigest(results=(result, ranked), sources=()), analysis, cache
    )

    assert chart == {
        "viz_type": "bar",
        "title": "GDP",
        "variable_dcids": ["Amount_GDP"],
        "place_dcids": ["country/DEU", "country/FRA"],
        "date": "2023",
    }


def test_the_default_bar_of_an_ascending_ranking_shows_the_lowest() -> None:
    # Test: The default chart of an ascending ranking of named places.
    # Situation: Fifteen named places, with values rising in list order,
    #   are ranked ascending, ten per end, and the table has no cohort.
    # Expectation: A bar of the ten lowest places in ascending order, rather
    #   than the ten highest.
    table = _make_table("t1", places=_COUNTIES[:15], dates=("2023",))
    analysis = _make_spec(step_id="s1", script="rank_cohort", table="t1")
    ranked = rank_cohort(
        table.table, max_entries_per_end=10, direction="asc", step_id="s1"
    )

    chart = _resolve_default_wire(
        _make_digest(ranked), analysis, _make_cache(table)
    )

    assert chart is not None
    assert chart["viz_type"] == "bar"
    assert chart["place_dcids"] == list(_COUNTIES[:10])


def test_the_default_bar_of_a_short_ranking_keeps_its_count_and_date() -> None:
    # Test: The default chart of a ranking that lists fewer places than the
    #   default cap, at its own date, even when another step on the same
    #   table appears earlier in the digest.
    # Situation: `s1` summarizes `t1`'s distribution at `2023`, and `s2`
    #   ranks five of fifteen named places at `2022`.
    # Expectation: `s1` produces no chart, and `s2` projects its exact five
    #   places at `2022` directly from its own metrics.
    table = _make_table("t1", places=_COUNTIES[:15], dates=("2022", "2023"))
    analysis = AnalysisSpecification.model_validate(
        {
            "steps": [
                {
                    "step_id": "s1",
                    "script": "summarize_distribution",
                    "table": "t1",
                },
                {
                    "step_id": "s2",
                    "script": "rank_cohort",
                    "table": "t1",
                    "n": 5,
                    "target_date": "2022",
                },
            ]
        }
    )
    digest = _make_digest(
        summarize_distribution(table.table, step_id="s1"),
        rank_cohort(
            table.table,
            max_entries_per_end=5,
            target_date="2022",
            step_id="s2",
        ),
    )

    chart = _resolve_default_wire(digest, analysis, _make_cache(table))

    assert chart is not None
    assert sorted(cast(list[str], chart["place_dcids"])) == list(
        _COUNTIES[10:15]
    )
    assert chart["date"] == "2022"


def test_a_large_single_date_cohort_series_is_a_cohort_bar() -> None:
    # Test: The default chart of a one-date series over more places than
    #   the cap.
    # Situation: The primary result summarizes thirty counties of one state
    #   at one date.
    # Expectation: A bar over the cohort at that date, rather than a bar of
    #   the first twenty-five counties.
    table = _make_table(
        "t1",
        places=_COUNTIES,
        dates=("2023",),
        parent="geoId/06",
        child_type="County",
    )
    analysis = _make_spec(step_id="s1", script="analyze_timeseries", table="t1")

    chart = _resolve_default_wire(
        _make_series_digest(table), analysis, _make_cache(table)
    )

    assert chart == {
        "viz_type": "bar",
        "title": "Total Population",
        "variable_dcids": ["Count_Person"],
        "parent_place": "geoId/06",
        "child_place_type": "County",
        "date": "2023",
    }


def test_the_default_chart_of_a_single_date_series_is_a_bar() -> None:
    # Test: The default chart of a time-series result with one date.
    # Situation: The primary result summarizes two countries at one date.
    # Expectation: A bar of both countries, in the summary's order, at that
    #   date.
    table = _make_table("t1", dates=("2023",))
    analysis = _make_spec(step_id="s1", script="analyze_timeseries", table="t1")

    chart = _resolve_default_wire(
        _make_series_digest(table), analysis, _make_cache(table)
    )

    assert chart == {
        "viz_type": "bar",
        "title": "Total Population",
        "variable_dcids": ["Count_Person"],
        "place_dcids": ["country/FRA", "country/DEU"],
        "date": "2023",
    }


def test_the_default_chart_of_a_large_cohort_series_is_a_cohort_line() -> None:
    # Test: The default chart of a series over more places than the cap.
    # Situation: The primary result summarizes thirty counties over two
    #   years.
    # Expectation: A line over the cohort rather than a place list.
    table = _make_table(
        "t1", places=_COUNTIES, parent="geoId/06", child_type="County"
    )
    analysis = _make_spec(step_id="s1", script="analyze_timeseries", table="t1")

    chart = _resolve_default_wire(
        _make_series_digest(table), analysis, _make_cache(table)
    )

    assert chart == {
        "viz_type": "line",
        "title": "Total Population",
        "variable_dcids": ["Count_Person"],
        "parent_place": "geoId/06",
        "child_place_type": "County",
    }


def test_the_default_chart_of_a_large_composition_is_a_cohort_bar() -> None:
    # Test: The default chart of a composition over more places than the cap.
    # Situation: Two component tables cover thirty counties of the same
    #   parent cohort at one date.
    # Expectation: A bar over the cohort rather than a place list, at the
    #   composition's reference date.
    male = _make_table(
        "t1",
        "Count_Person_Male",
        name="Male",
        places=_COUNTIES,
        dates=("2023",),
        parent="geoId/06",
        child_type="County",
    )
    female = _make_table(
        "t2",
        "Count_Person_Female",
        name="Female",
        places=_COUNTIES,
        dates=("2023",),
        parent="geoId/06",
        child_type="County",
    )
    result = compute_composition([male.table, female.table], step_id="s1")
    analysis = _make_spec(
        step_id="s1", script="compute_composition", components=["t1", "t2"]
    )

    chart = _resolve_default_wire(
        _make_digest(result), analysis, _make_cache(male, female)
    )

    assert chart == {
        "viz_type": "bar",
        "title": "Male, Female",
        "variable_dcids": ["Count_Person_Male", "Count_Person_Female"],
        "parent_place": "geoId/06",
        "child_place_type": "County",
        "date": "2023",
    }


def test_a_large_composition_without_a_shared_cohort_caps_its_places() -> None:
    # Test: Default composition chart when only one component has a cohort.
    # Situation: `t1` was fetched across thirty counties of California,
    #   while `t2` was fetched for the same thirty counties by name without
    #   a cohort.
    # Expectation: A bar of the first twenty-five places rather than a
    #   cohort bar that the resolver would reject.
    male = _make_table(
        "t1",
        "Count_Person_Male",
        name="Male",
        places=_COUNTIES,
        dates=("2023",),
        parent="geoId/06",
        child_type="County",
    )
    female = _make_table(
        "t2",
        "Count_Person_Female",
        name="Female",
        places=_COUNTIES,
        dates=("2023",),
    )
    result = compute_composition([male.table, female.table], step_id="s1")
    analysis = _make_spec(
        step_id="s1", script="compute_composition", components=["t1", "t2"]
    )

    chart = _resolve_default_wire(
        _make_digest(result), analysis, _make_cache(male, female)
    )

    assert chart is not None
    assert chart["viz_type"] == "bar"
    assert chart["place_dcids"] == list(_COUNTIES[:25])
    assert "parent_place" not in chart


def test_the_default_chart_of_a_cohort_relation_is_a_scatter() -> None:
    # Test: The chart floor for a `relate_cohorts` result across vintages.
    # Situation: The digest's only result relates diabetes (`t2`, `2021`) to
    #   income (`t1`, `2021` and `2023`, aligned on `2023`) across a cohort
    #   of states.
    # Expectation: One scatter chart of diabetes against income across the
    #   cohort, with no pinned date so neither variable is forced onto the
    #   other's reference year.
    cache, digest, analysis = _make_relation_cache()

    chart = _resolve_default_wire(digest, analysis, cache)

    assert chart == {
        "viz_type": "scatter",
        "title": "Diabetes, Income",
        "variable_dcids": ["Percent_Diabetes", "Median_Income"],
        "parent_place": "country/USA",
        "child_place_type": "State",
    }


def test_a_same_date_cohort_relation_pins_its_shared_date() -> None:
    # Test: Date pinning on a `relate_cohorts` default scatter when both
    #   variables share one aligned reference date.
    # Situation: Diabetes and income both hold `2022` and `2023`, and
    #   `relate_cohorts` aligns both on `2022`.
    # Expectation: The default scatter is pinned to `2022`.
    income = _make_cohort(
        "t1",
        variable_dcid="Median_Income",
        name="Income",
        dates=("2022", "2023"),
    )
    diabetes = _make_table(
        "t2",
        "Percent_Diabetes",
        name="Diabetes",
        unit="Percent",
        places=_STATES,
        dates=("2022", "2023"),
        parent="country/USA",
        child_type="State",
    )
    analysis = _make_spec(
        step_id="s1",
        script="relate_cohorts",
        target="t2",
        by="t1",
        n=2,
        target_date="2022",
        by_date="2022",
    )
    digest = _make_digest(
        relate_cohorts(
            diabetes.table,
            income.table,
            n=2,
            target_date="2022",
            by_date="2022",
            step_id="s1",
        )
    )

    chart = _resolve_default_wire(
        digest, analysis, _make_cache(income, diabetes)
    )

    assert chart == {
        "viz_type": "scatter",
        "title": "Diabetes, Income",
        "variable_dcids": ["Percent_Diabetes", "Median_Income"],
        "parent_place": "country/USA",
        "child_place_type": "State",
        "date": "2022",
    }


def test_no_default_chart_for_a_named_place_relation() -> None:
    # Test: The chart floor for a `relate_cohorts` result without a cohort.
    # Situation: Diabetes and income were fetched for six named states
    #   without a parent cohort, and `relate_cohorts` is the only result.
    # Expectation: No default chart, because a scatter requires a cohort and
    #   the floor does not invent single-variable rankings.
    income = _make_table(
        "t1", "Median_Income", name="Income", places=_STATES, dates=("2023",)
    )
    diabetes = _make_table(
        "t2",
        "Percent_Diabetes",
        name="Diabetes",
        unit="Percent",
        places=_STATES,
        dates=("2023",),
    )
    analysis = _make_spec(
        step_id="s1", script="relate_cohorts", target="t2", by="t1", n=2
    )
    digest = _make_digest(
        relate_cohorts(diabetes.table, income.table, n=2, step_id="s1")
    )

    assert (
        build_default_charts(digest, analysis, _make_cache(income, diabetes))
        == ()
    )


def test_a_relation_supplies_the_floor_ahead_of_an_earlier_ranking() -> None:
    # Test: The precedence of a `relate_cohorts` result in the chart floor.
    # Situation: The specification ranks income (`s1`) and then relates
    #   diabetes to income (`s2`), and the digest holds both results.
    # Expectation: The relation supplies the floor as a scatter rather than
    #   the single income ranking.
    cache, _, _ = _make_relation_cache()
    income = cache.get("t1")
    diabetes = cache.get("t2")
    assert income is not None and diabetes is not None
    both = _make_digest(
        rank_cohort(income.table, step_id="s1"),
        relate_cohorts(diabetes.table, income.table, n=2, step_id="s2"),
    )
    analysis = AnalysisSpecification.model_validate(
        {
            "steps": [
                {"step_id": "s1", "script": "rank_cohort", "table": "t1"},
                {
                    "step_id": "s2",
                    "script": "relate_cohorts",
                    "target": "t2",
                    "by": "t1",
                    "n": 2,
                },
            ]
        }
    )

    chart = _resolve_default_wire(both, analysis, cache)

    assert chart is not None
    assert chart["viz_type"] == "scatter"
    assert chart["title"] == "Diabetes, Income"


def test_a_mixed_per_capita_relation_falls_back_to_its_ranking() -> None:
    # Test: Fallback when a `relate_cohorts` scatter mixes per-capita and
    #   raw tables.
    # Situation: `s1` derives crimes per person, `s2` ranks `s1`, and `s3`
    #   relates `s1` to raw income `t3` across states.
    # Expectation: Because a single scatter cannot mix per-capita and raw
    #   variables, `s3` is rejected and `s2` supplies the per-capita ranking.
    cache, per_capita, derived_result = _make_per_capita_case(is_cohort=True)
    income = _make_cohort("t3", variable_dcid="Median_Income", name="Income")
    cache.store_fetched(income)
    ranked = rank_cohort(per_capita.table, step_id="s2")
    related = relate_cohorts(per_capita.table, income.table, n=2, step_id="s3")
    analysis = AnalysisSpecification.model_validate(
        {
            "steps": [
                _PER_CAPITA_STEP,
                {"step_id": "s2", "script": "rank_cohort", "table": "s1"},
                {
                    "step_id": "s3",
                    "script": "relate_cohorts",
                    "target": "s1",
                    "by": "t3",
                    "n": 2,
                },
            ]
        }
    )
    digest = _make_digest(derived_result, ranked, related)

    chart = _resolve_default_wire(digest, analysis, cache)

    assert chart is not None
    assert chart["viz_type"] == "ranking"
    assert chart["title"] == "Crimes per person"
    assert chart["per_capita"] is True


def test_a_staggered_single_point_series_charts_as_a_latest_bar() -> None:
    # Test: Default chart for a multi-date table where each place has one row.
    # Situation: France reports only in 2022 and Germany only in 2023, so
    #   `analyze_timeseries` produces `point_count == 1` for each place across
    #   two distinct dates.
    # Expectation: The floor emits a `bar` over both places with no pinned
    #   date rather than a `line` that resolution would reject.
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
    analysis = _make_spec(step_id="s1", script="analyze_timeseries", table="t1")

    chart = _resolve_default_wire(
        _make_series_digest(staggered), analysis, _make_cache(staggered)
    )

    assert chart == {
        "viz_type": "bar",
        "title": "Total Population",
        "variable_dcids": ["Count_Person"],
        "place_dcids": ["country/FRA", "country/DEU"],
    }
