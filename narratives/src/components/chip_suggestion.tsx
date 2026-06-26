/**
 * @fileoverview Suggestion chip — a single clickable starter-question pill
 * shown on the empty Data Agent home screen.
 */

interface ChipSuggestionProps {
  text: string;
  onClick?: (text: string) => void;
}

// Logically grouped Tailwind classes for readability.
const CHIP_CLASSES = [
  // Layout & dimensions
  "w-[250px] min-h-[72px] px-4 py-3 flex items-center justify-center sm:justify-start",
  // Borders & background
  "border border-gray-200 rounded-[20px] bg-white",
  // Typography & alignment
  "text-body-medium text-on-surface text-left",
  // Motion & transitions
  "cursor-pointer transition-all duration-200",
  // Shadow states
  "shadow-[0_1px_3px_rgba(0,0,0,0.02)] hover:shadow-md",
  // Interactive hover state
  "hover:bg-gray-50",
].join(" ");

/**
 * Renders a single suggestion chip. Clicking it forwards the chip text to the
 * optional `onClick` handler so the parent can pre-fill the prompt input.
 */
export function ChipSuggestion({ text, onClick }: ChipSuggestionProps) {
  return (
    <button
      type="button"
      onClick={() => onClick?.(text)}
      className={CHIP_CLASSES}
    >
      {text}
    </button>
  );
}
