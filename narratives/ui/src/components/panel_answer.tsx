/**
 * @fileoverview Renders a completed answer as a side-panel card: markdown body, sources, charts, disclaimer, export, and follow-ups.
 */

import { useRef, useState } from "react";
import type { ChatTurn } from "../hooks/use_sse_chat";
import { ChartTile } from "./tile_chart";
import { DisclaimerNote } from "./note_disclaimer";
import {
  ProvenanceInspector,
  isProvenanceDebugEnabled,
} from "./panel_debug_provenance";
import { ExportIcon } from "./icons";
import { ExportPdfButton } from "./button_export_pdf";
import { FollowUpQuestions } from "./questions_follow_up";
import { ResponseCard } from "./card_response";
import { Tooltip } from "./tooltip";
import { SourcesList } from "./list_sources";
import { downloadPdf } from "../utils/download_pdf";
import { Toast } from "./toast";

/**
 * Wraps the full answer in a "Side panel" card (Figma node 3427:16726):
 *   • Outer: 1px border (--color-border), 16px radius
 *   • Toolbar header (16/16/0/0 radius, #F9F9F9 fill, padding 12 12 12 20):
 *       left  = title text (user's question) — Title S, 14/20 Medium
 *       right = "Export PDF" outline pill (#F0F4F9 fill)
 *   • Content body (#FFFFFF) hosts the existing sections.
 */

interface AnswerPanelProps {
  turn: ChatTurn;
  isStreaming: boolean;
  onAsk?: (question: string) => void;
}

const COLOR_BORDER = "var(--color-border)";
/**
 * Per Figma 3427-16727 the toolbar fills with WHITE (fill_M9951K) and
 * 3427-16728 the content body fills the narrative surface — light grey in the
 * neutral theme, tinted blue (#F5FAFF) in the Base DC one.
 *
 * The body takes --color-surface-narrative rather than --color-surface-soft:
 * the narrative token exists so an instance can tint the answer tile without
 * moving every other soft surface, and SkeletonCard already paints with it. On
 * --color-surface-soft the card rendered blue while streaming and then flipped
 * to grey the moment the content replaced the skeleton.
 */
const COLOR_TOOLBAR_BG = "#FFFFFF";
const COLOR_BODY_BG = "var(--color-surface-narrative)";
// Material 3 "filled tonal" pair, shared with <ExportPdfButton />. Both are
// theme tokens so an instance restyles the button from branding.json.
const COLOR_TONAL_CONTAINER = "var(--color-brand-container)";
const COLOR_TONAL_CONTENT = "var(--color-on-brand-container)";
const COLOR_TITLE = "var(--color-on-surface)";
const FONT_LABEL =
  '"Google Sans Text", "Google Sans", Inter, system-ui, sans-serif';

