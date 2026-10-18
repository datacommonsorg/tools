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
 * @fileoverview Renders the loading skeleton shown while the first answer is prepared.
 */

import { useEffect, useState } from 'react';
import { STREAM_WORD_CLASS } from '@/src/utils/rehype_stream_words';

const PARAGRAPHS = 3;
const LINES_PER_PARAGRAPH = 4;
/** Stagger between lines. */
const LINE_STAGGER_MS = 120;

/** Random 60–100% widths, for ragged text. */
function randomLineWidths(): number[][] {
  return Array.from({ length: PARAGRAPHS }, () =>
    Array.from({ length: LINES_PER_PARAGRAPH }, () => 60 + Math.random() * 40),
  );
}

interface SkeletonCardProps {
  query: string;
}

/** Loading placeholder card shown while the agent works on `query`. */
export function SkeletonCard({ query }: SkeletonCardProps) {
  const [lineWidths] = useState(randomLineWidths);
  // Mount at 0% width, grow on the next frame.
  const [grown, setGrown] = useState(false);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setGrown(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  return (
    <div className="relative w-full rounded-card overflow-hidden bg-linear-to-b from-surface-narrative to-transparent">
      {/* Overlay so the border fades without the content. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 rounded-card border border-border mask-[linear-gradient(to_bottom,black,transparent)]"
      ></div>
      {/* Matches AnswerPanel so nothing shifts on handoff. */}
      <div className="py-3 pr-3 pl-5 border-b border-border bg-surface">
        <span className="block truncate text-label-large text-on-surface">
          {query}
        </span>
      </div>
      <div className="markdown-stream p-4 sm:p-6 flex flex-col gap-6">
        <div className="absolute top-50 bottom-0 right-0 left-0 bg-linear-to-b from-transparent to-surface z-10"></div>
        {lineWidths.map((paragraph, p) => (
          <div key={p} className="flex flex-row gap-4 items-start">
            <div className="flex flex-col gap-2 flex-1">
              {paragraph.map((width, l) => (
                // Wrapper fades/grows; inner bar pulses.
                <div
                  key={l}
                  className={`${STREAM_WORD_CLASS} motion-safe:transition-[width] duration-500 ease-in-out`}
                  style={{
                    width: `${grown ? width : 0}%`,
                    animationDelay: `${(p * LINES_PER_PARAGRAPH + l) * LINE_STAGGER_MS}ms`,
                    transitionDelay: `${(p * LINES_PER_PARAGRAPH + l) * LINE_STAGGER_MS}ms`,
                  }}
                >
                  <div className="h-3 rounded animate-pulse bg-skeleton-bar"></div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
