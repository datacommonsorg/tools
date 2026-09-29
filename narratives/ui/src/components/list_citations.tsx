/**
 * @fileoverview Renders an answer's citations: provider, dataset, range, link.
 */

import type { ProvenanceItem } from "../hooks/use_sse_chat";

/**
 * Figma node 3427-16738 (section heading) + 3427-16739 ("Body" with the
 * numbered list), retitled "Citations" and moved to the foot of the answer.
 *
 * The heading is "Citations" rather than "Sources" because a reader arriving
 * here is not browsing a list of datasets; they are checking a figure against
 * the place it came from, which is what a citation is for. The same research
 * is why a row spells out its provider, range and dataset instead of showing
 * only a name: a bare name gives a reader no way to tell whether the number
 * they just read is the number the source publishes.
 *
 * Each row receives id="source-N" so inline CitationChips can anchor.
 */

const COLOR_TITLE = "var(--color-on-surface)";
const COLOR_BODY = "var(--color-on-surface)";
const COLOR_LINK = "var(--color-brand-primary)";
const FONT_STACK =
  '"Google Sans Text", "Google Sans", Inter, system-ui, sans-serif';

/**
 * The attribution Data Commons asks every citation to carry: the numbers are
 * the provider's, re-served after Data Commons' own normalization, and the
 * line says so rather than leaving a reader to assume one or the other.
 */
const PROCESSING_NOTE = "with minor processing by Data Commons";

/** Section heading. Held here with the other user-facing strings. */
const CITATIONS_HEADING = "Citations";

interface CitationsListProps {
  sources: ProvenanceItem[];
}

/** Strips the scheme and any trailing slash, so the link reads as a reference. */
export function citationUrlLabel(url: string): string {
  return url.replace(/^[a-z]+:\/\//i, "").replace(/\/+$/, "");
}

/**
 * The prose part of a citation: who published it, what it is, and over what
 * years. Each piece is dropped when the data plane did not report it, so a
 * source known only by name still renders a sensible line.
 */
export function citationLead(source: ProvenanceItem): string {
  const parts = [source.provider, source.dataset || source.name].filter(
    (part): part is string => !!part && part.trim() !== "",
  );
  // The provider and the dataset are often the same string when the data plane
  // reported only one of them; saying it twice reads as an error.
  const unique = parts.filter((part, index) => parts.indexOf(part) === index);
  const lead = unique.join(", ");
  return source.dateRange ? `${lead} (${source.dateRange})` : lead;
}

/** Numbered list of citations matching the [n] chips in the answer. */
export function CitationsList({ sources }: CitationsListProps) {
  if (!sources || sources.length === 0) return null;

  // No top margin on the section: it is spaced by the answer card's own 16px
  // flex gap plus the heading's padding, and the margin stacked on both.
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
