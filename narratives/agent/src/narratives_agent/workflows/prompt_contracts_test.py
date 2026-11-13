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
"""Tests for `prompt_contracts`."""

import re
from pathlib import Path
from typing import get_args

import pytest
from pydantic import TypeAdapter

from narratives_agent.config import strip_prompt_comments
from narratives_agent.gemini.schemas import QueryClassification
from narratives_agent.workflows import prompt_contracts
from narratives_agent.workflows.charts import (
    BarSort,
    ChartKind,
    ChartSpecification,
)
from narratives_agent.workflows.mcp_loop import (
    DISCOVERY_TOOL_NAMES,
    SERVER_FUNCTION_NAMES,
)
from narratives_agent.workflows.pattern_guidance import build_pattern_directive
from narratives_agent.workflows.prompt_contracts import (
    ContractName,
    compose_system_instruction,
    load_prompt_contract,
)
from narratives_agent.workflows.specification import (
    _MAX_SPECIFICATION_STEPS,
    AnalysisSpecification,
)

# The step limit as the discovery contract writes it, keyed by its value.
_STEP_LIMIT_WORDS = {6: "six"}

_CONTRACTS: tuple[ContractName, ...] = get_args(ContractName.__value__)


def _extract_table_first_column_names(contract: str, heading: str) -> set[str]:
    """Returns backticked names from the first column of a heading's table."""
    _, found, remainder = contract.partition(f"### {heading}\n")
    assert found, f"Missing heading '### {heading}' in contract"
    section, _, _ = remainder.partition("\n### ")
    return set(re.findall(r"^\|\s*`([^`]+)`\s*\|", section, flags=re.MULTILINE))


@pytest.mark.parametrize("name", _CONTRACTS)
def test_every_shipped_contract_loads_and_strips_comments(
    name: ContractName,
) -> None:
    # Test: Loading of every shipped prompt contract.
    # Situation: `load_prompt_contract` is called for each `ContractName`.
    # Expectation: The returned text is non-empty and has all HTML comments
    #   stripped.
    load_prompt_contract.cache_clear()

    text = load_prompt_contract(name)

    assert text
    assert "<!--" not in text
    assert "-->" not in text


def test_missing_contract_file_raises_naming_the_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Test: Failure when a packaged contract file is missing.
    # Situation: `importlib.resources.files` points at an empty directory.
    # Expectation: `load_prompt_contract` raises `RuntimeError` naming
    #   `discovery.md`.
    load_prompt_contract.cache_clear()
    monkeypatch.setattr(prompt_contracts, "files", lambda _pkg: tmp_path)

    with pytest.raises(RuntimeError, match=r"discovery\.md"):
        load_prompt_contract("discovery")

    load_prompt_contract.cache_clear()


def test_empty_contract_file_raises_naming_the_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Test: Failure when a packaged contract file is empty after stripping
    #   HTML comments.
    # Situation: `discovery.md` contains only an HTML comment.
    # Expectation: `load_prompt_contract` raises `RuntimeError` naming
    #   `discovery.md`.
    load_prompt_contract.cache_clear()
    (tmp_path / "discovery.md").write_text(
        "<!-- comment only -->\n", encoding="utf-8"
    )
    monkeypatch.setattr(prompt_contracts, "files", lambda _pkg: tmp_path)

    with pytest.raises(RuntimeError, match=r"discovery\.md.*empty"):
        load_prompt_contract("discovery")

    load_prompt_contract.cache_clear()


