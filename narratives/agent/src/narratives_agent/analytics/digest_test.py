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
"""Tests for the digest types in `analytics.digest`.

Covers citation labels for single and composite provenance, the `has_data`
invariant, `ScriptResult` metrics-to-script pairing validation, JSON
serialization without NaN or Infinity, assembly of the ordered sources list
from per-result sources, and the prompt rendering.
"""

import json
import math
from dataclasses import dataclass, replace

import pytest

from narratives_agent.analytics.digest import (
    AnalysisDigest,
    CoverageReport,
    Provenance,
    ScriptResult,
    Source,
    json_safe,
    merge_provenance,
)
from narratives_agent.analytics.metrics import (
    METRICS_BY_SCRIPT,
    ScriptMetrics,
)

_WDI = Source(
    name="World Development Indicators",
    url="https://wdi.example",
)
_CENSUS = Source(
    name="Census",
    url="https://census.example",
)


@dataclass(frozen=True)
class _StubTimeseriesMetrics(ScriptMetrics):
    """Stub metrics record for `analyze_timeseries` in digest unit tests."""

    place_count: int = 1
    difference: float = 0.0
    near_int: float = 0.0
    pct_change: float = 0.0
    rate: float = 0.0
    count: float = 0.0
    huge: float = 0.0
    flag: bool = False
    series: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True)
class _StubRankingMetrics(ScriptMetrics):
    """Stub metrics record for `rank_cohort` in digest unit tests."""

    top_n: tuple[dict[str, object], ...] = ()
    ratio: float = 0.0
    growth: float = 0.0
    pair: tuple[int, int] = (1, 2)


@pytest.fixture(autouse=True)
def _register_stub_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    """Registers stub metrics classes for the digest unit tests."""
    monkeypatch.setitem(
        METRICS_BY_SCRIPT, "analyze_timeseries", _StubTimeseriesMetrics
    )
    monkeypatch.setitem(METRICS_BY_SCRIPT, "rank_cohort", _StubRankingMetrics)


def _result(
    step_id: str,
    provenance: Provenance,
    *,
    status: str = "ok",
    metrics: ScriptMetrics | None = None,
) -> ScriptResult:
    """Builds a minimal result for one step."""
    resolved_metrics: ScriptMetrics | None = None
    if status == "ok":
        resolved_metrics = (
            metrics if metrics is not None else _StubTimeseriesMetrics()
        )
    return ScriptResult(
        step_id=step_id,
        script="analyze_timeseries",
        status="ok" if status == "ok" else "refused",
        refusal_reason=None if status == "ok" else "no_observations",
        variables=("Count_Person",),
        variable_names={"Count_Person": "Total population"},
        provenance=provenance,
        metrics=resolved_metrics,
    )


def test_citation_label_renders_single_and_composite_citations() -> None:
    # Test: 1-based bracketed citation labels returned by `citation_label`.
    # Situation: A digest with two sources is queried with an empty
    #   `Provenance`, a single-source `Provenance`, a two-source composite
    #   `Provenance`, and again after copying the digest with `sources=()`.
    # Expectation: Returns `""`, `"[1]"`, `"[1, 2]"`, and still resolves
    #   `"[1, 2]"` by populating `sources` from `results`.
    r1 = _result("s1", Provenance(sources=(_WDI,)))
    r2 = _result("s2", Provenance(sources=(_CENSUS,)))
    digest = AnalysisDigest.from_results((r1, r2))
    composite = Provenance(
        sources=(_WDI, _CENSUS),
        methodology="Ratio of variable A to variable B joined on (place, date)",
    )
    assert digest.citation_label(Provenance()) == ""
    assert digest.citation_label(r1.provenance) == "[1]"
    assert digest.citation_label(composite) == "[1, 2]"
    assert replace(digest, sources=()).citation_label(composite) == "[1, 2]"


def test_merge_provenance_combines_sources_and_facets_in_order() -> None:
    # Test: `merge_provenance` across multiple table provenances.
    # Situation: Three `Provenance` records (for a count table, a population
    #   table, and a repeated source with a methodology) are merged with a
    #   combining `methodology`.
    # Expectation: The merged `Provenance` deduplicates `sources` and
    #   `facet_ids` in first-appearance order and joins the input methodology
    #   before the combining methodology.
    count = Provenance(sources=(_WDI,), facet_ids=("f1",))
    population = Provenance(sources=(_CENSUS,), facet_ids=("f2",))
    repeated = Provenance(
        sources=(_CENSUS,),
        facet_ids=("f2",),
        methodology="Aligned to 2020",
    )
    merged = merge_provenance(
        count, population, repeated, methodology="Count per person"
    )
    assert merged == Provenance(
        sources=(_WDI, _CENSUS),
        facet_ids=("f1", "f2"),
        methodology="Aligned to 2020; Count per person",
    )
    assert merge_provenance() == Provenance()


