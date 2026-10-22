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
"""Tests for `summarize_distribution` in `analytics.distribution`.

Covers cohort statistics, focal-place benchmarks, extrema ties, small and
constant cohorts, population-weighted means, and refusal propagation.
"""

import functools
import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

import pytest

from narratives_agent.analytics.alignment import (
    AlignedCohort,
    AlignmentRefusal,
    align_cohort,
)
from narratives_agent.analytics.digest import ScriptResult
from narratives_agent.analytics.distribution import summarize_distribution
from narratives_agent.analytics.metrics import (
    DistributionFocalEntry,
    DistributionMetrics,
    PlaceValue,
)
from narratives_agent.analytics.provenance import Provenance, Source
from narratives_agent.analytics.tables import ObservationRow, ObservationTable

_SOURCE = Source(name="Wikidata", url="https://wikidata")
_CENSUS = Source(name="Census", url="https://census")


def _build_table(
    observations: Sequence[tuple[str, str, float]],
    *,
    requested_places: Sequence[str] = (),
    variable_dcid: str = "Count_Person",
    variable_name: str = "Total population",
    facet_id: str = "f1",
    source: Source = _SOURCE,
) -> ObservationTable:
    """Builds a table from `(place, date, value)` triples in table order."""
    places = list(
        dict.fromkeys(
            [*requested_places, *(place for place, _, _ in observations)]
        )
    )
    return ObservationTable(
        variable_dcid=variable_dcid,
        variable_name=variable_name,
        unit="Person",
        scaling_factor=None,
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
    )


def _build_five_place_cohort() -> ObservationTable:
    """Five places on one date with values 1, 2, 3, 4, and 10."""
    return _build_table(
        [
            ("e", "2022", 10.0),
            ("a", "2022", 1.0),
            ("c", "2022", 3.0),
            ("b", "2022", 2.0),
            ("d", "2022", 4.0),
        ]
    )


def _build_weights(
    observations: Sequence[tuple[str, str, float]],
) -> ObservationTable:
    """Builds a population weights table from `_CENSUS`."""
    return _build_table(
        observations,
        variable_dcid="Count_Person_Weight",
        variable_name="Weight population",
        facet_id="f2",
        source=_CENSUS,
    )


def test_cohort_statistics_and_focal_benchmarks_are_exact() -> None:
    # Test: The full distribution of a cohort with focal places.
    # Situation: Values 1, 2, 3, 4, and 10 across places a to e on one
    #   date, with focal places `e`, an unknown `z`, and `a`, with `e`
    #   repeated.
    # Expectation: Mean 4, median 3, min `a` and max `e`, a gap of 9, the
    #   sample standard deviation, quartiles 2, 3, 4 with an IQR of 2,
    #   deciles by linear interpolation, the adjusted sample skewness, one
    #   focal entry each for `e` and `a` with their offsets, z-scores, and
    #   percentiles, `z` listed as missing with a caveat, no weighted mean,
    #   and a methodology naming the cohort, the date, and the benchmarks.
    result = summarize_distribution(
        _build_five_place_cohort(), focal_places=["e", "z", "a", "e"]
    )
    assert result.status == "ok"
    assert result.variables == ("Count_Person",)
    assert result.coverage is not None
    assert result.coverage.contributing_places == 5
    metrics = result.metrics
    assert isinstance(metrics, DistributionMetrics)
    assert metrics.reference_date == "2022"
    assert metrics.cohort_size == 5
    assert metrics.mean == 4.0
    assert metrics.median == 3.0
    assert metrics.min == PlaceValue(
        place_dcid="a",
        place_name="A",
        value=1.0,
    )
    assert metrics.max == PlaceValue(
        place_dcid="e",
        place_name="E",
        value=10.0,
    )
    assert metrics.max_minus_min == 9.0
    assert metrics.stdev == pytest.approx(3.5355339059327378)
    assert (metrics.q25, metrics.q50, metrics.q75) == (2.0, 3.0, 4.0)
    assert metrics.iqr == 2.0
    assert metrics.deciles == pytest.approx(
        {
            "p10": 1.4,
            "p20": 1.8,
            "p30": 2.2,
            "p40": 2.6,
            "p50": 3.0,
            "p60": 3.4,
            "p70": 3.8,
            "p80": 5.2,
            "p90": 7.6,
        }
    )
    assert metrics.skewness == pytest.approx(1.697056274847714)
    assert metrics.weighted_mean is None
    assert metrics.weight_variable_dcid is None
    assert metrics.weighted_place_count is None
    assert len(metrics.focal_entries) == 2
    entry_e, entry_a = metrics.focal_entries
    assert entry_e.place_dcid == "e"
    assert entry_e.place_name == "E"
    assert entry_e.value == 10.0
    assert entry_e.diff_from_median == 7.0
    assert entry_e.pct_of_median == pytest.approx(333.3333333333333)
    assert entry_e.diff_from_mean == 6.0
    assert entry_e.z_score == pytest.approx(1.697056274847714)
    assert entry_e.percentile == 100.0
    assert entry_a.place_dcid == "a"
    assert entry_a.place_name == "A"
    assert entry_a.value == 1.0
    assert entry_a.diff_from_median == -2.0
    assert entry_a.pct_of_median == pytest.approx(33.33333333333333)
    assert entry_a.diff_from_mean == -3.0
    assert entry_a.z_score == pytest.approx(-0.848528137423857)
    assert entry_a.percentile == 20.0
    assert metrics.missing_focal_places == ("z",)
    assert result.caveats == (
        "z has no value for Total population in the cohort on 2022, so no "
        "benchmark is available.",
    )
    assert result.provenance.sources == (_SOURCE,)
    assert result.provenance.methodology == (
        "Distribution of Total population across 5 places on 2022: mean, "
        "median, minimum, maximum, the gap from minimum to maximum "
        "(max_minus_min), sample standard deviation, quartiles and deciles "
        "by linear interpolation, and adjusted Fisher-Pearson sample "
        "skewness; focal places are compared with the cohort mean, median, "
        "and percentile."
    )


