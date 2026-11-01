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
"""Tests for `workflows.blocks`.

Covers `BlockSplitter`, including brute-force checks against an independent
oracle.
"""

import itertools
import json
from collections.abc import Sequence
from typing import Literal

import pytest

from narratives_agent.workflows.blocks import (
    BlockSplitter,
    ChartBlock,
    SynthesisBlock,
    TextBlock,
)
from narratives_agent.workflows.charts import (
    MAX_CHARTS_PER_TURN,
    ChartSpecification,
    PlaceList,
    ResolvedChart,
    ResolvedLineChart,
)


def _make_line_chart(title: str) -> ResolvedLineChart:
    """Builds a resolved line of one place with a title."""
    return ResolvedLineChart(
        title=title,
        variable_dcids=("Count_Person",),
        scope=PlaceList(("country/FRA",)),
    )


class _Recorder:
    """Records the blocks a splitter emits and resolves charts by title.

    An accepted specification resolves to a line of one place, whatever its
    kind, carrying the specification's title.
    """

    def __init__(self, should_accept: bool = True) -> None:
        self.blocks: list[SynthesisBlock] = []
        self.specs: list[ChartSpecification] = []
        self.should_accept = should_accept

    def record_block(self, block: SynthesisBlock) -> None:
        """Appends an emitted block."""
        self.blocks.append(block)

    def resolve(self, spec: ChartSpecification) -> ResolvedChart | None:
        """Records `spec` and accepts it as a chart, or rejects it."""
        self.specs.append(spec)
        if not self.should_accept:
            return None
        return _make_line_chart(spec.title)


def _split(
    text: str, chunk: int = 7, should_accept: bool = True
) -> tuple[BlockSplitter, _Recorder]:
    """Feeds `text` to a splitter in chunks of `chunk` characters."""
    recorder = _Recorder(should_accept)
    splitter = BlockSplitter(recorder.record_block, recorder.resolve)
    for start in range(0, len(text), chunk):
        splitter.feed(text[start : start + chunk])
    splitter.finish()
    return splitter, recorder


def _get_block_kind(block: SynthesisBlock) -> str:
    """Names the type of an emitted block."""
    return "text" if isinstance(block, TextBlock) else "chart"


_CHART = '{"kind": "line", "tables": ["t1"], "title": "Population"}'


def test_paragraphs_and_chart_blocks_are_emitted_in_order() -> None:
    # Test: The block sequence of a well-formed answer.
    # Situation: Two paragraphs, a chart fence after a blank line, a list
    #   with no internal blank lines, a chart fence opened after a single
    #   line break, and a closing paragraph with no trailing newline.
    # Expectation: Text and chart blocks appear in stream order with
    #   sequential indexes, the list stays one block, the paragraph before
    #   the mid-paragraph fence is flushed on its own, and the answer text
    #   is the text blocks joined by blank lines with the chart blocks
    #   stripped.
    text = (
        "First paragraph.\n\n"
        "Second paragraph\ncontinues here.\n\n"
        f"```chart\n{_CHART}\n```\n\n"
        "- one\n- two\n- three\n\n"
        f"Lead-in sentence.\n``` chart \n{_CHART}\n```\n"
        "Closing words."
    )

    splitter, recorder = _split(text)

    assert [
        (block.index, _get_block_kind(block)) for block in recorder.blocks
    ] == [
        (0, "text"),
        (1, "text"),
        (2, "chart"),
        (3, "text"),
        (4, "text"),
        (5, "chart"),
        (6, "text"),
    ]
    assert isinstance(recorder.blocks[1], TextBlock)
    assert recorder.blocks[1].markdown == "Second paragraph\ncontinues here."
    assert isinstance(recorder.blocks[2], ChartBlock)
    assert recorder.blocks[2].chart == _make_line_chart("Population")
    assert isinstance(recorder.blocks[3], TextBlock)
    assert recorder.blocks[3].markdown == "- one\n- two\n- three"
    assert isinstance(recorder.blocks[4], TextBlock)
    assert recorder.blocks[4].markdown == "Lead-in sentence."
    assert splitter.text == (
        "First paragraph.\n\nSecond paragraph\ncontinues here.\n\n"
        "- one\n- two\n- three\n\nLead-in sentence.\n\nClosing words."
    )
    assert splitter.charts_emitted == 2
    assert splitter.charts_rejected == 0
    assert [spec.tables for spec in recorder.specs] == [("t1",), ("t1",)]


