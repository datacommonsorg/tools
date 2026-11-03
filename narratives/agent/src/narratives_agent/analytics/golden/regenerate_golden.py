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
"""Builds and checks the golden fixture of the analytics library.

Run `uv run python -m narratives_agent.analytics.golden.regenerate_golden`
from `agent/` to rewrite `core_golden.json`, or pass `--check` to exit
non-zero when the checked-in fixture does not match the current output.
"""

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from narratives_agent.analytics.alignment import (
    align_cohort,
    find_unit_mismatch,
)
from narratives_agent.analytics.composition import compute_composition
from narratives_agent.analytics.derived import (
    compute_derived_metric,
    derive_observation_table,
)
from narratives_agent.analytics.digest import AnalysisDigest
from narratives_agent.analytics.distribution import summarize_distribution
from narratives_agent.analytics.provenance import (
    AlternativeSource,
    Provenance,
    Source,
)
from narratives_agent.analytics.ranking import rank_cohort
from narratives_agent.analytics.relations import relate_cohorts
from narratives_agent.analytics.summarize import summarize_table
from narratives_agent.analytics.tables import (
    ObservationRow,
    ObservationTable,
)
from narratives_agent.analytics.timeseries import analyze_timeseries
from narratives_agent.json_value import JsonObject, json_safe

__all__ = ["GOLDEN_PATH", "build_golden_cases", "main", "render_golden"]

GOLDEN_PATH = Path(__file__).with_name("core_golden.json")

_WDI_FACET_ID = "18369491376878146239"
_WIKIDATA_FACET_ID = "12850099660527362240"
_WDI_URL = "https://datatopics.worldbank.org/world-development-indicators/"
_WIKIDATA_URL = "https://www.wikidata.org/wiki/Wikidata:Main_Page"
_WDI_SOURCE = Source(name="datatopics.worldbank.org", url=_WDI_URL)
_WIKIDATA_SOURCE = Source(name="wikidata.org", url=_WIKIDATA_URL)
_ALTERNATIVE_WDI = AlternativeSource(
    facet_id=_WDI_FACET_ID,
    provenance_url=_WDI_URL,
    observation_period="P1Y",
)
_ALTERNATIVE_WIKIDATA = AlternativeSource(
    facet_id=_WIKIDATA_FACET_ID,
    provenance_url=_WIKIDATA_URL,
)
_ALTERNATIVE_WIKIDATA_POPULATION = AlternativeSource(
    facet_id=_WIKIDATA_FACET_ID,
    provenance_url=_WIKIDATA_URL,
    measurement_method="WikidataPopulation",
)

_POPULATION_VARIABLE = ("Count_Person", "Total population")
_CASE_COUNT_VARIABLE = ("Count_Case", "Reported cases")
_DIABETES_VARIABLE = ("Percent_Person_WithDiabetes", "Diabetes prevalence")
_THOUSANDS_SCALING_FACTOR = 1_000.0
_PER_HUNDRED_THOUSAND_SCALE = 100_000.0

_PLACE_NAMES = {
    "country/FRA": "France",
    "country/DEU": "Germany",
    "country/ZWE": "Zimbabwe",
    "country/ARG": "Argentina",
}
_COMPARISON_PLACES = {
    "country/FRA": "France",
    "country/DEU": "Germany",
}
_WEIGHTED_PLACES = {
    f"country/W{index}": f"Weighted {index}" for index in range(5)
}
_COMPOSITION_PLACES = {
    f"country/P{index}": f"Part {index}" for index in range(3)
}


def _resolve_default_alternatives(
    facet_id: str,
    variable: tuple[str, str],
) -> tuple[AlternativeSource, ...]:
    """Selects a realistic non-self-referential default alternative source."""
    if facet_id == _WIKIDATA_FACET_ID:
        return (_ALTERNATIVE_WDI,)
    if variable == _POPULATION_VARIABLE:
        return (_ALTERNATIVE_WIKIDATA_POPULATION,)
    return (_ALTERNATIVE_WIKIDATA,)


