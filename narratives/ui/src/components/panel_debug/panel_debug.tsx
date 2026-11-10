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
 * @fileoverview Debug panel: the icon button and the slide-over showing which
 * variables and data sources an answer used.
 */

import { useEffect, useRef, useState } from 'react';
import { InspectIcon } from '@/src/components/icons';
import { DebugPanelBody } from '@/src/components/panel_debug/body_debug';
import { DEBUG_PANEL_COPY } from '@/src/components/panel_debug/copy_debug';
import type { ChatTurn } from '@/src/hooks/use_sse_chat';

/**
 * Reports whether the debug panel is enabled, that is, whether the page was
 * opened with `?debug=provenance`. Evaluated per render (not at module load)
 * so it reacts to client-side navigation and stays safe under SSR and tests.
 */
export const isDebugPanelEnabled = (): boolean =>
  typeof window !== 'undefined' &&
  new URLSearchParams(window.location.search).get('debug') === 'provenance';

interface DebugPanelProps {
  turn: ChatTurn;
}

/**
 * The icon button that opens the debug panel, plus the slide-over it opens.
 * Renders nothing for a turn without tool calls.
 *
 * Rendered as an overlay drawer rather than inline because tool-call arguments
 * and multi-kilobyte raw responses would push the answer off screen. Out of
 * flow, it scrolls independently and can be dismissed.
 *
 * Follows drawer_menu.tsx: a scrim over the page, the panel above it, closed
 * by the button, the scrim, or Escape.
 */
export const DebugPanel = ({ turn }: DebugPanelProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  // Escape closes, and focus moves into the panel so keyboard focus does not
  // stay behind the scrim.
  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    };
    document.addEventListener('keydown', closeOnEscape);
    closeButtonRef.current?.focus();
    return () => document.removeEventListener('keydown', closeOnEscape);
  }, [isOpen]);

  const hasToolCalls = turn.toolCalls.length > 0;
  if (!hasToolCalls) {
    return null;
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        aria-label={DEBUG_PANEL_COPY.openButtonLabel}
        aria-expanded={isOpen}
        title={DEBUG_PANEL_COPY.openButtonTitle}
        className="w-9 h-9 flex items-center justify-center rounded-full bg-transparent cursor-pointer hover:bg-button-hover transition-colors text-on-surface-variant"
      >
        <InspectIcon size="sm" />
      </button>

      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-30 bg-scrim/30"
            onClick={() => setIsOpen(false)}
            aria-hidden="true"
          />
          <aside
            role="dialog"
            aria-modal="true"
            aria-label={DEBUG_PANEL_COPY.title}
            className="fixed top-0 right-0 h-full w-140 max-w-screen z-40 bg-surface border-l border-outline shadow-lg flex flex-col"
          >
            <header className="flex items-start justify-between gap-3 p-4 border-b border-outline shrink-0">
              <div className="flex flex-col gap-0.5 min-w-0">
                <h3 className="m-0 text-title-medium text-on-surface">
                  {DEBUG_PANEL_COPY.title}
                </h3>
                <p className="m-0 text-body-medium text-on-surface-variant truncate">
                  {turn.userMessage}
                </p>
              </div>
              <button
                ref={closeButtonRef}
                type="button"
                onClick={() => setIsOpen(false)}
                aria-label={DEBUG_PANEL_COPY.closeButtonLabel}
                className="w-9 h-9 shrink-0 flex items-center justify-center rounded-full bg-transparent cursor-pointer hover:bg-button-hover transition-colors text-on-surface-variant text-title-medium"
              >
                {DEBUG_PANEL_COPY.closeButtonGlyph}
              </button>
            </header>

            <div className="flex-1 overflow-y-auto p-4">
              <DebugPanelBody turn={turn} />
            </div>
          </aside>
        </>
      )}
    </>
  );
};