/** The full answer card: toolbar with export action, markdown body, charts, sources, and follow-ups. */
export function AnswerPanel({
  turn,
  isStreaming,
  onAsk,
}: AnswerPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const hasCharts = !!turn.chartConfig;
  /**
   * `turn.provenance` is the sources that actually supplied the answer's
   * numbers. The backend decides membership from which facet each observation
   * call served, so a source the agent only looked at on the way there is not
   * in here. Position n is `[n]`, in the prose and in the list below, because
   * the synthesis prompt was handed this same list already numbered.
   *
   * Nothing is filtered or renumbered here, on purpose. Either would make what
   * the reader sees depend on the agent having cited exactly right, and it does
   * not: it under-cites, and a source dropped for want of a marker leaves its
   * figures with no attribution at all. Selection belongs where the evidence
   * is -- the tool results -- not in the renderer.
   */
  const hasSources = turn.provenance.length > 0;
  // One export state for the card: the toolbar pill and the in-content button
  // are the same action in two placements, so they share a busy flag and a
  // single confirmation rather than each raising their own.
  const [exporting, setExporting] = useState(false);
  const [exported, setExported] = useState(false);

  const onExport = async () => {
    if (exporting) return;
    setExporting(true);
    try {
      await downloadPdf(panelRef.current, turn.userMessage);
      setExported(true);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div
      ref={panelRef}
      className="self-start shrink-0 w-full max-w-4xl flex flex-col overflow-hidden"
      style={{
        border: `1px solid ${COLOR_BORDER}`,
        borderRadius: 16,
        // Outer takes the body colour so the rounded corners of the
        // body section match the card. Toolbar paints white on top.
        background: COLOR_BODY_BG,
      }}
    >
      {/* Toolbar header */}
      <div
        className="flex items-center"
        style={{
          background: COLOR_TOOLBAR_BG,
          padding: "12px 12px 12px 20px",
          gap: 12,
          borderBottom: `1px solid ${COLOR_BORDER}`,
        }}
      >
        {/* On screen this is a one-line card title, so it truncates. In the
            exported PDF it is the document's heading and has to be readable in
            full, so the print rules in index.css undo the truncation and size
            it up — hence the hook class rather than styling it twice. */}
        <span
          className="flex-1 truncate print-question"
          style={{
            fontFamily: FONT_LABEL,
            fontSize: 14,
            lineHeight: "20px",
            fontWeight: 500,
            color: COLOR_TITLE,
          }}
          title={turn.userMessage}
        >
          {turn.userMessage}
        </span>
        {/* Only expose the toolbar pill once the turn is fully streamed —
            otherwise clicking it while the ChartTile's DataCommons web
            component is still hydrating produces a PDF missing the chart.
            This matches the filled "Export PDF" button below, which also
            waits for status === "done". */}
        {turn.status === "done" && (
          <div className="flex items-center gap-1 shrink-0" data-non-print="true">
            {/* Opens the provenance slide-over. Only under ?debug=provenance,
                so end users never see it. */}
            {isProvenanceDebugEnabled() && <ProvenanceInspector turn={turn} />}
            <ToolbarExportPdfPill onExport={onExport} busy={exporting} />
          </div>
        )}
      </div>

      {/* Content body */}
      <div
        className="flex flex-col p-4 sm:p-6"
        style={{
          gap: 16,
          background: COLOR_BODY_BG,
        }}
      >
        {/* 1. Markdown body — bare (no nested card chrome) */}
        <ResponseCard
          title={turn.userMessage}
          body={turn.text}
          streaming={isStreaming && turn.status !== "done"}
          sources={turn.provenance}
          bare
        />

        {/* 2. Sources */}
        {hasSources && <SourcesList sources={turn.provenance} />}

        {/* 3. Charts */}
        {hasCharts && (
          <ChartTile config={turn.chartConfig!} provenance={turn.provenance} />
        )}

        {/* 4. Truncation notice — the agent ran out of research steps
            before it was done, so this answer rests on less data than it
            intended to gather. Above the disclaimer because it is specific
            to this answer, where the disclaimer is generic. Deliberately not
            styled as an error: the answer is usable, just less complete. */}
        {turn.truncated && (
          <p
            className="m-0 text-body-medium text-on-surface-variant"
            role="status"
          >
            This answer may be incomplete — the agent reached its limit on
            research steps before it finished gathering data.
          </p>
        )}

        {/* 5. Disclaimer */}
        {(hasCharts || hasSources) && <DisclaimerNote />}

        {/* 6. Export PDF (filled, in-content) */}
        {turn.status === "done" && (
          <ExportPdfButton onExport={onExport} busy={exporting} />
        )}

        {/* 7. Follow-up questions — agent-generated, self-contained. Hidden
            when the agent returned none (no static fallback).

            Marked non-print: they are buttons that ask a NEW question, so they
            are an invitation to keep browsing rather than part of the answer
            being exported. In a saved PDF they read as unanswered questions
            belonging to the document, which is the opposite of their meaning. */}
        {turn.status === "done" && (turn.followUps?.length ?? 0) > 0 && (
          <div data-non-print="true">
            <FollowUpQuestions questions={turn.followUps ?? []} onAsk={onAsk} />
          </div>
        )}
      </div>
      {exported && (
        <Toast message="PDF downloaded" onDismiss={() => setExported(false)} />
      )}
    </div>
  );
}

/**
 * Tonal "Export PDF" pill in the card's toolbar header, with the `output`
 * leading icon. Shares the tonal container/content tokens and the icon with
 * the <ExportPdfButton /> inside the card body, so the two read as one control
 * in two placements rather than two different buttons.
 */
function ToolbarExportPdfPill({
  onExport,
  busy,
}: {
  onExport: () => void;
  busy: boolean;
}) {
  return (
    <Tooltip label="Download this answer as a PDF">
    <button
      type="button"
      onClick={onExport}
      disabled={busy}
      data-non-print="true"
      className="inline-flex items-center cursor-pointer hover:opacity-90"
      style={{
        background: COLOR_TONAL_CONTAINER,
        color: COLOR_TONAL_CONTENT,
        border: 0,
        borderRadius: 999,
        padding: "6px 16px",
        gap: 8,
        fontFamily: FONT_LABEL,
        fontSize: 14,
        lineHeight: "20px",
        fontWeight: 500,
      }}
      aria-label="Export PDF"
    >
      <ExportIcon size="xs" />
      <span>Export PDF</span>
    </button>
    </Tooltip>
  );
}