def _build_table(
    rows: Sequence[tuple[str, str, float]],
    *,
    variable: tuple[str, str] = _POPULATION_VARIABLE,
    names: Mapping[str, str] | None = None,
    requested_places: Sequence[str] | None = None,
    parent_place_dcid: str | None = None,
    child_place_type: str | None = None,
    facet_id: str = _WDI_FACET_ID,
    source: Source = _WDI_SOURCE,
    unit: str | None = None,
    scaling_factor: float | None = None,
    observation_period: str | None = "P1Y",
    alternative_sources: tuple[AlternativeSource, ...] | None = None,
) -> ObservationTable:
    """Builds an `ObservationTable` with rows sorted by `(place_dcid, date)`.

    `requested_places` becomes the table's requested places, deduplicated in
    order. When `requested_places` is `None`, the table's requested places are
    the sorted distinct places present in `rows`, matching
    `parse_observation_table`. `place_names` is keyed over the resolved
    `requested_places`. When `alternative_sources` is `None`, the non-selected
    fixture source is used so a table never lists its own selected facet as an
    alternative.

    Raises:
        ValueError: If `rows` contains duplicate `(place_dcid, date)` pairs,
            includes a place absent from `requested_places`, or lists
            `facet_id` inside `alternative_sources`.
    """
    resolved_names = dict(names or {})
    sorted_triples = sorted(rows, key=lambda item: (item[0], item[1]))
    if len({(place, date) for place, date, _ in sorted_triples}) != len(
        sorted_triples
    ):
        raise ValueError(
            "rows must not contain duplicate (place_dcid, date) pairs."
        )
    target_places = (
        tuple(dict.fromkeys(requested_places))
        if requested_places is not None
        else tuple(sorted({place for place, _, _ in sorted_triples}))
    )
    unrequested = sorted(
        {place for place, _, _ in sorted_triples} - set(target_places)
    )
    if unrequested:
        raise ValueError(
            "rows contain place(s) absent from requested_places: "
            f"{unrequested}."
        )
    place_names = {
        place: resolved_names.get(place, place) for place in target_places
    }
    observation_rows = tuple(
        ObservationRow(
            place_dcid=place,
            place_name=place_names[place],
            date=date,
            value=value,
            facet_id=facet_id,
        )
        for place, date, value in sorted_triples
    )
    resolved_alternatives = (
        _resolve_default_alternatives(facet_id, variable)
        if alternative_sources is None
        else alternative_sources
    )
    if any(
        alternative.facet_id == facet_id
        for alternative in resolved_alternatives
    ):
        raise ValueError(
            "alternative_sources must not include the selected facet "
            f"{facet_id!r}."
        )
    variable_dcid, variable_name = variable
    return ObservationTable(
        variable_dcid=variable_dcid,
        variable_name=variable_name,
        unit=unit,
        scaling_factor=scaling_factor,
        provenance=Provenance(sources=(source,), facet_ids=(facet_id,)),
        rows=observation_rows,
        requested_places=target_places,
        place_names=place_names,
        parent_place_dcid=parent_place_dcid,
        child_place_type=child_place_type,
        observation_period=observation_period,
        facet_id=facet_id,
        source=source,
        alternative_sources=resolved_alternatives,
    )


def _build_series_table(
    place: str,
    values: Sequence[tuple[str, float]],
) -> ObservationTable:
    """Builds a single-place series table."""
    return _build_table(
        [(place, date, value) for date, value in values],
        names=_PLACE_NAMES,
        requested_places=[place],
    )


def _build_single_point_table() -> ObservationTable:
    """Builds a single-observation series table for France on 2023."""
    return _build_series_table("country/FRA", [("2023", 68_287_487.0)])