def test_skewness_and_z_score_of_an_asymmetric_cohort() -> None:
    # Test: The skewness and a focal z-score of a right-skewed cohort.
    # Situation: Values 1, 2, 3, 5, and 10 across places a to e, with `e`
    #   focal.
    # Expectation: The adjusted Fisher-Pearson sample skewness and the
    #   z-score of `e` equal their reference values.
    asymmetric = summarize_distribution(
        _build_table(
            [
                ("a", "2022", 1.0),
                ("b", "2022", 2.0),
                ("c", "2022", 3.0),
                ("d", "2022", 5.0),
                ("e", "2022", 10.0),
            ]
        ),
        focal_places=["e"],
    ).metrics
    assert isinstance(asymmetric, DistributionMetrics)
    assert asymmetric.skewness == pytest.approx(1.3853578163699949)
    assert asymmetric.focal_entries[0].z_score == pytest.approx(
        1.6275192464723098
    )


def test_extrema_ties_resolve_to_the_smallest_dcid() -> None:
    # Test: Tie-breaking for the minimum and maximum.
    # Situation: Places `d` and `c` share the minimum and `b` and `a` share
    #   the maximum.
    # Expectation: `min` names `c` and `max` names `a`, the smaller DCID in
    #   each tie.
    metrics = summarize_distribution(
        _build_table(
            [
                ("d", "2022", 1.0),
                ("c", "2022", 1.0),
                ("b", "2022", 9.0),
                ("a", "2022", 9.0),
            ]
        )
    ).metrics
    assert isinstance(metrics, DistributionMetrics)
    assert metrics.min.place_dcid == "c"
    assert metrics.max.place_dcid == "a"


def test_a_cohort_of_one_place_has_no_dispersion() -> None:
    # Test: The one-place boundary.
    # Situation: A single place with one value, which is also a focal
    #   place.
    # Expectation: Mean and median equal the value, the standard
    #   deviation, quartiles, IQR, deciles, and skewness are None with a
    #   caveat naming the threshold, and the focal entry has no z-score but
    #   is at the hundredth percentile.
    result = summarize_distribution(
        _build_table([("a", "2022", 7.0)]), focal_places=["a"]
    )
    assert result.status == "ok"
    metrics = result.metrics
    assert isinstance(metrics, DistributionMetrics)
    assert metrics.cohort_size == 1
    assert (
        metrics.mean,
        metrics.median,
        metrics.max_minus_min,
    ) == (7.0, 7.0, 0.0)
    assert metrics.stdev is None
    assert (metrics.q25, metrics.q50, metrics.q75) == (
        None,
        None,
        None,
    )
    assert metrics.iqr is None
    assert metrics.deciles is None
    assert metrics.skewness is None
    assert metrics.focal_entries[0].z_score is None
    assert metrics.focal_entries[0].percentile == 100.0
    assert result.caveats == (
        "Only one place (A) reported a value for Total population on 2022; "
        "dispersion, quantiles, and z-scores require at least 2 places and "
        "skewness at least 3, so they are not computed.",
    )
    assert result.provenance.methodology == (
        "Distribution of Total population across 1 place on 2022: mean, "
        "median, minimum, maximum, and the gap from minimum to maximum "
        "(max_minus_min); focal places are compared with the cohort mean, "
        "median, and percentile."
    )


def test_a_cohort_of_two_places_has_dispersion_but_no_skewness() -> None:
    # Test: The two-place boundary.
    # Situation: Two places with values 2 and 4.
    # Expectation: The standard deviation, quartiles, IQR, and deciles are
    #   computed by interpolation between the two values, and skewness is
    #   None with a caveat naming its threshold.
    result = summarize_distribution(
        _build_table([("a", "2022", 2.0), ("b", "2022", 4.0)])
    )
    metrics = result.metrics
    assert isinstance(metrics, DistributionMetrics)
    assert metrics.stdev == pytest.approx(1.4142135623730951)
    assert (metrics.q25, metrics.q50, metrics.q75) == (2.5, 3.0, 3.5)
    assert metrics.iqr == 1.0
    assert metrics.deciles is not None
    assert metrics.deciles["p10"] == pytest.approx(2.2)
    assert metrics.deciles["p90"] == pytest.approx(3.8)
    assert metrics.skewness is None
    assert result.caveats == (
        "Skewness requires at least 3 places, so it is not computed for "
        "this cohort of two.",
    )
    assert result.provenance.methodology == (
        "Distribution of Total population across 2 places on 2022: mean, "
        "median, minimum, maximum, the gap from minimum to maximum "
        "(max_minus_min), sample standard deviation, and quartiles and "
        "deciles by linear interpolation."
    )


def test_a_constant_cohort_has_no_skewness_or_z_scores() -> None:
    # Test: A cohort in which every place reports the same value.
    # Situation: Three places all at 5.0, with one focal place.
    # Expectation: The standard deviation and IQR are zero, skewness is
    #   None, the focal z-score is None while its percentile is 100.0, and
    #   a caveat states that the values are constant.
    result = summarize_distribution(
        _build_table(
            [("a", "2022", 5.0), ("b", "2022", 5.0), ("c", "2022", 5.0)]
        ),
        focal_places=["b"],
    )
    metrics = result.metrics
    assert isinstance(metrics, DistributionMetrics)
    assert metrics.stdev == 0.0
    assert metrics.iqr == 0.0
    assert metrics.skewness is None
    assert metrics.focal_entries == (
        DistributionFocalEntry(
            place_dcid="b",
            place_name="B",
            value=5.0,
            diff_from_median=0.0,
            pct_of_median=100.0,
            diff_from_mean=0.0,
            z_score=None,
            percentile=100.0,
        ),
    )
    assert result.caveats == (
        "Every place reports the same value for Total population on 2022, "
        "so skewness and z-scores are undefined.",
    )


