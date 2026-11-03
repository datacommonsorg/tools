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
"""Tests for the window metrics and entries in `analytics.metrics`.

Covers the prose labels of every `SeriesMetric`, the finiteness checks of
the window entry subclasses, their substitutability for their base entries,
and the order in which `json_safe` serializes their fields.
"""

import math
from typing import get_args

import pytest

from narratives_agent.analytics.metrics import (
    SERIES_METRIC_LABELS,
    DistributionFocalEntry,
    PlaceValue,
    RankEntry,
    SeriesMetric,
    WindowDistributionFocalEntry,
    WindowPlaceValue,
    WindowRankEntry,
)
from narratives_agent.json_value import json_safe

_WINDOW_KEYS = ["from_date", "to_date", "from_value", "to_value"]


def _build_place_value(
    *, value: float = 4.0, from_value: float = 1.0, to_value: float = 5.0
) -> WindowPlaceValue:
    """Builds a window place value of a change from 2020 to 2024."""
    return WindowPlaceValue(
        place_dcid="geoId/06",
        place_name="California",
        value=value,
        from_date="2020",
        to_date="2024",
        from_value=from_value,
        to_value=to_value,
    )


def _build_rank_entry(
    *, value: float = 4.0, from_value: float = 1.0, to_value: float = 5.0
) -> WindowRankEntry:
    """Builds a window rank entry of a change from 2020 to 2024."""
    return WindowRankEntry(
        rank=1,
        is_tied=False,
        place_dcid="geoId/06",
        place_name="California",
        value=value,
        percentile=100.0,
        from_date="2020",
        to_date="2024",
        from_value=from_value,
        to_value=to_value,
    )


def _build_focal_entry(
    *,
    value: float = 4.0,
    from_value: float = 1.0,
    to_value: float = 5.0,
    z_score: float | None = 0.5,
) -> WindowDistributionFocalEntry:
    """Builds a window focal entry of a change from 2020 to 2024."""
    return WindowDistributionFocalEntry(
        place_dcid="geoId/06",
        place_name="California",
        value=value,
        diff_from_median=1.0,
        pct_of_median=133.0,
        diff_from_mean=0.5,
        z_score=z_score,
        percentile=75.0,
        from_date="2020",
        to_date="2024",
        from_value=from_value,
        to_value=to_value,
    )


def test_every_series_metric_has_a_label() -> None:
    # Test: The prose labels of the window metrics.
    # Situation: The keys of `SERIES_METRIC_LABELS` and the values of
    #   `SeriesMetric`.
    # Expectation: Every metric has exactly one non-empty label.
    assert set(SERIES_METRIC_LABELS) == set(get_args(SeriesMetric.__value__))
    assert all(SERIES_METRIC_LABELS.values())


@pytest.mark.parametrize("field_name", ["value", "from_value", "to_value"])
@pytest.mark.parametrize("number", [math.nan, math.inf, -math.inf])
def test_a_window_place_value_rejects_non_finite_numbers(
    field_name: str, number: float
) -> None:
    # Test: The finiteness check of `WindowPlaceValue`.
    # Situation: The figure or one endpoint value is `NaN` or infinite.
    # Expectation: Construction raises `ValueError` naming the field.
    with pytest.raises(ValueError, match=f"WindowPlaceValue.{field_name}"):
        _build_place_value(**{field_name: number})


@pytest.mark.parametrize("field_name", ["value", "from_value", "to_value"])
def test_a_window_rank_entry_rejects_non_finite_numbers(
    field_name: str,
) -> None:
    # Test: The finiteness check of `WindowRankEntry`.
    # Situation: The figure or one endpoint value is infinite.
    # Expectation: Construction raises `ValueError` naming the field.
    with pytest.raises(ValueError, match=f"WindowRankEntry.{field_name}"):
        _build_rank_entry(**{field_name: math.inf})


@pytest.mark.parametrize(
    "field_name", ["value", "from_value", "to_value", "z_score"]
)
def test_a_window_focal_entry_rejects_non_finite_numbers(
    field_name: str,
) -> None:
    # Test: The finiteness check of `WindowDistributionFocalEntry`.
    # Situation: The figure, one endpoint value, or the z-score is `NaN`.
    # Expectation: Construction raises `ValueError` naming the field.
    with pytest.raises(
        ValueError, match=f"WindowDistributionFocalEntry.{field_name}"
    ):
        _build_focal_entry(**{field_name: math.nan})


def test_a_window_focal_entry_accepts_an_undefined_z_score() -> None:
    # Test: The z-score of a focal entry in a constant cohort.
    # Situation: A window focal entry whose z-score is None.
    # Expectation: Construction succeeds and keeps None.
    assert _build_focal_entry(z_score=None).z_score is None


def test_window_entries_substitute_for_their_base_entries() -> None:
    # Test: The Liskov substitutability of the window entries.
    # Situation: One window place value, rank entry, and focal entry.
    # Expectation: Each is an instance of its base entry type.
    assert isinstance(_build_place_value(), PlaceValue)
    assert isinstance(_build_rank_entry(), RankEntry)
    assert isinstance(_build_focal_entry(), DistributionFocalEntry)


@pytest.mark.parametrize(
    ("entry", "base_keys"),
    [
        (_build_place_value(), ["place_dcid", "place_name", "value"]),
        (
            _build_rank_entry(),
            [
                "rank",
                "is_tied",
                "place_dcid",
                "place_name",
                "value",
                "percentile",
            ],
        ),
        (
            _build_focal_entry(),
            [
                "place_dcid",
                "place_name",
                "value",
                "diff_from_median",
                "pct_of_median",
                "diff_from_mean",
                "z_score",
                "percentile",
            ],
        ),
    ],
    ids=["place value", "rank entry", "focal entry"],
)
def test_window_entries_serialize_base_fields_then_window_fields(
    entry: object, base_keys: list[str]
) -> None:
    # Test: The serialized form of the window entries.
    # Situation: `json_safe` of each window entry, as the digest renders it.
    # Expectation: The keys are the base entry's fields in declaration
    #   order followed by `from_date`, `to_date`, `from_value`, and
    #   `to_value`, which carry the window's dates and values.
    serialized = json_safe(entry)
    assert isinstance(serialized, dict)
    assert list(serialized) == [*base_keys, *_WINDOW_KEYS]
    assert [serialized[key] for key in _WINDOW_KEYS] == [
        "2020",
        "2024",
        1.0,
        5.0,
    ]
