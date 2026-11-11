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
 * @fileoverview Tabbed debug panel body: coordinates the top-level tab bar and
 * renders the selected debug section (Overview, Provenance, Trajectory,
 * Response, or Timing).
 */

import { useId, useMemo, useState } from 'react';
import {
  DEBUG_PANEL_COPY,
  DEBUG_TAB_LABELS,
  formatDurationMs,
} from '@/src/components/panel_debug/copy_debug';
import { buildTurnDebugReport } from '@/src/components/panel_debug/report_debug';
import { OverviewTab } from '@/src/components/panel_debug/tab_debug_overview';
import { ProvenanceTab } from '@/src/components/panel_debug/tab_debug_provenance';
import { ResponseTab } from '@/src/components/panel_debug/tab_debug_response';
import { TimingTab } from '@/src/components/panel_debug/tab_debug_timing';
import { TrajectoryTab } from '@/src/components/panel_debug/tab_debug_trajectory';
import {
  type DebugTabItem,
  DebugTabs,
  getDebugTabElementId,
  getDebugTabPanelElementId,
} from '@/src/components/panel_debug/tabs_debug';
import { type ChatTurn, getTurnCharts } from '@/src/hooks/use_sse_chat';
import { inspectTurn } from '@/src/utils/inspect_turn';

/** Identifiers for each tab in the turn debug panel. */
export type DebugTabId =
  | 'overview'
  | 'provenance'
  | 'trajectory'
  | 'response'
  | 'timing';

/** Props for {@link DebugPanelBody}. */
export interface DebugPanelBodyProps {
  turn: ChatTurn;
}

/**
 * Renders the pinned debug tabs navigation and the active tab panel.
 */
export const DebugPanelBody = ({ turn }: DebugPanelBodyProps) => {
  const idPrefix = useId();
  const [activeTab, setActiveTab] = useState<DebugTabId>('overview');

  const report = useMemo(() => buildTurnDebugReport(turn), [turn]);
  const charts = useMemo(() => getTurnCharts(turn), [turn]);
  const inspection = useMemo(
    () => inspectTurn(turn.toolCalls, charts, turn.provenance),
    [turn.toolCalls, charts, turn.provenance],
  );

  const tabs: readonly DebugTabItem<DebugTabId>[] = useMemo(
    () => [
      { id: 'overview', label: DEBUG_TAB_LABELS.overview },
      {
        id: 'provenance',
        label: DEBUG_TAB_LABELS.provenance,
        badge: inspection.facets.length,
      },
      {
        id: 'trajectory',
        label: DEBUG_TAB_LABELS.trajectory,
        badge: turn.toolCalls.length,
      },
      {
        id: 'response',
        label: DEBUG_TAB_LABELS.response,
        badge: turn.blocks.length,
      },
      {
        id: 'timing',
        label: DEBUG_TAB_LABELS.timing,
        badge:
          turn.clientTimings?.totalMs !== undefined
            ? formatDurationMs(turn.clientTimings.totalMs)
            : undefined,
      },
    ],
    [
      inspection.facets.length,
      turn.toolCalls.length,
      turn.blocks.length,
      turn.clientTimings?.totalMs,
    ],
  );

  return (
    <>
      <div className="shrink-0 px-4 pt-2">
        <DebugTabs<DebugTabId>
          idPrefix={idPrefix}
          ariaLabel={DEBUG_PANEL_COPY.tablistAriaLabel}
          tabs={tabs}
          activeTabId={activeTab}
          onSelectTab={setActiveTab}
        />
      </div>
      <div
        role="tabpanel"
        id={getDebugTabPanelElementId(idPrefix, activeTab)}
        aria-labelledby={getDebugTabElementId(idPrefix, activeTab)}
        // biome-ignore lint/a11y/noNoninteractiveTabindex: Scrollable tabpanel container must be focusable per WAI-ARIA.
        tabIndex={0}
        className="flex-1 min-h-0 overflow-y-auto p-4"
      >
        {activeTab === 'overview' && <OverviewTab report={report} />}
        {activeTab === 'provenance' && (
          <ProvenanceTab inspection={inspection} />
        )}
        {activeTab === 'trajectory' && (
          <TrajectoryTab thoughts={turn.thoughts} toolCalls={turn.toolCalls} />
        )}
        {activeTab === 'response' && (
          <ResponseTab outcome={report.outcome} response={report.response} />
        )}
        {activeTab === 'timing' && (
          <TimingTab clientTimings={turn.clientTimings ?? null} />
        )}
      </div>
    </>
  );
};
