/**
 * @fileoverview Renders an inline numbered citation chip.
 */

/**
 * Small inline pill that renders [N] inside the markdown body as a
 * clickable badge linking to the matching entry in the Sources block.
 *
 * Visual spec (Figma node 3427-16728, token "ts1"):
 *   color: #175C75 (AI Dark Blue)
 *   weight: 500 (Medium)
 *   font: Google Sans Text Medium 16/24 (inherits from surrounding body)
 */

const COLOR = "var(--color-brand-primary)";

/** Small numbered [n] chip linking an answer sentence to its source. */
export function CitationChip({ n }: { n: number }) {
  return (
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
      aria-label={`Source ${n}`}
    >
      [{n}]
    </a>
  );
}

/**
 * Walk a children array and replace `[N]` patterns inside strings with
 * <CitationChip /> elements. Returns a new children array suitable for
 * React rendering. Pass any react-markdown component's `children` through
 * this helper to apply citation styling consistently inside p, li, td,
 * strong, em, etc.
 */
export function withCitationChips(
  children: React.ReactNode,
): React.ReactNode {
  if (children == null) return children;
  if (Array.isArray(children)) {
    return children.map((c, i) => (
      <ChildWithCitations key={i}>{c}</ChildWithCitations>
    ));
  }
  return <ChildWithCitations>{children}</ChildWithCitations>;
}

/** Splits child text on [n] markers and renders each as a CitationChip. */
function ChildWithCitations({ children }: { children: React.ReactNode }) {
  if (typeof children !== "string") {
    return <>{children}</>;
  }
  return <>{splitWithCitations(children)}</>;
}

/**
 * Split a string into a mixed array of text fragments and CitationChip
 * elements, matching `[N]` where N is 1-99. Handles multiple adjacent
 * citations like `[1] [2]` or `[1][2]`.
 */
function splitWithCitations(s: string): React.ReactNode[] {
  const pattern = /\[(\d{1,2})\]/g;
  const out: React.ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  let i = 0;
  while ((match = pattern.exec(s)) !== null) {
    if (match.index > last) {
      out.push(s.slice(last, match.index));
    }
    out.push(<CitationChip key={`c-${i++}`} n={Number(match[1])} />);
    last = match.index + match[0].length;
  }
  if (last < s.length) out.push(s.slice(last));
  return out.length === 0 ? [s] : out;
}