def test_a_chart_fence_at_the_start_of_the_stream_is_a_chart() -> None:
    # Test: A fence with no prose before it.
    # Situation: The stream opens with a chart fence.
    # Expectation: The first block is the chart, with no empty text block.
    _, recorder = _split(f"```chart\n{_CHART}\n```\n\nAfter.")

    assert [_get_block_kind(block) for block in recorder.blocks] == [
        "chart",
        "text",
    ]


def test_a_non_chart_fence_is_kept_in_the_prose_whole() -> None:
    # Test: Code fences other than charts.
    # Situation: A fenced code block with a blank line inside it sits
    #   between two paragraphs.
    # Expectation: The fence and its blank line stay in one text block, and
    #   no chart is resolved.
    text = "Before.\n\n```json\n{\n\n}\n```\n\nAfter."

    splitter, recorder = _split(text)

    assert list(splitter.text_blocks) == [
        "Before.",
        "```json\n{\n\n}\n```",
        "After.",
    ]
    assert recorder.specs == []


@pytest.mark.parametrize(
    ("body", "should_accept"),
    [
        ("{not json", True),
        ('{"kind": "line", "tables": [], "title": "x"}', True),
        ('{"kind": "line", "tables": ["t1"], "title": "x", "extra": 1}', True),
        (_CHART, False),
    ],
    ids=["malformed_json", "schema_violation", "unknown_field", "unresolved"],
)
def test_a_bad_chart_block_is_dropped_and_counted(
    body: str, should_accept: bool
) -> None:
    # Test: Chart blocks that cannot be shown.
    # Situation: The fence body is not JSON, fails the grammar, carries an
    #   unknown field, or is rejected by the resolver.
    # Expectation: No chart or text block is emitted for it, the rejection
    #   is counted, and the surrounding prose is intact.
    splitter, recorder = _split(
        f"Before.\n\n```chart\n{body}\n```\n\nAfter.",
        should_accept=should_accept,
    )

    assert [_get_block_kind(block) for block in recorder.blocks] == [
        "text",
        "text",
    ]
    assert splitter.text == "Before.\n\nAfter."
    assert splitter.charts_rejected == 1
    assert splitter.charts_emitted == 0


def test_an_unclosed_chart_fence_is_dropped_at_the_end() -> None:
    # Test: A trailing partial fence.
    # Situation: The stream ends inside a chart block.
    # Expectation: The prose before it is emitted, the JSON never reaches a
    #   text block, and the block counts as rejected.
    splitter, recorder = _split(f"Before.\n\n```chart\n{_CHART[:20]}")

    assert list(splitter.text_blocks) == ["Before."]
    assert recorder.specs == []
    assert splitter.charts_rejected == 1
    assert "kind" not in splitter.text


def test_charts_beyond_the_cap_are_dropped() -> None:
    # Test: The chart cap.
    # Situation: The answer holds one more chart block than the cap.
    # Expectation: The first `MAX_CHARTS_PER_TURN` are emitted, the extra
    #   one is counted as rejected without reaching the resolver.
    blocks = "\n\n".join(
        f"```chart\n{_CHART}\n```" for _ in range(MAX_CHARTS_PER_TURN + 1)
    )

    splitter, recorder = _split(f"Intro.\n\n{blocks}")

    assert splitter.charts_emitted == MAX_CHARTS_PER_TURN
    assert splitter.charts_rejected == 1
    assert len(recorder.specs) == MAX_CHARTS_PER_TURN


