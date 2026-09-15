/**
 * @fileoverview Provenance inspector: a slide-over showing which variables and
 * data sources an answer used.
 */

import { useEffect, useRef, useState } from "react";
import type { ChatTurn } from "../hooks/use_sse_chat";
import { inspectTurn } from "../utils/inspect_turn";
import { InspectIcon } from "./icons";

/**
 * Reports whether the provenance inspector is enabled — i.e. the page was
 * opened with `?debug=provenance`. Evaluated per render (not at module load) so
 * it reacts to client-side navigation and stays safe under SSR/tests. Mirrors
 * the `?debug=tokens` switch in header.tsx.
 */
export const isProvenanceDebugEnabled = () =>
  typeof window !== "undefined" &&
  new URLSearchParams(window.location.search).get("debug") === "provenance";

const MONO = '"IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace';

/** Section wrapper: a small uppercase label above its content. */
function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-1.5">
      <h4 className="m-0 text-label-large uppercase tracking-wide text-on-surface-variant">
        {label}
      </h4>
      {children}
    </section>
  );
}

/** One key/value pair on a facet's detail line. */
function Detail({ label, value }: { label: string; value?: string | number }) {
  if (value === undefined || value === "") return null;
  return (
    <span className="text-body-medium text-on-surface-variant">
      {label} <span style={{ fontFamily: MONO }}>{value}</span>
    </span>
  );
}

