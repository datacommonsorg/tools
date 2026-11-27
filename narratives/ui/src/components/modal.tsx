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
 * @fileoverview Renders a modal window as a native `<dialog>`, and exports the
 * card and button styling every modal shares.
 */

import { type ReactNode, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

/**
 * Card max-width utilities a modal can use, written out in full so Tailwind's
 * scanner emits them.
 */
type ModalWidth = 'max-w-198' | 'max-w-2xl';

/** Default card width: the widest of the app's modals. */
const DEFAULT_MODAL_WIDTH: ModalWidth = 'max-w-198';

/**
 * Card styling shared by every modal, including ones that cannot use
 * {@link Modal}. Width is applied separately so each modal can set its own.
 */
export const MODAL_CARD_CLASSES = 'rounded-dialog shadow-elevated text-left';

/**
 * The filled primary action of a modal. Temporary: a button component
 * replaces it in a follow-up.
 */
export const PRIMARY_BUTTON_CLASSES =
  'h-14 px-6 rounded-full text-body-large-emphasized bg-theme-primary text-on-theme-primary hover:opacity-90 transition-opacity';

interface ModalProps {
  open: boolean;
  /**
   * Called when the dialog closes. Omitting it makes the modal impossible to
   * dismiss: neither the backdrop nor Escape closes it.
   */
  onClose?: () => void;
  'aria-labelledby': string;
  /** Max-width utility that replaces {@link DEFAULT_MODAL_WIDTH}. */
  width?: ModalWidth;
  /** Surface, padding, and layout classes. Set the width with `width`. */
  className?: string;
  children: ReactNode;
}

/**
 * A modal native `<dialog>`, opened with `showModal()` while `open` is true.
 * The browser supplies the top layer, the focus trap, Escape, `inert` on the
 * rest of the page, and focus return to the opener. A dismissible modal also
 * closes on a backdrop click. It is portaled to `document.body` because a
 * `<dialog>` cannot sit inside phrasing content such as a `<p>`.
 */
export function Modal({
  open,
  onClose,
  'aria-labelledby': labelledBy,
  width = DEFAULT_MODAL_WIDTH,
  className = '',
  children,
}: Readonly<ModalProps>) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const isDismissible = onClose !== undefined;

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog === null) return;
    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  return createPortal(
    <dialog
      ref={dialogRef}
      aria-labelledby={labelledBy}
      closedby={isDismissible ? 'any' : 'none'}
      onClose={onClose}
      // Browsers without `closedby` still fire `cancel` on Escape.
      onCancel={isDismissible ? undefined : (event) => event.preventDefault()}
      // On narrow screens, the dialog is 2rem narrower than the viewport,
      // which leaves 16px of space on each side.
      className={`m-auto w-[calc(100%-2rem)] ${width} ${MODAL_CARD_CLASSES} dialog-motion backdrop:bg-scrim/30 ${className}`}
    >
      {children}
    </dialog>,
    document.body,
  );
}