def _build_multi_decade_values() -> list[tuple[str, float]]:
    """Returns a 2000 to 2020 series with a 2005 peak and a 2010 trough.

    The series ends at double its starting value.
    """
    return [
        ("2000", 100.0),
        ("2001", 110.0),
        ("2002", 120.0),
        ("2003", 130.0),
        ("2004", 140.0),
        ("2005", 180.0),
        ("2006", 150.0),
        ("2007", 140.0),
        ("2008", 130.0),
        ("2009", 120.0),
        ("2010", 100.0),
        ("2011", 110.0),
        ("2012", 120.0),
        ("2013", 130.0),
        ("2014", 140.0),
        ("2015", 150.0),
        ("2016", 160.0),
        ("2017", 170.0),
        ("2018", 180.0),
        ("2019", 190.0),
        ("2020", 200.0),
    ]


def _build_multi_decade_table() -> ObservationTable:
    """Builds the 2000 to 2020 positive series table for Germany."""
    return _build_series_table("country/DEU", _build_multi_decade_values())


def _build_shared_dates_table() -> ObservationTable:
    """Builds a two-country table sharing observation dates 2020 and 2021."""
    return _build_table(
        [
            ("country/FRA", "2020", 67.0),
            ("country/FRA", "2021", 67.5),
            ("country/DEU", "2020", 83.0),
            ("country/DEU", "2021", 83.2),
        ],
        names=_COMPARISON_PLACES,
        requested_places=list(_COMPARISON_PLACES),
    )


def _build_cohort_table() -> ObservationTable:
    """Builds a ten-country cohort with staggered latest dates.

    Nine countries report 2022, two of them also report 2023, and the tenth
    reports only 2021.
    """
    places = {f"country/C{index}": f"Country {index}" for index in range(10)}
    rows: list[tuple[str, str, float]] = []
    for index, place in enumerate(places):
        if index == 9:
            rows.append((place, "2021", 900.0))
            continue
        rows.append((place, "2022", float((index * 37) % 11) * 100.0))
        if index < 2:
            rows.append((place, "2023", float(index + 1) * 1_000.0))
    return _build_table(
        rows,
        names=places,
        facet_id=_WIKIDATA_FACET_ID,
        source=_WIKIDATA_SOURCE,
        parent_place_dcid="Earth",
        child_place_type="Country",
    )


def _build_tied_cohort_table() -> ObservationTable:
    """Builds five places on one date with the values 10, 8, 8, 5, and 5."""
    rows = [
        ("geoId/04", "2022", 5.0),
        ("geoId/02", "2022", 8.0),
        ("geoId/01", "2022", 10.0),
        ("geoId/05", "2022", 5.0),
        ("geoId/03", "2022", 8.0),
    ]
    return _build_table(
        rows,
        names={f"geoId/0{index}": f"State {index}" for index in range(1, 6)},
    )


def _build_sparse_cohort_table(
    *,
    variable: tuple[str, str] = _POPULATION_VARIABLE,
    unit: str | None = None,
) -> ObservationTable:
    """Builds ten requested places of which only three report."""
    places = [f"country/S{index}" for index in range(10)]
    return _build_table(
        [
            (places[0], "2022", 1.0),
            (places[1], "2022", 2.0),
            (places[2], "2022", 3.0),
        ],
        variable=variable,
        names={place: f"Sparse {index}" for index, place in enumerate(places)},
        requested_places=places,
        unit=unit,
    )


def _build_variable_table(
    variable: tuple[str, str],
    values: Sequence[tuple[str, str, float]],
    *,
    names: Mapping[str, str],
    unit: str | None = None,
    scaling_factor: float | None = None,
    facet_id: str = _WDI_FACET_ID,
    source: Source = _WDI_SOURCE,
) -> ObservationTable:
    """Builds a table for `variable` requested for `names`."""
    return _build_table(
        values,
        variable=variable,
        names=names,
        requested_places=list(names),
        unit=unit,
        scaling_factor=scaling_factor,
        facet_id=facet_id,
        source=source,
    )


