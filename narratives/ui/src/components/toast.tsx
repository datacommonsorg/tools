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
 * @fileoverview Material 3 snackbar shown after an action completes.
 */

import { X } from 'lucide-react';
import { useReducedMotion } from 'motion/react';
import { type RefObject, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

/** How long the snackbar stays up when left alone. */
export const VISIBLE_MS = 4000;

/** Countdown left after a hover or focus pause, long enough to move away. */
export const RESUME_MS = 1000;

/** Duration of `--animate-exit` in index.css; toast.test.tsx checks they match. */
export const EXIT_MS = 200;

/**
 * Touch-first devices skip the focus return: focusing a text field there opens
 * the on-screen keyboard, unasked, after a toast the user may not have touched.
 */
const TOUCH_QUERY = '(pointer: coarse)';

interface ToastProps {
  message: string;
  onDismiss: () => void;
  /**
   * Takes focus once the toast has closed, by timeout or the close button, so
   * the user lands back on the next action rather than on `<body>`. Skipped on
   * touch-first devices; see {@link TOUCH_QUERY}.
   */
  returnFocusRef?: RefObject<HTMLElement | null>;
}

/**
 * A single snackbar, pinned bottom-right above the page (tooltips still layer
 * over it), styled after the MUI Snackbar: inverse surface, left-aligned
 * message, close action at the trailing edge. Fades and slides up in, then
 * back down out before `onDismiss` unmounts it — whether it timed out or the
 * close button was pressed. The countdown pauses while the pointer is over the
 * toast or it holds focus, and resumes at {@link RESUME_MS} once both have
 * left.
 *
 * Deliberately self-dismissing rather than a queue: the only caller is the PDF
 * export, one message at a time. `role="status"` rather than `alert` — this
 * confirms something the user asked for, so it should not interrupt them.
 */
export function Toast({ message, onDismiss, returnFocusRef }: ToastProps) {
  const reduceMotion = useReducedMotion();
  const [leaving, setLeaving] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const paused = hovered || focused;
  const wasPausedRef = useRef(false);

  useEffect(() => {
    if (paused) {
      wasPausedRef.current = true;
      return;
    }
    const delay = wasPausedRef.current ? RESUME_MS : VISIBLE_MS;
    const timer = window.setTimeout(() => setLeaving(true), delay);
    return () => window.clearTimeout(timer);
  }, [paused]);

  // Stay mounted until the exit animation has played. A timer rather than
  // `animationend`, which never fires when reduced motion skips the animation.
  useEffect(() => {
    if (!leaving) return;
    const timer = window.setTimeout(
      () => {
        if (!window.matchMedia(TOUCH_QUERY).matches) {
          returnFocusRef?.current?.focus();
        }
        onDismiss();
      },
      reduceMotion ? 0 : EXIT_MS,
    );
    return () => window.clearTimeout(timer);
  }, [leaving, onDismiss, reduceMotion, returnFocusRef]);

  const animation = leaving
    ? 'motion-safe:animate-exit'
    : 'motion-safe:animate-enter';

  // Portalled to body: the caller sits inside the answer panel, whose stacking
  // context would otherwise trap z-50 beneath the sticky header.
  return createPortal(
    <div
      role="status"
      aria-live="polite"
      data-non-print="true"
      onPointerEnter={() => setHovered(true)}
      onPointerLeave={() => setHovered(false)}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      className={`fixed bottom-2 left-2 right-2 sm:bottom-6 sm:left-auto sm:right-6 sm:min-w-72 sm:max-w-xl z-50 flex items-center gap-2 py-1.5 px-4 rounded bg-inverse-surface text-on-inverse-surface text-body-medium shadow-lg ${animation}`}
    >
      <span className="py-2">{message}</span>
      {/* 44px hit area per FRONTEND.md; the negative margins keep the bar at
          MUI's 48px height and align the glyph with the trailing padding. */}
      <button
        type="button"
        aria-label="Close"
        onClick={() => setLeaving(true)}
        className="ml-auto -mr-3 -my-1.5 w-11 h-11 shrink-0 flex items-center justify-center rounded-full hover:bg-on-inverse-surface/10 transition-colors"
      >
        <X className="size-5" aria-hidden="true" />
      </button>
    </div>,
    document.body,
  );
}
