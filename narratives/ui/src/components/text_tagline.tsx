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
 * @fileoverview Renders the landing tagline, turning the configured phrase
 * into a link that opens a modal dialog.
 */

import { useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { Link } from '@/src/components/link';
import { TAGLINE_DIALOG_DISMISS_LABEL } from '@/src/config/copy_landing';
import type { TaglineLink } from '@/src/config/instance_config';

interface TaglineTextProps {
  tagline: string;
  link: TaglineLink | null;
}

/**
 * The tagline text. When `link.text` appears in it, that phrase becomes a
 * button that opens a native modal `<dialog>`, which supplies the focus trap,
 * Escape to close, and focus return to the button. The dialog is portaled to
 * `document.body` because a `<dialog>` cannot sit inside the tagline's `<p>`.
 */
export function TaglineText({ tagline, link }: TaglineTextProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  // Whether the current press started on the backdrop, so a text selection
  // that starts inside the dialog and ends outside it does not close it.
  const isPressOnBackdropRef = useRef(false);
  const titleId = useId();
  const start = link ? tagline.indexOf(link.text) : -1;
  if (!link || !link.text || start === -1) {
    return tagline;
  }

  const end = start + link.text.length;
  return (
    <>
      {tagline.slice(0, start)}
      {/* Underlined, not only colored: the link color is too close to the
          tagline color to mark the link on its own (WCAG 1.4.1). */}
      <button
        type="button"
        className="text-theme-primary underline"
        aria-haspopup="dialog"
        onClick={() => dialogRef.current?.showModal()}
      >
        {link.text}
      </button>
      {tagline.slice(end)}
      {createPortal(
        // biome-ignore lint/a11y/useKeyWithClickEvents: the click only dismisses on the backdrop; the native dialog already closes on Escape.
        <dialog
          ref={dialogRef}
          aria-labelledby={titleId}
          // A press and a release both on the backdrop target the dialog
          // itself; only that click closes it.
          onPointerDown={(event) => {
            isPressOnBackdropRef.current = event.target === event.currentTarget;
          }}
          onClick={(event) => {
            if (
              isPressOnBackdropRef.current &&
              event.target === event.currentTarget
            ) {
              event.currentTarget.close();
            }
          }}
          // The width keeps a 16px gutter on each side on narrow screens.
          className="m-auto w-[calc(100%-2rem)] max-w-198 rounded-dialog dialog-surface dialog-motion text-left shadow-elevated backdrop:bg-scrim/30"
        >
          <div className="flex flex-col gap-6 px-11 pt-14">
            {link.sections.map((section, index) => (
              <section key={section.title} className="flex flex-col gap-3">
                <h2
                  // The first heading names the dialog.
                  id={index === 0 ? titleId : undefined}
                  className="text-headline-small-emphasized text-headline"
                >
                  {section.title}
                </h2>
                <p className="text-body-large text-on-surface-variant">
                  {section.body}
                </p>
              </section>
            ))}
          </div>
          <div className="flex flex-wrap items-center justify-end gap-4 p-6 pl-2">
            {link.sources && (
              <Link
                href={link.sources.href}
                className="flex items-center h-14 px-6 rounded-full text-body-large-emphasized text-theme-primary hover:bg-button-hover transition-colors"
              >
                {link.sources.label}
              </Link>
            )}
            <button
              type="button"
              className="h-14 px-6 rounded-full text-body-large-emphasized bg-theme-primary text-white hover:opacity-90 transition-opacity"
              onClick={() => dialogRef.current?.close()}
            >
              {TAGLINE_DIALOG_DISMISS_LABEL}
            </button>
          </div>
        </dialog>,
        document.body,
      )}
    </>
  );
}
