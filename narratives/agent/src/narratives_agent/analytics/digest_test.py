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
invariant, `OkScriptResult` metrics-to-script pairing validation, JSON
serialization without NaN or Infinity, assembly of the ordered sources list
from per-result sources, and the prompt rendering.
"""

import json
import math
from dataclasses import dataclass, replace
from typing import ClassVar

import pytest

from narratives_agent.analytics.digest import (
    AnalysisDigest,
    CoverageReport,
    OkScriptResult,
    RefusedScriptResult,
    format_scaling_factor,
)
from narratives_agent.analytics.metrics import ScriptMetrics, ScriptName
from narratives_agent.analytics.provenance import Provenance, Source

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

    script: ClassVar[ScriptName] = "analyze_timeseries"

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

    script: ClassVar[ScriptName] = "rank_cohort"

    top_n: tuple[dict[str, object], ...] = ()
    ratio: float = 0.0
    growth: float = 0.0
    pair: tuple[int, int] = (1, 2)


def _ok(
    step_id: str,
    provenance: Provenance,
    *,
    metrics: ScriptMetrics | None = None,
) -> OkScriptResult:
    """Builds a minimal `analyze_timeseries` result for one step."""
    return OkScriptResult(
        step_id=step_id,
        script="analyze_timeseries",
        variables=("Count_Person",),
        variable_names={"Count_Person": "Total population"},
        provenance=provenance,
        metrics=metrics if metrics is not None else _StubTimeseriesMetrics(),
    )


def _refused(step_id: str, provenance: Provenance) -> RefusedScriptResult:
    """Builds a minimal refused `analyze_timeseries` result for one step."""
    return RefusedScriptResult(
        step_id=step_id,
        script="analyze_timeseries",
        refusal_reason="no_observations",
        variables=("Count_Person",),
        variable_names={"Count_Person": "Total population"},
        provenance=provenance,
    )


def test_citation_label_renders_single_and_composite_citations() -> None:
    # Test: 1-based bracketed citation labels returned by `citation_label`.
    # Situation: A digest with two sources is queried with an empty
    #   `Provenance`, a single-source `Provenance`, a two-source composite
    #   `Provenance`, and again after copying the digest with `sources=()`.
    # Expectation: Returns `""`, `"[1]"`, `"[1, 2]"`, and still resolves
    #   `"[1, 2]"` by populating `sources` from `results`.
    r1 = _ok("s1", Provenance(sources=(_WDI,)))
    r2 = _ok("s2", Provenance(sources=(_CENSUS,)))
    digest = AnalysisDigest.from_results((r1, r2))
    composite = Provenance(
        sources=(_WDI, _CENSUS),
        methodology="Ratio of variable A to variable B joined on (place, date)",
    )
    assert digest.citation_label(Provenance()) == ""
    assert digest.citation_label(r1.provenance) == "[1]"
    assert digest.citation_label(composite) == "[1, 2]"
    assert replace(digest, sources=()).citation_label(composite) == "[1, 2]"


def test_ok_result_rejects_metrics_of_another_script() -> None:
    # Test: `OkScriptResult.__post_init__` metrics-to-script pairing.
    # Situation: Callers attempt to build an ok result for a script with no
    #   metrics class (`align_cohort`), and an ok result whose metrics belong
    #   to a different script.
    # Expectation: Both raise `ValueError` naming the script and the metrics
    #   class.
    provenance = Provenance(sources=(_WDI,))
    with pytest.raises(
        ValueError, match=r"align_cohort.*_StubTimeseriesMetrics"
    ):
        OkScriptResult(
            step_id="s1",
            script="align_cohort",
            variables=("Count_Person",),
            variable_names={"Count_Person": "Total population"},
            provenance=provenance,
            metrics=_StubTimeseriesMetrics(),
        )
    with pytest.raises(
        ValueError, match=r"analyze_timeseries.*_StubRankingMetrics"
    ):
        _ok("s1", provenance, metrics=_StubRankingMetrics())


def test_result_variants_fix_their_status_fields() -> None:
    # Test: Discriminant fields of the two `ScriptResult` variants.
    # Situation: One `OkScriptResult` and one `RefusedScriptResult` are built.
    # Expectation: The ok result reports `status="ok"` and no refusal reason;
    #   the refused result reports `status="refused"` and no metrics.
    provenance = Provenance(sources=(_WDI,))
    ok = _ok("s1", provenance)
    refused = _refused("s2", provenance)
    assert (ok.status, ok.refusal_reason) == ("ok", None)
    assert (refused.status, refused.metrics) == ("refused", None)


def test_has_data_requires_an_ok_result() -> None:
    # Test: `AnalysisDigest.has_data` property.
    # Situation: One digest contains only a refused result, and a second
    #   digest contains an ok result.
    # Expectation: `has_data` is `False` for the first digest and `True` for
    #   the second.
    provenance = Provenance(sources=(_WDI,))
    refused = AnalysisDigest(
        results=(_refused("s1", provenance),),
        sources=(_WDI,),
    )
    populated = AnalysisDigest(
        results=(_ok("s1", provenance),),
        sources=(_WDI,),
    )
    assert refused.has_data is False
    assert populated.has_data is True


def test_digest_sources_must_match_the_results() -> None:
    # Test: Consistency between `AnalysisDigest.sources` and its results.
    # Situation: A digest is built with a `sources` tuple that omits a source
    #   its result cites, and a valid digest is asked for the citation of a
    #   source that none of its results cite.
    # Expectation: The mismatched digest raises `ValueError` at construction,
    #   and `citation_label` raises `ValueError` for the unknown source.
    result = _ok("s1", Provenance(sources=(_WDI, _CENSUS)))
    with pytest.raises(ValueError, match=r"sources"):
        AnalysisDigest(results=(result,), sources=(_CENSUS,))
    digest = AnalysisDigest.from_results((_ok("s1", Provenance((_WDI,))),))
    with pytest.raises(ValueError, match=r"Census"):
        digest.citation_label(Provenance(sources=(_CENSUS,)))


def test_from_results_orders_sources_by_first_appearance() -> None:
    # Test: Assembly of the digest's `sources` list.
    # Situation: A first result cites `_CENSUS` and a second result cites
    #   `(_WDI, _CENSUS)`.
    # Expectation: `sources` lists `_CENSUS` first and `_WDI` second, in
    #   first-appearance order without duplicates, and `citation_label`
    #   numbers them `[1]` and `[2, 1]`.
    first = _ok("s1", Provenance(sources=(_CENSUS,)))
    second = _ok("s2", Provenance(sources=(_WDI, _CENSUS)))
    digest = AnalysisDigest.from_results((first, second))
    assert digest.sources == (_CENSUS, _WDI)
    assert digest.citation_label(first.provenance) == "[1]"
    assert digest.citation_label(second.provenance) == "[2, 1]"


def test_to_dict_serializes_without_nan_or_infinity() -> None:
    # Test: Strict JSON serialization of `AnalysisDigest.to_dict()`.
    # Situation: `to_dict()` is called on a digest holding an ok result whose
    #   metrics contain `NaN`, `Infinity`, and a tuple, with a
    #   `CoverageReport`, plus a refused result.
    # Expectation: `json.dumps(..., allow_nan=False)` succeeds, non-finite
    #   floats serialize as `null`, the `CoverageReport` serializes as a plain
    #   dictionary, and each result reports its `status`, `refusal_reason`,
    #   and `metrics`.
    coverage = CoverageReport(
        contributing_places=9,
        requested_places=10,
        coverage_ratio=0.9,
        reference_date="2022",
        missing_places=("country/X",),
        mixed_vintages=True,
    )
    result = OkScriptResult(
        step_id="s1",
        script="rank_cohort",
        variables=("Count_Person",),
        variable_names={"Count_Person": "Total population"},
        provenance=Provenance(sources=(_WDI,)),
        coverage=coverage,
        metrics=_StubRankingMetrics(
            ratio=math.nan, growth=math.inf, pair=(1, 2)
        ),
    )
    refused = _refused("s2", Provenance(sources=(_WDI,)))
    digest = AnalysisDigest.from_results((result, refused))
    payload = digest.to_dict()
    encoded = json.dumps(payload, allow_nan=False)
    decoded = json.loads(encoded)
    assert decoded["has_data"] is True
    ok_json, refused_json = decoded["results"]
    assert ok_json["status"] == "ok"
    assert ok_json["refusal_reason"] is None
    assert ok_json["metrics"] == {
        "top_n": [],
        "ratio": None,
        "growth": None,
        "pair": [1, 2],
    }
    assert ok_json["coverage"]["missing_places"] == ["country/X"]
    assert refused_json["status"] == "refused"
    assert refused_json["refusal_reason"] == "no_observations"
    assert refused_json["metrics"] is None


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
    ranked = OkScriptResult(
        step_id="s1",
        script="rank_cohort",
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
    refused = _refused("s2", Provenance(sources=(_CENSUS,)))
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
    result = _ok("s1", Provenance(sources=(_WDI,)), metrics=metrics)
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

    scaled = replace(_ok("s1", Provenance(sources=(_WDI,))), scaling_factor=1e6)
    scaled_digest = AnalysisDigest.from_results((scaled,))
    assert "scaling factor: 1000000;" in scaled_digest.format_for_prompt()


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1_000_000.0, "1000000"), (0.01, "0.01"), (1e21, "1e+21")],
    ids=["whole-number", "fraction", "beyond-integer-range"],
)
def test_format_scaling_factor_renders_integers_and_fractions(
    value: float, expected: str
) -> None:
    # Test: `format_scaling_factor` output for each kind of factor.
    # Situation: The factor is a whole number below `1e15`, a fraction, or a
    #   whole number above `1e15`.
    # Expectation: Whole numbers below `1e15` render as plain integers, and
    #   the others render in compact `g` notation.
    assert format_scaling_factor(value) == expected


@pytest.mark.parametrize(
    ("requested_places", "reference_date", "expected"),
    [
        (1, "2022", "1 of 1 place on 2022"),
        (10, None, "1 of 10 places"),
    ],
    ids=["one-place", "no-reference-date"],
)
def test_coverage_describe_handles_one_place_and_no_reference_date(
    requested_places: int, reference_date: str | None, expected: str
) -> None:
    # Test: `CoverageReport.describe()` wording.
    # Situation: The cohort has a single place, or no reference date could be
    #   selected.
    # Expectation: A single place uses the singular `"place"`, and a missing
    #   reference date omits the `" on <date>"` suffix.
    coverage = CoverageReport(
        contributing_places=1,
        requested_places=requested_places,
        coverage_ratio=1 / requested_places,
        reference_date=reference_date,
    )
    assert coverage.describe() == expected


@pytest.mark.parametrize(
    "url",
    ["https://wdi.example", ""],
    ids=["url-equals-name", "empty-url"],
)
def test_format_for_prompt_lists_a_source_by_name_alone(url: str) -> None:
    # Test: Source line rendering when the URL adds nothing.
    # Situation: The only source's `url` equals its `name`, as `mcp/metadata`
    #   produces when a provenance node carries only a URL, or is empty.
    # Expectation: The `"Sources:"` entry lists the name without a
    #   parenthesized URL.
    source = Source(name=url or "Census", url=url)
    digest = AnalysisDigest.from_results(
        (_ok("s1", Provenance(sources=(source,))),)
    )
    assert digest.format_for_prompt().endswith(f"[1] {source.name}")