def test_compose_orders_guidance_contract_and_directive() -> None:
    # Test: Ordering of guidance, contract, and pattern directive.
    # Situation: `compose_system_instruction` is called with custom guidance
    #   and a ranking classification, and then with no classification.
    # Expectation: The guidance comes first, followed by the discovery
    #   contract, and when classified, the discovery pattern directive last.
    classification = QueryClassification.model_validate(
        {
            "serviceable": True,
            "pattern": "top_n_ranking",
            "geographic_shape": "single_place",
            "requires_computation": True,
        }
    )
    contract = load_prompt_contract("discovery")

    plain = compose_system_instruction("Custom guidance.", "discovery")
    guided = compose_system_instruction(
        "Custom guidance.", "discovery", classification
    )

    assert plain == f"Custom guidance.\n\n{contract}"
    assert guided.startswith(plain)
    assert guided.endswith(build_pattern_directive(classification, "discovery"))


def test_compose_places_the_addendum_after_the_contract() -> None:
    # Test: Placement of `contract_addendum`.
    # Situation: `compose_system_instruction` is called for synthesis with an
    #   addendum and a ranking classification.
    # Expectation: The addendum follows the synthesis contract directly, and
    #   the pattern directive stays last.
    classification = QueryClassification.model_validate(
        {
            "serviceable": True,
            "pattern": "top_n_ranking",
            "geographic_shape": "single_place",
            "requires_computation": True,
        }
    )
    contract = load_prompt_contract("synthesis")

    composed = compose_system_instruction(
        "Custom guidance.",
        "synthesis",
        classification,
        contract_addendum="### Title line",
    )

    assert composed.startswith(
        f"Custom guidance.\n\n{contract}\n\n### Title line"
    )
    assert composed.endswith(
        build_pattern_directive(classification, "synthesis")
    )


def test_composed_default_discovery_prompt_includes_guidance_and_contract() -> (
    None
):
    # Test: Composition of the shipped default `discovery.md` guidance with
    #   the packaged discovery contract.
    # Situation: `defaults/prompts/discovery.md` is read and stripped of HTML
    #   comments, then composed with the `discovery` contract.
    # Expectation: The composed instruction begins with the role heading from
    #   `defaults/prompts/discovery.md`, includes the tool and workflow
    #   sections from `workflows/contracts/discovery.md`, and contains no
    #   HTML comments.
    repo_root = Path(__file__).resolve().parents[4]
    guidance = strip_prompt_comments(
        (repo_root / "defaults" / "prompts" / "discovery.md").read_text(
            encoding="utf-8"
        )
    )

    composed = compose_system_instruction(guidance, "discovery")

    assert composed == f"{guidance}\n\n{load_prompt_contract('discovery')}"
    assert composed.startswith(
        "## Data Agent: Discovery and Analysis Specification"
    )
    assert "\n\n### Available Tools\n\n" in composed
    assert "<!--" not in composed


def test_discovery_contract_tables_match_declared_tools_and_scripts() -> None:
    # Test: Alignment between the `discovery` contract's tables and the
    #   declared discovery tools and specification scripts.
    # Situation: The first-column backticked names are parsed from the
    #   `### Available Tools` and `### Scripts` Markdown tables in
    #   `load_prompt_contract("discovery")`.
    # Expectation: The tools table lists exactly
    #   `DISCOVERY_TOOL_NAMES | SERVER_FUNCTION_NAMES`, and the scripts table
    #   lists exactly the keys of the `AnalysisSpecification` `steps`
    #   discriminator mapping.
    contract = load_prompt_contract("discovery")
    schema = AnalysisSpecification.model_json_schema()
    mapping = schema["properties"]["steps"]["items"]["discriminator"]["mapping"]

    tools = _extract_table_first_column_names(contract, "Available Tools")
    scripts = _extract_table_first_column_names(contract, "Scripts")

    assert tools == DISCOVERY_TOOL_NAMES | SERVER_FUNCTION_NAMES
    assert scripts == set(mapping)