def _build_currency_tables() -> tuple[
    ObservationTable, ObservationTable, ObservationTable
]:
    """Builds three tables with distinct variables, units, and scales."""
    names = {"country/FRA": _PLACE_NAMES["country/FRA"]}
    rows = [("country/FRA", "2022", 1.0)]
    dollars = _build_variable_table(
        (
            "Amount_EconomicActivity_GrossDomesticProduction_Nominal",
            "Nominal GDP",
        ),
        rows,
        names=names,
        unit="USDollar",
    )
    euros = _build_variable_table(
        ("Amount_Debt_Government", "Government debt"),
        rows,
        names=names,
        unit="Euro",
    )
    thousands = _build_variable_table(
        ("Amount_Consumption_Households", "Household consumption"),
        rows,
        names=names,
        unit="USDollar",
        scaling_factor=_THOUSANDS_SCALING_FACTOR,
    )
    return dollars, euros, thousands


def _build_income_table() -> ObservationTable:
    """Builds median income for five places on 2022, from WDI."""
    incomes = [20_000.0, 30_000.0, 40_000.0, 50_000.0, 100_000.0]
    return _build_variable_table(
        ("Median_Income_Person", "Median income"),
        [
            (place, "2022", income)
            for place, income in zip(_WEIGHTED_PLACES, incomes, strict=True)
        ],
        names=_WEIGHTED_PLACES,
        unit="USDollar",
    )


def _build_weights_table() -> ObservationTable:
    """Builds population weights for the same five places, from Wikidata.

    The last place holds six tenths of the population, so the weighted mean
    income is far above the unweighted one.
    """
    populations = [1_000.0, 1_000.0, 1_000.0, 1_000.0, 6_000.0]
    return _build_variable_table(
        _POPULATION_VARIABLE,
        [
            (place, "2022", population)
            for place, population in zip(
                _WEIGHTED_PLACES, populations, strict=True
            )
        ],
        names=_WEIGHTED_PLACES,
        facet_id=_WIKIDATA_FACET_ID,
        source=_WIKIDATA_SOURCE,
    )


def _build_rows_on(
    places: Sequence[str], date: str, values: Sequence[float]
) -> list[tuple[str, str, float]]:
    """Pairs each place with its value on one date."""
    return [
        (place, date, value)
        for place, value in zip(places, values, strict=True)
    ]


def _build_composition_tables() -> tuple[
    ObservationTable, ObservationTable, ObservationTable
]:
    """Builds a population total and male and female counts for three places.

    The counts fall short of the total by 20, 0, and 100 people, so the
    composition leaves a remainder unallocated for two of the places.
    """
    places = list(_COMPOSITION_PLACES)
    total = _build_variable_table(
        _POPULATION_VARIABLE,
        _build_rows_on(places, "2022", [1_000.0, 2_000.0, 4_000.0]),
        names=_COMPOSITION_PLACES,
    )
    male = _build_variable_table(
        ("Count_Person_Male", "Male population"),
        _build_rows_on(places, "2022", [480.0, 1_000.0, 1_900.0]),
        names=_COMPOSITION_PLACES,
        facet_id=_WIKIDATA_FACET_ID,
        source=_WIKIDATA_SOURCE,
    )
    female = _build_variable_table(
        ("Count_Person_Female", "Female population"),
        _build_rows_on(places, "2022", [500.0, 1_000.0, 2_000.0]),
        names=_COMPOSITION_PLACES,
        facet_id=_WIKIDATA_FACET_ID,
        source=_WIKIDATA_SOURCE,
    )
    return total, male, female


def _build_urban_table() -> ObservationTable:
    """Builds an urban population count overlapping male and female counts.

    Added to the male and female counts, it exceeds the total for every
    place, because the three variables are not disjoint parts of it.
    """
    return _build_variable_table(
        ("Count_Person_Urban", "Urban population"),
        _build_rows_on(
            list(_COMPOSITION_PLACES), "2022", [500.0, 1_000.0, 2_000.0]
        ),
        names=_COMPOSITION_PLACES,
        facet_id=_WIKIDATA_FACET_ID,
        source=_WIKIDATA_SOURCE,
    )


