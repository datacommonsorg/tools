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
 * @fileoverview Renders an answer's closing list of the measures Data Commons
 * lacks, from the `**Data gaps**` block the synthesis contract
 * (`workflows/contracts/synthesis.md`) asks the model to end with.
 */

import { DATA_GAPS_HEADING } from '@/src/config/copy_chat';

/**
 * Matches the `**Data gaps**\` label that opens the block. Keep it in sync
 * with the label the synthesis contract prescribes. Spaces or tabs around
 * the backslash are allowed, so a Markdown hard break of two trailing spaces
 * matches too; `[ \t]` rather than `\s`, so the match never crosses a line.
 */
export const DATA_GAPS_LABEL = /^\*\*Data gaps\*\*[ \t]*\\?[ \t]*(?:\n|$)/;

/**
 * Matches a `-`, `*`, or `+` bullet's marker. The contract asks for a
 * bulleted list of plain measure names, so a numbered line reads as intro
 * text and inline Markdown in an item renders as written.
 */
const BULLET_MARKER = /^\s*[-*+]\s+/;

interface DataGapsSectionProps {
  /** Id of the heading, which labels the section. */
  id: string;
  /** The block as the model wrote it, label included. */
  markdown: string;
}

/**
 * Renders the block as a titled section after the answer: the heading, the
 * intro line, and a bulleted list of the missing measures. The panel hides
 * it until the answer's reveal ends, as it does the citations.
 */
export function DataGapsSection({ id, markdown }: DataGapsSectionProps) {
  const lines = markdown
    .replace(DATA_GAPS_LABEL, '')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
  const intro = lines.filter((line) => !BULLET_MARKER.test(line));
  const items = lines
    .filter((line) => BULLET_MARKER.test(line))
    .map((line) => line.replace(BULLET_MARKER, ''));
  return (
    <section aria-labelledby={id} className="mt-6">
      <h2 id={id} className="text-title-large-emphasized text-on-surface mb-2">
        {DATA_GAPS_HEADING}
      </h2>
      {intro.length > 0 && (
        <p className="m-0 mb-2 text-body-medium text-on-surface">
          {intro.join(' ')}
        </p>
      )}
      {items.length > 0 && (
        <ul className="list-disc ml-6 flex flex-col gap-1 text-body-medium text-on-surface">
          {items.map((item, index) => (
            <li
              key={`${item}-${index}`}
              className="min-w-0 wrap-anywhere leading-5"
            >
              {item}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
