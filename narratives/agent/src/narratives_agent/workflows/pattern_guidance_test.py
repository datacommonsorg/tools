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
"""Tests for the pattern directives in `pattern_guidance`."""

import re
from typing import get_args

import pytest

from narratives_agent.analytics.digest import RefusalReason
from narratives_agent.gemini.schemas import (
    ChartVizType,
    GeographicShape,
    QueryClassification,
    QueryPattern,
)
from narratives_agent.workflows import pattern_guidance
from narratives_agent.workflows.fetch import build_fetch_declarations
from narratives_agent.workflows.mcp_loop import (
    DISCOVERY_TOOL_NAMES,
    SERVER_FUNCTION_NAMES,
)
from narratives_agent.workflows.pattern_guidance import DirectivePhase
from narratives_agent.workflows.specification import (
    SUBMIT_SPECIFICATION,
    build_specification_declarations,
)

# Arguments of MCP discovery tools whose schemas come from the MCP server at
# runtime.
_MCP_TOOL_ARGUMENTS = frozenset({"places", "include_topics"})

# Lowercase system-capability phrases that must not appear in directives.
_CAPABILITY_NOTE_PHRASES = (
    "release",
    "is available",
    "are available",
    "not available",
    "the server",
    "cannot compute",
)

_PHASES: tuple[DirectivePhase, ...] = get_args(DirectivePhase.__value__)


def _make_classification(
    pattern: str, shape: str = "single_place"
) -> QueryClassification:
    """Returns a serviceable classification with the given pattern and shape."""
    return QueryClassification.model_validate(
        {
            "serviceable": True,
            "pattern": pattern,
            "geographic_shape": shape,
            "requires_computation": False,
        }
    )


@pytest.mark.parametrize("phase", _PHASES)
@pytest.mark.parametrize("pattern", get_args(QueryPattern))
def test_every_pattern_has_its_own_directive(
    pattern: str, phase: DirectivePhase
) -> None:
    # Test: Directive selection by pattern, for each phase.
    # Situation: A classification carries each pattern of the vocabulary with
    #   a single-place shape.
    # Expectation: A non-empty directive is returned, it differs from every
    #   other pattern's directive for the same phase, and it carries no
    #   comparison sentence.
    directive = pattern_guidance.build_pattern_directive(
        _make_classification(pattern), phase
    )

    others = {
        pattern_guidance.build_pattern_directive(
            _make_classification(other), phase
        )
        for other in get_args(QueryPattern)
        if other != pattern
    }
    assert directive
    assert directive not in others
    assert pattern_guidance._COMPARISON_DIRECTIVE.get_phase_text(phase) not in (
        directive
    )


@pytest.mark.parametrize("phase", _PHASES)
@pytest.mark.parametrize("shape", get_args(GeographicShape))
def test_only_the_comparison_shape_adds_the_comparison_sentence(
    shape: str, phase: DirectivePhase
) -> None:
    # Test: The geographic shape's effect on the directive.
    # Situation: A trend classification carries each geographic shape.
    # Expectation: The directive ends with the phase's comparison sentence
    #   for the `comparison` shape only, and starts with the pattern's
    #   directive for the phase in every case.
    directive = pattern_guidance.build_pattern_directive(
        _make_classification("trend_delta", shape), phase
    )

    expected = pattern_guidance._DIRECTIVES["trend_delta"].get_phase_text(phase)
    comparison = pattern_guidance._COMPARISON_DIRECTIVE.get_phase_text(phase)
    assert directive.startswith(expected)
    assert directive.endswith(comparison) is (shape == "comparison")


def test_the_directive_is_appended_as_a_final_section() -> None:
    # Test: Composition of the system instruction.
    # Situation: A prompt body is combined with a ranking classification for
    #   each phase, and then with no classification, as when the classifier
    #   failed.
    # Expectation: The classification appends the phase's half of the
    #   directive after the prompt body under its heading, and no
    #   classification leaves the body as it was.
    prompt = "### Role\n\nYou are Data Agent."
    ranking = pattern_guidance._DIRECTIVES["top_n_ranking"]

    discovery = pattern_guidance.append_pattern_guidance(
        prompt, _make_classification("top_n_ranking"), "discovery"
    )
    synthesis = pattern_guidance.append_pattern_guidance(
        prompt, _make_classification("top_n_ranking"), "synthesis"
    )

    for guided, expected in (
        (discovery, ranking.discovery),
        (synthesis, ranking.synthesis),
    ):
        assert guided.startswith(prompt)
        assert pattern_guidance._DIRECTIVE_HEADING in guided
        assert guided.endswith(expected)
    assert (
        pattern_guidance.append_pattern_guidance(prompt, None, "discovery")
        == prompt
    )