def test_rounding_never_moves_figures_outside_the_cohort_range() -> None:
    # Test: Floating-point rounding on tied decimal values.
    # Situation: Three places at 0.1, whose floating-point mean is one ulp
    #   above 0.1; eight places at 0.3, 0.3, 0.9, 0.9, and four at 2.1,
    #   whose interpolated 70th percentile rounds one ulp above 2.1; and
    #   eight places with one value below and one above six ties at
    #   370.368, whose 20th percentile rounds above the 30th.
    # Expectation: The mean equals the shared value, every quartile and
    #   decile lies between the minimum and the maximum, and the deciles
    #   are in ascending order.
    constant = summarize_distribution(
        _build_table([(place, "2022", 0.1) for place in "abc"])
    ).metrics
    assert isinstance(constant, DistributionMetrics)
    assert constant.mean == 0.1
    for values in (
        [0.3, 0.3, 0.9, 0.9, 2.1, 2.1, 2.1, 2.1],
        [123.456, *([370.368] * 6), 864.192],
    ):
        metrics = summarize_distribution(
            _build_table(
                [
                    (f"p{index}", "2022", value)
                    for index, value in enumerate(values)
                ]
            )
        ).metrics
        assert isinstance(metrics, DistributionMetrics)
        assert metrics.deciles is not None
        deciles = list(metrics.deciles.values())
        assert deciles == sorted(deciles)
        assert metrics.q25 is not None and metrics.q75 is not None
        figures = [*deciles, metrics.q25, metrics.q75, metrics.mean]
        assert all(min(values) <= figure <= max(values) for figure in figures)
    tied = summarize_distribution(
        _build_table(
            [
                (f"p{index}", "2022", value)
                for index, value in enumerate([0.3, 0.3, 0.9, 0.9] + [2.1] * 4)
            ]
        )
    ).metrics
    assert isinstance(tied, DistributionMetrics)
    assert tied.deciles is not None
    assert tied.deciles["p70"] == 2.1


def test_pct_of_median_is_undefined_for_a_median_at_or_below_zero() -> None:
    # Test: The focal percentage of a zero or negative median.
    # Situation: Values -1, 0, and 1 (median 0) with the top place focal;
    #   and values -20, -12, -10, -8, and -5 (median -10) with the places
    #   above and below the median focal.
    # Expectation: `pct_of_median` is None in both cohorts, rather than a
    #   division by zero or a ratio that reads -5 as 50% and -20 as 200% of
    #   the median, and the signed offsets are still reported.
    zero = summarize_distribution(
        _build_table(
            [("a", "2022", -1.0), ("b", "2022", 0.0), ("c", "2022", 1.0)]
        ),
        focal_places=["c"],
    ).metrics
    assert isinstance(zero, DistributionMetrics)
    assert zero.focal_entries[0].pct_of_median is None
    assert zero.focal_entries[0].diff_from_median == 1.0
    negative = summarize_distribution(
        _build_table(
            [
                ("a", "2022", -10.0),
                ("b", "2022", -8.0),
                ("c", "2022", -5.0),
                ("d", "2022", -12.0),
                ("e", "2022", -20.0),
            ]
        ),
        focal_places=["c", "e"],
    ).metrics
    assert isinstance(negative, DistributionMetrics)
    assert negative.median == -10.0
    above, below = negative.focal_entries
    assert (above.pct_of_median, below.pct_of_median) == (None, None)
    assert (above.diff_from_median, below.diff_from_median) == (5.0, -10.0)


def test_pct_of_median_too_large_for_a_float_is_none() -> None:
    # Test: A focal percentage of the median that overflows a float.
    # Situation: Values 1e-300, 2e-300, and 1e10 (median 2e-300) with the
    #   top place focal, so the ratio to the median is 5e309.
    # Expectation: `pct_of_median` is None rather than infinity, and the
    #   other benchmarks are still reported.
    metrics = summarize_distribution(
        _build_table(
            [("a", "2022", 1e-300), ("b", "2022", 2e-300), ("c", "2022", 1e10)]
        ),
        focal_places=["c"],
    ).metrics
    assert isinstance(metrics, DistributionMetrics)
    entry = metrics.focal_entries[0]
    assert entry.pct_of_median is None
    assert entry.diff_from_median == pytest.approx(1e10)
    assert entry.percentile == 100.0


def test_population_weights_produce_a_weighted_mean_with_merged_sources() -> (
    None
):
    # Test: The population-weighted mean.
    # Situation: The five-place cohort citing `_SOURCE` and a weights table
    #   citing `_CENSUS` whose weights are 1 for four places and 6 for `e`,
    #   and which also carries a row on another date that must be ignored.
    # Expectation: The weighted mean is 7.0 over all five places, the
    #   result names both variables, carries both sources and facets, and
    #   the methodology names the weighting.
    weights = _build_weights(
        [
            ("a", "2022", 1.0),
            ("b", "2022", 1.0),
            ("c", "2022", 1.0),
            ("d", "2022", 1.0),
            ("e", "2022", 6.0),
            ("e", "2021", 1000.0),
        ]
    )
    result = summarize_distribution(_build_five_place_cohort(), weights=weights)
    assert result.status == "ok"
    metrics = result.metrics
    assert isinstance(metrics, DistributionMetrics)
    assert metrics.weighted_mean == 7.0
    assert metrics.weight_variable_dcid == "Count_Person_Weight"
    assert metrics.weighted_place_count == 5
    assert result.variables == ("Count_Person", "Count_Person_Weight")
    assert result.variable_names == {
        "Count_Person": "Total population",
        "Count_Person_Weight": "Weight population",
    }
    assert result.provenance.sources == (_SOURCE, _CENSUS)
    assert result.provenance.facet_ids == ("f1", "f2")
    assert result.provenance.methodology is not None
    assert "with the mean also weighted by Weight population" in (
        result.provenance.methodology
    )
    assert result.caveats == ()


def test_zero_weights_are_excluded_from_the_weighted_mean() -> None:
    # Test: Places with a zero weight, and a duplicate weights row.
    # Situation: The five-place cohort with two zero weights and three
    #   weights of 1; and weights of 1 with a second row of 6 for `e`.
    # Expectation: The mean is taken over the three positive weights and
    #   counts them; a duplicate weights row keeps the last value, as the
    #   cohort does, giving 7 over all five places.
    cohort = _build_five_place_cohort()
    partial = summarize_distribution(
        cohort,
        weights=_build_weights(
            [
                ("a", "2022", 0.0),
                ("b", "2022", 0.0),
                ("c", "2022", 1.0),
                ("d", "2022", 1.0),
                ("e", "2022", 1.0),
            ]
        ),
    )
    assert isinstance(partial.metrics, DistributionMetrics)
    assert partial.metrics.weighted_mean == pytest.approx(5.666666666666667)
    assert partial.metrics.weighted_place_count == 3
    duplicate = summarize_distribution(
        cohort,
        weights=_build_weights(
            [(place, "2022", 1.0) for place in "abcde"] + [("e", "2022", 6.0)]
        ),
    )
    assert isinstance(duplicate.metrics, DistributionMetrics)
    assert duplicate.metrics.weighted_mean == 7.0
    assert duplicate.metrics.weighted_place_count == 5


