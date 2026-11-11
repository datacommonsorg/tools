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
 * @fileoverview Debug panel: the icon button and the tabbed slide-over showing
 * turn details, provenance, trajectory thoughts, tool calls, and response blocks.
 */

import {
  AnimatePresence,
  domAnimation,
  LazyMotion,
  m,
  useReducedMotion,
} from 'motion/react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { BugReportIcon } from '@/src/components/icons';
import { DebugPanelBody } from '@/src/components/panel_debug/body_debug';
import { DEBUG_PANEL_COPY } from '@/src/components/panel_debug/copy_debug';
import { buildTurnDebugReport } from '@/src/components/panel_debug/report_debug';
import { EASE_OUT } from '@/src/config/motion';
import type { ChatTurn } from '@/src/hooks/use_sse_chat';

/** Duration of the debug drawer's slide transition, in seconds. */
const DRAWER_TRANSITION_SECONDS = 0.25;

/** Duration of the backdrop scrim's fade transition, in seconds. */
const SCRIM_TRANSITION_SECONDS = 0.2;

/** Milliseconds before the copy confirmation or failure notice resets. */
const COPY_STATUS_RESET_MS = 2_000;

type CopyStatus = 'idle' | 'copied' | 'failed';

const COPY_BUTTON_LABELS: Record<CopyStatus, string> = {
  idle: DEBUG_PANEL_COPY.copyJsonButtonLabel,
  copied: DEBUG_PANEL_COPY.copiedStatus,
  failed: DEBUG_PANEL_COPY.copyFailedStatus,
};

const COPY_LIVE_MESSAGES: Record<CopyStatus, string> = {
  idle: '',
  copied: DEBUG_PANEL_COPY.copiedStatus,
  failed: DEBUG_PANEL_COPY.copyFailedStatus,
};

const SCRIM_MOTION_PROPS = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
  transition: { duration: SCRIM_TRANSITION_SECONDS, ease: EASE_OUT },
};

const DRAWER_MOTION_PROPS = {
  initial: { x: '100%' },
  animate: { x: 0 },
  exit: { x: '100%' },
  transition: { duration: DRAWER_TRANSITION_SECONDS, ease: EASE_OUT },
};

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"]):not([disabled])';

/** Reports whether `element` is visible and tabbable inside `container`. */
const isElementVisibleWithin = (
  element: HTMLElement,
  container: HTMLElement,
): boolean => {
  if (
    element.tabIndex < 0 ||
    element.closest('[hidden], [inert], [aria-hidden="true"]')
  ) {
    return false;
  }
  const visibility = window.getComputedStyle(element).visibility;
  if (visibility === 'hidden' || visibility === 'collapse') {
    return false;
  }
  let current: HTMLElement | null = element;
  while (current && current !== container) {
    if (window.getComputedStyle(current).display === 'none') {
      return false;
    }
    current = current.parentElement;
  }
  return true;
};

/** Returns enabled, visible focusable descendants of `container` in DOM order. */
const getFocusableElements = (container: HTMLElement): HTMLElement[] =>
  Array.from(
    container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
  ).filter((element) => isElementVisibleWithin(element, container));

/** Wraps Tab and Shift+Tab focus at the boundaries of `dialog`. */
const trapDialogFocus = (
  event: KeyboardEvent,
  dialog: HTMLElement | null,
): void => {
  if (!dialog?.isConnected) {
    return;
  }
  const focusables = getFocusableElements(dialog);
  if (focusables.length === 0) {
    event.preventDefault();
    return;
  }
  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  const active = document.activeElement;
  if (!dialog.contains(active)) {
    event.preventDefault();
    first.focus();
    return;
  }
  if (event.shiftKey && active === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && active === last) {
    event.preventDefault();
    first.focus();
  }
};

interface DebugPanelProps {
  turn: ChatTurn;
}

/**
 * The icon button that opens the debug panel, plus the slide-over it opens.
 *
 * Rendered as an overlay drawer rather than inline because tool-call arguments
 * and multi-kilobyte raw responses would push the answer off screen. Out of
 * flow, it scrolls independently and can be dismissed.
 *
 * `TurnView` wraps `AnswerPanel` in `motion-safe:animate-stream-in`
 * (`animation-fill-mode: both` on `opacity`), creating a permanent stacking
 * context that traps fixed descendants beneath the sticky header and prompt
 * bar (`z-[5]`). Rendering the scrim and dialog through `createPortal` into
 * `document.body` escapes that stacking context.
 */