def test_an_appended_chart_takes_the_next_index() -> None:
    # Test: The default chart appended after the stream.
    # Situation: The stream holds one paragraph and the server appends a
    #   chart once it has finished.
    # Expectation: The chart block follows the text block with the next
    #   index and is counted as emitted.
    splitter, recorder = _split("Only prose.")
    splitter.append_chart(_make_line_chart("Default"))

    assert [(b.index, _get_block_kind(b)) for b in recorder.blocks] == [
        (0, "text"),
        (1, "chart"),
    ]
    assert splitter.charts_emitted == 1
    assert splitter.text == "Only prose."


def test_feed_after_finish_raises() -> None:
    # Test: The single-pass lifecycle of a splitter.
    # Situation: A splitter has finished its stream and is fed more text.
    # Expectation: `feed` raises, and no further block is emitted.
    splitter, recorder = _split("Only prose.")

    with pytest.raises(RuntimeError, match="after finish"):
        splitter.feed("More prose.\n\n")

    assert [_get_block_kind(block) for block in recorder.blocks] == ["text"]


def test_a_second_finish_emits_nothing() -> None:
    # Test: Calling `finish` twice.
    # Situation: A finished splitter, whose last paragraph was flushed, is
    #   finished again.
    # Expectation: The second call emits no block and counts no rejection.
    splitter, recorder = _split("Only prose.\n\n```chart\n{")

    splitter.finish()

    assert [_get_block_kind(block) for block in recorder.blocks] == ["text"]
    assert splitter.charts_rejected == 1


def test_an_info_string_fence_does_not_close_a_code_block() -> None:
    # Test: The closing fence of a non-chart code block.
    # Situation: A plain fenced block holds a fence line with the `python`
    #   info string, followed by a bare closing fence and a paragraph.
    # Expectation: The inner fence line is part of the code block, so the
    #   block and the paragraph are two text blocks and no chart is parsed.
    text = "```\n```python\nx = 1\n```\n\nAfter."

    splitter, recorder = _split(text)

    assert list(splitter.text_blocks) == [
        "```\n```python\nx = 1\n```",
        "After.",
    ]
    assert recorder.specs == []
    assert splitter.charts_rejected == 0


@pytest.mark.parametrize(
    ("text", "expected_text_blocks"),
    [
        (
            f"Intro.\n```\nMore.\n\n```chart\n{_CHART}\n```\n\nAfter.",
            ["Intro.\n```\nMore.", "After."],
        ),
        (
            f"````md\n```python\nx\n```\n\n```chart\n{_CHART}\n```\n\nAfter.",
            ["````md\n```python\nx\n```", "After."],
        ),
    ],
    ids=["stray_bare_fence", "longer_fence_left_open"],
)
def test_a_chart_fence_ends_a_code_block_left_open(
    text: str, expected_text_blocks: list[str]
) -> None:
    # Test: A chart block after a code block the model left open.
    # Situation: A stray bare fence, or a longer fence that the shorter fence
    #   it holds does not close, leaves a code block open when a chart block
    #   follows.
    # Expectation: The chart fence ends the open code block, which is
    #   emitted as text, and the chart is resolved, so no text block holds
    #   the chart's JSON.
    splitter, recorder = _split(text)

    assert list(splitter.text_blocks) == expected_text_blocks
    assert [spec.title for spec in recorder.specs] == ["Population"]
    assert splitter.charts_emitted == 1
    assert all("kind" not in block for block in splitter.text_blocks)


@pytest.mark.parametrize(
    "fence",
    ["````", "~~~~"],
    ids=["backticks", "tildes"],
)
def test_a_shorter_fence_does_not_close_a_longer_code_block(
    fence: str,
) -> None:
    # Test: The CommonMark closing-fence length rule.
    # Situation: A four-character fence holds a three-character example
    #   fence followed by a blank line, then closes with its own length.
    # Expectation: The shorter fence and the blank line stay in the code
    #   block, so the outer block is one text block and the paragraph after
    #   it is another.
    short = fence[:3]
    block = f"{fence}md\n{short}py\nx = 1\n{short}\n\nProse inside.\n{fence}"

    splitter, _ = _split(f"{block}\n\nAfter.")

    assert list(splitter.text_blocks) == [block, "After."]