def test_too_few_positive_weights_omit_the_weighted_mean() -> None:
    # Test: The weight coverage threshold.
    # Situation: The five-place cohort with one positive weight; with only
    #   zero weights; and with only zero weights at `min_coverage=0.0`.
    # Expectation: Each omits the weighted mean with a caveat whose verb
    #   agrees with the count and that states the places needed (three at
    #   the default coverage, and still one at 0.0); the weights variable is
    #   named in the metrics but not added to the result's variables or
    #   sources.
    cohort = _build_five_place_cohort()
    sparse = summarize_distribution(
        cohort, weights=_build_weights([("a", "2022", 1.0)])
    )
    assert isinstance(sparse.metrics, DistributionMetrics)
    assert sparse.metrics.weighted_mean is None
    assert sparse.metrics.weight_variable_dcid == "Count_Person_Weight"
    assert sparse.metrics.weighted_place_count == 1
    assert sparse.variables == ("Count_Person",)
    assert sparse.provenance.sources == (_SOURCE,)
    assert sparse.caveats == (
        "Only 1 of 5 places in the cohort has a positive value for Weight "
        "population on 2022, fewer than the 3 needed, so the weighted mean "
        "is omitted.",
    )
    zeros = summarize_distribution(
        cohort, weights=_build_weights([("a", "2022", 0.0), ("b", "2022", 0.0)])
    )
    assert isinstance(zeros.metrics, DistributionMetrics)
    assert zeros.metrics.weighted_mean is None
    assert zeros.metrics.weighted_place_count == 0
    assert zeros.caveats == (
        "Only 0 of 5 places in the cohort have a positive value for Weight "
        "population on 2022, fewer than the 3 needed, so the weighted mean "
        "is omitted.",
    )
    no_floor = summarize_distribution(
        cohort,
        weights=_build_weights([("a", "2022", 0.0)]),
        min_coverage=0.0,
    )
    assert isinstance(no_floor.metrics, DistributionMetrics)
    assert no_floor.metrics.weighted_mean is None
    assert no_floor.caveats == (
        "Only 0 of 5 places in the cohort have a positive value for Weight "
        "population on 2022, fewer than the 1 needed, so the weighted mean "
        "is omitted.",
    )


def test_weights_without_a_row_on_the_reference_date_omit_the_mean() -> None:
    # Test: Weights with no value on the cohort's reference date.
    # Situation: The five-place cohort on 2022 with a weights table that
    #   has no rows, a row on 2021, or a row at another precision.
    # Expectation: Each omits the weighted mean with a caveat saying the
    #   weights have no value on 2022, and counts no weighted places.
    cohort = _build_five_place_cohort()
    for absent in ([], [("a", "2021", 1.0)], [("a", "2022-07-01", 1.0)]):
        result = summarize_distribution(cohort, weights=_build_weights(absent))
        assert isinstance(result.metrics, DistributionMetrics)
        assert result.metrics.weighted_mean is None
        assert result.metrics.weighted_place_count == 0
        assert result.caveats == (
            "Weight population has no value on 2022 for any place in the "
            "cohort, so the weighted mean is omitted.",
        )


def test_negative_weights_omit_the_weighted_mean() -> None:
    # Test: Weights that include a negative value.
    # Situation: The five-place cohort with one negative weight; and an
    #   eight-place cohort with seven negative weights.
    # Expectation: Each omits the weighted mean with a caveat naming the
    #   places, capped at five names with the rest counted, and counts no
    #   weighted places.
    negative = summarize_distribution(
        _build_five_place_cohort(),
        weights=_build_weights(
            [("a", "2022", -1.0), ("b", "2022", 1.0), ("c", "2022", 1.0)]
        ),
    )
    assert isinstance(negative.metrics, DistributionMetrics)
    assert negative.metrics.weighted_mean is None
    assert negative.caveats == (
        "A reported a negative value for Weight population on 2022, so the "
        "weighted mean is omitted.",
    )
    many_negative = summarize_distribution(
        _build_table(
            [(f"p{index}", "2022", float(index + 1)) for index in range(8)]
        ),
        weights=_build_weights(
            [(f"p{index}", "2022", -1.0) for index in range(7)]
            + [("p7", "2022", 1.0)]
        ),
    )
    assert isinstance(many_negative.metrics, DistributionMetrics)
    assert many_negative.metrics.weighted_mean is None
    assert many_negative.metrics.weighted_place_count == 0
    assert many_negative.caveats == (
        "P0, P1, P2, P3, P4, and 2 other places reported a negative value "
        "for Weight population on 2022, so the weighted mean is omitted.",
    )


def test_weight_coverage_count_agrees_with_the_decision_at_ulp_boundaries() -> (
    None
):
    # Test: The stated count of places needed at single-ulp thresholds.
    # Situation: A 100-place cohort at `min_coverage=0.07` (where
    #   `0.07 * 100` exceeds 7 by one ulp) with 6 and then 7 positive
    #   weights; and 29 positive weights at a `min_coverage` one ulp above
    #   0.29.
    # Expectation: 6 fall short of the 7 needed (not 8) and 7 meet the
    #   threshold; 29 fall short with a caveat that states 30 needed, so
    #   the stated count agrees with the decision.
    hundred = _build_table(
        [(f"p{index}", "2022", float(index + 1)) for index in range(100)]
    )

    def summarize_with_weights(
        positive_count: int, min_coverage: float
    ) -> ScriptResult:
        weights = _build_weights(
            [(f"p{index}", "2022", 1.0) for index in range(positive_count)]
        )
        return summarize_distribution(
            hundred, weights=weights, min_coverage=min_coverage
        )

    short = summarize_with_weights(6, 0.07)
    assert isinstance(short.metrics, DistributionMetrics)
    assert short.metrics.weighted_mean is None
    assert short.metrics.weighted_place_count == 6
    assert short.caveats == (
        "Only 6 of 100 places in the cohort have a positive value for Weight "
        "population on 2022, fewer than the 7 needed, so the weighted mean "
        "is omitted.",
    )
    boundary = summarize_with_weights(7, 0.07)
    assert isinstance(boundary.metrics, DistributionMetrics)
    assert boundary.metrics.weighted_mean == 4.0
    assert boundary.metrics.weighted_place_count == 7
    above = summarize_with_weights(29, math.nextafter(0.29, 1.0))
    assert isinstance(above.metrics, DistributionMetrics)
    assert above.metrics.weighted_mean is None
    assert above.caveats == (
        "Only 29 of 100 places in the cohort have a positive value for Weight "
        "population on 2022, fewer than the 30 needed, so the weighted mean "
        "is omitted.",
    )