def test_composed_default_synthesis_prompt_includes_guidance_and_contract() -> (
    None
):
    # Test: Composition of the shipped default `synthesis.md` guidance with
    #   the packaged synthesis contract.
    # Situation: `defaults/prompts/synthesis.md` is read and stripped of HTML
    #   comments, then composed with the `synthesis` contract.
    # Expectation: The composed instruction begins with the role heading from
    #   `defaults/prompts/synthesis.md`, includes the citation and chart-block
    #   sections from `workflows/contracts/synthesis.md`, and contains no HTML
    #   comments.
    repo_root = Path(__file__).resolve().parents[4]
    guidance = strip_prompt_comments(
        (repo_root / "defaults" / "prompts" / "synthesis.md").read_text(
            encoding="utf-8"
        )
    )

    composed = compose_system_instruction(guidance, "synthesis")

    assert composed == f"{guidance}\n\n{load_prompt_contract('synthesis')}"
    assert composed.startswith("## Data Agent: Narrative Synthesis")
    assert "\n\n### Citations\n\n" in composed
    assert "\n\n### Chart blocks\n\n" in composed
    assert "<!--" not in composed


def test_synthesis_contract_matches_chart_specification_grammar() -> None:
    # Test: Alignment between `contracts/synthesis.md`,
    #   `defaults/prompts/synthesis.md`, and `ChartSpecification`.
    # Situation: The `### Chart blocks` section of
    #   `load_prompt_contract("synthesis")` and the shipped default
    #   `synthesis.md` prompt are inspected alongside `ChartKind`, `BarSort`,
    #   and `ChartSpecification`'s JSON Schema.
    # Expectation: The backticked lowercase identifiers in `### Chart blocks`
    #   equal the union of `ChartSpecification` property names, `ChartKind`,
    #   `BarSort`, and `"chart"`, `LineChartSpecification` takes no `date`
    #   field, legacy chart-config field names (`should_render`, `viz_type`,
    #   `per_capita`) do not appear, and `defaults/prompts/synthesis.md` names
    #   all five sections rendered by `render_synthesis_message`.
    contract = load_prompt_contract("synthesis")
    _, found, chart_blocks_section = contract.partition("### Chart blocks\n")
    assert found
    backticked = set(
        re.findall(r"`([a-z_]+)(?::\s*true)?`", chart_blocks_section)
    )

    schema = TypeAdapter(ChartSpecification).json_schema()
    defs = schema["$defs"]
    schema_fields = {
        field_name
        for defn in defs.values()
        for field_name in defn.get("properties", {})
    }
    expected_tokens = (
        schema_fields
        | set(get_args(ChartKind.__value__))
        | set(get_args(BarSort.__value__))
        | {"chart"}
    )
    assert backticked == expected_tokens
    assert "date" not in defs["LineChartSpecification"]["properties"]

    repo_root = Path(__file__).resolve().parents[4]
    guidance = strip_prompt_comments(
        (repo_root / "defaults" / "prompts" / "synthesis.md").read_text(
            encoding="utf-8"
        )
    )
    for legacy_term in ("should_render", "viz_type", "per_capita"):
        assert legacy_term not in contract
        assert legacy_term not in guidance
    for section_name in (
        "User Query",
        "NUMBERED SOURCES",
        "ANALYSIS DIGEST",
        "MISSING DATA",
        "TABLE INVENTORY",
    ):
        assert section_name in guidance


def _flattened_citations_section(contract: str) -> str:
    """Returns the `### Citations` section of `contract`, whitespace-joined."""
    _, found, remainder = contract.partition("### Citations\n")
    assert found
    citations, _, _ = remainder.partition("\n### ")
    return " ".join(citations.split())


