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
"""Tests for `workflows.data_gaps`."""

import pytest

from narratives_agent.workflows.data_gaps import (
    DataGaps,
    DataGapsCollector,
    is_data_gaps_label,
)

_INTRO = "These measures are not available in Data Commons:"


def _collect(text: str) -> tuple[DataGaps | None, list[str]]:
    """Reads a block whose first line is the label.

    Returns the parsed block and the lines left after it.
    """
    label, *rest = text.split("\n")
    collector = DataGapsCollector([label])
    for position, line in enumerate(rest):
        if not collector.add(line):
            return collector.build(), rest[position:]
    return collector.build(), []


@pytest.mark.parametrize(
    "line",
    [
        "**Data gaps**\\",
        "**Data gaps**",
        "**Data gaps** \\ ",
        "**Data gaps:**",
        "**Data gaps**:",
        "**Data Gaps**\\",
        "## Data gaps",
        "Data gaps:",
    ],
)
def test_a_label_line_is_recognized(line: str) -> None:
    # Test: The forms of the label line.
    # Situation: The label as the contract asks for it, and as a model
    #   writes it in its place: without the backslash, with spaces around
    #   it, with a colon, in another letter case, as a heading, and plain.
    # Expectation: Each line is a Data gaps label.
    assert is_data_gaps_label(line)


@pytest.mark.parametrize(
    "line",
    [
        "**Data gaps** remain for two measures.",
        "The **Data gaps** are listed below.",
        "- **Data gaps**",
        "**Data gap**",
    ],
)
def test_a_line_that_only_mentions_the_label_is_not_one(line: str) -> None:
    # Test: Lines that hold the label's words and are not the label line.
    # Situation: A sentence that opens with or contains the bold phrase, a
    #   list item holding it, and a different phrase.
    # Expectation: None of them is a Data gaps label.
    assert not is_data_gaps_label(line)


@pytest.mark.parametrize(
    "text",
    [
        f"**Data gaps**\\\n{_INTRO}\n- Antenatal care coverage\n- Screening",
        f"**Data gaps**\\\n\n{_INTRO}\n- Antenatal care coverage\n- Screening",
        f"**Data gaps**\\\n{_INTRO}\n\n- Antenatal care coverage\n- Screening",
        f"**Data gaps**\\\n{_INTRO}\n- Antenatal care coverage\n\n- Screening",
        f"**Data gaps**\\\n{_INTRO}\n1. Antenatal care coverage\n2) Screening",
        f"**Data gaps**\\\n{_INTRO}\n- Antenatal care\n  coverage\n- Screening",
    ],
    ids=[
        "contract_form",
        "blank_line_after_label",
        "blank_line_before_list",
        "blank_line_between_items",
        "numbered_list",
        "wrapped_item",
    ],
)
def test_a_block_is_read_across_its_layouts(text: str) -> None:
    # Test: The layouts a model gives the block.
    # Situation: The contract's form, the same block with a blank line in
    #   each place a model adds one, a numbered list, and an item wrapped
    #   onto a second line.
    # Expectation: Every layout yields the same intro and the same two
    #   items, and no line is left after the block.
    assert _collect(text) == (
        DataGaps(intro=_INTRO, items=("Antenatal care coverage", "Screening")),
        [],
    )


def test_items_and_intro_are_cleaned_to_plain_text() -> None:
    # Test: Inline Markdown in the intro and the items.
    # Situation: The intro ends with a hard-break backslash, and the items
    #   hold bold and italic marks, a citation marker, and an escaped
    #   dollar sign.
    # Expectation: The intro and items are plain text: the marks, the
    #   marker, and the backslashes are gone, and the dollar sign stays.
    gaps, rest = _collect(
        "**Data gaps**\\\n"
        "Global figures are **not** available:\\\n"
        "- **Antenatal care** coverage [1]\n"
        "- Out-of-pocket spending (US\\$)\n"
        "- *Screening*   coverage [2, 3]"
    )

    assert gaps == DataGaps(
        intro="Global figures are not available:",
        items=(
            "Antenatal care coverage",
            "Out-of-pocket spending (US$)",
            "Screening coverage",
        ),
    )
    assert rest == []


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        (r"Count\_Person", "Count_Person"),
        ("`Count_Person`", "Count_Person"),
        ("PM2_5 concentration", "PM2_5 concentration"),
        ("_Screening_ coverage", "Screening coverage"),
        ("__Antenatal__ care", "Antenatal care"),
    ],
    ids=[
        "escaped_underscore",
        "underscore_in_code",
        "underscore_inside_a_word",
        "underscore_italics",
        "underscore_bold",
    ],
)
def test_an_underscore_is_removed_only_as_an_emphasis_mark(
    item: str, expected: str
) -> None:
    # Test: Underscores in an item.
    # Situation: An escaped underscore, an identifier in a code span, an
    #   underscore inside a word, and underscores used as italic and bold
    #   marks.
    # Expectation: An underscore inside a word stays, an escaped one loses
    #   only its backslash, and the emphasis marks are removed.
    gaps, _ = _collect(f"**Data gaps**\n- {item}")

    assert gaps == DataGaps(intro="", items=(expected,))


def test_a_paragraph_after_the_list_ends_the_block() -> None:
    # Test: Where the block ends.
    # Situation: A blank line and a sentence follow the list.
    # Expectation: The block holds the items written before the blank
    #   line, and the sentence is left for the text after the block.
    gaps, rest = _collect(
        f"**Data gaps**\\\n{_INTRO}\n- A\n- B\n\nRelated figures are above."
    )

    assert gaps == DataGaps(intro=_INTRO, items=("A", "B"))
    assert rest == ["Related figures are above."]


def test_a_block_without_an_intro_has_an_empty_intro() -> None:
    # Test: A list directly under the label.
    # Situation: The model wrote no introducing line.
    # Expectation: The intro is empty and the items are read.
    assert _collect("**Data gaps**\n- A\n- B") == (
        DataGaps(intro="", items=("A", "B")),
        [],
    )


@pytest.mark.parametrize(
    "text",
    [
        "**Data gaps**\\",
        f"**Data gaps**\\\n{_INTRO}",
        f"**Data gaps**\\\n{_INTRO}\n\nFigures for 2020 are missing.",
        f"**Data gaps**\\\n{_INTRO}\n- \n- **",
    ],
    ids=[
        "label_only",
        "intro_only",
        "prose_in_place_of_a_list",
        "items_without_text",
    ],
)
def test_a_block_that_lists_no_measure_is_not_built(text: str) -> None:
    # Test: A label that no list of measures follows.
    # Situation: The label alone, the label and its intro, prose where the
    #   list belongs, and list items that hold no text once cleaned.
    # Expectation: No block is built, so the lines stay answer text.
    gaps, _ = _collect(text)

    assert gaps is None
