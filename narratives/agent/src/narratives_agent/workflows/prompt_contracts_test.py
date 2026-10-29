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

from narratives_agent.config import strip_prompt_comments
from narratives_agent.gemini.schemas import QueryClassification
from narratives_agent.workflows import prompt_contracts
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
from narratives_agent.workflows.specification import AnalysisSpecification

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
