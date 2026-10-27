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
"""Tests for `derive_observation_table` in `analytics.derived`.

Covers each operation, the derived table and its composite provenance,
chaining into the other analytical functions, undefined denominators and
baselines, the automatic per-capita scale, unit and scaling compatibility,
the target-place and date-window rules, helper preconditions, and
deterministic brute-force invariants against an independent oracle.
"""

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass

import pytest

from narratives_agent.analytics.alignment import AlignedCohort, align_cohort
from narratives_agent.analytics.derived import (
    DerivedMetricOutcome,
    _apply_operation,
    _format_scale,
    _select_fitting_scale,
    compute_derived_metric,
    derive_observation_table,
)
from narratives_agent.analytics.digest import (
    AnalysisDigest,
    OkScriptResult,
    RefusedScriptResult,
)
from narratives_agent.analytics.distribution import summarize_distribution
from narratives_agent.analytics.metrics import (
    DerivedMetrics,
    DerivedOperation,
    DistributionMetrics,
    RankingMetrics,
    TimeseriesMetrics,
)
from narratives_agent.analytics.provenance import Provenance, Source
from narratives_agent.analytics.ranking import rank_cohort
from narratives_agent.analytics.summarize import summarize_table
from narratives_agent.analytics.tables import (
    ObservationRow,
    ObservationTable,
    is_within_date_range,
)
from narratives_agent.analytics.timeseries import analyze_timeseries

_WDI = Source(name="World Development Indicators", url="https://wdi")
_CENSUS = Source(name="Census", url="https://census")


def _build_table(
    variable_dcid: str,
    observations: Sequence[tuple[str, str, float]],
    *,
    facet_id: str,
    source: Source,
    requested_places: Sequence[str] = (),
    unit: str | None = None,
    scaling_factor: float | None = None,
    parent_place_dcid: str | None = None,
    child_place_type: str | None = None,
) -> ObservationTable:
    """Builds a table of `variable_dcid` from `(place, date, value)` rows."""
    places = list(
        dict.fromkeys(
            [*requested_places, *(place for place, _, _ in observations)]
        )
    )
    return ObservationTable(
        variable_dcid=variable_dcid,
        variable_name=variable_dcid.replace("_", " "),
        unit=unit,
        scaling_factor=scaling_factor,
        provenance=Provenance(
            sources=(source,),
            facet_ids=(facet_id,),
        ),
        rows=tuple(
            ObservationRow(place, place.upper(), date, value)
            for place, date, value in observations
        ),
        requested_places=tuple(requested_places),
        place_names={place: place.upper() for place in places},
        parent_place_dcid=parent_place_dcid,
        child_place_type=child_place_type,
    )


def _build_count_table() -> ObservationTable:
    """Builds a count table for `a` and `b` on two dates, plus `c` on one."""
    return _build_table(
        "Count_Case",
        [
            ("a", "2020", 10.0),
            ("a", "2021", 30.0),
            ("b", "2020", 50.0),
            ("b", "2021", 80.0),
            ("c", "2020", 1.0),
        ],
        facet_id="f1",
        source=_WDI,
        requested_places=["a", "b", "c"],
        parent_place_dcid="country/USA",
        child_place_type="State",
    )


def _build_population_table() -> ObservationTable:
    """Builds a population table for `a` and `b` on both dates."""
    return _build_table(
        "Count_Person",
        [
            ("a", "2020", 1000.0),
            ("a", "2021", 1000.0),
            ("b", "2020", 1250.0),
            ("b", "2021", 3200.0),
            ("b", "2019", 999.0),
        ],
        facet_id="f2",
        source=_CENSUS,
        unit="Person",
    )


def test_per_capita_join_derives_a_table_with_composite_provenance() -> None:
    # Test: The per-capita join and the derived table it produces.
    # Situation: A count table from `_WDI` requested for `a`, `b`, and
    #   `c`, and a population table from `_CENSUS` that lacks `c`, joined
    #   per 100,000 people.
    # Expectation: Four rows for `a` and `b` on 2020 and 2021 sorted by
    #   place and date, with the rate per 100,000; a derived table with a
    #   default DCID and name, no unit or scaling, composite provenance
    #   carrying the formula, the count table's requested places, parent
    #   place, and child type; metrics describing the table; and a caveat
    #   that `c` is left out.
    outcome = derive_observation_table(
        _build_count_table(),
        _build_population_table(),
        operation="per_capita",
        scale=100_000.0,
    )
    assert isinstance(outcome, DerivedMetricOutcome)
    result = outcome.result
    assert result.status == "ok"
    assert result.script == "compute_derived_metric"
    assert result.variables == ("Count_Case", "Count_Person")
    assert result.unit is None
    assert result.scaling_factor is None
    assert result.coverage is not None
    assert result.coverage.contributing_places == 2
    assert result.coverage.requested_places == 3
    assert result.coverage.reference_date is None
    assert result.coverage.missing_places == ("c",)
    assert result.provenance.sources == (_WDI, _CENSUS)
    assert result.provenance.facet_ids == ("f1", "f2")
    assert result.provenance.methodology == (
        "Count Case (Count_Case) divided by Count Person (Count_Person) and "
        "multiplied by 100,000; pairs with a zero or negative denominator "
        "are skipped. Observations are joined on place and date."
    )
    assert result.caveats == (
        "No joined observations are available for C, so they are left out "
        "of the derived table.",
    )
    assert result.metrics == DerivedMetrics(
        derived_variable_dcid="derived_Count_Case_per_capita_Count_Person",
        derived_variable_name="Count Case per 100,000 people",
        operation="per_capita",
        scale=100_000.0,
        observation_count=4,
        place_count=2,
        date_range=("2020", "2021"),
        value_range=(1000.0, 4000.0),
        sample_rows=(
            ObservationRow(
                place_dcid="a",
                place_name="A",
                date="2020",
                value=1000.0,
                facet_id=None,
            ),
            ObservationRow(
                place_dcid="a",
                place_name="A",
                date="2021",
                value=3000.0,
                facet_id=None,
            ),
            ObservationRow(
                place_dcid="b",
                place_name="B",
                date="2020",
                value=4000.0,
                facet_id=None,
            ),
            ObservationRow(
                place_dcid="b",
                place_name="B",
                date="2021",
                value=2500.0,
                facet_id=None,
            ),
        ),
        missing_places=("c",),
    )
    table = outcome.table
    assert table is not None
    assert table.variable_dcid == "derived_Count_Case_per_capita_Count_Person"
    assert table.variable_name == "Count Case per 100,000 people"
    assert table.unit is None
    assert table.scaling_factor is None
    assert table.provenance == result.provenance
    assert table.requested_places == ("a", "b", "c")
    assert table.place_names == {"a": "A", "b": "B", "c": "C"}
    assert table.parent_place_dcid == "country/USA"
    assert table.child_place_type == "State"
    assert table.facet_id is None
    assert table.source is None
    assert [(row.place_dcid, row.date, row.value) for row in table.rows] == [
        ("a", "2020", 1000.0),
        ("a", "2021", 3000.0),
        ("b", "2020", 4000.0),
        ("b", "2021", 2500.0),
    ]


