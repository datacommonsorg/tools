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
 * @fileoverview Renders an answer's closing list of the measures Data Commons
 * lacks, from the list the agent parsed out of the answer's Data gaps block
 * (`workflows/data_gaps.py`).
 */

import { useId } from 'react';
import { DATA_GAPS_HEADING } from '@/src/config/copy_chat';

interface DataGapsSectionProps {
  /** The line that introduces the list, or `''` when the answer has none. */
  intro: string;
  /** The missing measures, as plain text. */
  items: string[];
}

/**
 * A titled section after the answer: the heading, the intro line, and a
 * bulleted list of the missing measures. The panel hides it until the
 * answer's reveal ends, as it does the citations.
 */
export function DataGapsSection({ intro, items }: DataGapsSectionProps) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="mt-6">
      <h2
        id={headingId}
        className="text-title-large-emphasized text-on-surface mb-2"
      >
        {DATA_GAPS_HEADING}
      </h2>
      {intro && (
        <p className="m-0 mb-2 text-body-medium text-on-surface">{intro}</p>
      )}
      <ul className="list-disc ml-6 flex flex-col gap-1 text-body-medium text-on-surface">
        {items.map((item, index) => (
          <li
            key={`${item}-${index}`}
            className="min-w-0 wrap-anywhere leading-5"
          >
            {item}
          </li>
        ))}
      </ul>
    </section>
  );
}
