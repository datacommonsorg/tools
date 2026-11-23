/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
 * implied. See the License for the specific language governing
 * permissions and limitations under the License.
 */

/**
 * @fileoverview Renders a section heading the model wrote as the heading of the section it opens.
 */

/**
 * Matches a section heading: one line holding a Markdown ATX heading, such
 * as `## Population by sex`, and captures its label. The agent's
 * `_HEADING_LINE` in `workflows/blocks.py` emits such a line as a block of
 * its own.
 */
const SECTION_HEADING_LINE = /^#{1,6}[ \t]+([^\n]*?)(?:[ \t]+#+)?$/;

/**
 * Matches the emphasis markers around a heading's label and a colon that
 * closes it, which the heading shows without.
 */
const LABEL_WRAPPING = /^[*_]+|[*_]*:?[*_]*$/g;

/**
 * Matches inline Markdown, a backslash escape, an HTML entity, or a citation
 * marker in a label. The heading renders its label as plain text, so a label
 * holding any of them stays a text block.
 */
const INLINE_MARKUP = /[*_`[\]<>\\]|&[#\w]+;/;

/** Matches a letter or a digit, which a label needs to name its section. */
const LABEL_CHARACTER = /[\p{L}\p{N}]/u;

/**
 * Typography of a section heading: the body text color, set apart by its
 * size and weight.
 */
const SECTION_HEADING_CLASS =
  'text-section-heading text-on-surface wrap-break-word';

/**
 * Returns the label of a section heading line: its text without the leading
 * hashes, the bold or italic markers around it, or a closing colon. Returns
 * an empty string when `markdown` is not one heading line.
 */
export function readSectionHeadingLabel(markdown: string): string {
  const label = SECTION_HEADING_LINE.exec(markdown.trim())?.[1] ?? '';
  return label.replace(LABEL_WRAPPING, '').trim();
}

/**
 * Whether `markdown` renders as a section heading: one Markdown heading line
 * whose label holds a letter or digit and no inline Markdown or citation
 * marker. A line that only ends with a colon is text, never a heading.
 */
export function isSectionHeading(markdown: string): boolean {
  const label = readSectionHeadingLabel(markdown);
  return LABEL_CHARACTER.test(label) && !INLINE_MARKUP.test(label);
}

interface SectionHeadingProps {
  /** The heading line, as the model wrote it. */
  markdown: string;
  /** Id that the section it opens points its `aria-labelledby` at. */
  id?: string;
}

/**
 * The heading of an answer section, from the heading line that opens it. It
 * is an h2: the answer panel's intro block owns the h1. Callers render only
 * a line that `isSectionHeading` accepts. The heading is not part of the
 * word-by-word reveal, so it shows at once, as the title and the chart
 * skeletons do.
 */
export function SectionHeading({ markdown, id }: SectionHeadingProps) {
  return (
    <h2 id={id} className={`answer-heading ${SECTION_HEADING_CLASS}`}>
      {readSectionHeadingLabel(markdown)}
    </h2>
  );
}
