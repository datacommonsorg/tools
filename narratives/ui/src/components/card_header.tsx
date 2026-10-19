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
  /** The user's question, shown as the card title. */
  title: string;
  /** Toolbar actions on the right; absent while the answer is in flight. */
  children?: ReactNode;
}

/**
 * Card title with a toolbar slot. The skeleton and the answer both render it,
 * so the header stays put when one crossfades into the other.
 */
export function CardHeader({ title, children }: CardHeaderProps) {
  return (
    <div className="flex items-center gap-3 py-3 pr-3 pl-5 border-b border-border bg-surface">
      {/* On screen this is a one-line card title, so it truncates. In the
          exported PDF it is the document's heading and has to be readable in
          full, so the print rules in index.css undo the truncation and size
          it up — hence the hook class rather than styling it twice. */}
      <span
        className="flex-1 truncate print-question text-label-large text-on-surface"
        title={title}
      >
        {title}
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
