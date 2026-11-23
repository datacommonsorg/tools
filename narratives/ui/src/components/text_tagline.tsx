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
  link: TaglineLink;
}

/**
 * The tagline text. When `link.text` appears in it, that phrase becomes a
 * button that opens a native modal `<dialog>`, which supplies the focus trap,
 * Escape to close, and focus return to the button. The dialog is portaled to
 * `document.body` because a `<dialog>` cannot sit inside the tagline's `<p>`.
 */
export function TaglineText({ tagline, link }: TaglineTextProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const start = link.text ? tagline.indexOf(link.text) : -1;
  if (start === -1) {
    return tagline;
  }

  const end = start + link.text.length;
  return (
    <>
      {tagline.slice(0, start)}
      {/* The button text has the same color as the surrounding text. It is
          marked as clickable by the highlight behind it. */}
      <button
        type="button"
        className="hover:text-theme-primary text-subtle bg-tagline-link/50 rounded-sm px-1"
        aria-haspopup="dialog"
        onClick={() => dialogRef.current?.showModal()}
      >
        {link.text}
      </button>
      {tagline.slice(end)}
      {createPortal(
        <dialog
          ref={dialogRef}
          aria-labelledby={titleId}
          // A click on the backdrop closes the dialog.
          closedby="any"
          // On narrow screens, the dialog is 2rem narrower than the viewport,
          // which leaves 16px of space on each side.
          className="m-auto w-[calc(100%-2rem)] max-w-198 rounded-dialog dialog-surface dialog-motion text-left shadow-elevated backdrop:bg-scrim/30"
        >
          <div className="flex flex-col gap-6 px-11 pt-14">
            {link.sections.map((section, index) => (
              <section key={index} className="flex flex-col gap-3">
                <h2
                  // The dialog uses the first heading as its accessible name.
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
              className="h-14 px-6 rounded-full text-body-large-emphasized bg-theme-primary text-on-theme-primary hover:opacity-90 transition-opacity"
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