def test_a_longer_bare_fence_closes_a_code_block() -> None:
    # Test: A closing fence longer than the opening fence.
    # Situation: A three-backtick block closes on a four-backtick bare fence,
    #   followed by a blank line and a paragraph.
    # Expectation: The longer fence closes the block, so the paragraph is a
    #   separate text block.
    splitter, _ = _split("```py\nx = 1\n````\n\nAfter.")

    assert list(splitter.text_blocks) == ["```py\nx = 1\n````", "After."]


# The observable outcome of one splitter run: the emitted blocks, the answer
# text, the charts, the emitted chart count, and the rejected chart count.
type _SplitOutcome = tuple[
    tuple[SynthesisBlock, ...], str, tuple[ResolvedChart, ...], int, int
]

# A stream holding every block transition the splitter handles: a paragraph
# that runs into a chart fence after a single line break, a valid chart, a
# paragraph after a chart closed by a single line break, a non-chart fence
# with an internal blank line, an invalid chart, and a closing paragraph
# with no trailing newline.
_RICH_STREAM = (
    "Intro\nline.\n"
    '```chart\n{"kind": "bar", "tables": ["t1"], "title": "A"}\n```\n'
    "Mid.\n\n"
    "```py\nx\n\ny\n```\n\n"
    "```chart\n{bad\n```\n"
    "End."
)


def _run_chunks(chunks: Sequence[str]) -> _SplitOutcome:
    """Feeds `chunks` to a splitter in order and returns its outcome."""
    recorder = _Recorder()
    splitter = BlockSplitter(recorder.record_block, recorder.resolve)
    for chunk in chunks:
        splitter.feed(chunk)
    splitter.finish()
    return (
        tuple(recorder.blocks),
        splitter.text,
        tuple(splitter.charts),
        splitter.charts_emitted,
        splitter.charts_rejected,
    )


def test_the_outcome_does_not_depend_on_chunk_boundaries() -> None:
    # Test: Chunk-boundary invariance of the splitter, by brute force.
    # Situation: `_RICH_STREAM` is fed as one chunk, one character at a
    #   time, and split at every one and every pair of cut points.
    # Expectation: Every split yields the single-chunk outcome, which holds
    #   the four text blocks and the one chart the stream spells out, with
    #   the invalid chart counted as rejected.
    stream = _RICH_STREAM
    expected = _run_chunks([stream])
    blocks, text, charts, emitted, rejected = expected
    assert [_get_block_kind(block) for block in blocks] == [
        "text",
        "chart",
        "text",
        "text",
        "text",
    ]
    assert text == "Intro\nline.\n\nMid.\n\n```py\nx\n\ny\n```\n\nEnd."
    assert [chart.title for chart in charts] == ["A"]
    assert (emitted, rejected) == (1, 1)

    assert _run_chunks(list(stream)) == expected
    for first in range(len(stream) + 1):
        assert _run_chunks([stream[:first], stream[first:]]) == expected
        for second in range(first, len(stream) + 1):
            chunks = [stream[:first], stream[first:second], stream[second:]]
            assert _run_chunks(chunks) == expected


# One segment of a generated stream: a paragraph, a valid chart, an invalid
# chart, a non-chart code block, or a longer code fence holding a shorter one.
type _Segment = Literal["paragraph", "chart", "invalid", "code", "nested"]

# The block an independent oracle expects: its kind and its Markdown or
# chart title.
type _ExpectedBlock = tuple[Literal["text", "chart"], str]


def _write_segment(segment: _Segment, number: int) -> tuple[str, str]:
    """Returns the stream text of a segment and the text or title it shows."""
    if segment == "paragraph":
        markdown = f"Paragraph {number}\ncontinues."
        return markdown, markdown
    if segment == "code":
        markdown = f"```py\na = {number}\n\nb = {number}\n```"
        return markdown, markdown
    if segment == "nested":
        markdown = f"````md\n```py\na = {number}\n```\n\nb = {number}\n````"
        return markdown, markdown
    if segment == "chart":
        title = f"Chart {number}"
        body = f'{{"kind": "bar", "tables": ["t1"], "title": "{title}"}}'
        return f"```chart\n{body}\n```", title
    return "```chart\n{broken\n```", ""