def test_merge_provenance_keeps_the_methodology_of_a_derived_input() -> None:
    # Test: Preservation and deduplication of `methodology` in
    #   `merge_provenance`.
    # Situation: A derived table's `Provenance` (whose `methodology` ends with
    #   a period) is merged with a weight table's `Provenance` (which has no
    #   `methodology`) in three ways: without a combining `methodology`, with a
    #   new combining `methodology`, and with an identical `methodology`. Two
    #   records with `methodology=None` are also merged.
    # Expectation: The derived methodology is preserved on its own, joined
    #   before a new combining methodology with `"; "`, deduplicated when
    #   repeated, and `None` when no input or argument specifies a methodology.
    derived = Provenance(
        sources=(_WDI, _CENSUS),
        methodology="Count_Case divided by Count_Person.",
    )
    weights = Provenance(sources=(_CENSUS,))

    assert merge_provenance(derived, weights).methodology == (
        "Count_Case divided by Count_Person."
    )
    assert merge_provenance(
        derived, weights, methodology="Weighted by Count_Person."
    ).methodology == (
        "Count_Case divided by Count_Person; Weighted by Count_Person."
    )
    assert merge_provenance(
        derived, methodology="Count_Case divided by Count_Person."
    ).methodology == ("Count_Case divided by Count_Person.")
    assert merge_provenance(weights, weights).methodology is None


def test_script_result_enforces_status_and_metrics_pairing() -> None:
    # Test: `ScriptResult.__post_init__` pairing invariants.
    # Situation: Callers attempt to build (1) a refused result with metrics,
    #   (2) an ok result with `metrics=None`, (3) an ok result for a script
    #   with no registered metrics class (`align_cohort`), and (4) an ok
    #   result whose metrics type belongs to a different script.
    # Expectation: Every invalid combination raises `ValueError`.
    provenance = Provenance(sources=(_WDI,))
    with pytest.raises(ValueError, match=r"refused.*metrics=None"):
        ScriptResult(
            step_id="s1",
            script="analyze_timeseries",
            status="refused",
            refusal_reason="no_observations",
            variables=("Count_Person",),
            variable_names={"Count_Person": "Total population"},
            provenance=provenance,
            metrics=_StubTimeseriesMetrics(),
        )
    with pytest.raises(ValueError, match=r"ok.*ScriptMetrics"):
        ScriptResult(
            step_id="s1",
            script="analyze_timeseries",
            status="ok",
            variables=("Count_Person",),
            variable_names={"Count_Person": "Total population"},
            provenance=provenance,
            metrics=None,
        )
    with pytest.raises(ValueError, match=r"align_cohort.*registered"):
        ScriptResult(
            step_id="s1",
            script="align_cohort",
            status="ok",
            variables=("Count_Person",),
            variable_names={"Count_Person": "Total population"},
            provenance=provenance,
            metrics=_StubTimeseriesMetrics(),
        )
    with pytest.raises(
        ValueError,
        match=r"analyze_timeseries.*_StubTimeseriesMetrics.*_StubRankingMetrics",
    ):
        ScriptResult(
            step_id="s1",
            script="analyze_timeseries",
            status="ok",
            variables=("Count_Person",),
            variable_names={"Count_Person": "Total population"},
            provenance=provenance,
            metrics=_StubRankingMetrics(),
        )


def test_has_data_requires_an_ok_result_with_metrics() -> None:
    # Test: `AnalysisDigest.has_data` property.
    # Situation: One digest contains only a refused `ScriptResult`, and a
    #   second digest contains an `"ok"` `ScriptResult` with metrics.
    # Expectation: `has_data` is `False` for the first digest and `True` for
    #   the second.
    provenance = Provenance(sources=(_WDI,))
    refused = AnalysisDigest(
        results=(_result("s1", provenance, status="refused"),),
        sources=(_WDI,),
    )
    populated = AnalysisDigest(
        results=(_result("s1", provenance),),
        sources=(_WDI,),
    )
    assert refused.has_data is False
    assert populated.has_data is True


def test_script_result_enforces_status_and_refusal_reason_pairing() -> None:
    # Test: `ScriptResult.__post_init__` refusal-reason invariants.
    # Situation: Callers attempt to build (1) a refused result without a
    #   `refusal_reason` and (2) an ok result with a `refusal_reason`.
    # Expectation: Both combinations raise `ValueError`.
    provenance = Provenance(sources=(_WDI,))
    with pytest.raises(ValueError, match=r"refused.*refusal_reason"):
        ScriptResult(
            step_id="s1",
            script="analyze_timeseries",
            status="refused",
            variables=("Count_Person",),
            variable_names={"Count_Person": "Total population"},
            provenance=provenance,
        )
    with pytest.raises(ValueError, match=r"ok.*refusal_reason=None"):
        replace(_result("s1", provenance), refusal_reason="no_observations")