def _build_stage_tables() -> list[ObservationTable]:
    """Builds three ordered education stages for two places on 2022."""
    places = list(_COMPOSITION_PLACES)[:2]
    names = {place: _COMPOSITION_PLACES[place] for place in places}
    stages = (
        ("Count_Student_Primary", "Primary students", (1_000.0, 500.0)),
        ("Count_Student_Secondary", "Secondary students", (800.0, 300.0)),
        ("Count_Student_Tertiary", "Tertiary students", (400.0, 90.0)),
    )
    return [
        _build_variable_table(
            (dcid, name),
            _build_rows_on(places, "2022", values),
            names=names,
        )
        for dcid, name, values in stages
    ]


def _build_case_tables() -> tuple[ObservationTable, ObservationTable]:
    """Builds case counts from WDI and populations from Wikidata, 2020 to 2022.

    France's population is flat and its cases triple; Germany's population
    grows faster than its cases, so the per-capita rates move in opposite
    directions and end on different values.
    """
    cases = _build_variable_table(
        _CASE_COUNT_VARIABLE,
        [
            ("country/FRA", "2020", 100.0),
            ("country/FRA", "2021", 200.0),
            ("country/FRA", "2022", 300.0),
            ("country/DEU", "2020", 400.0),
            ("country/DEU", "2021", 500.0),
            ("country/DEU", "2022", 600.0),
        ],
        names=_COMPARISON_PLACES,
    )
    population = _build_variable_table(
        _POPULATION_VARIABLE,
        [
            ("country/FRA", "2020", 1_000_000.0),
            ("country/FRA", "2021", 1_000_000.0),
            ("country/FRA", "2022", 1_000_000.0),
            ("country/DEU", "2020", 1_000_000.0),
            ("country/DEU", "2021", 1_500_000.0),
            ("country/DEU", "2022", 2_400_000.0),
        ],
        names=_COMPARISON_PLACES,
        facet_id=_WIKIDATA_FACET_ID,
        source=_WIKIDATA_SOURCE,
    )
    return cases, population


def _build_non_positive_denominator_tables() -> tuple[
    ObservationTable, ObservationTable
]:
    """Builds case counts paired with zero and negative populations."""
    cases = _build_variable_table(
        _CASE_COUNT_VARIABLE,
        [("country/FRA", "2022", 5.0), ("country/DEU", "2022", 5.0)],
        names=_COMPARISON_PLACES,
    )
    zero_population = _build_variable_table(
        _POPULATION_VARIABLE,
        [("country/FRA", "2022", 0.0), ("country/DEU", "2022", -1.0)],
        names=_COMPARISON_PLACES,
        facet_id=_WIKIDATA_FACET_ID,
        source=_WIKIDATA_SOURCE,
    )
    return cases, zero_population


def _build_relation_tables() -> tuple[ObservationTable, ObservationTable]:
    """Builds a health rate on 2021 and an income on 2022 for six counties each.

    Income covers counties 1 to 6 with a tie between counties 2 and 3; the
    health rate covers counties 1 to 5 and county 9, so each side has a
    place the other lacks and the two cohorts align on different dates.
    """
    income_places = [f"geoId/0600{index}" for index in range(1, 7)]
    health_places = [f"geoId/0600{index}" for index in (1, 2, 3, 4, 5, 9)]
    income = _build_table(
        _build_rows_on(
            income_places,
            "2022",
            [90_000.0, 70_000.0, 70_000.0, 50_000.0, 40_000.0, 30_000.0],
        ),
        variable=("Median_Income_Household", "Median household income"),
        names={place: f"County {place[-1]}" for place in income_places},
        parent_place_dcid="geoId/06",
        child_place_type="County",
        unit="USDollar",
    )
    health = _build_table(
        _build_rows_on(
            health_places, "2021", [7.5, 9.0, 8.0, 11.5, 12.0, 10.0]
        ),
        variable=_DIABETES_VARIABLE,
        names={place: f"County {place[-1]}" for place in health_places},
        parent_place_dcid="geoId/06",
        child_place_type="County",
        facet_id=_WIKIDATA_FACET_ID,
        source=_WIKIDATA_SOURCE,
        unit="Percent",
    )
    return health, income