def _build_case(
    segments: Sequence[_Segment],
    *,
    is_tight: bool,
    has_unclosed_tail: bool,
    has_appended_chart: bool,
) -> tuple[str, list[_ExpectedBlock]]:
    """Writes a stream from segments and the blocks an oracle expects.

    The oracle reads the segments rather than the stream: a paragraph or a
    code block (including a longer fence holding a shorter one) is one text
    block, a valid chart is one chart block until `MAX_CHARTS_PER_TURN`
    charts are shown, an invalid or unclosed chart shows nothing, and an
    appended chart is one chart block at the end. With `is_tight`, a single
    line break separates a chart fence from its neighbors; blank lines
    separate everything else.
    """
    pieces: list[str] = []
    expected: list[_ExpectedBlock] = []
    charts_shown = 0
    for number, segment in enumerate(segments):
        piece, shown = _write_segment(segment, number)
        if pieces:
            touches_chart = segment in ("chart", "invalid") or segments[
                number - 1
            ] in ("chart", "invalid")
            pieces.append("\n" if is_tight and touches_chart else "\n\n")
        pieces.append(piece)
        if segment in ("paragraph", "code", "nested"):
            expected.append(("text", shown))
        elif segment == "chart" and charts_shown < MAX_CHARTS_PER_TURN:
            expected.append(("chart", shown))
            charts_shown += 1
    if has_unclosed_tail:
        pieces.append('\n\n```chart\n{"kind": "line"')
    if has_appended_chart:
        expected.append(("chart", "Appended"))
    return "".join(pieces), expected


def _generate_cases() -> list[tuple[str, list[_ExpectedBlock], bool]]:
    """Generates every stream of one to four segments, with its variants."""
    alphabet: tuple[_Segment, ...] = (
        "paragraph",
        "chart",
        "invalid",
        "code",
        "nested",
    )
    cases: list[tuple[str, list[_ExpectedBlock], bool]] = []
    for length in range(1, 5):
        for segments in itertools.product(alphabet, repeat=length):
            for is_tight, has_tail, has_append in itertools.product(
                (False, True), repeat=3
            ):
                stream, expected = _build_case(
                    segments,
                    is_tight=is_tight,
                    has_unclosed_tail=has_tail,
                    has_appended_chart=has_append,
                )
                cases.append((stream, expected, has_append))
    return cases


def _run_case(
    stream: str, has_appended_chart: bool
) -> tuple[BlockSplitter, _Recorder]:
    """Feeds `stream` in three-character chunks, then appends a chart."""
    splitter, recorder = _split(stream, chunk=3)
    if has_appended_chart:
        splitter.append_chart(_make_line_chart("Appended"))
    return splitter, recorder


def _describe_block(block: SynthesisBlock) -> _ExpectedBlock:
    """Reduces an emitted block to the form the oracle expects."""
    if isinstance(block, TextBlock):
        return ("text", block.markdown)
    return ("chart", block.chart.title)


def test_generated_streams_emit_the_blocks_the_oracle_expects() -> None:
    # Test: The emitted blocks across a generated corpus.
    # Situation: Every stream of one to four paragraph, chart, invalid
    #   chart, and code segments, with tight or blank-line separators, with
    #   or without an unclosed chart at the end, and with or without a chart
    #   appended after `finish`.
    # Expectation: The blocks, in order, are the ones the oracle reads from
    #   the segments.
    for stream, expected, has_append in _generate_cases():
        _, recorder = _run_case(stream, has_append)

        assert [_describe_block(block) for block in recorder.blocks] == (
            expected
        ), stream


def test_generated_streams_number_their_blocks_contiguously() -> None:
    # Test: Block index contiguity across the generated corpus.
    # Situation: The corpus of the previous test.
    # Expectation: The block indexes are 0, 1, ..., one fewer than the
    #   number of blocks the oracle expects, including the appended chart.
    for stream, expected, has_append in _generate_cases():
        _, recorder = _run_case(stream, has_append)

        indexes = [block.index for block in recorder.blocks]
        assert indexes == list(range(len(expected))), stream


