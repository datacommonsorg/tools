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
"""Parses the Data gaps block that closes a synthesis answer.

The synthesis contract (`contracts/synthesis.md`, "Caveats and missing data")
has the model end an answer that could not cover every requested measure with
a `**Data gaps**` label line, one introducing line, and a bulleted list of the
missing measures. `DataGapsCollector` reads that block line by line and
returns it as a `DataGaps`, so the app renders the list from typed data and
does not parse Markdown.
"""

import re
from dataclasses import dataclass, field

__all__ = ["DataGaps", "DataGapsCollector", "is_data_gaps_label"]

# Matches the label line. The contract asks for `**Data gaps**\`; the other
# forms accepted are ones a model writes in its place: a `## ` heading, a
# colon inside or after the bold, no bold, and any letter case.
_LABEL_LINE = re.compile(
    r"(?:#{1,6}[ \t]+)?(?:\*\*|__)?data gaps:?(?:\*\*|__)?:?[ \t]*\\?",
    re.IGNORECASE,
)
# Matches the marker that opens a bulleted or numbered list item.
_ITEM_MARKER = re.compile(r"\s*(?:[-*+]|\d+[.)])\s+")
# Citation markers such as `[1]` or `[1, 2]`.
_CITATIONS = re.compile(r"\s*\[\d+(?:\s*,\s*\d+)*\]")
# A backslash escape, whose character is captured, a backslash that ends a
# line as a hard break, or an emphasis or code mark.
_ESCAPE_OR_MARK = re.compile(r"\\([^\w\s])|\\(?=\s|$)|[*_`]")


def is_data_gaps_label(line: str) -> bool:
    """Returns whether a line is the label that opens a Data gaps block.

    Args:
        line: One complete line of the synthesis output.

    Returns:
        True when the line holds only the Data gaps label.
    """
    return _LABEL_LINE.fullmatch(line.strip()) is not None


def _clean(text: str) -> str:
    """Returns `text` as plain text on one line.

    Removes citation markers, emphasis and code marks, and hard-break
    backslashes, replaces a backslash escape with the character it escapes,
    and collapses whitespace.
    """
    text = _ESCAPE_OR_MARK.sub(
        lambda match: match[1] or "", _CITATIONS.sub("", text)
    )
    return " ".join(text.split())


@dataclass(frozen=True)
class DataGaps:
    """The measures an answer could not cover, as plain text.

    Attributes:
        intro: The line that introduces the list, or `""` when the model
            wrote none.
        items: The missing measures, one per list item, in the order
            written. It is never empty.
    """

    intro: str
    items: tuple[str, ...]


@dataclass
class DataGapsCollector:
    """Collects the lines of one Data gaps block, from its label line on.

    Pass each line after the label to `add` until it returns False, which
    means the line belongs to the text after the block, or until the stream
    ends. The lines before the first list item form the intro. A line that
    opens with a list marker starts an item, and a line without a marker
    directly under an item continues that item. Blank lines between the
    label, the intro, and the items are part of the block. A line without a
    marker that follows a blank line ends the block, unless only the label
    has been read.

    Attributes:
        lines: The block's lines as written, starting with the label line.
    """

    lines: list[str]
    _intro: list[str] = field(default_factory=list, init=False, repr=False)
    _items: list[str] = field(default_factory=list, init=False, repr=False)
    _is_after_blank: bool = field(default=False, init=False, repr=False)

    def add(self, line: str) -> bool:
        """Adds the next line to the block when it is part of it.

        Args:
            line: The next complete line of the synthesis output, which is
                not a code fence or a Markdown heading.

        Returns:
            True when the line was added, or False when it ends the block
            and belongs to the text after it.
        """
        stripped = line.strip()
        if not stripped:
            self._is_after_blank = True
            self.lines.append(line)
            return True
        marker = _ITEM_MARKER.match(line)
        if marker is not None:
            self._items.append(line[marker.end() :])
        elif self._is_after_blank and (self._intro or self._items):
            return False
        elif self._items:
            self._items[-1] = f"{self._items[-1]} {stripped}"
        else:
            self._intro.append(stripped)
        self._is_after_blank = False
        self.lines.append(line)
        return True

    def build(self) -> DataGaps | None:
        """Returns the block read so far, or None when it lists no measure.

        Returns:
            The cleaned intro and items, or `None` when no list item holds
            text, in which case the lines are ordinary answer text.
        """
        items = tuple(
            cleaned for item in self._items if (cleaned := _clean(item))
        )
        if not items:
            return None
        return DataGaps(intro=_clean(" ".join(self._intro)), items=items)
