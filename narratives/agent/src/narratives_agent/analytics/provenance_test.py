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

from narratives_agent.analytics.provenance import (
    AlternativeSource,
    Provenance,
    Source,
    merge_provenance,
)


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


def test_alternative_source_defaults_optional_fields_to_none() -> None:
    # Test: `AlternativeSource` defaults and immutability.
    # Situation: An `AlternativeSource` is constructed with only `facet_id`.
    # Expectation: Optional metadata fields default to `None`.
    alt = AlternativeSource(facet_id="12850099660527362240")
    assert alt.facet_id == "12850099660527362240"
    assert alt.provenance_url is None
    assert alt.measurement_method is None
    assert alt.observation_period is None
    assert alt.unit is None
    assert alt.places_found_count is None


def test_merge_provenance_deduplicates_sources_and_joins_methodology() -> None:
    # Test: `merge_provenance` across multiple inputs with methodology clauses.
    # Situation: Two `Provenance` inputs share a source and a facet ID, and
    #   are merged with a combining methodology; methodologies end in periods.
    # Expectation: Sources and facet IDs deduplicate in first-seen order, and
    #   methodologies join with `"; "` after stripping intermediate trailing
    #   periods.
    wdi = Source(name="World Bank", url="https://wdi.example")
    census = Source(name="Census", url="https://census.example")
    first = Provenance(
        sources=(wdi,),
        facet_ids=("f1",),
        methodology="Aligned to 2020.",
    )
    second = Provenance(
        sources=(wdi, census),
        facet_ids=("f1", "f2"),
    )
    merged = merge_provenance(first, second, methodology="Ratio of A to B.")
    assert merged == Provenance(
        sources=(wdi, census),
        facet_ids=("f1", "f2"),
        methodology="Aligned to 2020; Ratio of A to B.",
    )
    assert merge_provenance() == Provenance()


def test_merge_provenance_treats_a_final_period_as_insignificant() -> None:
    # Test: Handling of trailing periods when deduplicating and joining
    #   methodology clauses.
    # Situation: First, two `Provenance` records with `"Aligned to 2020."` and
    #   `"Aligned to 2020"` are merged. Second, a record ending in the
    #   abbreviation `"U.S."` is merged with a combining `methodology`.
    # Expectation: The first merge deduplicates the two strings and retains
    #   the first-seen form (`"Aligned to 2020."`). The second merge strips
    #   only the single trailing period from `"U.S."` before joining with
    #   `"; "`.
    assert merge_provenance(
        Provenance(methodology="Aligned to 2020."),
        Provenance(methodology="Aligned to 2020"),
    ) == Provenance(methodology="Aligned to 2020.")
    assert merge_provenance(
        Provenance(methodology="Population of the U.S."),
        methodology="Ratio.",
    ) == Provenance(methodology="Population of the U.S; Ratio.")


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
    wdi = Source(name="World Bank", url="https://wdi.example")
    census = Source(name="Census", url="https://census.example")
    derived = Provenance(
        sources=(wdi, census),
        methodology="Count_Case divided by Count_Person.",
    )
    weights = Provenance(sources=(census,))

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
