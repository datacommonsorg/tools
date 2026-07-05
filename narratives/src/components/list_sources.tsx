/**
 * @fileoverview Renders the list of provenance sources for an answer.
 */

import type { ProvenanceItem } from "../hooks/use_sse_chat";

/**
 * Figma node 3427-16738 ("Sources" heading) + 3427-16739 ("Body" with the
 * numbered list). Each source is a numbered line — the number stays in
 * the default body color, the source name itself is rendered in
 * #175C75 (AI Dark Blue, token "ts4") as a hyperlink to provenanceUrl.
 * Each row receives id="source-N" so inline CitationChips can anchor.
 */

const COLOR_TITLE = "var(--color-on-surface)";
const COLOR_BODY = "var(--color-on-surface)";
const COLOR_LINK = "var(--color-brand-primary)";
const FONT_STACK =
  '"Google Sans Text", "Google Sans", Inter, system-ui, sans-serif';

interface SourcesListProps {
  sources: ProvenanceItem[];
}

/** Numbered list of source links matching the [n] citation chips in the answer. */
export function SourcesList({ sources }: SourcesListProps) {
  if (!sources || sources.length === 0) return null;

  return (
    <section aria-labelledby="sources-heading" className="mt-2">
      <h2
        id="sources-heading"
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
        Sources
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
        {sources.map((s, i) => {
          const n = i + 1;
          return (
            <li
              key={`${s.url}-${i}`}
              id={`source-${n}`}
              className="flex items-baseline gap-1.5"
            >
              <span aria-hidden="true">[{n}]</span>
              <a
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:underline"
                style={{
                  color: COLOR_LINK,
                  // Long source names/URLs often have no spaces; allow them
                  // to break mid-string. `minWidth: 0` lets this flex child
                  // shrink below its content width instead of overflowing.
                  minWidth: 0,
                  overflowWrap: "anywhere",
                  wordBreak: "break-word",
                }}
              >
                {s.name || s.url}
              </a>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