def test_the_derived_table_chains_into_every_other_script() -> None:
    # Test: Using the derived table as the input of the other functions.
    # Situation: The per-capita table from the count and population
    #   tables, passed to `summarize_table`, `align_cohort`, `rank_cohort`,
    #   `summarize_distribution`, and `analyze_timeseries`, and the results
    #   assembled into a digest with the derived step.
    # Expectation: Each function reads the table without adjustment, the
    #   cohort aligns to 2021 with 2 of 3 places, every downstream result
    #   carries both sources and opens its methodology with the per-capita
    #   formula, the digest lists the two sources in order, and the prompt
    #   rendering shows the composite citation.
    outcome = derive_observation_table(
        _build_count_table(),
        _build_population_table(),
        operation="per_capita",
        scale=100_000.0,
    )
    table = outcome.table
    assert table is not None
    formula = table.provenance.methodology
    assert formula is not None
    summary = summarize_table(table)
    assert summary.places_with_data_count == 2
    assert summary.places_without_data == ("C (c)",)
    aligned = align_cohort(table)
    assert isinstance(aligned, AlignedCohort)
    assert aligned.reference_date == "2021"
    assert aligned.coverage.contributing_places == 2
    ranked = rank_cohort(table, max_entries_per_end=1, step_id="s2")
    assert ranked.status == "ok"
    assert isinstance(ranked.metrics, RankingMetrics)
    assert ranked.metrics.top_n[0].place_dcid == "a"
    assert ranked.provenance.sources == (_WDI, _CENSUS)
    distribution = summarize_distribution(table, step_id="s3")
    assert distribution.status == "ok"
    assert isinstance(distribution.metrics, DistributionMetrics)
    assert distribution.metrics.median == 2750.0
    assert distribution.provenance.sources == (_WDI, _CENSUS)
    series = analyze_timeseries(table, places=["a"], step_id="s4")
    assert series.status == "ok"
    assert isinstance(series.metrics, TimeseriesMetrics)
    assert series.metrics.series[0].percent_change == 200.0
    assert series.provenance.sources == (_WDI, _CENSUS)
    for result in (ranked, distribution, series):
        assert result.provenance.methodology is not None
        assert result.provenance.methodology.startswith(
            f"{formula.rstrip('.')}; "
        )
    digest = AnalysisDigest.from_results(
        (outcome.result, ranked, distribution, series)
    )
    assert digest.sources == (_WDI, _CENSUS)
    assert digest.has_data is True
    prompt = digest.format_for_prompt()
    assert "Step s1: compute_derived_metric on Count Case (Count_Case), " in (
        prompt
    )
    assert prompt.count("cite: [1, 2]") == 4
    assert "[1] World Development Indicators (https://wdi)" in prompt
    assert "[2] Census (https://census)" in prompt


def test_undefined_pairs_are_skipped_with_a_caveat() -> None:
    # Test: Denominators and baselines that make a pair undefined.
    # Situation: A population of zero for `a` and negative for `b` on one
    #   date and positive on another, joined per capita; a ratio against a
    #   zero denominator; a percentage change from a zero baseline; and a
    #   ratio whose quotient overflows to infinity.
    # Expectation: The per-capita table keeps the defined pairs and states
    #   that two pairs were skipped using `format_place_names`; the ratio
    #   and the percentage change are refused as `no_observations` when
    #   every pair is skipped, with the skip caveat after the refusal
    #   caveat; the overflow is reported as not finite.
    count = _build_table(
        "Count_Case",
        [("a", "2020", 1.0), ("b", "2020", 1.0), ("b", "2021", 1.0)],
        facet_id="f1",
        source=_WDI,
    )
    population = _build_table(
        "Count_Person",
        [("a", "2020", 0.0), ("b", "2020", -5.0), ("b", "2021", 4.0)],
        facet_id="f2",
        source=_CENSUS,
    )
    per_capita = derive_observation_table(
        count, population, operation="per_capita", scale=1.0
    )
    assert per_capita.result.status == "ok"
    assert per_capita.table is not None
    assert [(row.place_dcid, row.value) for row in per_capita.table.rows] == [
        ("b", 0.25)
    ]
    assert per_capita.result.caveats == (
        "2 place and date pairs (A (2020) and B (2020)) were skipped because "
        "the denominator Count Person is zero or negative.",
        "No joined observations are available for A, so they are left out "
        "of the derived table.",
    )
    zero = _build_table(
        "Zero", [("a", "2020", 0.0)], facet_id="f2", source=_CENSUS
    )
    one = _build_table("One", [("a", "2020", 1.0)], facet_id="f1", source=_WDI)
    ratio = derive_observation_table(one, zero, operation="ratio")
    assert ratio.table is None
    assert ratio.result.status == "refused"
    assert ratio.result.refusal_reason == "no_observations"
    assert ratio.result.metrics is None
    assert ratio.result.coverage is not None
    assert ratio.result.coverage.requested_places == 1
    assert ratio.result.caveats == (
        "No observation of One and Zero shares a place and date within the "
        "requested window, so nothing can be derived.",
        "1 place and date pair (A (2020)) was skipped because the "
        "denominator Zero is zero.",
    )
    change = compute_derived_metric(one, zero, operation="pct_change")
    assert change.refusal_reason == "no_observations"
    assert change.metrics is None
    assert change.caveats[1] == (
        "1 place and date pair (A (2020)) was skipped because the baseline "
        "Zero is zero."
    )
    huge = _build_table(
        "Huge", [("a", "2020", 1e308)], facet_id="f1", source=_WDI
    )
    tiny = _build_table(
        "Tiny", [("a", "2020", 1e-308)], facet_id="f2", source=_CENSUS
    )
    overflow = compute_derived_metric(huge, tiny, operation="ratio")
    assert overflow.refusal_reason == "no_observations"
    assert overflow.metrics is None
    assert overflow.caveats[1] == (
        "1 place and date pair (A (2020)) was skipped because the result is "
        "not a finite number."
    )


