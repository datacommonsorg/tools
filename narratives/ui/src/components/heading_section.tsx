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
 * @fileoverview Renders an answer's lead-in line as the heading of the section it opens.
 */

/**
 * Matches a lead-in line: one line, not a heading, quote, list item, or table
 * row, that ends with a colon (optionally inside bold or italics). The
 * agent's `_LEAD_IN_LINE` in `workflows/blocks.py` matches the same lines.
 */
const LEAD_IN_LINE = /^(?![#>|]|[-*+]\s|\d+[.)]\s)[^\n]*:[*_]*$/;

/** Matches the emphasis markers and colon around a lead-in line's label. */
const LEAD_IN_WRAPPING = /^[*_]+|[*_]*:[*_]*$/g;

/**
 * Matches inline Markdown, a backslash escape, an HTML entity, or a citation
 * marker in a label. The heading renders its label as plain text, so a label
 * holding any of them stays a text block.
 */
const INLINE_MARKUP = /[*_`[\]<>\\]|&[#\w]+;/;

/** Matches a letter or a digit, which a label needs to name its section. */
const LABEL_CHARACTER = /[\p{L}\p{N}]/u;

/**
 * Typography of a section heading: a placeholder style, kept distinct from
 * the body text so a section heading is easy to tell apart.
 */
const SECTION_HEADING_CLASS =
  'text-section-heading text-theme-primary wrap-break-word';

/**
 * Returns the label of a lead-in line: its text without the closing colon or
 * the bold or italic markers around it.
 */
export function readLeadInLabel(markdown: string): string {
  return markdown.trim().replace(LEAD_IN_WRAPPING, '').trim();
}

/**
 * Whether `markdown` renders as a section heading: a one-line lead-in that
 * ends with a colon, whose label holds a letter or digit and no inline
 * Markdown or citation marker.
 */
export function isLeadInHeading(markdown: string): boolean {
  if (!LEAD_IN_LINE.test(markdown.trim())) return false;
  const label = readLeadInLabel(markdown);
  return LABEL_CHARACTER.test(label) && !INLINE_MARKUP.test(label);
}

interface SectionHeadingProps {
  /** The lead-in line, as the model wrote it. */
  markdown: string;
  /** Id that the section it opens points its `aria-labelledby` at. */
  id?: string;
}

/**
 * The heading of an answer section, from the lead-in line that opens it. It
 * is an h2: the answer panel's intro block owns the h1. Callers render only
 * a line that `isLeadInHeading` accepts. The heading is not part of the
 * word-by-word reveal, so it shows at once, as the title and the chart
 * skeletons do.
 */
export function SectionHeading({ markdown, id }: SectionHeadingProps) {
  return (
    <h2 id={id} className={`answer-heading ${SECTION_HEADING_CLASS}`}>
      {readLeadInLabel(markdown)}
    </h2>
  );
}
