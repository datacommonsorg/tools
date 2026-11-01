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

import { useReducedMotion } from 'motion/react';
import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

/** How long the snackbar stays up. M3 guidance is 4-10s for a short message. */
export const VISIBLE_MS = 5000;

/** Duration of `--animate-exit` in index.css; toast.test.tsx checks they match. */
export const EXIT_MS = 200;

interface ToastProps {
  message: string;
  onDismiss: () => void;
}

/**
 * A single snackbar, pinned bottom-right above the page (tooltips still layer
 * over it). Fades and slides up in, then back down out before `onDismiss`
 * unmounts it.
 *
 * Deliberately self-dismissing rather than a queue: the only caller is the PDF
 * export, one message at a time. `role="status"` rather than `alert` — this
 * confirms something the user asked for, so it should not interrupt them.
 */
export function Toast({ message, onDismiss }: ToastProps) {
  const reduceMotion = useReducedMotion();
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setLeaving(true), VISIBLE_MS);
    return () => window.clearTimeout(timer);
  }, []);

  // Stay mounted until the exit animation has played. A timer rather than
  // `animationend`, which never fires when reduced motion skips the animation.
  useEffect(() => {
    if (!leaving) return;
    const timer = window.setTimeout(onDismiss, reduceMotion ? 0 : EXIT_MS);
    return () => window.clearTimeout(timer);
  }, [leaving, onDismiss, reduceMotion]);

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
      className={`fixed bottom-3 left-4 right-4 sm:left-auto sm:right-6 sm:max-w-xl z-50 flex items-center justify-center min-h-12 py-3.5 px-4 rounded bg-theme-primary text-on-theme-primary text-body-medium text-center shadow-lg ${animation}`}
    >
      {message}
    </div>,
    document.body,
  );
}
