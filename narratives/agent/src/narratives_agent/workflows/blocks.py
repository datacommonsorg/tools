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
"""Splits the streamed synthesis answer into text and chart blocks.

`BlockSplitter` turns the streamed Markdown into interleaved `TextBlock` and
`ChartBlock` items as the text arrives, resolving each fenced `chart` block
through a caller-supplied `ChartResolver`.
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import ValidationError

from narratives_agent.workflows.charts import (
    MAX_CHARTS_PER_TURN,
    ChartSpecification,
    ResolvedChart,
    parse_chart_specification,
)

__all__ = [
    "BlockCallback",
    "BlockSplitter",
    "ChartBlock",
    "ChartResolver",
    "SynthesisBlock",
    "TextBlock",
]

logger = logging.getLogger(__name__)

# Info string on fenced code blocks that carry chart specifications.
_CHART_FENCE_TAG = "chart"
# Matches a Markdown code fence line with any leading whitespace, capturing
# the fence characters and the first word of its info string, which is empty
# on a bare fence. As in CommonMark, a backtick fence's info string holds no
# backtick, while a tilde fence's may hold any character.
_FENCE_LINE = re.compile(
    r"^\s*(?:(?P<backticks>`{3,})\s*(?P<backtick_info>[^\s`]*)(?:\s[^`]*)?"
    r"|(?P<tildes>~{3,})\s*(?P<tilde_info>\S*)(?:\s.*)?)$"
)


@dataclass(frozen=True)
class TextBlock:
    """One completed Markdown paragraph or fenced block from synthesis.

    Attributes:
        index: The block's position among all emitted blocks, from 0.
        markdown: The block's Markdown, stripped of surrounding whitespace.
    """

    index: int
    markdown: str


@dataclass(frozen=True)
class ChartBlock:
    """One resolved chart block emitted during or after synthesis.

    Attributes:
        index: The block's position among all emitted blocks, from 0.
        chart: The resolved chart.
    """

    index: int
    chart: ResolvedChart


# A block a `BlockSplitter` emits: a paragraph or a resolved chart.
type SynthesisBlock = TextBlock | ChartBlock
# Receives each block a `BlockSplitter` emits.
type BlockCallback = Callable[[SynthesisBlock], None]
# Resolves a parsed chart block, or returns None to reject it.
type ChartResolver = Callable[[ChartSpecification], ResolvedChart | None]


@dataclass
class _ChartFence:
    """An open chart block.

    Attributes:
        char: The fence character that opened it, which closes it.
        body: The block's lines so far.
    """

    char: str
    body: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _CodeFence:
    """An open fenced block that is not a chart, kept in the prose.

    Attributes:
        char: The fence character that opened it, which closes it.
        length: How many fence characters opened it; as in CommonMark, only
            a bare fence of at least this many characters closes it.
    """

    char: str
    length: int


@dataclass
class BlockSplitter:
    """Splits the synthesis stream into text and chart blocks as it arrives.

    Feed the stream's text deltas to `feed` and call `finish` once the
    stream ends; a splitter reads one stream. Outside a fenced block, prose
    is split into paragraphs at blank lines, so a list or a table without
    internal blank lines stays in one block; inside a fenced block that is
    not a chart, blank lines are kept. A chart block opens on a line that is
    only a fence with the `chart` info string, which ends the paragraph
    before it, and closes on a line that is only a bare fence. A JSON string
    cannot span lines, so no line of a chart body is a bare fence. When the
    block closes, its body is parsed as a `ChartSpecification` and resolved.
    A body that is not valid JSON, does not match the grammar, or fails
    resolution is dropped and counted in `charts_rejected`, as is a fence
    still open when the stream ends, so a chart block never reaches the
    reader as text. A chart fence line inside a code block the model left
    open ends that code block, which is emitted as text, and opens the chart
    block. A chart fence written inside a line of prose is not a chart block
    and stays in the text.
    Backtick and tilde fences are recognized with any leading whitespace, so
    an over-indented fence never leaks raw JSON into prose. As in CommonMark,
    a code block closes only on a bare fence of its opening character that is
    at least as long as its opening fence, so a longer fence that holds a
    shorter one stays in one text block; a chart block closes on a bare fence
    of its opening character of any length.

    Attributes:
        on_block: Receives each completed `TextBlock` or `ChartBlock`.
        resolve_chart: Resolves a parsed specification, or returns None.
        charts_rejected: How many chart blocks were dropped.
    """

    on_block: BlockCallback
    resolve_chart: ChartResolver
    charts_rejected: int = field(default=0, init=False)
    _text_blocks: list[str] = field(
        default_factory=list, init=False, repr=False
    )
    _charts: list[ResolvedChart] = field(
        default_factory=list, init=False, repr=False
    )
    _pending: str = field(default="", init=False, repr=False)
    _paragraph: list[str] = field(default_factory=list, init=False, repr=False)
    _open: _ChartFence | _CodeFence | None = field(
        default=None, init=False, repr=False
    )
    _next_index: int = field(default=0, init=False, repr=False)
    _finished: bool = field(default=False, init=False, repr=False)

    @property
    def text_blocks(self) -> tuple[str, ...]:
        """The text blocks emitted so far."""
        return tuple(self._text_blocks)

    @property
    def charts(self) -> tuple[ResolvedChart, ...]:
        """The resolved charts emitted so far."""
        return tuple(self._charts)

    @property
    def charts_emitted(self) -> int:
        """How many chart blocks were emitted."""
        return len(self._charts)

    @property
    def text(self) -> str:
        """The answer text: the text blocks joined by blank lines."""
        return "\n\n".join(self._text_blocks)

    def feed(self, delta: str) -> None:
        """Consumes one text delta, emitting every block it completes.

        A line is processed once its newline arrives, so the result does not
        depend on where the stream splits its deltas.

        Args:
            delta: The next piece of the streamed answer text.

        Returns:
            None. Completed blocks are passed to `on_block`.

        Raises:
            RuntimeError: If `finish` was already called; a splitter reads
                one stream.
        """
        if self._finished:
            raise RuntimeError(
                "BlockSplitter.feed() was called after finish()."
            )
        self._pending += delta
        *lines, self._pending = self._pending.split("\n")
        for line in lines:
            self._consume_line(line.removesuffix("\r"))

    def finish(self) -> None:
        """Flushes the buffered text once the stream has ended.

        Processes the last line, drops a chart fence that is still open and
        counts it in `charts_rejected`, and emits the last paragraph. After
        it, `feed` raises and a second `finish` does nothing, while
        `append_chart` may still add server-supplied charts.

        Returns:
            None. Completed blocks are passed to `on_block`.
        """
        if self._finished:
            return
        self._finished = True
        if self._pending:
            self._consume_line(self._pending.removesuffix("\r"))
            self._pending = ""
        if isinstance(self._open, _ChartFence):
            # The stream ended inside a chart block, so the block is dropped
            # rather than shown to the reader as raw JSON.
            self.charts_rejected += 1
        self._open = None
        self._flush_paragraph()

    def append_chart(self, chart: ResolvedChart) -> None:
        """Emits a chart the server supplied, such as a default chart.

        The chart takes the next block index and is not subject to
        `MAX_CHARTS_PER_TURN`; the caller bounds the charts it appends.

        Args:
            chart: The resolved chart to emit.

        Returns:
            None. The chart block is passed to `on_block`.
        """
        self._charts.append(chart)
        self._emit(ChartBlock(index=self._next_index, chart=chart))

    def _consume_line(self, line: str) -> None:
        """Routes one complete line to the open fence or the paragraph."""
        fence = _FENCE_LINE.fullmatch(line)
        if fence is None:
            self._consume_plain_line(line)
            return
        if fence["backticks"]:
            char, info = "`", fence["backtick_info"].lower()
            length = len(fence["backticks"])
        else:
            char, info = "~", fence["tilde_info"].lower()
            length = len(fence["tildes"])
        match self._open:
            case _ChartFence() as chart:
                # A closing fence carries no info string and repeats the
                # opening character; any other fence line is body.
                if not info and char == chart.char:
                    self._close_chart(chart)
                else:
                    chart.body.append(line)
            case _CodeFence() as code:
                if info == _CHART_FENCE_TAG:
                    # The model left the code block open; it is emitted as
                    # it stands so that the chart's JSON stays out of it.
                    self._open_chart(char)
                    return
                self._paragraph.append(line)
                if not info and char == code.char and length >= code.length:
                    self._open = None
            case None:
                if info == _CHART_FENCE_TAG:
                    self._open_chart(char)
                    return
                self._paragraph.append(line)
                self._open = _CodeFence(char, length)

    def _consume_plain_line(self, line: str) -> None:
        """Adds a line that is not a fence to the open block or paragraph.

        Outside a fenced block, a blank line ends the paragraph.
        """
        match self._open:
            case _ChartFence() as chart:
                chart.body.append(line)
            case _CodeFence():
                self._paragraph.append(line)
            case None:
                if line.strip():
                    self._paragraph.append(line)
                else:
                    self._flush_paragraph()

    def _open_chart(self, char: str) -> None:
        """Ends the current paragraph and opens a chart block."""
        self._flush_paragraph()
        self._open = _ChartFence(char)

    def _close_chart(self, chart: _ChartFence) -> None:
        """Resolves a closed chart block and emits or counts its chart."""
        self._open = None
        self._accept_chart_body("\n".join(chart.body))

    def _accept_chart_body(self, body: str) -> None:
        """Resolves a chart block body and emits or counts its chart."""
        chart = self._resolve(body)
        if chart is None:
            self.charts_rejected += 1
            return
        self._charts.append(chart)
        self._emit(ChartBlock(index=self._next_index, chart=chart))

    def _resolve(self, body: str) -> ResolvedChart | None:
        """Parses and resolves a chart fence body, or returns None.

        A validation failure is logged by its error count only, so the
        model's raw JSON is never written to the log.
        """
        if len(self._charts) >= MAX_CHARTS_PER_TURN:
            logger.info(
                "Chart block dropped: the answer already holds %d charts",
                MAX_CHARTS_PER_TURN,
            )
            return None
        try:
            spec = parse_chart_specification(body)
        except ValidationError as error:
            logger.info(
                "Chart block rejected: %d validation errors",
                error.error_count(),
            )
            return None
        return self.resolve_chart(spec)

    def _flush_paragraph(self) -> None:
        """Emits the buffered paragraph as a text block, unless it is blank."""
        text = "\n".join(self._paragraph).strip()
        self._paragraph = []
        if not text:
            return
        self._text_blocks.append(text)
        self._emit(TextBlock(index=self._next_index, markdown=text))

    def _emit(self, block: SynthesisBlock) -> None:
        """Passes a block to `on_block` and advances the block index."""
        self.on_block(block)
        self._next_index += 1