def test_long_skipped_pair_and_missing_place_lists_use_format_place_names() -> (
    None
):
    # Test: Truncation of skipped-pair and missing-place lists in caveats.
    # Situation: Seven places (`p1`..`p7`) where six have a zero denominator
    #   on 2020, only `p7` succeeds on 2020, and all seven are requested.
    # Expectation: Both the skipped-pairs caveat and the missing-places
    #   caveat name the first five items and summarize the remainder with
    #   `"and 1 other pair"` and `"and 1 other place"`, matching
    #   `digest.format_place_names`.
    places = [f"p{index}" for index in range(1, 8)]
    left = _build_table(
        "Count_Case",
        [(place, "2020", 10.0) for place in places],
        facet_id="f1",
        source=_WDI,
        requested_places=places,
    )
    right = _build_table(
        "Count_Person",
        [
            *((place, "2020", 0.0) for place in places[:6]),
            ("p7", "2020", 100.0),
        ],
        facet_id="f2",
        source=_CENSUS,
    )

    result = compute_derived_metric(left, right, operation="per_capita")

    assert result.status == "ok"
    assert result.caveats == (
        "6 place and date pairs (P1 (2020), P2 (2020), P3 (2020), P4 (2020), "
        "P5 (2020), and 1 other pair) were skipped because the denominator "
        "Count Person is zero or negative.",
        "No joined observations are available for P1, P2, P3, P4, P5, and 1 "
        "other place, so they are left out of the derived table.",
    )


def test_an_empty_join_across_date_granularities_says_why() -> None:
    # Test: The refusal caveat when the inputs' date granularities differ.
    # Situation: An annual table (`2020`, `2021`) joined with a monthly
    #   table (`2020-06`, `2021-06`) and a daily table (`2020-06-15`) for
    #   the same places; then the annual table joined with an annual table
    #   whose years do not overlap; then joined with a table whose only
    #   rows lie outside the window.
    # Expectation: The mismatched-granularity joins name annual against
    #   monthly or daily dates. The other two are refused as
    #   `no_observations` without the hint.
    annual = _build_table(
        "Annual",
        [("a", "2020", 1.0), ("b", "2021", 2.0)],
        facet_id="f1",
        source=_WDI,
    )
    monthly = _build_table(
        "Monthly",
        [("a", "2020-06", 10.0), ("b", "2021-06", 20.0)],
        facet_id="f2",
        source=_CENSUS,
    )
    mismatched = compute_derived_metric(annual, monthly, operation="ratio")
    assert mismatched.refusal_reason == "no_observations"
    assert mismatched.metrics is None
    assert mismatched.caveats == (
        "No observation of Annual and Monthly shares a place and date within "
        "the requested window, so nothing can be derived. Annual reports "
        "annual (YYYY) dates while Monthly reports monthly (YYYY-MM) dates, "
        "so no exact place and date pair can match; refetch one table at the "
        "other's granularity or align both to a shared date first.",
    )
    daily = _build_table(
        "Daily",
        [("a", "2020-06-15", 10.0)],
        facet_id="f2",
        source=_CENSUS,
    )
    daily_mismatch = compute_derived_metric(annual, daily, operation="ratio")
    assert "daily (YYYY-MM-DD) dates" in daily_mismatch.caveats[0]
    other_years = _build_table(
        "Other", [("a", "2010", 1.0)], facet_id="f2", source=_CENSUS
    )
    same_granularity = compute_derived_metric(
        annual, other_years, operation="ratio"
    )
    assert same_granularity.refusal_reason == "no_observations"
    assert same_granularity.metrics is None
    assert same_granularity.caveats == (
        "No observation of Annual and Other shares a place and date within "
        "the requested window, so nothing can be derived.",
    )
    out_of_window = compute_derived_metric(
        annual, monthly, operation="ratio", start_date="2019", end_date="2019"
    )
    assert out_of_window.refusal_reason == "no_observations"
    assert out_of_window.metrics is None
    assert out_of_window.caveats == (
        "No observation of Annual and Monthly shares a place and date within "
        "the requested window, so nothing can be derived.",
    )


@pytest.mark.parametrize(
    ("counts", "scale", "suffix"),
    [
        ((0.0, 0.0), 1.0, " per capita"),
        ((50_000.0, 120_000.0), 1.0, " per capita"),
        ((28.0, 40.0), 1_000.0, " per 1,000 people"),
        ((0.05, 0.08), 100_000.0, " per 100,000 people"),
        ((0.0001, 0.0002), 100_000.0, " per 100,000 people"),
    ],
    ids=[
        "all_zero",
        "per_person",
        "per_thousand",
        "per_hundred_thousand",
        "capped",
    ],
)
def test_a_per_capita_step_without_a_scale_takes_the_one_that_fits(
    counts: tuple[float, float], scale: float, suffix: str
) -> None:
    # Test: The automatic per-capita scale.
    # Situation: Two places of 1,000 people each report the given counts,
    #   and the step names no scale.
    # Expectation: The scale is the smallest of per person, per 1,000, and
    #   per 100,000 that puts the median value at or above one, capped at
    #   per 100,000; the values, the metrics, the table name, and the
    #   methodology all carry it.
    count = _build_table(
        "Count_Case",
        [("a", "2020", counts[0]), ("b", "2020", counts[1])],
        facet_id="f1",
        source=_WDI,
    )
    population = _build_table(
        "Count_Person",
        [("a", "2020", 1000.0), ("b", "2020", 1000.0)],
        facet_id="f2",
        source=_CENSUS,
    )

    outcome = derive_observation_table(
        count, population, operation="per_capita"
    )

    assert outcome.table is not None
    assert [row.value for row in outcome.table.rows] == [
        counts[0] * scale / 1000.0,
        counts[1] * scale / 1000.0,
    ]
    assert isinstance(outcome.result.metrics, DerivedMetrics)
    assert outcome.result.metrics.scale == scale
    assert outcome.table.variable_name == f"Count Case{suffix}"
    multiplied = f" and multiplied by {int(scale):,}" if scale != 1.0 else ""
    assert outcome.result.provenance.methodology is not None
    assert multiplied in outcome.result.provenance.methodology


def test_a_ratio_without_a_scale_is_unscaled() -> None:
    # Test: The default scale of a ratio.
    # Situation: A ratio step names no scale over values well below one.
    # Expectation: The values are the plain quotient; only a per-capita
    #   step chooses a scale from its values.
    count = _build_table(
        "Count_Case", [("a", "2020", 2.0)], facet_id="f1", source=_WDI
    )
    total = _build_table(
        "Count_All", [("a", "2020", 1000.0)], facet_id="f2", source=_CENSUS
    )

    outcome = derive_observation_table(count, total, operation="ratio")

    assert outcome.table is not None
    assert [row.value for row in outcome.table.rows] == [0.002]
    assert isinstance(outcome.result.metrics, DerivedMetrics)
    assert outcome.result.metrics.scale == 1.0