@pytest.mark.parametrize("pattern", ["clustering", "forecasting"])
def test_unimplemented_patterns_say_so(pattern: str) -> None:
    # Test: Directives for the methods the agent loop does not perform.
    # Situation: A classification carries `clustering` or `forecasting`.
    # Expectation: The discovery half tells the loop not to attempt the
    #   method, and the synthesis half tells the answer to say plainly that
    #   the method is not performed, so the answer does not improvise a
    #   projection or a clustering.
    discovery = pattern_guidance.build_pattern_directive(
        _make_classification(pattern), "discovery"
    )
    synthesis = pattern_guidance.build_pattern_directive(
        _make_classification(pattern), "synthesis"
    )

    assert discovery.startswith("Do not attempt")
    assert "say plainly that no" in synthesis


@pytest.mark.parametrize("phase", _PHASES)
@pytest.mark.parametrize("pattern", get_args(QueryPattern))
def test_directives_carry_no_capability_notes(
    pattern: str, phase: DirectivePhase
) -> None:
    # Test: The absence of implementation notes in the directives.
    # Situation: Each pattern's directive for each phase with the comparison
    #   sentence appended, the longest text a phase receives as part of its
    #   system instruction.
    # Expectation: No directive remarks on the release, on which scripts
    #   are available, or on the server, because the model repeats such
    #   remarks to the reader as caveats that have nothing to do with the
    #   data. The check is a tripwire on the phrases that leaked, not a
    #   semantic test.
    directive = pattern_guidance.build_pattern_directive(
        _make_classification(pattern, "comparison"), phase
    ).lower()

    for phrase in _CAPABILITY_NOTE_PHRASES:
        assert phrase not in directive


def _collect_declared_scripts() -> set[str]:
    """Returns the script names the `submit_specification` schema accepts."""
    (submit,) = [
        declaration
        for declaration in build_specification_declarations()
        if declaration.name == SUBMIT_SPECIFICATION
    ]
    schema = submit.parameters_json_schema
    assert isinstance(schema, dict)
    properties = schema.get("properties")
    assert isinstance(properties, dict)
    steps = properties.get("steps")
    assert isinstance(steps, dict)
    step = steps.get("items")
    assert isinstance(step, dict)
    discriminator = step.get("discriminator")
    assert isinstance(discriminator, dict)
    mapping = discriminator.get("mapping")
    assert isinstance(mapping, dict)
    return set(mapping)


def _collect_schema_names(schema: object, names: set[str]) -> None:
    """Collects every property name and string enum or const in a schema."""
    if isinstance(schema, dict):
        for key, value in schema.items():
            if key == "properties" and isinstance(value, dict):
                names.update(k for k in value if isinstance(k, str))
            elif key == "enum" and isinstance(value, list):
                names.update(item for item in value if isinstance(item, str))
            elif key == "const" and isinstance(value, str):
                names.add(value)
            _collect_schema_names(value, names)
    elif isinstance(schema, list):
        for item in schema:
            _collect_schema_names(item, names)


def _collect_declared_vocabulary() -> set[str]:
    """Returns every name a directive may put in backticks.

    The vocabulary is read from the code that defines each name: the server
    functions and their argument schemas (which hold the scripts, their
    parameters, and their enum values), the MCP discovery tools, the
    refusal reasons the digest reports, and the chart kinds synthesis
    accepts.
    """
    names: set[str] = set(SERVER_FUNCTION_NAMES | DISCOVERY_TOOL_NAMES)
    for declaration in (
        build_fetch_declarations() + build_specification_declarations()
    ):
        _collect_schema_names(declaration.parameters_json_schema, names)
    names.update(get_args(RefusalReason.__value__))
    names.update(get_args(ChartVizType))
    names.update(_MCP_TOOL_ARGUMENTS)
    return names


def _collect_directive_texts(phase: DirectivePhase) -> list[str]:
    """Returns every directive text of a phase, the comparison one included."""
    texts = [
        directive.get_phase_text(phase)
        for directive in pattern_guidance._DIRECTIVES.values()
    ]
    texts.append(pattern_guidance._COMPARISON_DIRECTIVE.get_phase_text(phase))
    return texts


