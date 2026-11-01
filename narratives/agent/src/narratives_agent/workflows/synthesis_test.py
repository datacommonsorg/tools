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
"""Tests for `workflows.synthesis`.

Covers `build_synthesis_inputs` and `render_synthesis_message`.
"""

from collections.abc import Mapping, Sequence
from dataclasses import replace

import pytest

from narratives_agent.analytics.derived import derive_observation_table
from narratives_agent.analytics.digest import AnalysisDigest, ScriptResult
from narratives_agent.analytics.provenance import Provenance, Source
from narratives_agent.analytics.tables import (
    MAX_NAME_CHARS,
    ObservationRow,
    ObservationTable,
)
from narratives_agent.analytics.timeseries import analyze_timeseries
from narratives_agent.workflows.charts import INVENTORY_PLACE_CAP
from narratives_agent.workflows.specification import AnalysisSpecification
from narratives_agent.workflows.synthesis import (
    SynthesisSource,
    TableDerivation,
    build_synthesis_inputs,
    render_synthesis_message,
)
from narratives_agent.workflows.turn_cache import CachedTable

_INSEE = Source(name="INSEE", url="https://insee.fr/")
# Thirty counties of one state, more than an explicit place list allows.
_COUNTIES = tuple(f"geoId/{number:05d}" for number in range(30))


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


def _make_spec(**fields: object) -> AnalysisSpecification:
    """Builds a one-step specification with the given step fields."""
    return AnalysisSpecification.model_validate({"steps": [fields]})


def _make_digest(*results: ScriptResult) -> AnalysisDigest:
    """Builds a digest from script results that cite nothing."""
    return AnalysisDigest.from_results(results)


def _make_sourced_digest(entry: CachedTable) -> AnalysisDigest:
    """Builds a digest of one time-series summary of `entry` citing INSEE."""
    sourced = replace(entry.table, provenance=Provenance(sources=(_INSEE,)))
    return _make_digest(analyze_timeseries(sourced, step_id="s1"))


def test_prompt_inputs_keep_external_text_typed_and_drop_findings() -> None:
    # Test: The typed inputs of the synthesis user message.
    # Situation: A specification with a finding derives a per-capita table
    #   `s1` from a fetched count and population, and a ratio `s2` of two
    #   other tables; the digest has one result and a missing-data note,
    #   and two sources are streamed, one of them named only by its URL.
    # Expectation: The sources and the inventory are typed fields; the
    #   finding appears nowhere; `s1` is chartable per capita, `s2` is
    #   unchartable, a fetched table lists its places by DCID and name, and
    #   the per-capita calculation appears once, in the digest.
    population = _make_table("t1")
    count = _make_table("t2", "Count_Crime", name="Crimes", unit="Count")
    gdp = _make_table("t3", "Amount_GDP", name="GDP", unit="USDollar")
    spec = AnalysisSpecification.model_validate(
        {
            "steps": [
                {
                    "step_id": "s1",
                    "script": "compute_derived_metric",
                    "left": "t2",
                    "right": "t1",
                    "operation": "per_capita",
                },
                {
                    "step_id": "s2",
                    "script": "compute_derived_metric",
                    "left": "t3",
                    "right": "t2",
                    "operation": "ratio",
                },
            ],
            "findings": ["France publishes an annual estimate."],
        }
    )
    per_capita = derive_observation_table(
        count.table, population.table, operation="per_capita", step_id="s1"
    )
    ratio = derive_observation_table(gdp.table, count.table, step_id="s2")
    assert per_capita.table is not None and ratio.table is not None
    per_capita_cached = CachedTable("s1", per_capita.table)
    ratio_cached = CachedTable("s2", ratio.table)
    digest = AnalysisDigest(
        results=(per_capita.result,),
        sources=(),
        missing_notes=("No county breakdown exists.",),
    )

    inputs = build_synthesis_inputs(
        "Crime per person?",
        digest,
        spec,
        (population, count, gdp, per_capita_cached, ratio_cached),
        [
            _INSEE,
            Source(name="", url="https://bls.gov/"),
            Source(name="Census", url=""),
        ],
    )
    message = render_synthesis_message(inputs)

    assert inputs.sources == (
        SynthesisSource("INSEE", "https://insee.fr/"),
        SynthesisSource("https://bls.gov/", "https://bls.gov/"),
        SynthesisSource("Census", ""),
    )
    derivations = {item.table_id: item.derivation for item in inputs.inventory}
    assert derivations == {
        "t1": None,
        "t2": None,
        "t3": None,
        "s1": TableDerivation(
            "t2", "t1", is_charted_per_capita=True, scale=1.0
        ),
        "s2": TableDerivation("t3", "t2", is_charted_per_capita=False),
    }
    assert inputs.inventory[0].places == (
        ("country/DEU", "DEU"),
        ("country/FRA", "FRA"),
    )
    formula = per_capita.table.provenance.methodology
    assert formula is not None
    assert message.count(formula) == 1
    assert "France publishes an annual estimate." not in message
    assert "[1] INSEE - https://insee.fr/" in message
    assert "[2] https://bls.gov/\n" in message
    assert "[3] Census\n" in message
    assert "Step s1: compute_derived_metric" in message
    assert "- No county breakdown exists." in message
    assert (
        "- t1: Total Population (Count_Person); unit: Person; 2 places; "
        "dates 2022 to 2023; places with data: DEU (country/DEU), FRA "
        "(country/FRA)"
    ) in message
    assert (
        "- s1 (derived from t2 and t1; chartable, the chart shows values per "
        "person)"
    ) in message
    assert (
        "- s2 (derived from t3 and t2; not a Data Commons variable, do not "
        "chart it)"
    ) in message


