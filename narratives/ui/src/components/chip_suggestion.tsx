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
  'w-full sm:w-[250px] min-h-[72px] px-4 py-3 flex items-center justify-center sm:justify-start',
  // Borders & background
  'border border-outline rounded-chip bg-surface',
  // Typography & text alignment
  'text-body-medium text-on-surface text-left',
  // Motion & transitions
  'transition-all duration-200',
  // Shadow states
  'shadow-[0_1px_3px_rgba(0,0,0,0.02)] hover:shadow-md',
  // Interactive hover states
  'hover:bg-surface-soft cursor-pointer',
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