def _build_timeseries_cases() -> JsonObject:
    """Builds the time-series and multi-decade summary golden cases."""
    positive = _build_multi_decade_table()
    zero_start = _build_series_table(
        "country/ZWE", [("2010", 0.0), ("2015", 25.0), ("2020", 50.0)]
    )
    negative_end = _build_series_table(
        "country/ARG", [("2010", 50.0), ("2015", 10.0), ("2020", -5.0)]
    )
    daily_change = _build_series_table(
        "country/FRA", [("2020-03-01", 1.0), ("2020-03-02", 10.0)]
    )
    mixed_precision = _build_series_table(
        "country/FRA", [("2020", 5.0), ("2020-01", 50.0)]
    )
    disjoint = _build_table(
        [
            ("country/FRA", "2010", 65.0),
            ("country/FRA", "2011", 65.3),
            ("country/DEU", "2020", 83.0),
            ("country/DEU", "2021", 83.2),
        ],
        names=_COMPARISON_PLACES,
        requested_places=list(_COMPARISON_PLACES),
    )
    return {
        "timeseries_single_point": analyze_timeseries(
            _build_single_point_table()
        ).to_dict(),
        "timeseries_multi_decade_positive": analyze_timeseries(
            positive
        ).to_dict(),
        "summary_multi_decade_positive": json_safe(summarize_table(positive)),
        "timeseries_zero_start": analyze_timeseries(zero_start).to_dict(),
        "timeseries_negative_end": analyze_timeseries(negative_end).to_dict(),
        "timeseries_daily_change_under_a_year": analyze_timeseries(
            daily_change
        ).to_dict(),
        "timeseries_mixed_precision": analyze_timeseries(
            mixed_precision
        ).to_dict(),
        "timeseries_multi_place_shared_date": analyze_timeseries(
            _build_shared_dates_table()
        ).to_dict(),
        "timeseries_multi_place_disjoint_dates": analyze_timeseries(
            disjoint
        ).to_dict(),
    }


def _build_cohort_and_ranking_cases() -> JsonObject:
    """Builds the cohort alignment, cohort summary, and ranking golden cases."""
    cohort = _build_cohort_table()
    tied = _build_tied_cohort_table()
    sparse = _build_sparse_cohort_table()
    return {
        "alignment_prefers_coverage_over_recency": json_safe(
            align_cohort(cohort)
        ),
        "summary_cohort": json_safe(summarize_table(cohort)),
        "ranking_with_ties": rank_cohort(
            tied,
            max_entries_per_end=3,
            focal_places=["geoId/05", "geoId/09"],
        ).to_dict(),
        "ranking_with_ties_ascending": rank_cohort(
            tied, max_entries_per_end=2, direction="asc"
        ).to_dict(),
        "refusal_insufficient_coverage": json_safe(align_cohort(sparse)),
        "refusal_ranking_insufficient_coverage": rank_cohort(sparse).to_dict(),
        "refusal_ranking_invalid_n": rank_cohort(
            tied, max_entries_per_end=0
        ).to_dict(),
    }


def _build_empty_and_unit_cases() -> JsonObject:
    """Builds the empty-table and unit/scaling compatibility golden cases."""
    empty = _build_table(
        [],
        requested_places=["country/FRA"],
        facet_id=_WIKIDATA_FACET_ID,
        source=_WIKIDATA_SOURCE,
        observation_period=None,
        alternative_sources=(),
    )
    dollars, euros, thousands = _build_currency_tables()
    return {
        "summary_empty_table": json_safe(summarize_table(empty)),
        "refusal_empty_table_alignment": json_safe(align_cohort(empty)),
        "refusal_empty_table_timeseries": analyze_timeseries(empty).to_dict(),
        "refusal_unit_mismatch": json_safe(find_unit_mismatch(dollars, euros)),
        "refusal_scaling_mismatch": json_safe(
            find_unit_mismatch(dollars, thousands)
        ),
        "compatible_units": json_safe(find_unit_mismatch(dollars, dollars)),
    }