def test_quotients_multiply_by_the_scale_before_dividing() -> None:
    # Test: Order of arithmetic in scaled quotients.
    # Situation: 300 cases over a population of 1,000,000 per 100,000, where
    #   `(300 / 1_000_000) * 100_000` rounds to `29.999999999999996` while
    #   `300 * 100_000 / 1_000_000` is exact `30.0`.
    # Expectation: The derived row value is exact `30.0`.
    cases = _build_table(
        "Cases", [("a", "2022", 300.0)], facet_id="f1", source=_WDI
    )
    population = _build_table(
        "Pop", [("a", "2022", 1_000_000.0)], facet_id="f2", source=_CENSUS
    )
    outcome = derive_observation_table(
        cases, population, operation="per_capita", scale=100_000.0
    )
    assert outcome.table is not None
    assert outcome.table.rows[0].value == 30.0


def test_difference_sum_and_pct_change_keep_or_set_the_unit() -> None:
    # Test: The additive operations.
    # Situation: Two tables in thousands of dollars with values 150 and
    #   100 for one place.
    # Expectation: The difference is 50 and the sum 250, each keeping the
    #   unit and scaling factor of the inputs with a default name; the
    #   percentage change is 50 in `Percent` with no scaling factor and
    #   `scale == 1.0`; and each result carries the formula as its
    #   methodology.
    left = _build_table(
        "Revenue",
        [("a", "2020", 150.0)],
        facet_id="f1",
        source=_WDI,
        unit="USDollar",
        scaling_factor=1000.0,
    )
    right = _build_table(
        "Cost",
        [("a", "2020", 100.0)],
        facet_id="f2",
        source=_CENSUS,
        unit="USDollar",
        scaling_factor=1000.0,
    )
    difference = derive_observation_table(left, right, operation="difference")
    assert difference.table is not None
    assert difference.table.rows[0].value == 50.0
    assert difference.table.unit == "USDollar"
    assert difference.table.scaling_factor == 1000.0
    assert difference.table.variable_name == "Revenue minus Cost"
    assert difference.result.provenance.methodology == (
        "Revenue (Revenue) minus Cost (Cost). Observations are joined on "
        "place and date."
    )
    total = derive_observation_table(left, right, operation="sum")
    assert total.table is not None
    assert total.table.rows[0].value == 250.0
    assert total.table.variable_name == "Revenue plus Cost"
    change = derive_observation_table(left, right, operation="pct_change")
    assert change.table is not None
    assert change.table.rows[0].value == 50.0
    assert change.table.unit == "Percent"
    assert change.table.scaling_factor is None
    assert isinstance(change.result.metrics, DerivedMetrics)
    assert change.result.metrics.scale == 1.0
    assert (
        change.table.variable_name == "Percentage change from Cost to Revenue"
    )
    assert change.result.provenance.methodology == (
        "Revenue (Revenue) minus Cost (Cost), divided by the magnitude of "
        "Cost (Cost) and expressed in percent; pairs with a zero baseline "
        "are skipped. Observations are joined on place and date."
    )


def test_names_units_and_identifiers_can_be_overridden_and_sanitized() -> None:
    # Test: The naming defaults, their overrides, and display-name
    #   sanitization.
    # Situation: A ratio with the default scale, a ratio with a scale of
    #   100, a ratio with a scale of 2.5, a per-capita rate with an explicit
    #   DCID, a name containing newlines and zero-width spaces, and a unit
    #   containing extra whitespace, plus an empty-after-sanitization unit on
    #   a difference.
    # Expectation: The default names read `A / B`, `A as a percentage of
    #   B`, and `A / B, times 2.5`; the explicit values are sanitized via
    #   `clean_display_name` on both the table and the result; and an empty
    #   sanitized unit falls back to the operation's default unit.
    left = _build_table(
        "Exports",
        [("a", "2020", 3.0)],
        facet_id="f1",
        source=_WDI,
        unit="USDollar",
    )
    right = _build_table(
        "Imports",
        [("a", "2020", 2.0)],
        facet_id="f2",
        source=_CENSUS,
        unit="USDollar",
    )
    plain = derive_observation_table(left, right)
    assert plain.table is not None
    assert plain.table.variable_name == "Exports / Imports"
    assert plain.table.rows[0].value == 1.5
    percent = derive_observation_table(left, right, scale=100.0)
    assert percent.table is not None
    assert percent.table.variable_name == "Exports as a percentage of Imports"
    assert percent.table.rows[0].value == 150.0
    scaled = derive_observation_table(left, right, scale=2.5)
    assert scaled.table is not None
    assert scaled.table.variable_name == "Exports / Imports, times 2.5"
    explicit = derive_observation_table(
        left,
        right,
        operation="per_capita",
        derived_variable_dcid="ExportsPerImport",
        derived_variable_name="Exports\n\u200b per   import",
        derived_unit="Ratio\t\u200b unit",
        step_id="s7",
    )
    assert explicit.table is not None
    assert explicit.table.variable_dcid == "ExportsPerImport"
    assert explicit.table.variable_name == "Exports per import"
    assert explicit.table.unit == "Ratio unit"
    assert explicit.result.step_id == "s7"
    assert explicit.result.unit == "Ratio unit"
    assert isinstance(explicit.result.metrics, DerivedMetrics)
    assert explicit.result.metrics.derived_variable_dcid == "ExportsPerImport"
    assert explicit.result.metrics.derived_variable_name == "Exports per import"

    blank_unit = derive_observation_table(
        left, right, operation="difference", derived_unit="   \u200b  "
    )
    assert blank_unit.table is not None
    assert blank_unit.table.unit == "USDollar"


@pytest.mark.parametrize(
    ("scale", "detail"),
    [
        (True, "True"),
        (0.0, "0.0"),
        (-1.0, "-1.0"),
        (float("inf"), "inf"),
        (float("nan"), "nan"),
    ],
    ids=["bool", "zero", "negative", "infinite", "nan"],
)
def test_a_bad_scale_is_refused_as_invalid_parameters(
    scale: float, detail: str
) -> None:
    # Test: Validation of `scale`.
    # Situation: A boolean, zero, a negative number, infinity, and NaN.
    # Expectation: Each is refused with `invalid_parameters`, no table,
    #   `metrics=None`, and a caveat naming the value.
    outcome = derive_observation_table(
        _build_count_table(), _build_population_table(), scale=scale
    )
    assert outcome.table is None
    assert outcome.result.refusal_reason == "invalid_parameters"
    assert outcome.result.metrics is None
    assert outcome.result.caveats == (
        f"The scale must be a finite number above zero, not {detail}.",
    )