def test_digest_sources_must_match_the_results() -> None:
    # Test: Consistency between `AnalysisDigest.sources` and its results.
    # Situation: A digest is built with a `sources` tuple that omits a source
    #   its result cites, and a valid digest is asked for the citation of a
    #   source that none of its results cite.
    # Expectation: The mismatched digest raises `ValueError` at construction,
    #   and `citation_label` raises `ValueError` for the unknown source.
    result = _result("s1", Provenance(sources=(_WDI, _CENSUS)))
    with pytest.raises(ValueError, match=r"sources"):
        AnalysisDigest(results=(result,), sources=(_CENSUS,))
    digest = AnalysisDigest.from_results((_result("s1", Provenance((_WDI,))),))
    with pytest.raises(ValueError, match=r"Census"):
        digest.citation_label(Provenance(sources=(_CENSUS,)))


def test_from_results_orders_sources_by_first_appearance() -> None:
    # Test: Assembly of the digest's `sources` list.
    # Situation: A first result cites `_CENSUS` and a second result cites
    #   `(_WDI, _CENSUS)`.
    # Expectation: `sources` lists `_CENSUS` first and `_WDI` second, in
    #   first-appearance order without duplicates, and `citation_label`
    #   numbers them `[1]` and `[2, 1]`.
    first = _result("s1", Provenance(sources=(_CENSUS,)))
    second = _result("s2", Provenance(sources=(_WDI, _CENSUS)))
    digest = AnalysisDigest.from_results((first, second))
    assert digest.sources == (_CENSUS, _WDI)
    assert digest.citation_label(first.provenance) == "[1]"
    assert digest.citation_label(second.provenance) == "[2, 1]"


def test_to_dict_serializes_without_nan_or_infinity() -> None:
    # Test: Strict JSON serialization of `AnalysisDigest.to_dict()`.
    # Situation: `to_dict()` is called on a digest whose result contains `NaN`,
    #   `Infinity`, a tuple, and a `CoverageReport` dataclass.
    # Expectation: `json.dumps(..., allow_nan=False)` succeeds, non-finite
    #   floats serialize as `null`, and the `CoverageReport` serializes as a
    #   plain dictionary.
    coverage = CoverageReport(
        contributing_places=9,
        requested_places=10,
        coverage_ratio=0.9,
        reference_date="2022",
        missing_places=("country/X",),
        mixed_vintages=True,
    )
    result = ScriptResult(
        step_id="s1",
        script="rank_cohort",
        status="ok",
        variables=("Count_Person",),
        variable_names={"Count_Person": "Total population"},
        provenance=Provenance(sources=(_WDI,)),
        coverage=coverage,
        metrics=_StubRankingMetrics(
            ratio=math.nan, growth=math.inf, pair=(1, 2)
        ),
    )
    digest = AnalysisDigest.from_results((result,))
    payload = digest.to_dict()
    encoded = json.dumps(payload, allow_nan=False)
    decoded = json.loads(encoded)
    assert decoded["has_data"] is True
    assert decoded["results"][0]["metrics"] == {
        "top_n": [],
        "ratio": None,
        "growth": None,
        "pair": [1, 2],
    }
    assert decoded["results"][0]["coverage"]["missing_places"] == ["country/X"]


def test_json_safe_converts_sets_and_nested_dataclasses() -> None:
    # Test: `json_safe` conversion of sets, dataclasses, and unsupported types.
    # Situation: `json_safe` is called on a dictionary containing a `frozenset`
    #   and a `CoverageReport` with `math.inf`, and then called on a plain
    #   `object()` instance.
    # Expectation: The `frozenset` converts to a sorted list, the dataclass
    #   converts to a dictionary with `None` in place of `math.inf`, and the
    #   unsupported `object()` raises `TypeError`.
    coverage = CoverageReport(
        contributing_places=1,
        requested_places=0,
        coverage_ratio=math.inf,
        reference_date=None,
    )
    converted = json_safe(
        {"places": frozenset({"b", "a"}), "coverage": coverage}
    )
    assert converted == {
        "places": ["a", "b"],
        "coverage": {
            "contributing_places": 1,
            "requested_places": 0,
            "coverage_ratio": None,
            "reference_date": None,
            "missing_places": [],
            "mixed_vintages": False,
        },
    }
    with pytest.raises(TypeError, match=r"Cannot serialize"):
        json_safe(object())