def test_synthesis_contract_cites_sourced_figures_by_variable() -> None:
    # Test: Active citation rules in `contracts/synthesis.md`.
    # Situation: The `### Citations` section of
    #   `load_prompt_contract("synthesis")`, which the model receives, is
    #   inspected.
    # Expectation: A sourced figure that reports one variable's own value
    #   carries that variable's `cite by variable:` marker, calculated
    #   figures carry no marker, a list or table whose figures share one
    #   marker is cited once, two variables of one source take two numbers,
    #   and the rules that cite calculated figures are absent.
    citations = _flattened_citations_section(load_prompt_contract("synthesis"))

    assert (
        "When a step lists `cite by variable:`, a sourced figure that reports "
        "one variable's own value, such as a single place's observed value, "
        "carries that variable's marker instead."
    ) in citations
    assert (
        "Never attach a marker to a figure the server calculated from the "
        "sourced values"
    ) in citations
    assert (
        "When every figure in a list or a table carries the same marker, "
        "cite it once"
    ) in citations
    assert (
        "Each row names one source and the variable it is cited for, so two "
        "variables from one source have two numbers"
    ) in citations
    assert "drawn from a single source" not in citations
    assert "A figure computed from more than one variable" not in citations
    assert "so every source that contributed is cited" not in citations


def test_synthesis_contract_cites_calculation_only_sources_by_name() -> None:
    # Test: Citation of a source that reaches the answer only through
    #   calculated figures.
    # Situation: The `### Citations` section of
    #   `load_prompt_contract("synthesis")` is inspected.
    # Expectation: Such a source is cited after its name in the headline and
    #   in the column header of a table of those figures, with markers from
    #   the producing steps' `cite:`, and the rule that every listed source
    #   carries a marker names that placement, so it cannot contradict the
    #   rule that calculated figures carry none.
    citations = _flattened_citations_section(load_prompt_contract("synthesis"))

    assert (
        "When a source reaches the answer only through calculated figures, "
        "such as the population behind a per-person rate or the series "
        "behind a ranked change, cite it where the answer names it rather "
        "than beside a number"
    ) in citations
    assert (
        "Take the markers from the `cite:` of the steps that produced the "
        "figures."
    ) in citations
    assert (
        "so each should carry at least one marker, beside a sourced figure "
        "or, by the rule above, after the source's name."
    ) in citations


def test_synthesis_contract_keeps_calculated_figure_citations_disabled() -> (
    None
):
    # Test: Disabled citation rules for calculated figures.
    # Situation: The raw `contracts/synthesis.md` file is read before its HTML
    #   comments are stripped.
    # Expectation: Its `### Citations` section still holds, inside an HTML
    #   comment, the rules that give a figure computed from more than one
    #   variable the step's whole `cite:` marker and a single-variable
    #   summary that variable's marker, so they can be restored.
    raw = (
        Path(prompt_contracts.__file__).parent / "contracts" / "synthesis.md"
    ).read_text(encoding="utf-8")
    citations = _flattened_citations_section(raw)

    assert (
        "A figure computed from more than one variable (a mean or median "
        "over places selected by another variable, a difference, a ratio, a "
        "share, a correlation, a weighted mean, or any value of a derived "
        "variable such as a per-capita rate) carries the step's whole "
        "`cite:` marker"
    ) in citations
    assert (
        "each group's Var_A mean, such as **10.2%** [1, 2], and the gap of "
        "**2.1** [1, 2] between the group means carry both."
    ) in citations
    assert (
        "A figure computed from more than one variable"
        not in strip_prompt_comments(raw)
    )


def test_discovery_contract_requires_a_step_for_every_reported_table() -> None:
    # Test: The rule that only step results reach the answer.
    # Situation: The text of every packaged contract, as the model receives
    #   it.
    # Expectation: Step 3 states that every table the answer reports,
    #   compares, or charts must be the input of a step, and neither
    #   contract tells the loop to leave a fetched table without one.
    discovery = " ".join(load_prompt_contract("discovery").split())

    assert (
        "Every table the answer reports, compares, or charts must be the "
        "input of a step."
    ) in discovery
    for name in get_args(ContractName.__value__):
        assert "no step" not in load_prompt_contract(name)


