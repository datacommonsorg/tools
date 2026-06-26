/**
 * @fileoverview Sources list rendered beneath an answer (Figma node 3427-16738
 * heading + 3427-16739 numbered body). Each source is a numbered line — the
 * number stays in the default body color, the source name is rendered in
 * #175C75 (AI Dark Blue, token "ts4") as a hyperlink. Each row receives
 * id="source-N" so inline ChipCitations can anchor to it.
 */

import type { ProvenanceItem } from "../hooks/use_sse_chat";

const COLOR_TITLE = "#1B1C1D";
const COLOR_BODY = "#1B1C1D";
const COLOR_LINK = "#175C75";
const FONT_STACK =
  '"Google Sans Text", "Google Sans", Inter, system-ui, sans-serif';

interface ListSourcesProps {
  sources: ProvenanceItem[];
}

/**
 * Renders the numbered, linked list of provenance sources for an answer.
 * Returns nothing when there are no sources.
 */
export function ListSources({ sources }: ListSourcesProps) {
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
        {sources.map((source, index) => {
          const position = index + 1;
          return (
            <li
              key={`${source.url}-${index}`}
              id={`source-${position}`}
              className="flex items-baseline gap-1.5"
            >
              <span aria-hidden="true">[{position}]</span>
              <a
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:underline"
                style={{ color: COLOR_LINK }}
              >
                {source.name || source.url}
              </a>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
