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
 * @fileoverview Renders one section of an answer: an optional heading above a stats block and the chart that illustrates it.
 */

import { type ReactNode, useId } from 'react';
import { SectionHeading } from '@/src/components/heading_section';

/**
 * Classes of the section's own surface. The section is a size container, so
 * the row's breakpoint measures the width inside its padding.
 */
const SECTION_CLASS =
  '@container answer-section flex flex-col gap-4 px-5 py-4 rounded-card bg-surface-section border border-border';

/**
 * Classes of the stats and chart row. It stacks by default and splits into
 * two columns once the section's content box is 41.5rem wide and the chart
 * tile drew. Bullet and numbered stats share one indent and spacing, and the
 * last list adds no margin below the row.
 */
const ROW_CLASS = [
  'answer-pair grid grid-cols-1 items-start gap-x-5 gap-y-2',
  '[&_:is(ul,ol)]:pl-4 [&_:is(ul,ol)]:last-of-type:mb-0 [&_li]:pb-1 [&_li]:leading-6',
  '@min-[41.5rem]:has-[>.dc-charts-container]:grid-cols-2',
].join(' ');

/**
 * Extra class of a row whose stats are bullets: side by side, the bullets sit
 * 4px below the chart card's top edge, so the text does not touch the line.
 * A table keeps its own card edge level with the chart's.
 */
const ROW_TOP_SPACE_CLASS =
  '@min-[41.5rem]:has-[>.dc-charts-container]:[&>.markdown-body]:pt-1';

/**
 * Marker class of each section variant, by what sits beside the chart and
 * whether a lead-in heading opens it, so each variant can be styled on its
 * own.
 */
const VARIANT_CLASS = {
  list: { plain: 'answer-section-list', leadIn: 'answer-section-lead-in-list' },
  table: {
    plain: 'answer-section-table',
    leadIn: 'answer-section-lead-in-table',
  },
} as const;

interface AnswerSectionProps {
  /** The lead-in line that heads the section, as the model wrote it. */
  leadIn?: string;
  /** The stats block: a bullet list or a table. */
  stats: ReactNode;
  /** Whether the stats block is a table rather than a bullet list. */
  isTable: boolean;
  /** The chart tile that illustrates the stats. */
  chart: ReactNode;
}

/**
 * One section of an answer: its heading, when the model wrote a lead-in line,
 * across the full width, then the stats on the left and their chart on the
 * right, both from the top. The stats come first in the document too, so a
 * narrow answer stacks them above the chart and screen readers follow the
 * visual order. Two columns need two charts' minimum width of 320px plus the
 * 20px gap, so the row splits once the section's content box is 41.5rem
 * (664px) wide; when the chart drew nothing and the tile is gone, the stats take the
 * full width.
 */
export function AnswerSection({
  leadIn,
  stats,
  isTable,
  chart,
}: AnswerSectionProps) {
  const headingId = useId();
  const variantClass =
    VARIANT_CLASS[isTable ? 'table' : 'list'][
      leadIn === undefined ? 'plain' : 'leadIn'
    ];
  return (
    <section
      className={`${SECTION_CLASS} ${variantClass}`}
      aria-labelledby={leadIn === undefined ? undefined : headingId}
    >
      {leadIn !== undefined && (
        <SectionHeading id={headingId} markdown={leadIn} />
      )}
      <div
        className={isTable ? ROW_CLASS : `${ROW_CLASS} ${ROW_TOP_SPACE_CLASS}`}
      >
        {stats}
        {chart}
      </div>
    </section>
  );
}
