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
 * @fileoverview Renders an answer's citations: variable, provider, dataset,
 * range, link.
 */

import {
  citationAnchorId,
  displayCitationNumber,
  getCitationVariableLabel,
} from '@/src/components/chip_citation';
import type { ProvenanceItem } from '@/src/hooks/use_sse_chat';

/**
 * Figma node 3427-16738 (section heading) + 3427-16739 ("Body" with the
 * numbered list).
 *
 * Each row receives the id the inline CitationChips anchor to, scoped per turn
 * so two answers citing one source do not both claim the same anchor.
 */

/** The attribution every citation carries. */
const PROCESSING_NOTE = 'with minor processing by Data Commons';

/** Separates the items of one citation row. */
const CITATION_ITEM_SEPARATOR = ', ';

/** Section heading. */
const CITATIONS_HEADING = 'Citations';

interface CitationsListProps {
  sources: ProvenanceItem[];
  /** Display label for each position; defaults to the position itself. */
  numbers?: number[];
  /** Which turn these sources belong to, so the anchors stay unique. */
  turnIndex?: number;
}

/**
 * The prose part of a citation: variable, publisher, dataset, years, joined
 * by {@link CITATION_ITEM_SEPARATOR}. Each piece is dropped when the data
 * plane did not report it.
 */
export function citationLead(source: ProvenanceItem): string {
  const url = source.url.trim();
  const parts = [source.provider, source.dataset || source.name]
    .map((part) => part?.trim() ?? '')
    // A name that fell back to the URL is already shown by the link itself.
    .filter((part) => part !== '' && part !== url);
  // The two fields are often the same string; saying it twice reads as a bug.
  const unique = parts.filter((part, index) => parts.indexOf(part) === index);
  const dateRange = source.dateRange ? `(${source.dateRange})` : '';
  return [getCitationVariableLabel(source), ...unique, dateRange]
    .filter((part) => part !== '')
    .join(CITATION_ITEM_SEPARATOR);
}

/** Numbered list of citations matching the [n] chips in the answer. */
export function CitationsList({
  sources,
  numbers,
  turnIndex,
}: CitationsListProps) {
  if (!sources || sources.length === 0) return null;

  // `my-6` adds to the answer card's flex gap, setting the citations apart
  // from the answer above and the disclaimer below.
  return (
    <section
      aria-labelledby={`citations-heading-${turnIndex ?? 0}`}
      className="my-6"
    >
      <h2
        id={`citations-heading-${turnIndex ?? 0}`}
        className="text-title-large-emphasized text-on-surface mb-6"
      >
        {CITATIONS_HEADING}
      </h2>
      <ol className="list-none p-0 m-0 flex flex-col gap-1.5 text-body-large text-on-surface">
        {sources.map((source, index) => {
          const shown = displayCitationNumber(index + 1, numbers);
          const lead = citationLead(source);
          return (
            <li
              key={`${source.url}-${index}`}
              id={citationAnchorId(turnIndex, shown)}
              className="flex items-baseline gap-1.5"
            >
              <span aria-hidden="true">[{shown}]</span>
              {/* Long dataset names and URLs often have no spaces; allow them
                  to break mid-string. `min-w-0` lets this flex child
                  shrink below its content width instead of overflowing. */}
              <span className="min-w-0 wrap-anywhere leading-5.5">
                {lead && `${lead}${CITATION_ITEM_SEPARATOR}`}
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-theme-primary underline"
                >
                  {source.url}
                </a>
                {CITATION_ITEM_SEPARATOR}
                {PROCESSING_NOTE}
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