@pytest.mark.parametrize("operation", ["difference", "sum", "pct_change"])
def test_scale_on_non_quotient_operation_is_refused_as_invalid_parameters(
    operation: DerivedOperation,
) -> None:
    # Test: Rejecting `scale` on operations that do not take a multiplier.
    # Situation: `difference`, `sum`, and `pct_change` called with
    #   `scale=10.0`.
    # Expectation: Each is refused with `invalid_parameters` and a caveat
    #   stating that `scale` applies only to `per_capita` and `ratio`.
    outcome = derive_observation_table(
        _build_count_table(),
        _build_population_table(),
        operation=operation,
        scale=10.0,
    )
    assert outcome.table is None
    assert outcome.result.refusal_reason == "invalid_parameters"
    assert outcome.result.caveats == (
        "The scale parameter applies only to 'per_capita' and 'ratio', not "
        f"{operation!r}.",
    )


def test_bad_parameters_and_repeated_variables_are_refused() -> None:
    # Test: Validation of operation name, date window, `derived_variable_dcid`,
    #   `places`, `min_coverage`, and distinct input variables.
    # Situation: An unrecognized operation; a `start_date` of `latest` and
    #   a calendar-impossible `end_date` of `2021-02-29`; an inverted window;
    #   an invalid `derived_variable_dcid`; a bare string and an invalid DCID
    #   in `places`; an out-of-range `min_coverage`; and the same variable on
    #   both sides.
    # Expectation: Each is refused with `invalid_parameters` and a clear
    #   caveat; the repeated-variable refusal deduplicates `variables` while
    #   keeping the first input's display name.
    count = _build_count_table()
    population = _build_population_table()

    bad_operation = derive_observation_table(
        count,
        population,
        operation="product",
        derived_unit="  Custom\nUnit ",
    )
    assert bad_operation.table is None
    assert bad_operation.result.refusal_reason == "invalid_parameters"
    assert bad_operation.result.unit == "Custom Unit"
    assert bad_operation.result.caveats == (
        "The operation must be 'per_capita', 'ratio', 'difference', 'sum', "
        "or 'pct_change', not 'product'.",
    )

    bad_bound = compute_derived_metric(count, population, start_date="latest")
    assert bad_bound.refusal_reason == "invalid_parameters"
    assert bad_bound.caveats == (
        "The date bound 'latest' is not a year, a year and month, or a full "
        "date.",
    )

    impossible_date = compute_derived_metric(
        count, population, end_date="2021-02-29"
    )
    assert impossible_date.refusal_reason == "invalid_parameters"
    assert impossible_date.caveats == (
        "The date bound '2021-02-29' is not a year, a year and month, or a "
        "full date.",
    )

    inverted = compute_derived_metric(
        count, population, start_date="2021", end_date="2020"
    )
    assert inverted.refusal_reason == "invalid_parameters"
    assert inverted.caveats == (
        "The date window starts at 2021 and ends at 2020, which is before "
        "it starts.",
    )

    bad_dcid = compute_derived_metric(
        count, population, derived_variable_dcid="bad dcid"
    )
    assert bad_dcid.refusal_reason == "invalid_parameters"
    assert bad_dcid.caveats == ("derived_variable_dcid must be a valid DCID.",)

    bare_places = compute_derived_metric(count, population, places="geoId/06")
    assert bare_places.refusal_reason == "invalid_parameters"
    assert bare_places.caveats == (
        "places must be a sequence of DCIDs, not the string 'geoId/06'.",
    )

    invalid_place = compute_derived_metric(
        count, population, places=["a", "not a dcid"]
    )
    assert invalid_place.refusal_reason == "invalid_parameters"
    assert invalid_place.caveats == (
        "places must hold DCIDs, but entry 2 of 2 is not a valid DCID.",
    )

    bad_coverage = compute_derived_metric(count, population, min_coverage=1.5)
    assert bad_coverage.refusal_reason == "invalid_parameters"
    assert bad_coverage.caveats == (
        "The minimum coverage must be between 0 and 1, not 1.5.",
    )

    duplicate_right = ObservationTable(
        variable_dcid="Count_Case",
        variable_name="Alternate case label",
        unit=count.unit,
        scaling_factor=count.scaling_factor,
        provenance=population.provenance,
        rows=population.rows,
        requested_places=population.requested_places,
        place_names=population.place_names,
    )
    repeated = compute_derived_metric(count, duplicate_right)
    assert repeated.refusal_reason == "invalid_parameters"
    assert repeated.variables == ("Count_Case",)
    assert repeated.variable_names == {"Count_Case": "Count Case"}
    assert repeated.caveats == (
        "left and right must be different variables, but Count_Case was "
        "given for both.",
    )


def test_helper_preconditions_raise_value_error_on_invalid_scale() -> None:
    # Test: Preconditions on `_format_scale`, `_apply_operation`, and
    #   `_select_fitting_scale`.
    # Situation: `_format_scale` and `_apply_operation` called with boolean,
    #   zero, negative, infinite, and NaN scales; `_select_fitting_scale`
    #   called with an empty sequence.
    # Expectation: `_format_scale` and `_apply_operation` raise `ValueError`
    #   on every invalid scale; `_select_fitting_scale([])` returns `1.0`.
    for invalid_scale in (True, 0.0, -2.0, float("inf"), float("nan")):
        with pytest.raises(ValueError, match="finite number above zero"):
            _format_scale(invalid_scale)
        with pytest.raises(ValueError, match="finite number above zero"):
            _apply_operation("ratio", 10.0, 2.0, invalid_scale)
    assert _select_fitting_scale([]) == 1.0


