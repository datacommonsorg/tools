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
"""Loads code-owned prompt contracts and composes phase system instructions.

System prompts in `defaults/prompts/` hold operator-overridable domain and
geographic guidance. The rules the server depends on (the tool surface, the
fetch and specification workflow, and the output formats) live in packaged
markdown files under `narratives_agent/workflows/contracts/` and are appended
after the configured guidance on every request so an instance override cannot
drop or contradict them.
"""

from functools import cache
from importlib.resources import files
from typing import Literal

from narratives_agent.config import strip_prompt_comments
from narratives_agent.gemini.schemas import QueryClassification
from narratives_agent.workflows.pattern_guidance import append_pattern_guidance

__all__ = [
    "ContractName",
    "compose_system_instruction",
    "load_prompt_contract",
]

# The packaged contracts under `narratives_agent.workflows.contracts`.
type ContractName = Literal["discovery", "synthesis"]

_CONTRACTS_PACKAGE = "narratives_agent.workflows.contracts"


@cache
def load_prompt_contract(name: ContractName) -> str:
    """Returns the comment-stripped text of the packaged contract `name`.

    Args:
        name: The stem of the markdown contract file under
            `narratives_agent.workflows.contracts`.

    Returns:
        The non-empty contract text with HTML comments stripped.

    Raises:
        RuntimeError: If the contract file is missing, unreadable, or empty
            once HTML comments are stripped.
    """
    filename = f"{name}.md"
    resource = files(_CONTRACTS_PACKAGE).joinpath(filename)
    try:
        raw = resource.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise RuntimeError(
            f"Prompt contract {filename!r} could not be read from "
            f"{_CONTRACTS_PACKAGE}."
        ) from exc
    contract = strip_prompt_comments(raw)
    if not contract:
        raise RuntimeError(
            f"Prompt contract {filename!r} in {_CONTRACTS_PACKAGE} is empty."
        )
    return contract


def compose_system_instruction(
    guidance: str,
    contract: ContractName,
    classification: QueryClassification | None = None,
) -> str:
    """Composes guidance, a code-owned contract, and pattern guidance.

    Args:
        guidance: The configured prompt body for the phase.
        contract: Which packaged contract to append after `guidance`.
        classification: The classify phase's verdict, or `None` when the
            classifier failed.

    Returns:
        The composed system instruction with `guidance` first, the packaged
        contract second, and the pattern directive last when `classification`
        is present.

    Raises:
        RuntimeError: If the packaged contract file for `contract` is missing,
            unreadable, or empty once HTML comments are stripped.
    """
    contract_text = load_prompt_contract(contract)
    composed = f"{guidance}\n\n{contract_text}" if guidance else contract_text
    return append_pattern_guidance(composed, classification, contract)
