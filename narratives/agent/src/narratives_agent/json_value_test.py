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
"""Tests for `json_safe` in `json_value`."""

import math
from dataclasses import dataclass

import pytest

from narratives_agent.json_value import json_safe


@dataclass(frozen=True)
class _Coverage:
    """Nested dataclass fixture for `json_safe`."""

    ratio: float
    missing: tuple[str, ...] = ()


def test_json_safe_converts_sets_and_nested_dataclasses() -> None:
    # Test: `json_safe` conversion of sets, dataclasses, and unsupported types.
    # Situation: `json_safe` is called on a dictionary containing a `frozenset`
    #   and a dataclass holding `math.inf` and a tuple, and then called on a
    #   plain `object()` instance.
    # Expectation: The `frozenset` converts to a sorted list, the dataclass
    #   converts to a dictionary with `None` in place of `math.inf` and a list
    #   in place of the tuple, and the unsupported `object()` raises
    #   `TypeError`.
    converted = json_safe(
        {
            "places": frozenset({"b", "a"}),
            "coverage": _Coverage(ratio=math.inf, missing=("country/X",)),
        }
    )
    assert converted == {
        "places": ["a", "b"],
        "coverage": {"ratio": None, "missing": ["country/X"]},
    }
    with pytest.raises(TypeError, match=r"Cannot serialize"):
        json_safe(object())