def test_large_magnitudes_give_the_exact_mean_without_overflow() -> None:
    # Test: Means whose floating-point sums would overflow.
    # Situation: Values 1e200, 2e200, and 3e200 with weights of 1e200 each,
    #   whose value-weight products exceed the float range; and values 1e308,
    #   1e308, and 1.5e308, whose sum exceeds it.
    # Expectation: The weighted mean is 2e200 rather than infinity or the
    #   maximum, and the mean is the exact mean of the three values rather
    #   than an `OverflowError`.
    weighted = summarize_distribution(
        _build_table(
            [("a", "2022", 1e200), ("b", "2022", 2e200), ("c", "2022", 3e200)]
        ),
        weights=_build_weights([(place, "2022", 1e200) for place in "abc"]),
    ).metrics
    assert isinstance(weighted, DistributionMetrics)
    assert weighted.weighted_mean == pytest.approx(2e200)
    huge = summarize_distribution(
        _build_table(
            [("a", "2022", 1e308), ("b", "2022", 1e308), ("c", "2022", 1.5e308)]
        )
    ).metrics
    assert isinstance(huge, DistributionMetrics)
    assert huge.mean == float((Fraction(1e308) * 2 + Fraction(1.5e308)) / 3)


def test_weights_cohort_must_share_the_reference_date() -> None:
    # Test: Weights passed as an `AlignedCohort`.
    # Situation: A weights cohort aligned to 2021 against a cohort aligned
    #   to 2022, and then a weights cohort aligned to 2022.
    # Expectation: The first is refused with `invalid_parameters` carrying
    #   the cohort coverage and a caveat naming both dates; the second is
    #   weighted as a table would be.
    cohort = _build_five_place_cohort()
    rows = [(place, "2021", 1.0) for place in "abcde"]
    stale = align_cohort(_build_weights(rows))
    assert isinstance(stale, AlignedCohort)
    refused = summarize_distribution(cohort, weights=stale)
    assert refused.status == "refused"
    assert refused.refusal_reason == "invalid_parameters"
    assert refused.metrics is None
    assert refused.coverage is not None
    assert refused.coverage.contributing_places == 5
    assert refused.caveats == (
        "The weights cohort for Weight population is aligned to 2021, not "
        "to the cohort's reference date 2022.",
    )
    current = align_cohort(
        _build_weights([(place, "2022", 1.0) for place in "abcde"])
    )
    assert isinstance(current, AlignedCohort)
    weighted = summarize_distribution(cohort, weights=current)
    assert isinstance(weighted.metrics, DistributionMetrics)
    assert weighted.metrics.weighted_mean == 4.0


def test_bad_parameters_are_refused_as_invalid_parameters() -> None:
    # Test: Parameter validation for a table.
    # Situation: A `target_date` of `latest`, which is not a year, a year
    #   and month, or a full date; `min_coverage` values of -0.1 and 1.5;
    #   a bare string `a` as `focal_places`; and `focal_places` whose second
    #   entry holds a space, which no DCID contains.
    # Expectation: Each is a refusal with `invalid_parameters`,
    #   `metrics=None`, no coverage, and a caveat naming the bad value (the
    #   invalid DCID by its position only, so the string never reaches the
    #   caveat), rather than a coverage refusal or a raised `ValueError`.
    cohort = _build_five_place_cohort()
    cases = [
        (
            summarize_distribution(cohort, target_date="latest"),
            "The target date 'latest' is not a year, a year and month, or a "
            "full date.",
        ),
        (
            summarize_distribution(cohort, min_coverage=-0.1),
            "The minimum coverage must be between 0 and 1, not -0.1.",
        ),
        (
            summarize_distribution(cohort, min_coverage=1.5),
            "The minimum coverage must be between 0 and 1, not 1.5.",
        ),
        (
            summarize_distribution(cohort, focal_places="a"),
            "focal_places must be a sequence of DCIDs, not the string 'a'.",
        ),
        (
            summarize_distribution(cohort, focal_places=["a", "not a dcid"]),
            "focal_places must hold DCIDs, but entry 2 of 2 is not a valid "
            "DCID.",
        ),
    ]
    for result, message in cases:
        assert result.status == "refused"
        assert result.refusal_reason == "invalid_parameters"
        assert result.metrics is None
        assert result.coverage is None
        assert result.caveats == (message,)


def test_many_missing_focal_places_are_capped_in_the_caveat() -> None:
    # Test: The caveat for more missing focal places than the name cap.
    # Situation: The five-place cohort with seven focal places, none of
    #   which is in the cohort.
    # Expectation: Every place is listed in `missing_focal_places`, and the
    #   caveat names the first five and counts the other two.
    missing = [f"m{index}" for index in range(1, 8)]
    result = summarize_distribution(
        _build_five_place_cohort(), focal_places=missing
    )
    assert isinstance(result.metrics, DistributionMetrics)
    assert result.metrics.focal_entries == ()
    assert result.metrics.missing_focal_places == tuple(missing)
    assert result.caveats == (
        "m1, m2, m3, m4, m5, and 2 other places have no value for Total "
        "population in the cohort on 2022, so no benchmark is available.",
    )


def test_alignment_refusals_propagate_with_their_coverage() -> None:
    # Test: A table that cannot be aligned.
    # Situation: Ten requested places of which three report, below the
    #   default coverage; and an empty table.
    # Expectation: Each result is refused with the alignment's reason, the
    #   coverage figure is carried, and the refusal message is the caveat.
    places = [f"p{index}" for index in range(10)]
    sparse = summarize_distribution(
        _build_table(
            [("p0", "2022", 1.0), ("p1", "2022", 2.0), ("p2", "2022", 3.0)],
            requested_places=places,
        )
    )
    assert sparse.status == "refused"
    assert sparse.refusal_reason == "insufficient_coverage"
    assert sparse.metrics is None
    assert sparse.coverage is not None
    assert sparse.coverage.contributing_places == 3
    assert sparse.caveats == (
        "Only 3 of 10 places on 2022 have a value for Total population "
        "(Count_Person), below the required 50% coverage.",
    )
    empty = summarize_distribution(_build_table([], requested_places=places))
    assert empty.refusal_reason == "no_observations"
    assert empty.metrics is None
    assert empty.coverage is not None
    assert empty.coverage.contributing_places == 0


