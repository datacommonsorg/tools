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
 * @fileoverview Renders an answer's citations: provider, dataset, range, link.
 */

import type { ProvenanceItem } from "../hooks/use_sse_chat";

/**
 * Figma node 3427-16738 (section heading) + 3427-16739 ("Body" with the
 * numbered list).
 *
 * Each row receives id="source-N" so inline CitationChips can anchor.
 */

const COLOR_TITLE = "var(--color-on-surface)";
const COLOR_BODY = "var(--color-on-surface)";
const COLOR_LINK = "var(--color-brand-primary)";
const FONT_STACK =
  '"Google Sans Text", "Google Sans", Inter, system-ui, sans-serif';

/** The attribution every citation carries. */
const PROCESSING_NOTE = "with minor processing by Data Commons";

/** Section heading. */
const CITATIONS_HEADING = "Citations";

interface CitationsListProps {
  sources: ProvenanceItem[];
}

/** Strips the scheme and any trailing slash, so the link reads as a reference. */
export function citationUrlLabel(url: string): string {
  return url.replace(/^[a-z]+:\/\//i, "").replace(/\/+$/, "");
}

/**
 * The prose part of a citation: publisher, dataset, years. Each piece is
 * dropped when the data plane did not report it.
 */
export function citationLead(source: ProvenanceItem): string {
  const url = source.url.trim();
  const parts = [source.provider, source.dataset || source.name]
    .map((part) => part?.trim() ?? "")
    // A name that fell back to the URL is already shown by the link itself.
    .filter((part) => part !== "" && part !== url);
  // The two fields are often the same string; saying it twice reads as a bug.
  const unique = parts.filter((part, index) => parts.indexOf(part) === index);
  const lead = unique.join(", ");
  if (!source.dateRange) return lead;
  return lead ? `${lead} (${source.dateRange})` : `(${source.dateRange})`;
}

/** Numbered list of citations matching the [n] chips in the answer. */
export function CitationsList({ sources }: CitationsListProps) {
  if (!sources || sources.length === 0) return null;

  // No top margin: the answer card's flex gap and the heading's padding
  // already space this, and a margin stacked on both.
  return (
    <section aria-labelledby="citations-heading">
      <h2
        id="citations-heading"
        className="font-medium"
        style={{
          fontFamily: '"Google Sans", "Google Sans Text", sans-serif',
          fontSize: 22,
          lineHeight: "28px",
          color: COLOR_TITLE,
          fontWeight: 500,
          margin: 0,
          paddingTop: 12,
        }}
      >
        {CITATIONS_HEADING}
      </h2>
      <ol
        className="list-none p-0 m-0 mt-2 flex flex-col gap-1"
        style={{
          fontFamily: FONT_STACK,
          fontSize: 16,
          lineHeight: "24px",
          fontWeight: 500,
          color: COLOR_BODY,
        }}
      >
        {sources.map((source, index) => {
          const position = index + 1;
          const lead = citationLead(source);
          return (
            <li
              key={`${source.url}-${index}`}
              id={`source-${position}`}
              className="flex items-baseline gap-1.5"
            >
              <span aria-hidden="true">[{position}]</span>
              {/* Long dataset names and URLs often have no spaces; allow them
                  to break mid-string. `minWidth: 0` lets this flex child
                  shrink below its content width instead of overflowing. */}
              <span
                style={{
                  minWidth: 0,
                  overflowWrap: "anywhere",
                  wordBreak: "break-word",
                }}
              >
                {lead && `${lead} `}(
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:underline"
                  style={{ color: COLOR_LINK }}
                >
                  {citationUrlLabel(source.url)}
                </a>
                ){", "}
                {PROCESSING_NOTE}
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
