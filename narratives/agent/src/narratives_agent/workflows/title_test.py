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
"""Tests for `workflows.title`.

Covers `parse_title_line`, `clean_title`, `title_directive`, and
`TitleExtractor`.
"""

import pytest

from narratives_agent.workflows.title import (
    MAX_TITLE_WORDS,
    NO_TITLE_DIRECTIVE,
    TITLE_DIRECTIVE,
    TitleExtractor,
    clean_title,
    parse_title_line,
    title_directive,
)

_ANSWER = (
    "According to the World Bank, life expectancy was higher in Japan.\n\n"
    "- **Long-term trend:** it rose in both countries.\n"
)


def _extract(
    text: str, *, accept: bool = True, chunk: int = 5
) -> tuple[TitleExtractor, str, list[str]]:
    """Feeds `text` to an extractor in chunks of `chunk` characters.

    Returns:
        The finished extractor, the text it forwarded, and the titles it
        reported.
    """
    forwarded: list[str] = []
    titles: list[str] = []
    extractor = TitleExtractor(
        forward=forwarded.append, on_title=titles.append, accept=accept
    )
    for start in range(0, len(text), chunk):
        extractor.feed(text[start : start + chunk])
    extractor.finish()
    return extractor, "".join(forwarded), titles


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("# Life expectancy in Japan", "Life expectancy in Japan"),
        ("## Life expectancy in Japan ##", "Life expectancy in Japan"),
        ("**Life expectancy in Japan**", "Life expectancy in Japan"),
        ("Title: Life expectancy in Japan", "Life expectancy in Japan"),
        ("**Title:** Life expectancy in Japan", "Life expectancy in Japan"),
        ("According to the World Bank, life expectancy rose.", None),
        ("- **Trend:** it rose.", None),
        ("#hashtag without a space", None),
    ],
)
def test_title_lines_are_recognized(line: str, expected: str | None) -> None:
    # Test: Recognition of title lines by `parse_title_line`.
    # Situation: The line is a Markdown heading, a fully bold line, a
    #   "Title:" label, or ordinary answer prose.
    # Expectation: The title text is returned for the three title forms and
    #   `None` for prose, a bulleted bold label, or a hash without a space.
    assert parse_title_line(line) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Life expectancy in Japan", "Life expectancy in Japan"),
        ('"Life expectancy in Japan."', "Life expectancy in Japan"),
        ("Title: *Life expectancy* in Japan [1]", "Life expectancy in Japan"),
        ("  Life   expectancy\tin Japan:  ", "Life expectancy in Japan"),
        ("Median household income?", "Median household income"),
        ("PM2.5 concentration in Delhi", "PM2.5 concentration in Delhi"),
        ("", None),
        ("  ...  ", None),
        (" ".join(["word"] * (MAX_TITLE_WORDS + 1)), None),
        ("x" * 101, None),
    ],
)
def test_titles_are_cleaned_or_rejected(raw: str, expected: str | None) -> None:
    # Test: Cleaning of raw titles by `clean_title`.
    # Situation: The raw title carries quotes, trailing punctuation, a
    #   "Title:" label, emphasis, citations, or extra whitespace; keeps a
    #   number inside a measure name; is empty; or is too long.
    # Expectation: Decoration is removed while internal punctuation in a
    #   measure name is kept; empty and overlong titles give `None`.
    assert clean_title(raw) == expected


def test_the_directive_asks_for_a_title_only_with_data() -> None:
    # Test: Selection of the title format directive.
    # Situation: The turn has data, then has none.
    # Expectation: The title directive is returned with data and the
    #   no-title directive without.
    assert title_directive(has_data=True) == TITLE_DIRECTIVE
    assert title_directive(has_data=False) == NO_TITLE_DIRECTIVE


@pytest.mark.parametrize("chunk", [1, 3, 5, 40, 10_000])
def test_a_title_line_is_taken_off_the_stream(chunk: int) -> None:
    # Test: Extraction of a title line from a chunked stream.
    # Situation: The answer opens with `# <title>` and a blank line, fed in
    #   chunks of several sizes.
    # Expectation: The title is reported once and kept on the extractor, and
    #   the forwarded text is the answer without the title line.
    extractor, forwarded, titles = _extract(
        "# Life expectancy in Japan and France\n\n" + _ANSWER, chunk=chunk
    )

    assert titles == ["Life expectancy in Japan and France"]
    assert extractor.title == "Life expectancy in Japan and France"
    assert forwarded.strip() == _ANSWER.strip()


def test_leading_blank_lines_before_the_title_are_skipped() -> None:
    # Test: Blank lines ahead of the title line.
    # Situation: The stream opens with blank lines and then the title line.
    # Expectation: The title is still recognized and not forwarded.
    extractor, forwarded, _ = _extract(
        "\n\n  \n# Median gross rent\n" + _ANSWER
    )

    assert extractor.title == "Median gross rent"
    assert "Median gross rent" not in forwarded


def test_an_answer_without_a_title_line_is_forwarded_whole() -> None:
    # Test: A data turn whose answer omits the title line.
    # Situation: The stream opens directly with the answer's first sentence.
    # Expectation: No title is reported and the whole answer is forwarded.
    extractor, forwarded, titles = _extract(_ANSWER)

    assert titles == []
    assert extractor.title is None
    assert forwarded == _ANSWER


def test_a_title_on_a_turn_without_data_is_dropped() -> None:
    # Test: A title line written on a turn without data.
    # Situation: `accept` is false and the answer opens with a title line.
    # Expectation: No title is reported and the title line is not forwarded.
    extractor, forwarded, titles = _extract(
        "# Immigration data for Germany\n\n" + _ANSWER, accept=False
    )

    assert titles == []
    assert extractor.title is None
    assert forwarded.strip() == _ANSWER.strip()


def test_an_overlong_title_line_is_dropped_from_the_answer() -> None:
    # Test: A title line that fails cleaning.
    # Situation: The heading holds a sentence longer than the word limit.
    # Expectation: No title is reported, and the line is still kept out of
    #   the forwarded answer rather than shown as a heading.
    sentence = " ".join(["word"] * (MAX_TITLE_WORDS + 3))
    extractor, forwarded, titles = _extract(f"# {sentence}\n\n" + _ANSWER)

    assert titles == []
    assert extractor.title is None
    assert sentence not in forwarded


def test_a_stream_without_a_newline_is_decided_at_finish() -> None:
    # Test: Decision on a stream whose only line has no newline.
    # Situation: The stream is one line of prose with no trailing newline.
    # Expectation: Nothing is forwarded before `finish`, and the line is
    #   forwarded whole once the stream ends.
    forwarded: list[str] = []
    extractor = TitleExtractor(
        forward=forwarded.append, on_title=lambda _: None, accept=True
    )
    extractor.feed("Life expectancy rose in Japan.")
    assert forwarded == []

    extractor.finish()

    assert forwarded == ["Life expectancy rose in Japan."]


def test_an_empty_stream_forwards_nothing() -> None:
    # Test: An empty or blank synthesis stream.
    # Situation: The stream carries only whitespace.
    # Expectation: No title is reported and nothing is forwarded.
    extractor, forwarded, titles = _extract("  \n\n ")

    assert titles == []
    assert extractor.title is None
    assert forwarded == ""
