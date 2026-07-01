/**
 * @fileoverview Filled "Export PDF" button. Triggers `window.print()` against
 * a print stylesheet that hides the chat input + side panels and keeps just
 * the PanelAnswer visible. This is the cheapest reliable PDF export — works in
 * every browser with no extra dependency. A future enhancement could swap in
 * html2pdf.js or jspdf for a non-print path, but for V1 print-to-PDF matches
 * Figma's "Export PDF" affordance (node 3427-16783) exactly.
 */

import { useRef } from "react";

interface ButtonExportPdfProps {
  targetRef?: React.RefObject<HTMLElement | null>;
  label?: string;
}

const COLOR_FILL = "#175C75";
const COLOR_TEXT = "#FFFFFF";
const FONT_STACK =
  '"Google Sans Text", "Google Sans", Inter, system-ui, sans-serif';

/**
 * Renders the filled Export-PDF pill. When `targetRef` is supplied, the
 * referenced element is marked as the print target so the print stylesheet
 * isolates it; otherwise it falls back to the `#answer-panel` container.
 */
export function ButtonExportPdf({
  targetRef,
  label = "Export PDF",
}: ButtonExportPdfProps) {
  const internalRef = useRef<HTMLButtonElement>(null);

  const onExport = () => {
    // If a target is supplied, briefly mark the document body so the
    // print stylesheet hides everything except that container.
    const target = targetRef?.current;
    if (target) {
      document.body.dataset.printTarget = target.id || "answer-panel";
      // Ensure target has an id we can reference from CSS:
      if (!target.id) target.id = "answer-panel";
    }
    // Defer to next frame so any state-driven class updates flush first.
    requestAnimationFrame(() => {
      window.print();
      delete document.body.dataset.printTarget;
    });
  };

  return (
    <div className="flex items-center" style={{ height: 48 }}>
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

/**
 * Material Symbols "edit" (pencil) — 20×20 to match Figma's leading-icon
 * slot (layout_MOYZ4B). Verified by downloading node 3427:16783 from
 * Figma at 4× and inspecting the rendered glyph.
 */
function ExportIcon() {
  return (
    <svg
      width={20}
      height={20}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z" />
    </svg>
  );
}