def _build_aligned_cohort_with_caveats() -> AlignedCohort:
    """Aligns three requested places, one of them stale, to 2022."""
    aligned = align_cohort(
        _build_table(
            [("a", "2022", 1.0), ("b", "2022", 2.0), ("c", "2021", 3.0)],
            requested_places=["a", "b", "c"],
        )
    )
    assert isinstance(aligned, AlignedCohort)
    assert aligned.caveats
    return aligned


def test_an_aligned_cohort_is_summarized_without_realignment() -> None:
    # Test: Passing an `AlignedCohort` directly.
    # Situation: A cohort aligned to 2022 with one requested place missing,
    #   summarized with no `target_date`, with the matching `target_date`,
    #   and with `min_coverage=1.5` and no weights.
    # Expectation: The summary uses the cohort's reference date and carries
    #   its coverage and caveats; the matching date and the unused
    #   `min_coverage` give the same result.
    aligned = _build_aligned_cohort_with_caveats()
    result = summarize_distribution(aligned)
    assert isinstance(result.metrics, DistributionMetrics)
    assert result.metrics.reference_date == "2022"
    assert result.metrics.cohort_size == 2
    assert result.coverage == aligned.coverage
    assert result.caveats[: len(aligned.caveats)] == aligned.caveats
    assert summarize_distribution(aligned, target_date="2022") == result
    assert summarize_distribution(aligned, min_coverage=1.5) == result


def test_an_aligned_cohort_with_bad_parameters_is_refused() -> None:
    # Test: Parameter validation for an `AlignedCohort`.
    # Situation: The aligned cohort with `min_coverage=1.5` and weights,
    #   where it is the weight coverage threshold; a different and a
    #   malformed `target_date`; a bare string as `focal_places`; and an
    #   invalid DCID among them.
    # Expectation: Each is refused with `invalid_parameters`, carrying the
    #   cohort's coverage and its caveats, followed by the reason.
    aligned = _build_aligned_cohort_with_caveats()
    weights = _build_weights([("a", "2022", 1.0), ("b", "2022", 1.0)])
    refusals = [
        (
            summarize_distribution(aligned, weights=weights, min_coverage=1.5),
            "The minimum coverage must be between 0 and 1, not 1.5.",
        ),
        (
            summarize_distribution(aligned, target_date="2021"),
            "The cohort is aligned to 2022, so it cannot be summarized on the "
            "target date 2021.",
        ),
        (
            summarize_distribution(aligned, target_date="latest"),
            "The target date 'latest' is not a year, a year and month, or a "
            "full date.",
        ),
        (
            summarize_distribution(aligned, focal_places="a"),
            "focal_places must be a sequence of DCIDs, not the string 'a'.",
        ),
        (
            summarize_distribution(aligned, focal_places=["a", "b c"]),
            "focal_places must hold DCIDs, but entry 2 of 2 is not a valid "
            "DCID.",
        ),
    ]
    for refused, message in refusals:
        assert refused.status == "refused"
        assert refused.refusal_reason == "invalid_parameters"
        assert refused.metrics is None
        assert refused.coverage == aligned.coverage
        assert refused.caveats == (*aligned.caveats, message)


_DECILE_NAMES = tuple(f"p{index * 10}" for index in range(1, 10))
_VALUE_SHAPES = (
    "increasing",
    "ties",
    "constant",
    "signed",
    "mixed",
    "decimal_ties",
)
_WEIGHT_SHAPES = (
    "none",
    "positive",
    "some_zero",
    "one_positive",
    "partial_rows",
    "negative",
)