def test_unit_rules_depend_on_the_operation() -> None:
    # Test: Unit and scaling compatibility per operation.
    # Situation: Dollars against euros, and dollars against thousands of
    #   dollars, each tried as a difference and as a ratio.
    # Expectation: The difference refuses both, as `unit_mismatch` and
    #   `scaling_mismatch`; the ratio allows the differing units but
    #   refuses the differing scaling factors with a message naming both
    #   variables.
    dollars = _build_table(
        "Gdp",
        [("a", "2020", 2.0)],
        facet_id="f1",
        source=_WDI,
        unit="USDollar",
    )
    euros = _build_table(
        "Debt",
        [("a", "2020", 1.0)],
        facet_id="f2",
        source=_CENSUS,
        unit="Euro",
    )
    thousands = _build_table(
        "Debt",
        [("a", "2020", 1.0)],
        facet_id="f2",
        source=_CENSUS,
        unit="USDollar",
        scaling_factor=1000.0,
    )
    assert (
        compute_derived_metric(
            dollars, euros, operation="difference"
        ).refusal_reason
        == "unit_mismatch"
    )
    assert (
        compute_derived_metric(
            dollars, thousands, operation="difference"
        ).refusal_reason
        == "scaling_mismatch"
    )
    ratio = compute_derived_metric(dollars, euros, operation="ratio")
    assert ratio.status == "ok"
    assert isinstance(ratio.metrics, DerivedMetrics)
    assert ratio.metrics.value_range == (2.0, 2.0)
    scaled = compute_derived_metric(dollars, thousands, operation="ratio")
    assert scaled.refusal_reason == "scaling_mismatch"
    assert scaled.metrics is None
    assert scaled.caveats == (
        "Scaling factors differ: Gdp (Gdp) reports a scaling factor of 1; "
        "Debt (Debt) reports a scaling factor of 1000.",
    )


def test_the_target_places_window_and_duplicates_follow_the_join_rules() -> (
    None
):
    # Test: The target places, cohort metadata fallbacks, the date window,
    #   and duplicate rows.
    # Situation: The count and population tables joined with `places`
    #   naming `b` and an unknown `z`; with a window of 2021 only; with no
    #   requested places on either table so the union of observed places
    #   applies; with `left` lacking `requested_places` and cohort metadata
    #   while `right` provides both; with `left` specifying a subset of
    #   `right.requested_places` without cohort metadata; and with a
    #   duplicate population row for `a` on 2020 whose last value is
    #   retained.
    # Expectation: The `places` join covers 1 of 2 with `z` missing; the
    #   window keeps only the 2021 rows; the union target places are `a`,
    #   `b`, and `c`; `right.requested_places` and `right`'s cohort metadata
    #   apply when `left.requested_places` is empty, whereas a proper subset
    #   on `left` leaves cohort metadata as `None`; and the duplicate yields
    #   the later denominator.
    restricted = derive_observation_table(
        _build_count_table(), _build_population_table(), places=["b", "z", "b"]
    )
    assert restricted.result.coverage is not None
    assert restricted.result.coverage.requested_places == 2
    assert isinstance(restricted.result.metrics, DerivedMetrics)
    assert restricted.result.metrics.missing_places == ("z",)
    assert restricted.table is not None
    assert {row.place_dcid for row in restricted.table.rows} == {"b"}
    assert restricted.table.place_names["z"] == "z"
    windowed = compute_derived_metric(
        _build_count_table(),
        _build_population_table(),
        start_date="2021",
        end_date="2021",
    )
    assert isinstance(windowed.metrics, DerivedMetrics)
    assert windowed.metrics.date_range == ("2021", "2021")
    assert windowed.metrics.observation_count == 2
    unrequested = _build_table(
        "Count_Case",
        [("a", "2020", 1.0), ("c", "2020", 1.0)],
        facet_id="f1",
        source=_WDI,
    )
    union = compute_derived_metric(unrequested, _build_population_table())
    assert union.coverage is not None
    assert union.coverage.requested_places == 3
    assert isinstance(union.metrics, DerivedMetrics)
    assert union.metrics.missing_places == ("c", "b")
    right_with_cohort = _build_table(
        "Count_Person",
        [("a", "2020", 1000.0), ("b", "2020", 1250.0)],
        facet_id="f2",
        source=_CENSUS,
        requested_places=["a", "b", "d"],
        parent_place_dcid="country/USA",
        child_place_type="State",
    )
    right_fallback = derive_observation_table(unrequested, right_with_cohort)
    assert right_fallback.table is not None
    assert right_fallback.table.requested_places == ("a", "b", "d")
    assert right_fallback.table.parent_place_dcid == "country/USA"
    assert right_fallback.table.child_place_type == "State"
    assert isinstance(right_fallback.result.metrics, DerivedMetrics)
    assert right_fallback.result.metrics.missing_places == ("b", "d")
    left_subset = _build_table(
        "Count_Case",
        [("a", "2020", 1.0), ("b", "2020", 2.0)],
        facet_id="f1",
        source=_WDI,
        requested_places=["a", "b"],
    )
    subset_outcome = derive_observation_table(left_subset, right_with_cohort)
    assert subset_outcome.table is not None
    assert subset_outcome.table.requested_places == ("a", "b")
    assert subset_outcome.table.parent_place_dcid is None
    assert subset_outcome.table.child_place_type is None
    duplicated = _build_table(
        "Count_Person",
        [("a", "2020", 1.0), ("a", "2020", 4.0)],
        facet_id="f2",
        source=_CENSUS,
    )
    outcome = derive_observation_table(
        _build_count_table(), duplicated, operation="ratio", places=["a"]
    )
    assert outcome.table is not None
    assert outcome.table.rows[0].value == 2.5


def test_min_coverage_refuses_a_sparse_join_with_its_coverage() -> None:
    # Test: The optional coverage floor across plural and singular counts.
    # Situation: The count and population tables, whose join covers 2 of
    #   the 3 requested places, with `min_coverage` of 0.9; and a 1-of-4
    #   join with `min_coverage` of 0.625.
    # Expectation: Each is refused with `insufficient_coverage`, no table,
    #   the coverage figure, and a caveat with matching verb (`have` vs
    #   `has`) and formatted percentage (`90%` vs `62.5%`).
    outcome = derive_observation_table(
        _build_count_table(), _build_population_table(), min_coverage=0.9
    )
    assert outcome.table is None
    assert outcome.result.refusal_reason == "insufficient_coverage"
    assert outcome.result.metrics is None
    assert outcome.result.coverage is not None
    assert outcome.result.coverage.contributing_places == 2
    assert outcome.result.caveats == (
        "Only 2 of 3 places have a derived value, below the required 90% "
        "coverage.",
    )

    singular = derive_observation_table(
        _build_count_table(),
        _build_population_table(),
        places=["a", "c", "d", "e"],
        min_coverage=0.625,
    )
    assert singular.table is None
    assert singular.result.refusal_reason == "insufficient_coverage"
    assert singular.result.caveats == (
        "Only 1 of 4 places has a derived value, below the required 62.5% "
        "coverage.",
    )


