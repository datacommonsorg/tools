/**
 * @fileoverview Renders a clickable suggestion chip.
 */

interface SuggestionChipProps {
  text: string;
  onClick?: (text: string) => void;
}

/**
 * Logically grouped Tailwind classes for high readability.
 */
const CHIP_CLASSES = [
  // Layout & dimensions
  "w-full sm:w-[250px] min-h-[72px] px-4 py-3 flex items-center justify-center sm:justify-start",
  // Borders & background
  "border border-outline rounded-[20px] bg-surface",
  // Typography & text alignment
  "text-body-medium text-on-surface text-left",
  // Motion & transitions
  "transition-all duration-200",
  // Shadow states
  "shadow-[0_1px_3px_rgba(0,0,0,0.02)] hover:shadow-md",
  // Interactive hover states
  "hover:bg-surface-soft cursor-pointer",
].join(" ");

/** Renders one clickable prompt-suggestion chip. */
export function SuggestionChip({ text, onClick }: SuggestionChipProps) {
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