def test_generated_streams_join_the_text_of_their_text_blocks() -> None:
    # Test: Text reconstruction across the generated corpus.
    # Situation: The corpus of the previous tests.
    # Expectation: `splitter.text` is the text blocks' Markdown joined by
    #   blank lines, and equals the oracle's text blocks joined the same
    #   way.
    for stream, expected, has_append in _generate_cases():
        splitter, recorder = _run_case(stream, has_append)

        emitted = "\n\n".join(
            block.markdown
            for block in recorder.blocks
            if isinstance(block, TextBlock)
        )
        oracle = "\n\n".join(
            shown for kind, shown in expected if kind == "text"
        )
        assert splitter.text == emitted == oracle, stream


def test_generated_streams_keep_chart_fences_out_of_text_blocks() -> None:
    # Test: Chart fences never reach the reader as text.
    # Situation: The corpus of the previous tests, whose chart, invalid
    #   chart, and unclosed chart segments all open a `chart` fence.
    # Expectation: No text block holds a line that opens a `chart` fence.
    for stream, _, has_append in _generate_cases():
        _, recorder = _run_case(stream, has_append)

        for block in recorder.blocks:
            if isinstance(block, TextBlock):
                assert "```chart" not in block.markdown, stream


def test_a_fence_with_any_info_string_opens_a_code_block() -> None:
    # Test: Info strings outside letters, digits, `_`, and `-`.
    # Situation: A `c++` fence and a fence whose info string has a second
    #   word each hold code with a blank line inside it, and a chart block
    #   follows each.
    # Expectation: Each code block, blank line included, is one text block,
    #   and both chart blocks are resolved rather than read as code.
    text = (
        "```c++\nint x;\n\nint y;\n```\n\n"
        f"```chart\n{_CHART}\n```\n\n"
        '```python title="a.py"\nx = 1\n\ny = 2\n```\n\n'
        f"```chart\n{_CHART}\n```"
    )

    splitter, recorder = _split(text)

    assert list(splitter.text_blocks) == [
        "```c++\nint x;\n\nint y;\n```",
        '```python title="a.py"\nx = 1\n\ny = 2\n```',
    ]
    assert [_get_block_kind(block) for block in recorder.blocks] == [
        "text",
        "chart",
        "text",
        "chart",
    ]
    assert splitter.charts_rejected == 0


@pytest.mark.parametrize(
    "title",
    ["a ```b", 'say \\"```\\" twice ```'],
    ids=["fence_mark_in_a_title", "fence_mark_after_an_escaped_quote"],
)
def test_a_fence_mark_inside_a_json_string_does_not_close_a_chart(
    title: str,
) -> None:
    # Test: Backticks inside a JSON string value of a chart block.
    # Situation: A chart whose title holds a fence mark, once after an
    #   escaped quote, is followed by a valid chart and a paragraph.
    # Expectation: The mark is part of the first body, both charts are
    #   resolved, none is rejected, and no text block holds chart JSON.
    first = '{"kind": "line", "tables": ["t1"], "title": "' + title + '"}'
    json.loads(first)
    text = f"```chart\n{first}\n```\n\n```chart\n{_CHART}\n```\n\nAfter."

    splitter, recorder = _split(text)

    assert [spec.title for spec in recorder.specs] == [
        json.loads(first)["title"],
        "Population",
    ]
    assert splitter.charts_emitted == 2
    assert splitter.charts_rejected == 0
    assert list(splitter.text_blocks) == ["After."]


def test_an_unterminated_string_ends_with_its_line() -> None:
    # Test: A chart body that leaves a JSON string open.
    # Situation: A chart body line opens a string it never closes, and the
    #   next line is a closing fence followed by a paragraph.
    # Expectation: The closing fence still closes the block, the invalid
    #   chart is rejected, and the paragraph is kept as text.
    text = 'Before.\n\n```chart\n{"kind": "line", "title": "abc\n```\n\nAfter.'

    splitter, _ = _split(text)

    assert list(splitter.text_blocks) == ["Before.", "After."]
    assert splitter.charts_emitted == 0
    assert splitter.charts_rejected == 1