@pytest.mark.parametrize(
    "operation", ["per_capita", "ratio", "difference", "sum", "pct_change"]
)
def test_compute_derived_metric_returns_the_outcome_result(
    operation: DerivedOperation,
) -> None:
    # Test: The result-only wrapper.
    # Situation: Each operation run through both entry points with the
    #   same arguments.
    # Expectation: `compute_derived_metric` returns exactly the result of
    #   `derive_observation_table`.
    assert compute_derived_metric(
        _build_count_table(),
        _build_population_table(),
        operation=operation,
        step_id="s3",
    ) == (
        derive_observation_table(
            _build_count_table(),
            _build_population_table(),
            operation=operation,
            step_id="s3",
        ).result
    )


@dataclass(frozen=True)
class _OracleExpectation:
    """Independent oracle prediction for one derived-metric scenario."""

    expected_status: str
    expected_refusal_reason: str | None
    expected_rows: tuple[tuple[str, str, float], ...]
    expected_scale: float
    expected_unit: str | None
    expected_scaling_factor: float | None
    expected_target_places: tuple[str, ...]
    expected_contributing_places: int
    expected_missing_places: tuple[str, ...]
    expected_skipped_count: int


def _compute_oracle_pair_value(
    operation: DerivedOperation,
    left_value: float,
    right_value: float,
    scale: float,
) -> float | None:
    """Computes one pair's derived value from first principles, or None."""
    if operation == "per_capita":
        if right_value <= 0.0:
            return None
        candidate = left_value * scale / right_value
    elif operation == "ratio":
        if right_value == 0.0:
            return None
        candidate = left_value * scale / right_value
    elif operation == "difference":
        candidate = left_value - right_value
    elif operation == "sum":
        candidate = left_value + right_value
    else:
        if right_value == 0.0:
            return None
        candidate = (left_value - right_value) / abs(right_value) * 100.0
    return candidate if math.isfinite(candidate) else None


def _build_oracle_expectation(
    left: ObservationTable,
    right: ObservationTable,
    *,
    operation: DerivedOperation,
    scale: float | None,
    places: Sequence[str] | None,
    start_date: str | None,
    end_date: str | None,
    min_coverage: float,
) -> _OracleExpectation:
    """Computes the expected outcome of `derive_observation_table`."""
    if operation in ("difference", "sum"):
        expected_unit: str | None = left.unit
        expected_scaling_factor: float | None = left.scaling_factor
    elif operation == "pct_change":
        expected_unit = "Percent"
        expected_scaling_factor = None
    else:
        expected_unit = None
        expected_scaling_factor = None

    if places:
        target_places = tuple(dict.fromkeys(places))
    elif left.requested_places:
        target_places = tuple(dict.fromkeys(left.requested_places))
    elif right.requested_places:
        target_places = tuple(dict.fromkeys(right.requested_places))
    else:
        left_places = sorted({row.place_dcid for row in left.rows})
        right_places = sorted({row.place_dcid for row in right.rows})
        target_places = tuple(dict.fromkeys([*left_places, *right_places]))

    target_set = frozenset(target_places)
    left_map = {
        (row.place_dcid, row.date): row.value
        for row in left.rows
        if row.place_dcid in target_set
        and is_within_date_range(row.date, start_date, end_date)
    }
    right_map = {
        (row.place_dcid, row.date): row.value
        for row in right.rows
        if row.place_dcid in target_set
        and is_within_date_range(row.date, start_date, end_date)
    }
    shared_keys = sorted(left_map.keys() & right_map.keys())

    if scale is not None:
        resolved_scale = scale
    elif operation == "per_capita":
        unscaled = [
            value
            for key in shared_keys
            if (
                value := _compute_oracle_pair_value(
                    operation, left_map[key], right_map[key], 1.0
                )
            )
            is not None
            and value != 0.0
        ]
        if not unscaled:
            resolved_scale = 1.0
        else:
            median_magnitude = statistics.median(
                abs(value) for value in unscaled
            )
            resolved_scale = 100_000.0
            for candidate_scale in (1.0, 1_000.0, 100_000.0):
                if median_magnitude * candidate_scale >= 1.0:
                    resolved_scale = candidate_scale
                    break
    else:
        resolved_scale = 1.0

    derived_rows: list[tuple[str, str, float]] = []
    skipped_count = 0
    for place, date in shared_keys:
        computed = _compute_oracle_pair_value(
            operation,
            left_map[place, date],
            right_map[place, date],
            resolved_scale,
        )
        if computed is None:
            skipped_count += 1
        else:
            derived_rows.append((place, date, computed))

    joined_places = {place for place, _, _ in derived_rows}
    missing_places = tuple(
        place for place in target_places if place not in joined_places
    )
    contributing_count = len(joined_places)

    if not derived_rows:
        return _OracleExpectation(
            expected_status="refused",
            expected_refusal_reason="no_observations",
            expected_rows=(),
            expected_scale=resolved_scale,
            expected_unit=expected_unit,
            expected_scaling_factor=expected_scaling_factor,
            expected_target_places=target_places,
            expected_contributing_places=0,
            expected_missing_places=target_places,
            expected_skipped_count=skipped_count,
        )

    ratio = contributing_count / len(target_places)
    has_coverage = min_coverage <= 0.0 or (
        ratio >= min_coverage or math.isclose(ratio, min_coverage)
    )
    if not has_coverage:
        return _OracleExpectation(
            expected_status="refused",
            expected_refusal_reason="insufficient_coverage",
            expected_rows=(),
            expected_scale=resolved_scale,
            expected_unit=expected_unit,
            expected_scaling_factor=expected_scaling_factor,
            expected_target_places=target_places,
            expected_contributing_places=contributing_count,
            expected_missing_places=missing_places,
            expected_skipped_count=skipped_count,
        )

    return _OracleExpectation(
        expected_status="ok",
        expected_refusal_reason=None,
        expected_rows=tuple(derived_rows),
        expected_scale=resolved_scale,
        expected_unit=expected_unit,
        expected_scaling_factor=expected_scaling_factor,
        expected_target_places=target_places,
        expected_contributing_places=contributing_count,
        expected_missing_places=missing_places,
        expected_skipped_count=skipped_count,
    )


