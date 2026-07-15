/**
 * @fileoverview Renders a completed answer as a side-panel card: markdown body, sources, charts, disclaimer, export, and follow-ups.
 */

import { useRef } from "react";
import type { ChatTurn } from "../hooks/use_sse_chat";
import { ChartTile } from "./tile_chart";
import { DisclaimerNote } from "./note_disclaimer";
import { ExportPdfButton } from "./button_export_pdf";
import { FollowUpQuestions } from "./questions_follow_up";
import { ResponseCard } from "./card_response";
import { SourcesList } from "./list_sources";
import { printElement } from "../utils/print_element";

/**
 * Wraps the full answer in a "Side panel" card (Figma node 3427:16726):
 *   • Outer: 1px #E3E3E3 border, 16px radius
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

const COLOR_BORDER = "#E3E3E3";
/**
 * Per Figma 3427-16727 the toolbar fills with WHITE (fill_M9951K) and
 * 3427-16728 the content body fills with light grey #F9F9F9 (fill_OQPE64).
 */
const COLOR_TOOLBAR_BG = "#FFFFFF";
const COLOR_BODY_BG = "var(--color-surface-soft)";
const COLOR_OUTLINE_PILL = "#F0F4F9";
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
  const hasSources = turn.provenance.length > 0;

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
        <span
          className="flex-1 truncate"
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
          <ToolbarExportPdfPill targetRef={panelRef} />
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
          bare
        />

        {/* 2. Sources */}
        {hasSources && <SourcesList sources={turn.provenance} />}

        {/* 3. Charts */}
        {hasCharts && (
          <ChartTile config={turn.chartConfig!} provenance={turn.provenance} />
        )}

        {/* 4. Disclaimer */}
        {(hasCharts || hasSources) && <DisclaimerNote />}

        {/* 5. Export PDF (filled, in-content) */}
        {turn.status === "done" && (
          <ExportPdfButton targetRef={panelRef} />
        )}

        {/* 6. Follow-up questions — agent-generated, self-contained. Hidden
            when the agent returned none (no static fallback). */}
        {turn.status === "done" && (turn.followUps?.length ?? 0) > 0 && (
          <FollowUpQuestions questions={turn.followUps ?? []} onAsk={onAsk} />
        )}
      </div>
    </div>
  );
}

/**
 * Outline-style Export PDF pill that lives in the card's toolbar header.
 * Distinct from the filled <ExportPdfButton /> that sits inside the card
 * body — both appear in Figma 3427-16715 and the user's screenshot.
 */
function ToolbarExportPdfPill({
  targetRef,
}: {
  targetRef: React.RefObject<HTMLElement | null>;
}) {
  const onExport = () => printElement(targetRef.current);
  return (
    <button
      type="button"
      onClick={onExport}
      data-non-print="true"
      className="cursor-pointer hover:opacity-90"
      style={{
        background: COLOR_OUTLINE_PILL,
        color: COLOR_TITLE,
        border: 0,
        borderRadius: 999,
        padding: "6px 16px",
        fontFamily: FONT_LABEL,
        fontSize: 14,
        lineHeight: "20px",
        fontWeight: 500,
      }}
      aria-label="Export PDF"
    >
      Export PDF
    </button>
  );
}
