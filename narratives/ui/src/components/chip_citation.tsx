/**
 * @fileoverview Renders an inline numbered citation chip.
 */

import type { ProvenanceItem } from "../hooks/use_sse_chat";
import { Tooltip } from "./tooltip";

/**
 * Small inline pill that renders [N] inside the markdown body as a
 * clickable badge linking to the matching entry in the Sources block.
 *
 * The number is never rewritten. `[n]` is position n of the provenance list,
 * which is the same numbered list the synthesis prompt was given, and the same
 * order SourcesList renders. One numbering, three places, nothing to keep in
 * sync -- so a marker this file never sees (inside an element with no override
 * of its own, or in exported or copied text) is still correct, just not a link.
 *
 * Visual spec (Figma node 3427-16728, token "ts1"):
 *   color: #175C75 (AI Dark Blue)
 *   weight: 500 (Medium)
 *   font: Google Sans Text Medium 16/24 (inherits from surrounding body)
 */

const COLOR = "var(--color-brand-primary)";

/**
 * Name of the source a `[n]` chip points at.
 *
 * SourcesList numbers its entries from 1, so chip `n` is `sources[n - 1]`.
 * Falls back to the bare URL when the source has no name, and to the plain
 * "Source n" when the answer cites an index the provenance list doesn't cover.
 */
export function sourceLabel(n: number, sources?: ProvenanceItem[]): string {
  const source = sources?.[n - 1];
  return source?.name || source?.url || `Source ${n}`;
}

/** Accessible name for a chip: the number, plus the source when we know it. */
function citationAriaLabel(n: number, sources?: ProvenanceItem[]): string {
  const label = sourceLabel(n, sources);
  // Past the end of the list sourceLabel already returns "Source n"; prefixing
  // it again would have a screen reader announce "Source 9: Source 9".
  return label === `Source ${n}` ? label : `Source ${n}: ${label}`;
}

/**
 * True when `n` names a row the Sources block actually renders.
 *
 * The agent occasionally writes a number the data never justified. There is no
 * `#source-n` anchor for it and no source to name, so it must not be a link:
 * it used to render as one and clicking it did nothing.
 */
export function isCitable(n: number, sources?: ProvenanceItem[]): boolean {
  return !!sources && n >= 1 && n <= sources.length;
}

/** Small numbered [n] chip linking an answer sentence to its source. */
export function CitationChip({
  n,
  sources,
}: {
  n: number;
  sources?: ProvenanceItem[];
}) {
  if (!isCitable(n, sources)) {
    return <>[{n}]</>;
  }

  const label = sourceLabel(n, sources);
  return (
    <Tooltip label={label}>
    <a
      href={`#source-${n}`}
      onClick={(e) => {
        // Smooth scroll instead of jumping abruptly
        const target = document.getElementById(`source-${n}`);
        if (target) {
          e.preventDefault();
          target.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      }}
      className="font-medium no-underline hover:underline"
      style={{ color: COLOR, fontWeight: 500 }}
      // The number alone tells a screen-reader user nothing about where the
      // claim came from; the visible tooltip's text belongs here too.
      aria-label={citationAriaLabel(n, sources)}
    >
      [{n}]
    </a>
    </Tooltip>
  );
}

/**
 * Walk a children array and replace `[N]` patterns inside strings with
 * <CitationChip /> elements. Returns a new children array suitable for
 * React rendering. Pass any react-markdown component's `children` through
 * this helper to apply citation styling consistently inside p, li, td,
 * strong, headings, em, etc.
 */
export function renderWithCitations(
  children: React.ReactNode,
  sources?: ProvenanceItem[],
): React.ReactNode {
  if (children == null) return children;
  if (Array.isArray(children)) {
    return children.map((c, i) => (
      <ChildWithCitations key={i} sources={sources}>
        {c}
      </ChildWithCitations>
    ));
  }
  return <ChildWithCitations sources={sources}>{children}</ChildWithCitations>;
}

/** Splits child text on [n] markers and renders each as a CitationChip. */
function ChildWithCitations({
  children,
  sources,
}: {
  children: React.ReactNode;
  sources?: ProvenanceItem[];
}) {
  if (typeof children !== "string") {
    return <>{children}</>;
  }
  return <>{splitWithCitations(children, sources)}</>;
}

/**
 * Split a string into a mixed array of text fragments and CitationChip
 * elements, matching `[N]` where N is 1-99. Handles multiple adjacent
 * citations like `[1] [2]` or `[1][2]`.
 */
function splitWithCitations(
  s: string,
  sources?: ProvenanceItem[],
): React.ReactNode[] {
  const pattern = /\[(\d{1,2})\]/g;
  const out: React.ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  let i = 0;
  while ((match = pattern.exec(s)) !== null) {
    if (match.index > last) {
      out.push(s.slice(last, match.index));
    }
    out.push(
      <CitationChip key={`c-${i++}`} n={Number(match[1])} sources={sources} />,
    );
    last = match.index + match[0].length;
  }
  if (last < s.length) out.push(s.slice(last));
  return out.length === 0 ? [s] : out;
}