def test_discovery_contract_states_the_specification_step_limit() -> None:
    # Test: The step limit in the discovery contract.
    # Situation: The discovery contract and `_MAX_SPECIFICATION_STEPS`.
    # Expectation: Step 3 and the step budget in "Choosing indicators" both
    #   state the limit the specification model enforces, so changing one
    #   without the other fails.
    discovery = " ".join(load_prompt_contract("discovery").split())
    limit = _STEP_LIMIT_WORDS[_MAX_SPECIFICATION_STEPS]

    assert f"At most {limit} steps." in discovery
    assert f"Keep within the {limit} steps of Step 3" in discovery


def test_synthesis_contract_writes_no_sentence_about_a_scatter_chart() -> None:
    # Test: The removed scatter disclaimer.
    # Situation: The synthesis contract the model receives.
    # Expectation: It does not ask for a fixed sentence after a `scatter`
    #   chart. The server drops a chart block it cannot draw but keeps the
    #   prose, so such a sentence described a chart the reader never saw.
    contract = " ".join(load_prompt_contract("synthesis").split())

    assert "Follow a `scatter` chart with this one sentence" not in contract
    assert "rather than measuring a statistical or causal link" not in contract


def test_synthesis_contract_gives_the_headline_series_no_bullet() -> None:
    # Test: The layout of an answer that covers several series.
    # Situation: The synthesis contract the model receives.
    # Expectation: The series whose figure the headline gives gets no bullet
    #   of its own, so the first bullet never repeats the headline and an
    #   answer of five indicators stays within four bullets.
    contract = " ".join(load_prompt_contract("synthesis").split())

    assert (
        "The series whose figure the headline gives gets no bullet of its own"
    ) in contract
    assert (
        "An answer that covers five indicators then has one in the headline "
        "and four bullets."
    ) in contract


def test_synthesis_contract_matches_the_opening_to_the_question() -> None:
    # Test: How the answer opens relative to the question asked.
    # Situation: The synthesis contract the model receives.
    # Expectation: A fit step precedes "Writing the answer" and names the
    #   four cases; an answer built on related measures names them and what
    #   they measure before any figure, and claims a measure is unavailable
    #   only when the MISSING DATA notes name it; the missing measures close
    #   the answer under `**Data gaps:**`; and the old rule that named the
    #   indicators after the headline is gone.
    contract = load_prompt_contract("synthesis")
    flattened = " ".join(contract.split())

    assert contract.index(
        "### Matching the answer to the question"
    ) < contract.index("### Writing the answer")
    for case in (
        "**Direct.**",
        "**Related measures.**",
        "**Definition.**",
        "**No data.**",
    ):
        assert case in flattened
    assert (
        "Open with one short sentence that names those indicators and says "
        "what they measure of the topic, then give the headline figure in "
        "the next sentence."
    ) in flattened
    assert (
        "Describe what the reported indicators cover, never what Data "
        "Commons lacks, unless the MISSING DATA notes name it"
    ) in flattened
    assert (
        "end the answer with them, after the last bullet, table, or chart: "
        "the bold label `**Data gaps:**`"
    ) in flattened
    assert "name them in a separate short sentence after the headline" not in (
        flattened
    )


def test_synthesis_contract_keeps_parts_tables_and_labels_accurate() -> None:
    # Test: Parts and wholes, tables of all places, labels, and windows.
    # Situation: The synthesis contract the model receives.
    # Expectation: A place compared with the place that contains it is a part
    #   and its whole, never peers; a table of every place lists every place
    #   the digest gives and never works out a missing figure; the example
    #   that read as a riddle is gone; total and rate trend bullets carry
    #   distinct labels; lows and peaks stay within the question's window;
    #   and technical indicator names get a plain meaning.
    contract = load_prompt_contract("synthesis")
    flattened = " ".join(contract.split())

    assert "### A place and the place that contains it" in contract
    assert (
        'Never write that the whole "led", "had more", or "was higher" '
        "in a count"
    ) in flattened
    assert "### Tables of all places" in contract
    assert "the ten-row limit does not apply" in flattened
    assert "Never work out a missing figure from the others" in flattened
    assert "The ten highest include eight states." not in flattened
    assert "never `**Long-term trend:**` for both" in flattened
    assert "Leave out a peak or low that falls on the first or last year" in (
        flattened
    )
    assert "say what it counts in plain words at first mention" in flattened
    assert "A sentence opens with at most one introductory clause" in (
        flattened
    )
    assert "with thousands separators (a comma between each group of" in (
        flattened
    )
    assert 'Never describe the places as "reporting"' in flattened