@pytest.mark.parametrize("phase", _PHASES)
def test_every_backticked_name_in_a_directive_exists(
    phase: DirectivePhase,
) -> None:
    # Test: The names the directives put in backticks.
    # Situation: Every pattern directive and the comparison sentence, for
    #   each phase.
    # Expectation: Each backticked name is a server function, an MCP
    #   discovery tool or one of its arguments, a script or a parameter or
    #   enum value of the specification schema, a refusal reason, or a
    #   chart kind, so the model is never told about a tool, argument, or
    #   refusal that does not exist.
    named = {
        name
        for text in _collect_directive_texts(phase)
        for name in re.findall(r"`([^`]+)`", text)
    }

    unknown = named - _collect_declared_vocabulary()

    assert not unknown, f"Directives name undeclared terms: {sorted(unknown)}"


@pytest.mark.parametrize("pattern", get_args(QueryPattern))
def test_every_discovery_directive_names_a_declared_server_function(
    pattern: str,
) -> None:
    # Test: The discovery directives match the tool surface the discovery
    #   loop declares.
    # Situation: A classification carries each pattern of the vocabulary.
    # Expectation: The discovery half names at least one of the five server
    #   functions, so the model is pointed at a fetch or a terminal call
    #   that exists.
    directive = pattern_guidance.build_pattern_directive(
        _make_classification(pattern), "discovery"
    )

    assert any(f"`{name}`" in directive for name in SERVER_FUNCTION_NAMES)


@pytest.mark.parametrize("pattern", get_args(QueryPattern))
def test_every_discovery_directive_names_an_accepted_script(
    pattern: str,
) -> None:
    # Test: The scripts the discovery directives name are the ones the
    #   specification accepts.
    # Situation: A classification carries each pattern of the vocabulary,
    #   `data_availability` included, since it anchors its survey in one
    #   fetched table.
    # Expectation: The discovery half names at least one script from the
    #   `submit_specification` schema's `script` enum.
    directive = pattern_guidance.build_pattern_directive(
        _make_classification(pattern), "discovery"
    )

    assert any(
        f"`{script}`" in directive for script in _collect_declared_scripts()
    )


def test_synthesis_directives_name_no_tools_or_scripts() -> None:
    # Test: What the synthesis half keeps away from the synthesis model.
    # Situation: Every pattern's synthesis directive and the synthesis
    #   comparison sentence.
    # Expectation: None names a server function, a discovery tool, or a
    #   script, and none opens with a fetch instruction. The synthesis model
    #   cannot call tools, and when it was handed the discovery
    #   instructions it narrated them as its own work ("I'm ranking the
    #   counties with rank_cohort") instead of reading the digest.
    forbidden = SERVER_FUNCTION_NAMES | DISCOVERY_TOOL_NAMES
    forbidden |= _collect_declared_scripts()

    for text in _collect_directive_texts("synthesis"):
        named = set(re.findall(r"`([^`]+)`", text))
        assert not named & forbidden, f"Synthesis directive names {named}"
        assert not text.startswith("Fetch")


def test_the_comparison_sentence_asks_for_one_fetch() -> None:
    # Test: The comparison directive's retrieval instruction.
    # Situation: A single-point classification of comparison shape, in the
    #   discovery phase.
    # Expectation: The appended sentence tells the loop to fetch every named
    #   place in one `fetch_observations` call, so the places share a facet.
    directive = pattern_guidance.build_pattern_directive(
        _make_classification("single_point", "comparison"), "discovery"
    )

    assert "one `fetch_observations` call" in directive


def test_the_ranking_directive_relates_only_a_second_variable() -> None:
    # Test: The two paths of the top-N discovery directive.
    # Situation: The `top_n_ranking` discovery directive.
    # Expectation: Its first sentence answers a one-variable ranking with
    #   `rank_cohort` and names no relation; `relate_cohorts` appears only
    #   after the sentence about a second variable, which fetches both
    #   variables across the cohort with `fetch_child_observations`.
    directive = pattern_guidance.build_pattern_directive(
        _make_classification("top_n_ranking"), "discovery"
    )
    one_variable, _, two_variables = directive.partition(
        "When the question asks for a second variable"
    )

    assert "`rank_cohort`" in one_variable
    assert "`relate_cohorts`" not in one_variable
    assert "`relate_cohorts`" in two_variables
    assert "`fetch_child_observations` in the same round" in two_variables


@pytest.mark.parametrize("phase", _PHASES)
def test_the_correlation_directive_relates_and_never_divides(
    phase: DirectivePhase,
) -> None:
    # Test: The correlation directive.
    # Situation: The `correlation` directive for each phase.
    # Expectation: The discovery half specifies `relate_cohorts`, and
    #   neither half names a ratio, the quotient of two indicators that the
    #   relation replaces.
    directive = pattern_guidance.build_pattern_directive(
        _make_classification("correlation"), phase
    )

    if phase == "discovery":
        assert "`relate_cohorts`" in directive
    assert "ratio" not in directive