def _build_digest_cases() -> JsonObject:
    """Builds the `AnalysisDigest` serialization and prompt golden cases."""
    digest = AnalysisDigest.from_results(
        (
            analyze_timeseries(_build_multi_decade_table(), step_id="s1"),
            rank_cohort(
                _build_cohort_table(), max_entries_per_end=3, step_id="s2"
            ),
        ),
        missing_notes=("No county-level series was found for this topic.",),
    )
    return {
        "digest": digest.to_dict(),
        "digest_prompt": digest.format_for_prompt(),
    }


def _build_distribution_cases() -> JsonObject:
    """Builds the `summarize_distribution` golden cases and refusal."""
    return {
        "distribution_with_focal_places": summarize_distribution(
            _build_cohort_table(), focal_places=["country/C3", "country/C9"]
        ).to_dict(),
        "distribution_with_population_weights": summarize_distribution(
            _build_income_table(), weights=_build_weights_table()
        ).to_dict(),
        "distribution_one_place": summarize_distribution(
            _build_single_point_table(), focal_places=["country/FRA"]
        ).to_dict(),
        "distribution_two_places": summarize_distribution(
            _build_shared_dates_table()
        ).to_dict(),
        "refusal_distribution_insufficient_coverage": summarize_distribution(
            _build_sparse_cohort_table()
        ).to_dict(),
    }


def _build_composition_cases() -> JsonObject:
    """Builds the `compute_composition` golden cases and refusals."""
    total, male, female = _build_composition_tables()
    dollars, euros, thousands = _build_currency_tables()
    return {
        "composition_with_total": compute_composition(
            [male, female], total=total
        ).to_dict(),
        "composition_implied_total": compute_composition(
            [male, female]
        ).to_dict(),
        "refusal_composition_components_exceed_total": compute_composition(
            [male, female, _build_urban_table()], total=total
        ).to_dict(),
        "composition_stages": compute_composition(
            _build_stage_tables(), mode="stages"
        ).to_dict(),
        "refusal_composition_unit_mismatch": compute_composition(
            [euros], total=dollars
        ).to_dict(),
        "refusal_composition_scaling_mismatch": compute_composition(
            [thousands], total=dollars
        ).to_dict(),
        "refusal_composition_insufficient_coverage": compute_composition(
            [_build_sparse_cohort_table()]
        ).to_dict(),
    }


def _build_derived_cases() -> JsonObject:
    """Builds the derived-metric, multi-step chaining, and refusal cases."""
    case_counts, case_population = _build_case_tables()
    per_capita = derive_observation_table(
        case_counts,
        case_population,
        operation="per_capita",
        scale=_PER_HUNDRED_THOUSAND_SCALE,
    )
    if per_capita.table is None:
        raise RuntimeError(
            "derive_observation_table returned a refusal for the per-capita "
            f"fixture: {per_capita.result.refusal_reason}."
        )
    total, male, female = _build_composition_tables()
    dollars, euros, thousands = _build_currency_tables()
    zero_cases, zero_population = _build_non_positive_denominator_tables()

    chained_ranking = rank_cohort(
        per_capita.table, max_entries_per_end=2, step_id="s2"
    )
    chained_distribution = summarize_distribution(
        per_capita.table, focal_places=["country/FRA"], step_id="s3"
    )
    chained_series = analyze_timeseries(per_capita.table, step_id="s4")
    derived_digest = AnalysisDigest.from_results(
        (
            per_capita.result,
            chained_ranking,
            chained_distribution,
            chained_series,
        )
    )
    return {
        "derived_per_capita": per_capita.result.to_dict(),
        "derived_per_capita_table": json_safe(per_capita.table),
        "derived_difference": compute_derived_metric(
            total, female, operation="difference"
        ).to_dict(),
        "derived_pct_change": compute_derived_metric(
            male, female, operation="pct_change"
        ).to_dict(),
        "refusal_derived_unit_mismatch": compute_derived_metric(
            dollars, euros, operation="difference"
        ).to_dict(),
        "refusal_derived_scaling_mismatch": compute_derived_metric(
            dollars, thousands, operation="ratio"
        ).to_dict(),
        "refusal_derived_non_positive_denominator": compute_derived_metric(
            zero_cases, zero_population, operation="per_capita"
        ).to_dict(),
        "derived_chained_ranking": chained_ranking.to_dict(),
        "derived_chained_distribution": chained_distribution.to_dict(),
        "derived_chained_timeseries": chained_series.to_dict(),
        "derived_digest": derived_digest.to_dict(),
        "derived_digest_prompt": derived_digest.format_for_prompt(),
    }


