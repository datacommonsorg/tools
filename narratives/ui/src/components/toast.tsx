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

import { useEffect } from 'react';
import { createPortal } from 'react-dom';

/** How long the snackbar stays up. M3 guidance is 4-10s for a short message. */
const VISIBLE_MS = 5000;

interface ToastProps {
  message: string;
  /** Optional trailing action, e.g. "Open file". */
  actionLabel?: string;
  onAction?: () => void;
  onDismiss: () => void;
}

/**
 * A single snackbar, pinned top-right above all other layers.
 *
 * Deliberately self-dismissing rather than a queue: the only caller is the PDF
 * export, one message at a time. `role="status"` rather than `alert` — this
 * confirms something the user asked for, so it should not interrupt them.
 */
export function Toast({
  message,
  actionLabel,
  onAction,
  onDismiss,
}: ToastProps) {
  useEffect(() => {
    const timer = window.setTimeout(onDismiss, VISIBLE_MS);
    return () => window.clearTimeout(timer);
  }, [onDismiss]);

  // Portalled to body: the caller sits inside the answer panel, whose stacking
  // context would otherwise trap z-50 beneath the sticky header.
  return createPortal(
    <div
      role="status"
      aria-live="polite"
      data-non-print="true"
      className={`fixed top-3 right-6 z-50 flex items-center gap-2 min-h-12 max-w-[min(560px,calc(100vw-2rem))] rounded bg-theme-primary text-white text-body-medium shadow-lg ${
        actionLabel ? 'py-1.5 pl-4 pr-2' : 'py-3.5 px-4'
      }`}
    >
      <span className="flex-1">{message}</span>
      {actionLabel && (
        <button
          type="button"
          onClick={() => {
            onAction?.();
            onDismiss();
          }}
          className="px-3 py-2.5 rounded border-0 bg-transparent text-white text-label-large"
        >
          {actionLabel}
        </button>
      )}
    </div>,
    document.body,
  );
}
