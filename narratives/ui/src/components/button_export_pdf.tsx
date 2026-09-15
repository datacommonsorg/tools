/**
 * @fileoverview Renders a button that exports the answer panel to PDF via the browser print flow.
 */

import { useRef } from "react";
import { ExportIcon } from "./icons";
import { Tooltip } from "./tooltip";

/**
 * Material 3 "filled tonal" pill, standardised across the Data Commons apps:
 *   - container: --color-brand-container, a tint derived from the brand primary
 *   - label and icon: --color-on-brand-container
 *   - pill: border-radius 100px
 *   - padding 10px 16px, gap 8px
 *   - height 48 (Round Small height 40, but the wrapper "Content" frame is 48)
 *   - leading icon: the "output" symbol, 20px
 *   - label: Google Sans Text Medium 14/20
 *
 * Both colors are theme tokens, so an instance restyles the button through
 * branding.json rather than here.
 *
 * Behaviour: the parent renders the panel to a PDF and downloads it — see
 * utils/download_pdf.ts. The button itself is presentation only; it takes the
 * handler and a busy flag so the toolbar pill and this button stay one action
 * in two placements.
 */

interface ExportPdfButtonProps {
  onExport: () => void;
  busy?: boolean;
  label?: string;
}

const COLOR_FILL = "var(--color-brand-container)";
const COLOR_TEXT = "var(--color-on-brand-container)";
const FONT_STACK =
  '"Google Sans Text", "Google Sans", Inter, system-ui, sans-serif';

/** Tonal "Export PDF" pill that prints the enclosing answer panel to PDF. */
export function ExportPdfButton({
  onExport,
  busy = false,
  label = "Export PDF",
}: ExportPdfButtonProps) {
  const internalRef = useRef<HTMLButtonElement>(null);

  return (
    <div className="flex items-center" style={{ height: 48 }} data-non-print="true">
      <Tooltip label="Download this answer as a PDF">
      <button
        ref={internalRef}
        type="button"
        onClick={onExport}
        disabled={busy}
        className="inline-flex items-center justify-center cursor-pointer transition-opacity hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60"
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
        <span>{busy ? "Preparing…" : label}</span>
      </button>
      </Tooltip>
    </div>
  );
}