def _build_invariant_fixtures() -> tuple[ObservationTable, ObservationTable]:
    """Builds deterministic left and right tables with edge-case rows."""
    left = _build_table(
        "Metric_Left",
        [
            ("p1", "2020", 12.0),
            ("p1", "2021", 36.0),
            ("p2", "2020", 0.0),
            ("p2", "2021", 150.0),
            ("p3", "2020", 25.0),
            ("p3", "2021", 1e308),
            ("p4", "2020", 40.0),
            ("p5", "2022", 80.0),
        ],
        facet_id="f1",
        source=_WDI,
        requested_places=["p1", "p2", "p3", "p4", "p6"],
        unit="USDollar",
        scaling_factor=100.0,
    )
    right = _build_table(
        "Metric_Right",
        [
            ("p1", "2020", 400.0),
            ("p1", "2020", 600.0),
            ("p1", "2021", 1200.0),
            ("p2", "2020", 0.0),
            ("p2", "2021", -50.0),
            ("p3", "2020", 500.0),
            ("p3", "2021", 1e-308),
            ("p5", "2020", 90.0),
        ],
        facet_id="f2",
        source=_CENSUS,
        unit="USDollar",
        scaling_factor=100.0,
    )
    return left, right


def _assert_outcome_matches_oracle_rows_and_status(
    outcome: DerivedMetricOutcome, oracle: _OracleExpectation
) -> None:
    """Asserts that the outcome status, table presence, and rows match."""
    assert outcome.result.status == oracle.expected_status
    if oracle.expected_status == "refused":
        assert outcome.table is None
        assert isinstance(outcome.result, RefusedScriptResult)
        assert outcome.result.refusal_reason == oracle.expected_refusal_reason
        return

    assert outcome.table is not None
    assert isinstance(outcome.result, OkScriptResult)
    actual_rows = tuple(
        (row.place_dcid, row.date, row.value) for row in outcome.table.rows
    )
    assert len(actual_rows) == len(oracle.expected_rows)
    for (actual_place, actual_date, actual_value), (
        expected_place,
        expected_date,
        expected_value,
    ) in zip(actual_rows, oracle.expected_rows, strict=True):
        assert actual_place == expected_place
        assert actual_date == expected_date
        assert math.isclose(
            actual_value, expected_value, rel_tol=1e-12, abs_tol=0.0
        )


def _assert_outcome_matches_oracle_metrics_and_units(
    outcome: DerivedMetricOutcome, oracle: _OracleExpectation
) -> None:
    """Asserts that units, scaling factors, and `DerivedMetrics` match."""
    assert outcome.result.unit == oracle.expected_unit
    assert outcome.result.scaling_factor == oracle.expected_scaling_factor
    if oracle.expected_status == "refused":
        assert outcome.result.metrics is None
        return

    assert outcome.table is not None
    assert outcome.table.unit == oracle.expected_unit
    assert outcome.table.scaling_factor == oracle.expected_scaling_factor
    metrics = outcome.result.metrics
    assert isinstance(metrics, DerivedMetrics)
    assert metrics.scale == oracle.expected_scale
    assert metrics.observation_count == len(oracle.expected_rows)
    assert metrics.place_count == oracle.expected_contributing_places
    assert metrics.missing_places == oracle.expected_missing_places
    values = [value for _, _, value in oracle.expected_rows]
    dates = [date for _, date, _ in oracle.expected_rows]
    assert metrics.value_range == (min(values), max(values))
    assert metrics.date_range == (min(dates), max(dates))
    count = len(outcome.table.rows)
    sample_indices = (
        list(range(count))
        if count <= 5
        else sorted({round(index * (count - 1) / 4) for index in range(5)})
    )
    assert metrics.sample_rows == tuple(
        outcome.table.rows[index] for index in sample_indices
    )


def _assert_outcome_matches_oracle_coverage_and_caveats(
    outcome: DerivedMetricOutcome, oracle: _OracleExpectation
) -> None:
    """Asserts that coverage counts, missing places, and caveats match."""
    coverage = outcome.result.coverage
    assert coverage is not None
    assert coverage.requested_places == len(oracle.expected_target_places)
    assert coverage.contributing_places == oracle.expected_contributing_places
    assert coverage.missing_places == oracle.expected_missing_places
    expected_ratio = oracle.expected_contributing_places / len(
        oracle.expected_target_places
    )
    assert math.isclose(coverage.coverage_ratio, expected_ratio)
    if oracle.expected_skipped_count > 0:
        assert any("skipped" in caveat for caveat in outcome.result.caveats)
    else:
        assert not any("skipped" in caveat for caveat in outcome.result.caveats)


def test_derived_metric_invariants_across_deterministic_grid() -> None:
    # Test: Brute-force invariants across operations, scales, place filters,
    #   date windows, zero/negative denominators, overflow, and coverage
    #   floors against an independent oracle.
    # Situation: Deterministic left and right tables with duplicate dates,
    #   zero and negative denominators, overflow pairs, unjoined places, and
    #   multiple dates, evaluated across all five operations, valid scales,
    #   place subsets, windows, and `min_coverage` thresholds.
    # Expectation: Every run matches `_build_oracle_expectation` on status,
    #   refusal reason, derived rows, resolved scale, unit, scaling factor,
    #   metrics ranges, coverage report, and skip caveats.
    left, right = _build_invariant_fixtures()
    operations: tuple[DerivedOperation, ...] = (
        "per_capita",
        "ratio",
        "difference",
        "sum",
        "pct_change",
    )
    place_options: tuple[Sequence[str] | None, ...] = (
        None,
        ("p1", "p2", "p3"),
        ("p2", "p6"),
    )
    window_options: tuple[tuple[str | None, str | None], ...] = (
        (None, None),
        ("2020", "2020"),
        ("2021", "2021"),
        ("2018", "2018"),
    )
    coverage_options: tuple[float, ...] = (0.0, 0.5, 0.95)

    for operation in operations:
        scales: tuple[float | None, ...] = (
            (None, 1.0, 100.0)
            if operation in ("per_capita", "ratio")
            else (None,)
        )
        for scale in scales:
            for places in place_options:
                for start_date, end_date in window_options:
                    for min_coverage in coverage_options:
                        outcome = derive_observation_table(
                            left,
                            right,
                            operation=operation,
                            scale=scale,
                            places=places,
                            start_date=start_date,
                            end_date=end_date,
                            min_coverage=min_coverage,
                        )
                        oracle = _build_oracle_expectation(
                            left,
                            right,
                            operation=operation,
                            scale=scale,
                            places=places,
                            start_date=start_date,
                            end_date=end_date,
                            min_coverage=min_coverage,
                        )
                        _assert_outcome_matches_oracle_rows_and_status(
                            outcome, oracle
                        )
                        _assert_outcome_matches_oracle_metrics_and_units(
                            outcome, oracle
                        )
                        _assert_outcome_matches_oracle_coverage_and_caveats(
                            outcome, oracle
                        )
