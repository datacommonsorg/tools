// Figma node 3427-16777 "Disclaimer" → 3427-16778 "DisclaimerNote".
// Info icon + body text + thin divider below.
// Token "ts5" (the \_ space character) maps to color #F9F9F9, used only
// inside the text — we collapse it back to a regular space.

const COLOR_TEXT = "#5C5F5E";
const COLOR_DIVIDER = "#E3E3E3";
const FONT_STACK =
  '"Google Sans Text", "Google Sans", Inter, system-ui, sans-serif';

interface DisclaimerNoteProps {
  text?: string;
}

const DEFAULT_TEXT =
  "This data overview was crafted using Gemini to help you navigate the statistical variables available in Data Commons. Think of it as a starting point for your exploration, not an exhaustive answer. We encourage you to always double-check your findings against the original data linked on each chart.";

export default function DisclaimerNote({ text = DEFAULT_TEXT }: DisclaimerNoteProps) {
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
        <InfoIcon />
        <p
          className="m-0"
          style={{
            fontFamily: FONT_STACK,
            fontSize: 16,
            lineHeight: "24px",
            fontWeight: 500,
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

// Google Symbols 'info' rounded — 14×14 to match Figma's small icon
// (token layout_5IS08A: 14×14, fill #5C5F5E).
function InfoIcon() {
  return (
    <svg
      width={14}
      height={14}
      viewBox="0 0 24 24"
      fill={COLOR_TEXT}
      aria-hidden="true"
      style={{ flexShrink: 0, marginTop: 4 }}
    >
      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z" />
    </svg>
  );
}