def _build_relation_cases() -> JsonObject:
    """Builds the `relate_cohorts` two-cohort golden case and refusal."""
    relation_target, relation_by = _build_relation_tables()
    sparse_target = _build_sparse_cohort_table(
        variable=_DIABETES_VARIABLE,
        unit="Percent",
    )
    return {
        "relation_two_cohorts": relate_cohorts(
            relation_target, relation_by, n=2
        ).to_dict(),
        "refusal_relation_insufficient_coverage": relate_cohorts(
            sparse_target, _build_cohort_table()
        ).to_dict(),
    }


def _merge_case_families(families: Sequence[JsonObject]) -> JsonObject:
    """Merges per-family case mappings, rejecting duplicate case names."""
    merged: JsonObject = {}
    for family in families:
        duplicate_keys = sorted(merged.keys() & family.keys())
        if duplicate_keys:
            joined = ", ".join(duplicate_keys)
            raise ValueError(f"Duplicate golden case name(s): {joined}.")
        merged.update(family)
    return merged


def build_golden_cases() -> JsonObject:
    """Runs every golden case and returns the serialized expectations.

    Returns:
        A JSON object mapping each case name to the serialized output of
        the analytics call that the case runs.

    Raises:
        ValueError: If more than one case-family builder defines the same
            case name.
        RuntimeError: If `derive_observation_table` returns a refusal for
            the per-capita fixture inputs.
    """
    return _merge_case_families(
        (
            _build_timeseries_cases(),
            _build_cohort_and_ranking_cases(),
            _build_empty_and_unit_cases(),
            _build_digest_cases(),
            _build_distribution_cases(),
            _build_composition_cases(),
            _build_derived_cases(),
            _build_relation_cases(),
        )
    )


def render_golden(cases: JsonObject) -> str:
    """Serializes the cases as the exact text of the fixture file.

    Args:
        cases: The case names and their serialized outputs, as returned by
            `build_golden_cases`.

    Returns:
        Indented JSON with sorted keys and a trailing newline, so equal cases
        always render to identical text.

    Raises:
        ValueError: If `cases` contains a non-finite float (`NaN` or
            infinity).
    """
    return json.dumps(cases, indent=2, sort_keys=True, allow_nan=False) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Regenerates the fixture, or checks it when `--check` is given.

    Args:
        argv: The command-line arguments, without the program name. `None`
            reads them from `sys.argv`.

    Returns:
        The process exit status: 0 when the fixture was written or matches
        the current output, and 1 when `--check` finds it missing or out of
        date. `--check` never writes the file.

    Raises:
        SystemExit: If `argparse` rejects unrecognized flags or `--help` is
            requested.
    """
    parser = argparse.ArgumentParser(
        description="Regenerate or check the analytics golden fixture."
    )
    parser.add_argument(
        "--check",
        dest="is_check_mode",
        action="store_true",
        help="Exit with status 1 when the fixture does not match the code.",
    )
    arguments = parser.parse_args(argv)
    rendered = render_golden(build_golden_cases())
    if arguments.is_check_mode:
        current = (
            GOLDEN_PATH.read_text(encoding="utf-8")
            if GOLDEN_PATH.exists()
            else ""
        )
        if current != rendered:
            print(
                f"{GOLDEN_PATH} is out of date; rerun without --check to "
                "regenerate it and review the diff.",
                file=sys.stderr,
            )
            return 1
        print(f"{GOLDEN_PATH} matches the current code.")
        return 0
    GOLDEN_PATH.write_text(rendered, encoding="utf-8")
    print(f"Wrote {GOLDEN_PATH}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
