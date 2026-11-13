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
 * @fileoverview Renders the header shared by the answer card and its loading skeleton.
 */

import type { ReactNode } from 'react';

interface CardHeaderProps {
  /**
   * The card title: a label with the citation count once the answer presents
   * data, a no-matching-data label when it has none, or an empty string,
   * which leaves the header empty. Omitted while the answer loads, when the
   * header shows a ghost line instead.
   */
  title?: string;
  /** Toolbar actions on the right; absent while the answer is in flight. */
  children?: ReactNode;
}

/**
 * Card title with a toolbar slot. The skeleton and the answer both render it,
 * so the header stays put when one crossfades into the other.
 */
export function CardHeader({ title, children }: CardHeaderProps) {
  return (
    <div className="flex items-start gap-3 py-2 pr-2 pl-5 border-b border-border bg-surface">
      {/* Wraps onto as many lines as the question needs. utils/download_pdf.ts
          finds this class and restyles it as the PDF's heading. */}
      <span className="flex-1 min-w-0 py-1.5 wrap-break-word print-question text-label-large text-on-surface">
        {title ?? (
          // A ghost line like the body's, sized inside one text line so the
          // header keeps its height when the title replaces it.
          <span
            aria-hidden="true"
            className="inline-block align-middle h-3 w-48 max-w-full rounded animate-pulse bg-skeleton-bar"
          />
        )}
      </span>
      {/* Always mounted at the pill's 32px height so the header doesn't grow
          when the actions appear. */}
      <div
        className="flex items-center gap-1 shrink-0 min-h-8"
        data-non-print="true"
      >
        {children}
      </div>
    </div>
  );
}