/** The inspector's contents, without any chrome. */
function InspectorBody({ turn }: { turn: ChatTurn }) {
  const [openResult, setOpenResult] = useState<number | null>(null);
  const inspection = inspectTurn(turn.toolCalls, turn.chartConfig, turn.provenance);
  const usedFacets = inspection.facets.filter((facet) => facet.used);

  return (
    <div className="flex flex-col gap-5">
      {/* "Which provenances were used" is the question this view exists to
          answer, so it leads. Only sources that actually supplied figures are
          listed: the candidates the server ranked below them are part of how
          the answer was reached, not part of what it rests on. inspectTurn
          still records them, so widening this filter is a one-line change. */}
      {usedFacets.length > 0 && (
        <Section label="Provenances used">
          <ul className="m-0 p-0 list-none flex flex-col gap-3">
            {usedFacets.map((facet) => (
              <li
                key={facet.facetId}
                className="flex flex-col gap-0.5 pl-3"
                style={{ borderLeft: "3px solid var(--color-brand-primary)" }}
              >
                <span className="text-body-medium">
                  <strong>{facet.provenance ?? "(unnamed source)"}</strong>
                </span>
                <span className="flex flex-wrap gap-x-4 gap-y-0.5">
                  <Detail label="coverage" value={facet.dateRange} />
                  <Detail label="observations" value={facet.obsCount} />
                  <Detail label="unit" value={facet.unit} />
                  <Detail label="licence" value={facet.license} />
                </span>
                <Detail label="facet" value={facet.facetId} />
                {facet.url && (
                  // Truncated to one line: some provenance URLs are OECD-style
                  // query strings that otherwise wrap over five lines and bury
                  // the entry they belong to. The full URL stays in href and
                  // title, so nothing is actually lost.
                  <a
                    href={facet.url}
                    target="_blank"
                    rel="noreferrer"
                    title={facet.url}
                    className="text-body-medium block"
                    style={{
                      color: "var(--color-brand-primary)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {facet.url}
                  </a>
                )}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {inspection.variables.length > 0 && (
        <Section label="Variables">
          <ul className="m-0 p-0 list-none flex flex-col gap-1">
            {inspection.variables.map((variable) => (
              <li key={variable.dcid} className="text-body-medium">
                <span style={{ fontFamily: MONO }}>{variable.dcid}</span>
                {variable.name && (
                  <span className="text-on-surface-variant"> — {variable.name}</span>
                )}
                {!variable.fetched && (
                  // Found while searching, but no numbers pulled from it. Say
                  // what it is rather than what it isn't.
                  <span className="text-on-surface-variant"> (resolved during search)</span>
                )}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {inspection.places.length > 0 && (
        <Section label={`Places (${inspection.places.length})`}>
          <p
            className="m-0 text-body-medium"
            style={{ fontFamily: MONO, wordBreak: "break-word" }}
          >
            {inspection.places.join(", ")}
          </p>
        </Section>
      )}

      {inspection.charts.length > 0 && (
        <Section label="Charts requested">
          <ul className="m-0 p-0 list-none flex flex-col gap-1.5">
            {inspection.charts.map((chart, index) => (
              <li key={index} className="flex flex-col text-body-medium">
                <span>{chart.title}</span>
                <span
                  className="text-on-surface-variant"
                  style={{ fontFamily: MONO, wordBreak: "break-word" }}
                >
                  {chart.variables.join(", ")}
                  {chart.places.length > 0 && ` @ ${chart.places.length} place(s)`}
                </span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* Raw responses stay behind a per-call toggle: they are untruncated and
          can run to tens of kilobytes. */}
      {turn.toolCalls.length > 0 && (
        <Section label={`Tool calls (${turn.toolCalls.length})`}>
          <ol className="m-0 pl-5 flex flex-col gap-3">
            {turn.toolCalls.map((call, index) => (
              <li key={index} className="flex flex-col gap-1">
                <span className="text-body-medium">
                  <span style={{ fontFamily: MONO }}>{call.name}</span>
                  {call.status === "error" && (
                    <span style={{ color: "var(--color-error-strong)" }}> · error</span>
                  )}
                </span>
                <pre
                  className="m-0 p-2 rounded text-body-medium"
                  style={{
                    fontFamily: MONO,
                    background: "var(--color-surface-soft)",
                    overflowX: "auto",
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-word",
                  }}
                >
                  {JSON.stringify(call.arguments, null, 2)}
                </pre>
                {call.result && (
                  <>
                    <button
                      type="button"
                      onClick={() => setOpenResult(openResult === index ? null : index)}
                      className="self-start text-label-large cursor-pointer bg-transparent p-0"
                      style={{ color: "var(--color-brand-primary)", border: 0 }}
                    >
                      {openResult === index ? "Hide" : "Show"} raw response (
                      {call.result.length.toLocaleString()} chars)
                    </button>
                    {openResult === index && (
                      <pre
                        className="m-0 p-2 rounded text-body-medium"
                        style={{
                          fontFamily: MONO,
                          background: "var(--color-surface-soft)",
                          maxHeight: 300,
                          overflow: "auto",
                          whiteSpace: "pre-wrap",
                          wordBreak: "break-word",
                        }}
                      >
                        {call.result}
                      </pre>
                    )}
                  </>
                )}
              </li>
            ))}
          </ol>
        </Section>
      )}
    </div>
  );
}

/**
 * The icon button that opens the inspector, plus the slide-over it opens.
 *
 * A slide-over rather than an inline block: the inspector is longer than most
 * answers — every candidate source, every tool call, and optionally a raw
 * response of tens of kilobytes — so inline it buried the answer it was meant to
 * explain. Out of flow, it can also scroll independently and be dismissed.
 *
 * Follows drawer_session.tsx: a scrim over the page, the panel above it, closed
 * by the button, the scrim, or Escape.
 */
export function ProvenanceInspector({ turn }: { turn: ChatTurn }) {
  const [open, setOpen] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);

  // Escape closes, and focus moves into the panel so the keyboard lands
  // somewhere sensible instead of staying behind the scrim.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    closeRef.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const hasAnything = turn.toolCalls.length > 0;
  if (!hasAnything) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Inspect data sources for this answer"
        aria-expanded={open}
        title="Inspect data sources"
        className="w-9 h-9 flex items-center justify-center rounded-full bg-transparent cursor-pointer hover:bg-button-hover transition-colors text-on-surface-variant"
        style={{ border: 0 }}
      >
        <InspectIcon size="sm" />
      </button>

      {open && (
        <>
          <div
            className="fixed inset-0 z-30 bg-scrim/30"
            onClick={() => setOpen(false)}
            aria-hidden="true"
          />
          <aside
            role="dialog"
            aria-modal="true"
            aria-label="Provenance inspector"
            className="fixed top-0 right-0 h-full z-40 bg-surface border-l border-outline shadow-lg flex flex-col"
            style={{ width: "min(560px, 100vw)" }}
          >
            <header className="flex items-start justify-between gap-3 p-4 border-b border-outline shrink-0">
              <div className="flex flex-col gap-0.5 min-w-0">
                <h3 className="m-0 text-title-medium text-on-surface">Provenance inspector</h3>
                <p className="m-0 text-body-medium text-on-surface-variant truncate">
                  {turn.userMessage}
                </p>
              </div>
              <button
                ref={closeRef}
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close provenance inspector"
                className="w-9 h-9 shrink-0 flex items-center justify-center rounded-full bg-transparent cursor-pointer hover:bg-button-hover transition-colors text-on-surface-variant text-title-medium"
                style={{ border: 0 }}
              >
                ×
              </button>
            </header>

            <div className="flex-1 overflow-y-auto p-4">
              <InspectorBody turn={turn} />
            </div>
          </aside>
        </>
      )}
    </>
  );
}