def _generate_values(
    generator: random.Random, shape: str, cohort_size: int
) -> list[float]:
    """Returns values of one shape for `cohort_size` places, shuffled.

    The `decimal_ties` shape draws tied decimal values that binary floating
    point cannot represent exactly, where interpolation between two equal
    order statistics can round away from them.
    """
    if shape == "increasing":
        values = [float(index + 1) for index in range(cohort_size)]
    elif shape == "ties":
        values = [float(index // 2) for index in range(cohort_size)]
    elif shape == "constant":
        values = [5.0] * cohort_size
    elif shape == "signed":
        values = [
            1.5 * (index - cohort_size // 2) for index in range(cohort_size)
        ]
    elif shape == "mixed":
        values = [
            generator.choice((-3.0, -0.5, 0.0, 0.25, 2.0, 7.5))
            for _ in range(cohort_size)
        ]
    elif shape == "decimal_ties":
        values = [
            generator.choice((0.1, 0.3, 0.9, 2.1, 370.368))
            for _ in range(cohort_size)
        ]
    else:
        raise ValueError(f"Unknown value shape {shape!r}.")
    generator.shuffle(values)
    return values


def _generate_weights(
    generator: random.Random, shape: str, places: Sequence[str]
) -> dict[str, float] | None:
    """Returns whole-number weights of one shape keyed by place, or None."""
    if shape == "none":
        return None
    weights = {place: float(generator.randint(1, 5)) for place in places}
    if shape == "some_zero":
        for place in places[: len(places) // 3]:
            weights[place] = 0.0
    elif shape == "one_positive":
        weights = dict.fromkeys(places, 0.0)
        weights[places[0]] = 3.0
    elif shape == "partial_rows":
        weights = {place: weights[place] for place in places[::2]}
    elif shape == "negative":
        weights[places[0]] = -1.0
    return weights


def _interpolate_quantile(values: Sequence[float], fraction: Fraction) -> float:
    """Returns the inclusive quantile at `fraction` of sorted `values`."""
    position = fraction * (len(values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    weight = float(position - lower)
    return values[lower] + (values[upper] - values[lower]) * weight


def _compute_direct_center(values: Sequence[float]) -> tuple[float, float]:
    """Returns the mean and median of sorted `values` by textbook formulas."""
    size = len(values)
    middle = size // 2
    median = (
        values[middle]
        if size % 2
        else (values[middle - 1] + values[middle]) / 2
    )
    return sum(values) / size, median


def _compute_direct_stdev(values: Sequence[float], mean: float) -> float:
    """Returns the sample standard deviation of `values` about `mean`."""
    squared = sum((value - mean) ** 2 for value in values)
    return math.sqrt(squared / (len(values) - 1))


@dataclass(frozen=True)
class _DistributionCase:
    """One generated summary: its inputs, its aligned cohort, and its result.

    `aligned` is the table's alignment, which is an `AlignmentRefusal` when
    the table cannot be aligned at `min_coverage`.
    """

    table: ObservationTable
    aligned: AlignedCohort | AlignmentRefusal
    focal_places: tuple[str, ...]
    weight_values: dict[str, float] | None
    weights: ObservationTable | None
    min_coverage: float
    result: ScriptResult


@functools.cache
def _generate_distribution_cases() -> tuple[_DistributionCase, ...]:
    """Builds every generated distribution case once for the invariant tests.

    Covers every cohort size from 1 to 9 with each value shape, shuffled
    across DCIDs by a seeded generator, plus a stale place that alignment
    leaves out; each weight shape; `min_coverage` of 0.5 and 0.8; and focal
    places that are present, missing, stale, and repeated.
    """
    generator = random.Random(17)
    cases: list[_DistributionCase] = []
    for cohort_size in range(1, 10):
        places = [f"p{index:02d}" for index in range(cohort_size)]
        focal_options: tuple[tuple[str, ...], ...] = (
            (),
            (places[-1], places[0]),
            ("nowhere", places[0]),
            (places[0], "stale", places[0], "nowhere", "stale"),
        )
        for shape in _VALUE_SHAPES:
            values = _generate_values(generator, shape, cohort_size)
            table = _build_table(
                [
                    (place, "2022", value)
                    for place, value in zip(places, values, strict=True)
                ]
                + [("stale", "2020", 0.5)]
            )
            for weight_shape in _WEIGHT_SHAPES:
                weight_values = _generate_weights(
                    generator, weight_shape, places
                )
                weights = (
                    None
                    if weight_values is None
                    else _build_weights(
                        [
                            (place, "2022", weight)
                            for place, weight in weight_values.items()
                        ]
                    )
                )
                for min_coverage in (0.5, 0.8):
                    aligned = align_cohort(table, min_coverage=min_coverage)
                    for focal_places in focal_options:
                        cases.append(
                            _DistributionCase(
                                table=table,
                                aligned=aligned,
                                focal_places=focal_places,
                                weight_values=weight_values,
                                weights=weights,
                                min_coverage=min_coverage,
                                result=summarize_distribution(
                                    table,
                                    weights=weights,
                                    focal_places=focal_places,
                                    min_coverage=min_coverage,
                                ),
                            )
                        )
    return tuple(cases)


def _list_summarized_cases() -> list[
    tuple[_DistributionCase, DistributionMetrics, AlignedCohort]
]:
    """Returns every generated case that summarized, with its typed parts."""
    summarized = []
    for case in _generate_distribution_cases():
        if isinstance(case.aligned, AlignedCohort):
            assert isinstance(case.result.metrics, DistributionMetrics)
            summarized.append((case, case.result.metrics, case.aligned))
    assert len(summarized) == 2160
    return summarized


def test_generated_summaries_match_for_a_table_and_its_aligned_cohort() -> None:
    # Test: Equivalence of the two inputs.
    # Situation: Every generated case (see `_generate_distribution_cases`),
    #   summarized again from its aligned cohort.
    # Expectation: Both results are equal; a table that cannot be aligned
    #   is refused with the alignment's reason.
    for case in _generate_distribution_cases():
        if isinstance(case.aligned, AlignmentRefusal):
            assert case.result.refusal_reason == case.aligned.reason
            continue
        assert case.result == summarize_distribution(
            case.aligned,
            weights=case.weights,
            focal_places=case.focal_places,
            min_coverage=case.min_coverage,
        )


def test_generated_summaries_bound_and_order_their_figures() -> None:
    # Test: The range, order, and presence of the summary figures.
    # Situation: Every generated case that summarizes.
    # Expectation: The extrema bound the mean, median, quartiles, and
    #   deciles, which are ordered; the dispersion figures are present
    #   exactly from two places and skewness exactly from three places with
    #   a nonzero spread.
    for _, metrics, aligned in _list_summarized_cases():
        lowest, highest = metrics.min.value, metrics.max.value
        assert metrics.cohort_size == len(aligned.rows)
        assert lowest <= metrics.mean <= highest
        assert lowest <= metrics.median <= highest
        assert metrics.max_minus_min == pytest.approx(highest - lowest)
        assert (metrics.skewness is None) == (
            metrics.cohort_size < 3 or metrics.stdev == 0.0
        )
        if metrics.cohort_size < 2:
            assert metrics.stdev is None
            assert (metrics.q25, metrics.q50, metrics.q75) == (None, None, None)
            assert metrics.iqr is None
            assert metrics.deciles is None
            continue
        q25, q50, q75 = metrics.q25, metrics.q50, metrics.q75
        assert metrics.stdev is not None
        assert q25 is not None and q50 is not None and q75 is not None
        assert metrics.iqr is not None and metrics.deciles is not None
        assert lowest <= q25 <= metrics.median <= q75 <= highest
        assert q50 == pytest.approx(metrics.median)
        assert metrics.iqr == pytest.approx(q75 - q25)
        assert tuple(metrics.deciles) == _DECILE_NAMES
        deciles = list(metrics.deciles.values())
        assert deciles == sorted(deciles)
        assert all(lowest <= decile <= highest for decile in deciles)


def test_generated_summaries_match_the_direct_center_and_extrema() -> None:
    # Test: The mean, median, and extrema against a direct computation.
    # Situation: Every generated case that summarizes.
    # Expectation: The mean and median equal the textbook formulas over the
    #   sorted values, and the extrema name the smallest and largest values,
    #   ties by DCID.
    for _, metrics, aligned in _list_summarized_cases():
        values = sorted(row.value for row in aligned.rows)
        mean, median = _compute_direct_center(values)
        assert metrics.mean == pytest.approx(mean)
        assert metrics.median == pytest.approx(median)
        lowest = min(aligned.rows, key=lambda row: (row.value, row.place_dcid))
        highest = min(
            aligned.rows, key=lambda row: (-row.value, row.place_dcid)
        )
        assert metrics.min.place_dcid == lowest.place_dcid
        assert metrics.max.place_dcid == highest.place_dcid


def test_generated_summaries_match_the_direct_dispersion() -> None:
    # Test: The standard deviation and quantiles against a direct
    #   computation.
    # Situation: Every generated case with at least two places.
    # Expectation: The sample standard deviation and the inclusive
    #   quartiles and deciles equal the textbook formulas.
    for _, metrics, aligned in _list_summarized_cases():
        values = sorted(row.value for row in aligned.rows)
        if len(values) < 2:
            continue
        mean, _ = _compute_direct_center(values)
        assert metrics.stdev == pytest.approx(
            _compute_direct_stdev(values, mean)
        )
        assert (metrics.q25, metrics.q50, metrics.q75) == pytest.approx(
            tuple(
                _interpolate_quantile(values, Fraction(part, 4))
                for part in (1, 2, 3)
            )
        )
        assert metrics.deciles == pytest.approx(
            {
                name: _interpolate_quantile(values, Fraction(part, 10))
                for part, name in enumerate(_DECILE_NAMES, start=1)
            }
        )


def test_generated_summaries_match_the_direct_skewness() -> None:
    # Test: The skewness against a direct computation.
    # Situation: Every generated case that reports a skewness.
    # Expectation: It equals the adjusted Fisher-Pearson sample skewness.
    for _, metrics, aligned in _list_summarized_cases():
        if metrics.skewness is None:
            continue
        values = sorted(row.value for row in aligned.rows)
        size = len(values)
        mean, _ = _compute_direct_center(values)
        stdev = _compute_direct_stdev(values, mean)
        cubed = sum(((value - mean) / stdev) ** 3 for value in values)
        assert metrics.skewness == pytest.approx(
            size / ((size - 1) * (size - 2)) * cubed
        )


def test_generated_summaries_match_the_direct_focal_benchmarks() -> None:
    # Test: Each focal entry against a direct computation.
    # Situation: Every generated case that summarizes with focal entries.
    # Expectation: The percentile is the share of places at or below the
    #   value, the offsets are from the median and the mean, and the
    #   z-score and percentage of the median, when defined, equal their
    #   formulas.
    for _, metrics, aligned in _list_summarized_cases():
        values = sorted(row.value for row in aligned.rows)
        mean, median = _compute_direct_center(values)
        by_place = {row.place_dcid: row.value for row in aligned.rows}
        for entry in metrics.focal_entries:
            value = by_place[entry.place_dcid]
            at_or_below = sum(1 for other in values if other <= value)
            assert entry.percentile == pytest.approx(
                at_or_below / len(values) * 100.0
            )
            assert entry.diff_from_median == pytest.approx(value - median)
            assert entry.diff_from_mean == pytest.approx(value - mean)
            if entry.z_score is not None:
                stdev = _compute_direct_stdev(values, mean)
                assert entry.z_score == pytest.approx((value - mean) / stdev)
            if entry.pct_of_median is not None:
                assert entry.pct_of_median == pytest.approx(
                    value / median * 100.0
                )


def test_generated_summaries_match_the_direct_weighted_mean() -> None:
    # Test: The weighted mean against a direct computation.
    # Situation: Every generated case that reports a weighted mean.
    # Expectation: It equals the sum of value times weight over the sum of
    #   the weights, taken over the places with a positive weight.
    for case, metrics, aligned in _list_summarized_cases():
        if case.weight_values is None or metrics.weighted_mean is None:
            continue
        by_place = {row.place_dcid: row.value for row in aligned.rows}
        pairs = [
            (by_place[place], weight)
            for place, weight in case.weight_values.items()
            if place in by_place and weight > 0.0
        ]
        weighted = sum(value * weight for value, weight in pairs) / sum(
            weight for _, weight in pairs
        )
        assert metrics.weighted_mean == pytest.approx(weighted)


def test_generated_summaries_benchmark_each_focal_place_once() -> None:
    # Test: The focal entries and missing focal places.
    # Situation: Every generated case that summarizes.
    # Expectation: Every distinct focal place is either benchmarked, in
    #   request order, or missing; focal percentiles lie in `(0, 100]`; and
    #   z-scores and percentages of the median are None exactly when
    #   undefined.
    for case, metrics, aligned in _list_summarized_cases():
        cohort_places = {row.place_dcid for row in aligned.rows}
        requested = list(dict.fromkeys(case.focal_places))
        assert [entry.place_dcid for entry in metrics.focal_entries] == [
            place for place in requested if place in cohort_places
        ]
        assert metrics.missing_focal_places == tuple(
            place for place in requested if place not in cohort_places
        )
        for entry in metrics.focal_entries:
            assert 0.0 < entry.percentile <= 100.0
            assert (entry.z_score is None) == (
                metrics.stdev is None or metrics.stdev == 0.0
            )
            assert (entry.pct_of_median is None) == (metrics.median <= 0.0)


def test_generated_summaries_report_the_weighted_mean_when_due() -> None:
    # Test: The weighted mean and its place count.
    # Situation: Every generated case that summarizes.
    # Expectation: Without weights, the weighted figures are None; with
    #   them, the weighted mean is reported exactly when no paired weight is
    #   negative and enough places have a positive weight, lies within the
    #   extrema, and counts those places.
    for case, metrics, aligned in _list_summarized_cases():
        if case.weight_values is None:
            assert metrics.weighted_mean is None
            assert metrics.weighted_place_count is None
            assert metrics.weight_variable_dcid is None
            continue
        assert metrics.weight_variable_dcid == "Count_Person_Weight"
        paired = [
            case.weight_values[row.place_dcid]
            for row in aligned.rows
            if row.place_dcid in case.weight_values
        ]
        positive = sum(1 for weight in paired if weight > 0.0)
        has_negative_weight = any(weight < 0.0 for weight in paired)
        is_weighted_mean_reported = (
            not has_negative_weight
            and positive > 0
            and positive / metrics.cohort_size >= case.min_coverage
        )
        assert (metrics.weighted_mean is not None) == is_weighted_mean_reported
        assert metrics.weighted_place_count == (
            0 if has_negative_weight else positive
        )
        if metrics.weighted_mean is not None:
            assert (
                metrics.min.value <= metrics.weighted_mean <= metrics.max.value
            )