def test_a_chart_fence_inside_a_line_stays_in_the_text() -> None:
    # Test: The CommonMark rule that a fence stands on a line of its own.
    # Situation: A chart fence, body, and closing fence are written inside
    #   a line of prose.
    # Expectation: The line is a text block, no chart is parsed, and none
    #   is rejected.
    inline = f"Lead-in ```chart {_CHART}``` trailing."

    splitter, recorder = _split(f"{inline}\n\nAfter.")

    assert list(splitter.text_blocks) == [inline, "After."]
    assert recorder.specs == []
    assert splitter.charts_rejected == 0


def test_only_a_bare_fence_line_closes_a_chart_block() -> None:
    # Test: Fence lines inside an open chart block.
    # Situation: A chart body is followed by a line that opens another
    #   chart and a line with text after its backticks, before the bare
    #   fence that closes the block.
    # Expectation: Both lines are part of the body, so the one block is
    #   rejected, and no text block holds chart JSON.
    text = (
        f"```chart\n{_CHART}\n```chart\n{_CHART}\n``` not a close\n```\n\n"
        "After."
    )

    splitter, recorder = _split(text)

    assert [_get_block_kind(block) for block in recorder.blocks] == ["text"]
    assert list(splitter.text_blocks) == ["After."]
    assert splitter.charts_rejected == 1


def test_a_tilde_chart_fence_is_a_chart_block() -> None:
    # Test: A chart block fenced with tildes.
    # Situation: A `~~~chart` block closes with `~~~`; a `~~~ chart` block
    #   holds a backtick fence line in its body and closes with `~~~`; a
    #   backtick chart block and a paragraph follow.
    # Expectation: The first tilde block is resolved. The backtick line
    #   belongs to the second tilde block's body, so that block is rejected
    #   as invalid JSON. The backtick block is resolved, and no text block
    #   holds chart JSON.
    text = (
        f"~~~chart\n{_CHART}\n~~~\n\n"
        f"~~~ chart\n{_CHART}\n```\n~~~\n\n"
        f"```chart\n{_CHART}\n```\n\nAfter."
    )

    splitter, recorder = _split(text)

    assert [_get_block_kind(block) for block in recorder.blocks] == [
        "chart",
        "chart",
        "text",
    ]
    assert splitter.charts_rejected == 1
    assert list(splitter.text_blocks) == ["After."]


def test_a_tilde_chart_fence_may_hold_backticks_in_its_info_string() -> None:
    # Test: A tilde chart fence whose info string holds backticks.
    # Situation: A `~~~chart` fence line ends with a backticked word, which
    #   CommonMark allows after a tilde fence but not a backtick one, and a
    #   paragraph follows the block.
    # Expectation: The block is resolved as a chart, and the paragraphs
    #   before and after it are the only text blocks, so the chart's JSON
    #   never reaches the reader.
    text = f"Before.\n\n~~~chart `title`\n{_CHART}\n~~~\n\nAfter."

    splitter, recorder = _split(text)

    assert [_get_block_kind(block) for block in recorder.blocks] == [
        "text",
        "chart",
        "text",
    ]
    assert splitter.charts_rejected == 0
    assert list(splitter.text_blocks) == ["Before.", "After."]


def test_crlf_streams_parse_chart_fences_and_paragraphs() -> None:
    # Test: Carriage-return/line-feed normalization in `BlockSplitter`.
    # Situation: `_RICH_STREAM` with `\r\n` line endings and a trailing `\r` is
    #   fed both in one piece and one character at a time so every `\r\n` pair
    #   splits across chunks.
    # Expectation: Both runs produce the exact block sequence, text, and chart
    #   counts of the `\n` stream, with no stray `\r` in emitted Markdown.
    expected = _run_chunks([_RICH_STREAM])
    crlf_stream = _RICH_STREAM.replace("\n", "\r\n") + "\r"

    assert _run_chunks([crlf_stream]) == expected
    assert _run_chunks(list(crlf_stream)) == expected
