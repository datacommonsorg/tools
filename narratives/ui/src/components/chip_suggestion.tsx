/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
 * implied. See the License for the specific language governing
 * permissions and limitations under the License.
 */

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
  'flex w-full min-h-18 items-center justify-center px-4 py-3 sm:w-62.5 sm:justify-start',
  // Borders & background
  'rounded-chip border border-border bg-surface-narrative',
  // Typography & text alignment
  'text-left text-body-medium text-on-surface',
  // Shadow states
  'shadow-xs hover:shadow-md',
  // Interaction & focus
  'cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2',
  // Motion: hover/focus lift, skipped under reduced motion
  'transition duration-200 motion-safe:hover:-translate-y-1 motion-safe:focus-visible:-translate-y-1',
].join(' ');

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