export const DebugPanel = ({ turn }: DebugPanelProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const [hasOpened, setHasOpened] = useState(false);
  const [copyStatus, setCopyStatus] = useState<CopyStatus>('idle');
  const copyTimerRef = useRef<number | null>(null);
  const shouldReduceMotion = Boolean(useReducedMotion());
  const triggerButtonRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const wasOpenRef = useRef(false);
  const prevTurnRef = useRef(turn);

  const clearCopyTimer = useCallback(() => {
    if (copyTimerRef.current !== null) {
      window.clearTimeout(copyTimerRef.current);
      copyTimerRef.current = null;
    }
  }, []);

  const showCopyStatus = useCallback(
    (status: CopyStatus) => {
      clearCopyTimer();
      setCopyStatus(status);
      copyTimerRef.current = window.setTimeout(() => {
        setCopyStatus('idle');
        copyTimerRef.current = null;
      }, COPY_STATUS_RESET_MS);
    },
    [clearCopyTimer],
  );

  useEffect(() => {
    return () => {
      clearCopyTimer();
    };
  }, [clearCopyTimer]);

  useEffect(() => {
    if (prevTurnRef.current !== turn) {
      prevTurnRef.current = turn;
      clearCopyTimer();
      setCopyStatus('idle');
    }
  }, [turn, clearCopyTimer]);

  // Move focus into the dialog on open, trap Tab inside it, close on Escape,
  // and restore focus to the trigger when closing if it remains connected.
  useEffect(() => {
    if (!isOpen) {
      clearCopyTimer();
      setCopyStatus('idle');
      if (wasOpenRef.current && triggerButtonRef.current?.isConnected) {
        triggerButtonRef.current.focus();
      }
      wasOpenRef.current = false;
      return;
    }
    wasOpenRef.current = true;
    if (closeButtonRef.current?.isConnected) {
      closeButtonRef.current.focus();
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        setIsOpen(false);
        return;
      }
      if (event.key === 'Tab') {
        trapDialogFocus(event, dialogRef.current);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, clearCopyTimer]);

  const openDrawer = () => {
    setHasOpened(true);
    setIsOpen(true);
  };

  const handleCopyJson = async () => {
    if (typeof navigator.clipboard?.writeText !== 'function') {
      showCopyStatus('failed');
      return;
    }
    try {
      const report = buildTurnDebugReport(turn);
      await navigator.clipboard.writeText(JSON.stringify(report, null, 2));
      showCopyStatus('copied');
    } catch {
      showCopyStatus('failed');
    }
  };

  const drawerPortal =
    hasOpened && typeof document !== 'undefined'
      ? createPortal(
          <LazyMotion features={domAnimation} strict>
            <AnimatePresence>
              {isOpen && (
                <m.div
                  key="debug-scrim"
                  {...(!shouldReduceMotion && SCRIM_MOTION_PROPS)}
                  data-non-print="true"
                  className="fixed inset-0 z-30 bg-scrim/30"
                  onClick={() => setIsOpen(false)}
                  aria-hidden="true"
                />
              )}
              {isOpen && (
                <m.aside
                  key="debug-drawer"
                  ref={dialogRef}
                  {...(!shouldReduceMotion && DRAWER_MOTION_PROPS)}
                  role="dialog"
                  aria-modal="true"
                  aria-label={DEBUG_PANEL_COPY.title}
                  data-non-print="true"
                  className="fixed top-0 right-0 h-full w-140 max-w-screen z-40 bg-surface border-l border-outline shadow-lg flex flex-col"
                >
                  <header className="flex items-start justify-between gap-3 p-4 border-b border-outline shrink-0">
                    <div className="flex flex-col gap-0.5 min-w-0">
                      <h3 className="text-body-large-emphasized text-on-surface">
                        {DEBUG_PANEL_COPY.title}
                      </h3>
                      <p className="text-body-medium text-on-surface-variant truncate">
                        {turn.userMessage}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        type="button"
                        onClick={handleCopyJson}
                        className="min-h-11 px-3 py-1.5 rounded-full border border-border bg-surface text-label-large text-on-surface hover:bg-button-hover transition-colors inline-flex items-center justify-center"
                      >
                        {COPY_BUTTON_LABELS[copyStatus]}
                      </button>
                      <button
                        ref={closeButtonRef}
                        type="button"
                        onClick={() => setIsOpen(false)}
                        aria-label={DEBUG_PANEL_COPY.closeButtonLabel}
                        className="w-11 h-11 shrink-0 flex items-center justify-center rounded-full hover:bg-button-hover transition-colors text-on-surface-variant text-body-large-emphasized"
                      >
                        <span aria-hidden="true">
                          {DEBUG_PANEL_COPY.closeButtonGlyph}
                        </span>
                      </button>
                    </div>
                    <div aria-live="polite" className="sr-only">
                      {COPY_LIVE_MESSAGES[copyStatus]}
                    </div>
                  </header>

                  <div className="flex-1 min-h-0 flex flex-col">
                    <DebugPanelBody turn={turn} />
                  </div>
                </m.aside>
              )}
            </AnimatePresence>
          </LazyMotion>,
          document.body,
        )
      : null;

  return (
    <>
      {/* `download_pdf.ts` and `index.css` strip `[data-non-print="true"]`
          elements from print and PDF exports. */}
      <button
        ref={triggerButtonRef}
        type="button"
        onClick={openDrawer}
        aria-label={DEBUG_PANEL_COPY.openButtonLabel}
        aria-expanded={isOpen}
        title={DEBUG_PANEL_COPY.openButtonTitle}
        data-non-print="true"
        className="group w-11 h-11 flex items-center justify-center rounded-full hover:bg-button-hover transition-colors text-error"
      >
        <BugReportIcon
          size="sm"
          className="motion-safe:transition-transform motion-safe:duration-400 motion-safe:group-hover:rotate-25"
        />
      </button>
      {drawerPortal}
    </>
  );
};
