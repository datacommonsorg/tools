/**
 * @fileoverview Renders a button that exports the answer panel to PDF via the browser print flow.
 */

import { useRef } from "react";
import { ExportIcon } from "./icons";
import { printElement } from "../utils/print_element";

/**
 * Figma node 3427-16783 "Button" → Type=Round, Size=Small, Style=Filled.
 *   - filled: AI Dark Blue #175C75
 *   - pill: border-radius 100px
 *   - padding 10px 16px, gap 8px
 *   - height 48 (Round Small height 40, but the wrapper "Content" frame is 48)
 *   - leading icon: Google Symbols 20px (figma puts "edit" as a placeholder;
 *     we use a download/picture-as-pdf icon since the label says "Export PDF")
 *   - label: Google Sans Text Medium 14/20, color #FFFFFF
 *
 * Behaviour: triggers `window.print()` against a print stylesheet that
 * hides chat input + side panels and keeps just the AnswerPanel visible.
 * This is the cheapest reliable PDF export — works in every browser, no
 * extra dependency. A future enhancement could swap in html2pdf.js or
 * jspdf for a non-print path, but for V1 print-to-PDF matches Figma's
 * "Export PDF" affordance exactly.
 */

interface ExportPdfButtonProps {
  targetRef?: React.RefObject<HTMLElement | null>;
  label?: string;
}

const COLOR_FILL = "var(--color-brand-primary)";
const COLOR_TEXT = "#FFFFFF";
const FONT_STACK =
  '"Google Sans Text", "Google Sans", Inter, system-ui, sans-serif';

/** Filled "Export PDF" pill that prints the enclosing answer panel to PDF. */
export function ExportPdfButton({
  targetRef,
  label = "Export PDF",
}: ExportPdfButtonProps) {
  const internalRef = useRef<HTMLButtonElement>(null);

  const onExport = () => printElement(targetRef?.current ?? null);

  return (
    <div className="flex items-center" style={{ height: 48 }} data-non-print="true">
      <button
        ref={internalRef}
        type="button"
        onClick={onExport}
        className="inline-flex items-center justify-center cursor-pointer transition-opacity hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2"
        style={{
          backgroundColor: COLOR_FILL,
          color: COLOR_TEXT,
          border: 0,
          borderRadius: 100,
          padding: "10px 16px",
          gap: 8,
          fontFamily: FONT_STACK,
          fontSize: 14,
          lineHeight: "20px",
          fontWeight: 500,
        }}
      >
        <ExportIcon />
        <span>{label}</span>
      </button>
    </div>
  );
}
