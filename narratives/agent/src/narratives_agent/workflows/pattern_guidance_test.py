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
"""Tests for the pattern directives in `workflows.pattern_guidance`."""

from typing import get_args

import pytest

from narratives_agent.gemini.schemas import (
    GeographicShape,
    QueryClassification,
    QueryPattern,
)
from narratives_agent.workflows import pattern_guidance

# Lowercase substrings that describe internal system capabilities rather than
# analytical output and must not appear in directives appended to synthesis.
_CAPABILITY_NOTE_PHRASES = (
    "release",
    "is available",
    "are available",
    "not available",
    "the server",
    "cannot compute",
)


def _classified(
    pattern: str, shape: str = "single_place"
) -> QueryClassification:
    """Returns a serviceable classification with `pattern` and `shape`."""
    return QueryClassification.model_validate(
        {
            "serviceable": True,
            "pattern": pattern,
            "geographic_shape": shape,
            "requires_computation": False,
        }
    )


@pytest.mark.parametrize("pattern", get_args(QueryPattern))
def test_every_pattern_has_its_own_directive(pattern: str) -> None:
    # Test: Directive lookup for every `QueryPattern` value.
    # Situation: A single-place classification is constructed for each pattern
    #   in `QueryPattern`.
    # Expectation: `pattern_directive` returns a non-empty string unique to that
    #   pattern without `_COMPARISON_DIRECTIVE`.
    directive = pattern_guidance.pattern_directive(_classified(pattern))

    others = {
        pattern_guidance.pattern_directive(_classified(other))
        for other in get_args(QueryPattern)
        if other != pattern
    }
    assert directive
    assert directive not in others
    assert pattern_guidance._COMPARISON_DIRECTIVE not in directive


@pytest.mark.parametrize("shape", get_args(GeographicShape))
def test_only_the_comparison_shape_adds_the_comparison_sentence(
    shape: str,
) -> None:
    # Test: Geographic shape handling in `pattern_directive`.
    # Situation: A `trend_delta` classification is constructed for each
    #   `GeographicShape` value.
    # Expectation: The returned directive starts with the pattern directive and
    #   ends with `_COMPARISON_DIRECTIVE` only when `shape == "comparison"`.
    directive = pattern_guidance.pattern_directive(
        _classified("trend_delta", shape)
    )

    assert directive.startswith(pattern_guidance._DIRECTIVES["trend_delta"])
    assert directive.endswith(pattern_guidance._COMPARISON_DIRECTIVE) is (
        shape == "comparison"
    )


def test_the_directive_is_appended_as_a_final_section() -> None:
    # Test: System instruction composition in `with_pattern_guidance`.
    # Situation: A base prompt is passed to `with_pattern_guidance` once with a
    #   `top_n_ranking` classification and once with `None`.
    # Expectation: When classified, the directive is appended under
    #   `_DIRECTIVE_HEADING`; when `None`, the base prompt is returned
    #   unchanged.
    prompt = "### Role\n\nYou are Data Agent."

    guided = pattern_guidance.with_pattern_guidance(
        prompt, _classified("top_n_ranking")
    )

    assert guided.startswith(prompt)
    assert pattern_guidance._DIRECTIVE_HEADING in guided
    assert guided.endswith(pattern_guidance._DIRECTIVES["top_n_ranking"])
    assert pattern_guidance.with_pattern_guidance(prompt, None) == prompt


@pytest.mark.parametrize("pattern", ["clustering", "forecasting"])
def test_unimplemented_patterns_say_so(pattern: str) -> None:
    # Test: Directives for patterns not computed by the agent loop.
    # Situation: A classification carries `clustering` or `forecasting`.
    # Expectation: The directive instructs the answer to state plainly that no
    #   clustering or projection is performed.
    directive = pattern_guidance.pattern_directive(_classified(pattern))

    assert "say plainly that no" in directive


@pytest.mark.parametrize("pattern", get_args(QueryPattern))
def test_directives_carry_no_capability_notes(pattern: str) -> None:
    # Test: Absence of system capability disclaimers in pattern directives.
    # Situation: Each pattern directive is formatted with
    #   `geographic_shape="comparison"`.
    # Expectation: None of the forbidden capability disclaimer phrases appear
    #   in the lowercase directive text.
    directive = pattern_guidance.pattern_directive(
        _classified(pattern, "comparison")
    ).lower()

    for phrase in _CAPABILITY_NOTE_PHRASES:
        assert phrase not in directive