def test_synthesis_contract_selects_bullets_without_new_figures() -> None:
    # Test: How the answer chooses its bullets.
    # Situation: The synthesis contract the model receives.
    # Expectation: Each bullet must earn its place; the writer chooses among
    #   the digest's results and never adds a figure; a crossover compares
    #   two given figures for the same date, with no difference or ratio the
    #   digest does not give; places sharing measures are grouped by measure;
    #   and partial coverage is stated as the span covered, not a list of
    #   missing years.
    flattened = " ".join(load_prompt_contract("synthesis").split())

    assert "Each bullet has to earn its place." in flattened
    assert "choose among them, never add to them" in flattened
    assert "every figure in a bullet is one the digest gives" in flattened
    assert "never two figures from different dates" in flattened
    assert (
        'with no difference, ratio, or "times" the digest does not give'
    ) in flattened
    assert "group the bullets by measure, not by place" in flattened
    assert "open with the span it covers, not a list of the years it lacks" in (
        flattened
    )
    assert "Choose the labels from the results the digest computed" not in (
        flattened
    )
    assert "Never rescale a figure into another unit or form" in flattened


def test_synthesis_contract_names_publishers_units_and_remainders() -> None:
    # Test: Source names, counted units, and breakdown leftovers.
    # Situation: The synthesis contract the model receives.
    # Expectation: The answer names the publishing organization rather than
    #   a program or website; says what an indicator counts when it differs
    #   from the question's word; gives a breakdown leader's share only as
    #   computed, never a summed share; describes the digest's unallocated
    #   remainder as unassigned, not as a category.
    flattened = " ".join(load_prompt_contract("synthesis").split())

    assert "Name the organization that publishes the data" in flattened
    assert "say once what it counts" in flattened
    assert "the share of the largest one or two categories exactly" in (
        flattened
    )
    assert "such as the combined share of the top three categories" in (
        flattened
    )
    assert "The digest's unallocated remainder is not a category" in flattened
    assert "categories that form a ladder" in flattened
    assert "the subject next to its verb" in flattened


def test_synthesis_contract_examples_carry_no_figures() -> None:
    # Test: Figures in the synthesis contract's examples.
    # Situation: The synthesis contract the model receives, without its
    #   `### Citations` section, whose examples are kept as they are.
    # Expectation: No bold figure appears anywhere else: every example
    #   shows the shape of a sentence with placeholders such as
    #   `**[value]**`, so an answer can never take a figure from an example.
    contract = load_prompt_contract("synthesis")
    before, _, rest = contract.partition("### Citations\n")
    _, _, after = rest.partition("\n### ")
    outside_citations = before + after
    bold_spans = re.findall(r"\*\*([^*\n]+?)\*\*", outside_citations)
    figures = [
        span
        for span in bold_spans
        if re.search(r"\d", span) and "[" not in span and not span.endswith(":")
    ]

    assert figures == []
    assert "**[value]**" in outside_citations