def test_the_inventory_states_the_scale_of_a_per_capita_digest() -> None:
    # Test: The per-capita scale in the inventory.
    # Situation: A per-capita table is computed per 100,000 people, and the
    #   digest holds its result.
    # Expectation: Its inventory line states that the digest reports values
    #   per 100000 people and that the chart shows values per person.
    population = _make_table("t1")
    count = _make_table("t2", "Count_Crime", name="Crimes", unit="Count")
    spec = _make_spec(
        step_id="s1",
        script="compute_derived_metric",
        left="t2",
        right="t1",
        operation="per_capita",
        scale=100_000,
    )
    derived = derive_observation_table(
        count.table,
        population.table,
        operation="per_capita",
        scale=100_000,
        step_id="s1",
    )
    assert derived.table is not None

    message = render_synthesis_message(
        build_synthesis_inputs(
            "q",
            _make_digest(derived.result),
            spec,
            (population, count, CachedTable("s1", derived.table)),
            [],
        )
    )

    assert (
        "- s1 (derived from t2 and t1; chartable, the digest reports values "
        "per 100000 people and the chart shows values per person)"
    ) in message


def test_a_per_capita_table_states_its_numerator_cohort() -> None:
    # Test: The cohort the inventory states for a per-capita table.
    # Situation: Population is a cohort of three states, and crimes were
    #   fetched for the same three states by name, so the per-capita table
    #   `s1` holds the population's cohort while its numerator holds none.
    # Expectation: The `s1` item has no cohort and its line counts its
    #   places, because a chart of `s1` draws the numerator, which has no
    #   cohort to draw.
    states = ("geoId/01", "geoId/02", "geoId/03")
    population = _make_table(
        "t1", places=states, parent="country/USA", child_type="State"
    )
    count = _make_table(
        "t2", "Count_Crime", name="Crimes", unit="Count", places=states
    )
    derived = derive_observation_table(
        count.table, population.table, operation="per_capita", step_id="s1"
    )
    assert derived.table is not None
    assert derived.table.child_place_type == "State"
    spec = _make_spec(
        step_id="s1",
        script="compute_derived_metric",
        left="t2",
        right="t1",
        operation="per_capita",
    )

    inputs = build_synthesis_inputs(
        "q",
        _make_digest(derived.result),
        spec,
        (population, count, CachedTable("s1", derived.table)),
        [],
    )

    cohorts = {item.table_id: item.cohort for item in inputs.inventory}
    assert cohorts["s1"] is None
    assert cohorts["t1"] is not None
    line = next(
        text
        for text in render_synthesis_message(inputs).splitlines()
        if text.startswith("- s1")
    )
    assert "; 3 places;" in line
    assert "every State" not in line


