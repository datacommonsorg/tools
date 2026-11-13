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
"""Takes the answer title off the start of the synthesis stream.

When the turn has data, the synthesis model is told (`title_directive`) to
open its answer with one title line, `# ` followed by a short label for the
data the answer presents. `TitleExtractor` sits in front of the block
splitter: it holds the stream until the first non-blank line is complete,
takes that line off when it is a title line, and forwards everything else
unchanged, so the title never reaches the answer text or the signed
transcript. A turn without data gets no title, even when the model writes
one.
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field

__all__ = [
    "MAX_TITLE_CHARS",
    "MAX_TITLE_WORDS",
    "NO_TITLE_DIRECTIVE",
    "TITLE_DIRECTIVE",
    "TitleExtractor",
    "clean_title",
    "parse_title_line",
    "title_directive",
]

logger = logging.getLogger(__name__)

# Upper bounds past which a title line is dropped rather than shown. The
# prompt asks for 3 to 10 words; the slack tolerates a long place name, while
# a line past these bounds is a sentence, not a label.
MAX_TITLE_WORDS = 12
MAX_TITLE_CHARS = 100

# Code-owned output format appended to the synthesis system instruction. The
# editorial rules for the title's wording live in the configured synthesis
# prompt (`defaults/prompts/synthesis.md`, "Title rules").
TITLE_DIRECTIVE = (
    "### Title line\n\n"
    "This answer presents statistics, so its first line is its title: `# ` "
    "followed by a plain noun phrase of 3 to 10 words, written to the Title "
    "rules. Leave a blank line after it, then write the answer. Write no "
    "other heading."
)
NO_TITLE_DIRECTIVE = (
    "### Title line\n\n"
    "This answer presents no statistics, so write no title: begin directly "
    "with the answer."
)

# A Markdown ATX heading of any level, with optional closing hashes.
_HEADING_LINE = re.compile(r"#{1,6}[ \t]+(?P<title>.+?)(?:[ \t]+#+)?")
# A line that is bold from end to end.
_BOLD_LINE = re.compile(r"\*\*(?P<title>[^*]+)\*\*")
# A leading "Title:" label, bold or plain.
_TITLE_LABEL = re.compile(r"(?:\*\*)?title[ \t]*:[ \t]*(?:\*\*)?[ \t]*", re.I)
# Citation markers such as `[1]` or `[1, 2]`.
_CITATIONS = re.compile(r"\s*\[\d+(?:\s*,\s*\d+)*\]")
# Inline Markdown emphasis and code marks.
_EMPHASIS = re.compile(r"[*_`]")
# Characters trimmed from both ends of a title.
_TRIMMED = " \t\"'\u201c\u201d\u2018\u2019.,:;!?"


def title_directive(has_data: bool) -> str:
    """Returns the title format directive for a turn.

    Args:
        has_data: Whether the turn's digest holds computed data.

    Returns:
        `TITLE_DIRECTIVE` when the turn has data, else `NO_TITLE_DIRECTIVE`.
    """
    return TITLE_DIRECTIVE if has_data else NO_TITLE_DIRECTIVE


def parse_title_line(line: str) -> str | None:
    """Returns the raw title a line carries, or None when it is not one.

    A title line is a Markdown heading, a line that is bold from end to end,
    or a line that starts with a "Title:" label. The model is asked for the
    first form; the others are common slips that still carry a title.

    Args:
        line: One complete line of the synthesis output.

    Returns:
        The line's title text before cleaning, or `None`.
    """
    stripped = line.strip()
    if match := _HEADING_LINE.fullmatch(stripped):
        return match["title"]
    if match := _BOLD_LINE.fullmatch(stripped):
        return match["title"]
    if match := _TITLE_LABEL.match(stripped):
        return stripped[match.end() :]
    return None


def clean_title(raw: str) -> str | None:
    """Cleans a raw title, or returns None when it is not usable.

    Removes a leading "Title:" label, citation markers, emphasis marks, and
    surrounding quotes and punctuation, and collapses whitespace.

    Args:
        raw: The title text taken from a title line.

    Returns:
        The cleaned title, or `None` when it is empty or longer than
        `MAX_TITLE_WORDS` words or `MAX_TITLE_CHARS` characters.
    """
    text = _TITLE_LABEL.sub("", raw.strip(), count=1)
    text = _EMPHASIS.sub("", _CITATIONS.sub("", text))
    text = " ".join(text.split()).strip(_TRIMMED)
    if not text:
        return None
    if len(text) > MAX_TITLE_CHARS or len(text.split()) > MAX_TITLE_WORDS:
        logger.info(
            "Title dropped: %d words, %d characters",
            len(text.split()),
            len(text),
        )
        return None
    return text


@dataclass
class TitleExtractor:
    """Takes the title line off the start of the synthesis stream.

    Feed the stream's text deltas to `feed` and call `finish` once the
    stream ends. The extractor holds text only until the first non-blank
    line is complete, which the block splitter would buffer anyway, so it
    adds no delay. A title line is removed from the stream whether or not it
    is accepted; any other first line is forwarded with the rest.

    Attributes:
        forward: Receives the stream text that follows the title line, or the
            whole stream when it does not open with one.
        on_title: Receives the cleaned title once, when one is accepted.
        accept: Whether the turn may carry a title; `False` drops any title
            line the model writes.
        title: The accepted title, or `None`.
    """

    forward: Callable[[str], None]
    on_title: Callable[[str], None]
    accept: bool
    title: str | None = field(default=None, init=False)
    _buffer: str = field(default="", init=False, repr=False)
    _decided: bool = field(default=False, init=False, repr=False)

    def feed(self, delta: str) -> None:
        """Consumes one text delta of the synthesis stream.

        Args:
            delta: The next piece of the streamed answer text.
        """
        if self._decided:
            self.forward(delta)
            return
        self._buffer += delta
        self._decide(final=False)

    def finish(self) -> None:
        """Decides on any held text once the stream has ended."""
        if not self._decided:
            self._decide(final=True)

    def _decide(self, *, final: bool) -> None:
        """Takes off or forwards the first line once it is complete."""
        held = self._buffer.lstrip()
        if not held:
            self._decided = final
            return
        line, newline, rest = held.partition("\n")
        if not newline and not final:
            return
        self._decided = True
        self._buffer = ""
        raw = parse_title_line(line.removesuffix("\r"))
        if raw is None:
            if self.accept:
                logger.info("Synthesis wrote no title line")
            self.forward(held)
            return
        title = clean_title(raw)
        if self.accept and title is not None:
            self.title = title
            self.on_title(title)
        elif not self.accept:
            logger.info("Title dropped: the turn has no data")
        if rest:
            self.forward(rest)
