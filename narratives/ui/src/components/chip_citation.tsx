/**
 * @fileoverview Renders an inline numbered citation chip.
 */

import { createContext, useContext } from "react";
import type { ProvenanceItem } from "../hooks/use_sse_chat";
import { Tooltip } from "./tooltip";

/**
 * Small inline pill that renders [N] inside the markdown body as a
 * clickable badge linking to the matching entry in the Sources block.
 *
 * The agent's own numbering is never rewritten: `[n]` is position n of this
 * turn's provenance, the same list the synthesis prompt was given. Only the
 * label that position wears changes, from the {@link CitationNumbering} an
 * answer panel provides, so the chip, its anchor and its row cannot
 * disagree.
 *
 * Visual spec (Figma node 3427-16728, token "ts1"):
 *   color: #175C75 (AI Dark Blue)
 *   weight: 500 (Medium)
 *   font: Google Sans Text Medium 16/24 (inherits from surrounding body)
 */

const COLOR = "var(--color-brand-primary)";

/** How one answer's citations are labelled and anchored on the page. */
export interface CitationNumbering {
  /** Display label for each provenance position: `numbers[n - 1]` labels `[n]`. */
  numbers?: number[];
  /** Which turn this answer is, so its anchors cannot collide with another's. */
  turnIndex?: number;
}

const CitationNumberingContext = createContext<CitationNumbering>({});

/** Supplies the labels and anchor scope for one answer's citations. */
export const CitationNumberingProvider = CitationNumberingContext.Provider;

/** The numbering in force for the answer currently rendering. */
export function useCitationNumbering(): CitationNumbering {
  return useContext(CitationNumberingContext);
}

/** The label shown for the agent's `[n]`, which is `n` when nothing remapped it. */
export function displayCitationNumber(n: number, numbers?: number[]): number {
  return numbers?.[n - 1] ?? n;
}

/**
 * The DOM id of a Citations row. Scoped by turn as well as number: a source
 * cited twice keeps one label, so the label alone is not unique.
 */
export function citationAnchorId(
  turnIndex: number | undefined,
  shown: number,
): string {
  return `citation-${turnIndex ?? 0}-${shown}`;
}

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
function citationAriaLabel(
  n: number,
  shown: number,
  sources?: ProvenanceItem[],
): string {
  const label = sourceLabel(n, sources);
  // Past the end of the list sourceLabel already returns "Source n"; prefixing
  // it again would have a screen reader announce "Source 9: Source 9".
  return label === `Source ${n}` ? label : `Source ${shown}: ${label}`;
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
  const { numbers, turnIndex } = useCitationNumbering();

  if (!isCitable(n, sources)) {
    return <>[{n}]</>;
  }

  const shown = displayCitationNumber(n, numbers);
  const anchor = citationAnchorId(turnIndex, shown);
  const label = sourceLabel(n, sources);
  return (
    <Tooltip label={label}>
    <a
      href={`#${anchor}`}
      onClick={(e) => {
        // Smooth scroll instead of jumping abruptly
        const target = document.getElementById(anchor);
        if (target) {
          e.preventDefault();
          target.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      }}
      className="font-medium no-underline hover:underline"
      style={{ color: COLOR, fontWeight: 500 }}
      // The number alone tells a screen-reader user nothing about where the
      // claim came from; the visible tooltip's text belongs here too.
      aria-label={citationAriaLabel(n, shown, sources)}
    >
      [{shown}]
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
