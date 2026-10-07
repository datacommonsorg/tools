/*
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
 * @fileoverview Renders the prompt box shared by the landing view and the chat
 * footer: an autosizing textarea with a submit (or stop) button, an elevated
 * pill that expands into a card as the text wraps, and a rotating gradient
 * ring while it holds focus.
 */

import { useRef } from 'react';
import { useTextareaAutosize } from '@/src/hooks/use_textarea_autosize';
import { SendIcon } from './icons';
import { Tooltip } from './tooltip';

interface PromptInputProps {
  value: string;
  /** Also the textarea's accessible name; replaced on screen while streaming. */
  placeholder: string;
  onValueChange: (value: string) => void;
  onSubmit: () => void;
  /** While true the textarea is locked and the button becomes a stop control. */
  isStreaming?: boolean;
  onStop?: () => void;
}

/**
 * Prompt box: a 56px pill while the text fits on one line, the expanded input
 * radius once it wraps. The focus ring is a sibling stacked in the same grid
 * cell as the content, so it overlays the box without absolute positioning.
 */
export function PromptInput({
  value,
  placeholder,
  onValueChange,
  onSubmit,
  isStreaming = false,
  onStop,
}: PromptInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isExpanded = useTextareaAutosize(textareaRef, value);
  const actionLabel = isStreaming ? 'Stop Response' : 'Submit';
  // The one gate for every submit path: the button, the form and Enter.
  const canSubmit = !isStreaming && value.trim().length > 0;
  const submit = () => {
    if (canSubmit) onSubmit();
  };

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      // Pill radius is exactly half the 56px min-height, not rounded-full: a
      // 9999px radius stays visually round for the whole transition and snaps
      // to rounded-input at the end.
      className={`group grid w-full max-w-[720px] mx-auto bg-surface shadow-elevated motion-safe:transition-[border-radius] duration-200 ease-out ${
        isExpanded ? 'rounded-input' : 'rounded-[28px]'
      }`}
    >
      <span
        aria-hidden="true"
        className="glow-ring col-start-1 row-start-1 pointer-events-none opacity-0 group-focus-within:opacity-100 group-focus-within:[animation-play-state:running] motion-safe:transition-opacity duration-200 ease-linear"
      />

      {/* 8px + 40px button + 8px = the 56px pill. The button sits at the top
          so it stays on the first row as the box grows. */}
      <div className="col-start-1 row-start-1 flex items-start gap-3 p-2">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => onValueChange(e.target.value)}
          // The accessible name stays the prompt's own placeholder while the
          // visible one reports the stream.
          placeholder={isStreaming ? 'Streaming…' : placeholder}
          aria-label={placeholder}
          disabled={isStreaming}
          rows={1}
          // Caps at four lines (max-h-24); the autosize hook turns scrolling
          // on only past that cap.
          className="flex-1 bg-transparent outline-none resize-none max-h-24 overflow-y-hidden text-body-large leading-6 text-on-surface caret-brand-primary placeholder:text-placeholder pl-4 my-2 motion-safe:transition-[height] duration-200 ease-out"
          onKeyDown={(e) => {
            // Shift+Enter inserts a newline; Enter mid-IME-composition commits
            // the composition rather than submitting.
            if (
              e.key === 'Enter' &&
              !e.shiftKey &&
              !e.nativeEvent.isComposing
            ) {
              e.preventDefault();
              submit();
            }
          }}
        />
        {/* One button, two jobs — so its name changes with its job. */}
        <Tooltip label={actionLabel}>
          <button
            type={isStreaming ? 'button' : 'submit'}
            onClick={isStreaming ? onStop : undefined}
            disabled={!isStreaming && !canSubmit}
            aria-label={actionLabel}
            // Expanded: nudge the button in from the corner so it clears the
            // larger card radius. Translated, not margined, so the textarea
            // beside it does not reflow during the transition.
            className={`w-10 h-10 shrink-0 rounded-full flex items-center justify-center bg-surface-blue enabled:hover:bg-button-hover transition-colors motion-safe:transition-[translate,background-color] duration-200 ease-out disabled:opacity-50 ${
              isExpanded ? '-translate-x-1.25 translate-y-1.25' : ''
            }`}
          >
            {isStreaming ? (
              <div className="w-3 h-3 rounded-sm bg-brand-primary" />
            ) : (
              <SendIcon size="xs" />
            )}
          </button>
        </Tooltip>
      </div>
    </form>
  );
}