def test_the_inventory_caps_the_places_it_names() -> None:
    # Test: The place cap of the inventory.
    # Situation: A cohort table with a scaling factor holds more places
    #   than the cap.
    # Expectation: The item names the first `INVENTORY_PLACE_CAP` places,
    #   the line states the scaling factor beside the unit, and the line
    #   counts the rest as more places.
    places = _COUNTIES
    table = _make_table(
        "t1",
        places=places,
        parent="geoId/06",
        child_type="County",
        scaling_factor=1_000_000.0,
    )

    inputs = build_synthesis_inputs(
        "q", AnalysisDigest((), ()), None, (table,), []
    )

    (item,) = inputs.inventory
    assert len(item.places) == INVENTORY_PLACE_CAP
    assert item.place_count == len(_COUNTIES)
    message = render_synthesis_message(inputs)
    line = next(
        text for text in message.splitlines() if text.startswith("- t1")
    )
    assert "every County in geoId/06" in line
    assert "unit: Person (scaling factor 1000000);" in line
    assert line.endswith(
        f", and {len(_COUNTIES) - INVENTORY_PLACE_CAP} more places"
    )


def test_an_empty_digest_states_that_no_results_were_computed() -> None:
    # Test: The synthesis message of a digest without results.
    # Situation: The digest holds no results, sources, or missing-data
    #   notes, and the inventory holds one table.
    # Expectation: The digest section states that no results were
    #   computed, and the sources and missing-data sections are left out.
    inputs = build_synthesis_inputs(
        "q", AnalysisDigest((), ()), None, (_make_table("t1"),), []
    )

    message = render_synthesis_message(inputs)

    assert "No results were computed." in message
    assert "NUMBERED SOURCES" not in message
    assert "MISSING DATA" not in message
    assert "TABLE INVENTORY" in message


def test_a_sourced_digest_lists_its_sources_once() -> None:
    # Test: The sources of a digest whose results cite them.
    # Situation: The digest's one result cites INSEE, and the caller passes
    #   the digest's sources.
    # Expectation: The message names INSEE once, in the numbered sources
    #   section, and holds no `"Sources:"` section of the digest.
    entry = _make_table("t1")
    digest = _make_sourced_digest(entry)
    assert digest.sources == (_INSEE,)

    message = render_synthesis_message(
        build_synthesis_inputs("q", digest, None, (entry,), digest.sources)
    )

    assert message.count("INSEE") == 1
    assert "Sources:" not in message
    assert "cite: [1]" in message


def test_sources_that_differ_from_a_sourced_digest_are_rejected() -> None:
    # Test: The source check of `build_synthesis_inputs`.
    # Situation: The digest's one result cites INSEE, and the caller passes
    #   a different source.
    # Expectation: `ValueError`, since the citation numbers in the digest
    #   would point at the wrong sources.
    entry = _make_table("t1")
    digest = _make_sourced_digest(entry)

    with pytest.raises(ValueError, match="digest's sources"):
        build_synthesis_inputs(
            "q", digest, None, (entry,), [Source(name="BLS", url="")]
        )


def test_external_metadata_and_urls_are_sanitized_to_single_lines() -> None:
    # Test: Sanitization of external names, units, and provenance URLs.
    # Situation: A cached table carries line breaks and control or directional
    #   format characters in `variable_name`, `unit`, and `place_names`, and
    #   provenance includes both a source with line breaks and invisible format
    #   characters in its name and URL and an unnamed URL longer than
    #   `MAX_NAME_CHARS`.
    # Expectation: Every source and inventory line is a single sanitized line,
    #   and the long unnamed URL is preserved intact once without truncation.
    base = _make_table("t1", places=("country/FRA",))
    dirty = CachedTable(
        "t1",
        replace(
            base.table,
            variable_name="Total\n\u202ePopulation\x07",
            unit="Per\r\nson\x00",
            place_names={"country/FRA": "Fra\nnce\u202e"},
        ),
    )
    long_url = "https://example.org/" + ("a" * MAX_NAME_CHARS)
    sources = [
        Source(
            name="Euro\nstat\u202e",
            url="https://ec.europa.eu/\r\nstats\u200b?x=1",
        ),
        Source(name="", url=long_url),
    ]

    inputs = build_synthesis_inputs(
        "q", AnalysisDigest((), ()), None, (dirty,), sources
    )
    message = render_synthesis_message(inputs)

    assert inputs.sources == (
        SynthesisSource("Euro stat", "https://ec.europa.eu/stats?x=1"),
        SynthesisSource(long_url, long_url),
    )
    (item,) = inputs.inventory
    assert item.variable_name == "Total Population"
    assert item.unit == "Per son"
    assert item.places == (("country/FRA", "Fra nce"),)
    assert "\u202e" not in message
    assert "\u200b" not in message
    assert "[1] Euro stat - https://ec.europa.eu/stats?x=1\n" in message
    assert f"[2] {long_url}\n" in message
    assert f"{long_url} - {long_url}" not in message