def test_synthesis_contract_answers_direction_with_parallel_bullets() -> None:
    # Test: Broad questions about direction, and the units in their bullets.
    # Situation: The synthesis contract the model receives.
    # Expectation: A direction question is answered in words from the
    #   computed changes, judging words only when every change agrees; three
    #   or more indicators get a figure-free opening and parallel bullets; a
    #   unit is given once per bullet; a rate keeps the group its name
    #   defines; and a qualifier every gap shares goes in the lead-in line.
    flattened = " ".join(load_prompt_contract("synthesis").split())

    assert "in words taken from the changes the digest computed" in flattened
    assert "only when every reported change points the same way" in flattened
    assert "the opening carries the indicators and their direction but no" in (
        flattened
    )
    assert "give a measure's unit with its first figure only" in flattened
    assert 'never "per 1,000 people"' in flattened
    assert "put it in that line once instead of in each item" in flattened
    assert "so the sentence always names that period" in flattened
    assert "Never let a long-term change stand for the years asked" in (
        flattened
    )
    assert 'never "fell **-[change]**"' in flattened
    assert "Never turn figures into a threshold or an estimate" in flattened


def test_discovery_contract_keeps_unavailable_indicators_out_of_related() -> (
    None
):
    # Test: What `related` may name.
    # Situation: The discovery contract the model receives.
    # Expectation: It forbids listing in `related` an indicator without
    #   data or one recorded in `missing`, because each `related` entry
    #   becomes a follow-up question.
    discovery = " ".join(load_prompt_contract("discovery").split())

    assert (
        "Never list an indicator you found no data for, or one you record in "
        "`missing`"
    ) in discovery


def test_discovery_contract_searches_a_region_and_its_countries() -> None:
    # Test: Questions about a region or grouping of countries.
    # Situation: The discovery contract the model receives.
    # Expectation: It searches the region and its member countries in
    #   parallel, prefers a region-wide figure only for a one-figure
    #   question that has one, otherwise fetches the member countries, never
    #   reports a region unavailable before trying them, and uses the short
    #   region name and a DCID taken from search results.
    discovery = " ".join(load_prompt_contract("discovery").split())

    assert "For a region or grouping of countries" in discovery
    assert "search each angle both ways, in parallel" in discovery
    assert "has data for the region itself, fetch it for the region" in (
        discovery
    )
    assert "Otherwise fetch the member countries with" in discovery
    assert (
        "Never call `report_unavailable` for a region before the "
        "member-country search and fetch have been tried"
    ) in discovery
    assert 'not "Latin America and the Caribbean"' in discovery
    assert "Take the region's DCID only from search results" in discovery


def test_discovery_contract_never_guesses_place_dcids() -> None:
    # Test: Where place DCIDs may come from.
    # Situation: The discovery contract the model receives.
    # Expectation: The no-guessing rule covers places as well as
    #   indicators: a place DCID must come from an earlier search or fetch
    #   result in the turn, except a country's standard ISO DCID, and a
    #   region whose member countries have no data is reported unavailable
    #   instead of being retried under other DCIDs.
    discovery = " ".join(load_prompt_contract("discovery").split())

    assert "Never guess a DCID, for an indicator or for a place" in discovery
    assert "must appear in a search or fetch result earlier in this turn" in (
        discovery
    )
    assert "The one exception is a country's standard DCID" in discovery
    assert "Never try other DCIDs for the region, or a broader place" in (
        discovery
    )


def test_synthesis_contract_never_turns_members_into_a_region_figure() -> None:
    # Test: Answers about a region built from its member countries.
    # Situation: The synthesis contract the model receives.
    # Expectation: A region-wide figure leads when the digest has one;
    #   otherwise the answer says the figure is a median across countries,
    #   names the region as the digest does, and never opens with the
    #   missing regional figure or calculates one.
    synthesis = load_prompt_contract("synthesis")
    flattened = " ".join(synthesis.split())

    assert "### A region and its countries" in synthesis
    assert "When the digest gives a figure for the region itself" in flattened
    assert "never present the median, the mean, or one country's value as" in (
        flattened
    )
    assert "Name the region as the digest names it" in flattened
    assert '"countries and territories"' in flattened
    assert "Never open with it" in flattened
