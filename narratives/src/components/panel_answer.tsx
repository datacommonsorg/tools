/**
 * @fileoverview PanelAnswer component wrapping the full answer display structure,
 * including toolbar, body, markdown response card, sources, charts, disclaimers,
 * and PDF export actions.
 */

import { useRef } from "react";
import type { ChatTurn } from "../hooks/use_sse_chat";
import { TileChart } from "./tile_chart";
import NoteDisclaimer from "./note_disclaimer";
import ButtonExportPdf from "./button_export_pdf";
import QuestionsFollowUp from "./questions_follow_up";
import CardResponse from "./card_response";
import ListSources from "./list_sources";

// TODO(followup): Extract the inline styling in this react component into a template/theme file.

/**
 * Props for the PanelAnswer component.
 */
interface PanelAnswerProps {
  turn: ChatTurn;
  isStreaming: boolean;
  onAsk?: (question: string) => void;
}

const STUB_FOLLOWUPS = [
  "Compare this with a related indicator",
  "Show this broken down by region",
  "Show this for the most recent year only",
];

const COLOR_BORDER = "#E3E3E3";
// Per Figma 3427-16727 the toolbar fills with WHITE (fill_M9951K) and
// 3427-16728 the content body fills with light grey #F9F9F9 (fill_OQPE64).
const COLOR_TOOLBAR_BG = "#FFFFFF";
const COLOR_BODY_BG = "#F9F9F9";
const COLOR_OUTLINE_PILL = "#F0F4F9";
const COLOR_TITLE = "#1B1C1D";
const FONT_LABEL =
  '"Google Sans Text", "Google Sans", Inter, system-ui, sans-serif';

/**
 * PanelAnswer component wraps the full answer in a side panel card layout.
 */
export function PanelAnswer({
  turn,
  isStreaming,
  onAsk,
}: PanelAnswerProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const hasCharts = !!turn.chartConfig;
  const hasSources = turn.provenance.length > 0;

  return (
    <div
      ref={panelRef}
      id="answer-panel"
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
        <ToolbarExportPdfPill targetRef={panelRef} />
      </div>

      {/* Content body */}
      <div
        className="flex flex-col"
        style={{
          padding: "24px",
          gap: 16,
          background: COLOR_BODY_BG,
        }}
      >
        {/* 1. Markdown body — bare (no nested card chrome) */}
        <CardResponse
          title={turn.userMessage}
          body={turn.text}
          streaming={isStreaming && turn.status !== "done"}
          bare
        />

        {/* 2. Sources */}
        {hasSources && <ListSources sources={turn.provenance} />}

        {/* 3. Charts */}
        {hasCharts && (
          <TileChart config={turn.chartConfig!} provenance={turn.provenance} />
        )}

        {/* 4. Disclaimer */}
        {(hasCharts || hasSources) && <NoteDisclaimer />}

        {/* 5. Export PDF (filled, in-content) */}
        {turn.status === "done" && (
          <ButtonExportPdf targetRef={panelRef} />
        )}

        {/* 6. Follow-up questions */}
        {turn.status === "done" && (
          <QuestionsFollowUp questions={STUB_FOLLOWUPS} onAsk={onAsk} />
        )}
      </div>
    </div>
  );
}

/**
 * Outline-style Export PDF pill that lives in the card's toolbar header.
 * Distinct from the filled <ButtonExportPdf /> that sits inside the card
 * body — both appear in Figma 3427-16715 and the user's screenshot.
 */
function ToolbarExportPdfPill({
  targetRef,
}: {
  targetRef: React.RefObject<HTMLElement | null>;
}) {
  const onExport = () => {
    const target = targetRef.current;
    if (target) {
      if (!target.id) {
        target.id = "answer-panel";
      }
      document.body.dataset.printTarget = target.id;
    }
    requestAnimationFrame(() => {
      window.print();
      delete document.body.dataset.printTarget;
    });
  };
  return (
    <button
      type="button"
      onClick={onExport}
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