def test_format_for_prompt_renders_results_sources_and_missing_notes() -> None:
    # Test: Text rendering of `AnalysisDigest.format_for_prompt()`.
    # Situation: `format_for_prompt()` is called on a digest with one `"ok"`
    #   result (including unit, coverage, methodology, metrics, and a caveat),
    #   one `"refused"` result, two sources, and one missing-data note.
    # Expectation: Renders each step block with its header, metadata,
    #   methodology, compact JSON metrics, and caveats, followed by the
    #   numbered `"Sources:"` and `"Missing data:"` sections.
    coverage = CoverageReport(
        contributing_places=9,
        requested_places=10,
        coverage_ratio=0.9,
        reference_date="2022",
    )
    ranked = ScriptResult(
        step_id="s1",
        script="rank_cohort",
        status="ok",
        variables=("Count_Person",),
        variable_names={"Count_Person": "Total population"},
        unit="Person",
        provenance=Provenance(
            sources=(_WDI,),
            methodology="Ranked 9 places on 2022",
        ),
        coverage=coverage,
        metrics=_StubRankingMetrics(top_n=({"place_dcid": "a", "value": 1.0},)),
        caveats=("9 of 10 places reported a value.",),
    )
    refused = _result(
        "s2",
        Provenance(sources=(_CENSUS,)),
        status="refused",
    )
    digest = AnalysisDigest.from_results(
        (ranked, refused),
        missing_notes=("No data for median income by county.",),
    )
    text = digest.format_for_prompt()
    assert text == (
        "Step s1: rank_cohort on Total population (Count_Person)\n"
        "  unit: Person; coverage: 9 of 10 places on 2022; cite: [1]\n"
        "  method: Ranked 9 places on 2022\n"
        '  metrics: {"top_n":[{"place_dcid":"a","value":1}],'
        '"ratio":0,"growth":0,"pair":[1,2]}\n'
        "  caveat: 9 of 10 places reported a value.\n"
        "\n"
        "Step s2: analyze_timeseries on Total population (Count_Person) "
        "[refused: no_observations]\n"
        "  cite: [2]\n"
        "\n"
        "Sources:\n"
        "[1] World Development Indicators (https://wdi.example)\n"
        "[2] Census (https://census.example)\n"
        "\n"
        "Missing data:\n"
        "- No data for median income by county."
    )


def test_format_for_prompt_rounds_figures_to_display_precision() -> None:
    # Test: Float rounding in `format_for_prompt()` versus full precision in
    #   `to_dict()`.
    # Situation: A digest is built from a result whose metrics include a float
    #   with a binary rounding artifact, a multi-decimal percentage, a rate
    #   between 0 and 1, a whole-number float below `1e15`, a float above
    #   `1e15`, a boolean, and nested containers.
    # Expectation: `format_for_prompt()` rounds floats >= 1 to 2 decimals,
    #   floats in `(0, 1)` to 3 significant digits, and whole-number floats
    #   below `1e15` to integers while preserving `1e+21`, booleans, and
    #   strings, whereas `to_dict()` preserves exact floating-point values.
    metrics = _StubTimeseriesMetrics(
        place_count=1,
        difference=1.6000000000000014,
        near_int=-25.000000000000007,
        pct_change=45.68175136297,
        rate=0.02818185351838144,
        count=30188424.0,
        huge=1e21,
        flag=True,
        series=({"place_dcid": "a", "values": [0.5, 2.345678]},),
    )
    result = _result(
        "s1",
        Provenance(sources=(_WDI,)),
        metrics=metrics,
    )
    digest = AnalysisDigest.from_results((result,))

    text = digest.format_for_prompt()

    assert (
        '  metrics: {"place_count":1,"difference":1.6,"near_int":-25,'
        '"pct_change":45.68,"rate":0.0282,"count":30188424,"huge":1e+21,'
        '"flag":true,"series":[{"place_dcid":"a","values":[0.5,2.35]}]}'
    ) in text
    serialized = digest.to_dict()
    results_list = serialized["results"]
    assert isinstance(results_list, list)
    first_result = results_list[0]
    assert isinstance(first_result, dict)
    metrics_dict = first_result["metrics"]
    assert isinstance(metrics_dict, dict)
    assert metrics_dict["difference"] == 1.6000000000000014

    scaled = ScriptResult(
        step_id="s1",
        script="analyze_timeseries",
        status="ok",
        variables=("Count_Person",),
        variable_names={"Count_Person": "Total population"},
        scaling_factor=1_000_000.0,
        provenance=Provenance(sources=(_WDI,)),
        metrics=_StubTimeseriesMetrics(),
    )
    scaled_digest = AnalysisDigest.from_results((scaled,))
    assert "scaling factor: 1000000;" in scaled_digest.format_for_prompt()
