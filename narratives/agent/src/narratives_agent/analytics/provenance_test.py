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
"""Tests for provenance domain types in `analytics.provenance`."""

import dataclasses

import pytest

from narratives_agent.analytics.provenance import Source


def test_source_defaults_optional_citation_fields_to_none() -> None:
    # Test: Default field values on a minimal `Source`.
    # Situation: A `Source` is constructed with only `name` and `url`.
    # Expectation: All optional metadata fields default to `None`.
    source = Source(name="World Bank", url="https://worldbank.example")
    assert source.name == "World Bank"
    assert source.url == "https://worldbank.example"
    assert source.license is None
    assert source.provider is None
    assert source.dataset is None
    assert source.date_range is None


def test_source_is_frozen_and_hashable_by_value() -> None:
    # Test: Immutability and value-based hashing of `Source`.
    # Situation: Two `Source` instances carry identical fields, and a caller
    #   attempts to mutate one and deduplicate both with `dict.fromkeys`.
    # Expectation: Mutation raises `FrozenInstanceError`, and `dict.fromkeys`
    #   retains a single entry.
    first = Source(
        name="World Development Indicators",
        url="https://wdi.example",
        license="CC-BY-4.0",
        provider="World Bank",
        dataset="World Development Indicators",
        date_range="1960 \u2013 2023",
    )
    second = Source(
        name="World Development Indicators",
        url="https://wdi.example",
        license="CC-BY-4.0",
        provider="World Bank",
        dataset="World Development Indicators",
        date_range="1960 \u2013 2023",
    )
    assert first == second
    assert list(dict.fromkeys([first, second])) == [first]
    field_name = "name"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(first, field_name, "Changed")
