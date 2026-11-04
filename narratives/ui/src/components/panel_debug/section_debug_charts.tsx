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
 * @fileoverview Debug panel section listing the charts a turn asked the UI to
 * render.
 */

import {
  DEBUG_SECTION_HEADINGS,
  formatChartPlacesSuffix,
} from '@/src/components/panel_debug/copy_debug';
import { DebugSection } from '@/src/components/panel_debug/section_debug';
import type { TurnInspection } from '@/src/utils/inspect_turn';

interface ChartsSectionProps {
  charts: TurnInspection['charts'];
}

/**
 * Lists each requested chart's title, variables, and place count. Renders
 * nothing without charts.
 */
export const ChartsSection = ({ charts }: ChartsSectionProps) => {
  if (charts.length === 0) {
    return null;
  }
  return (
    <DebugSection label={DEBUG_SECTION_HEADINGS.charts}>
      <ul className="m-0 p-0 list-none flex flex-col gap-1.5">
        {charts.map((chart, index) => (
          <li key={index} className="flex flex-col text-body-medium">
            <span>{chart.title}</span>
            <span className="text-on-surface-variant font-mono-plex wrap-anywhere">
              {chart.variables.join(', ')}
              {chart.places.length > 0 &&
                formatChartPlacesSuffix(chart.places.length)}
            </span>
          </li>
        ))}
      </ul>
    </DebugSection>
  );
};
