/**
 * @fileoverview Renders the AI-generated-content disclaimer note.
 */

import { GeminiInfoIcon } from "./icons";

/**
 * Figma node 3427-16777 "Disclaimer" → 3427-16778 "DisclaimerNote".
 * Info icon + body text + thin divider below.
 * Token "ts5" (the \_ space character) maps to color #F9F9F9, used only
 * inside the text — we collapse it back to a regular space.
 */

const COLOR_TEXT = "#5C5F5E";
const COLOR_DIVIDER = "var(--color-border)";
const FONT_STACK =
  '"Google Sans Text", "Google Sans", Inter, system-ui, sans-serif';

interface DisclaimerNoteProps {
  text?: string;
}

/**
 * The approved AI-content wording. Exported because the composer footer in
 * data_agent.tsx shows the same disclaimer — when the two were separate
 * literals one of them was updated and the other was not.
 */
export const DISCLAIMER_TEXT =
  "Data Commons by Google. Data overviews are synthesized by Gemini. Gemini is AI and can make mistakes; please verify content against primary source data.";

/** Small AI-generated-content disclaimer shown under each answer. */
export function DisclaimerNote({ text = DISCLAIMER_TEXT }: DisclaimerNoteProps) {
  return (
    <section
      className="flex flex-col gap-1.5"
      style={{ alignSelf: "stretch" }}
      aria-label="Disclaimer"
    >
      <div
        className="flex items-start gap-2.5"
        style={{ padding: "10px 0 16px" }}
      >
        <GeminiInfoIcon
          size="xs"
          style={{ flexShrink: 0, marginTop: 4 }}
        />
        <p
          className="m-0"
          style={{
            fontFamily: FONT_STACK,
            fontSize: 16,
            lineHeight: "24px",
            fontWeight: 400,
            color: COLOR_TEXT,
          }}
        >
          {text}
        </p>
      </div>
      <hr style={{ border: 0, borderTop: `1px solid ${COLOR_DIVIDER}` }} />
    </section>
  );
}

