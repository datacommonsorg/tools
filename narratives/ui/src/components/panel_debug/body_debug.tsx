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
 * renders the selected debug section (Overview, Data, Trajectory, Analysis,
 * Synthesis, Response, Timing, Tokens, or Configuration).
 */

import { useId, useMemo, useState } from 'react';
import {
  DEBUG_PANEL_COPY,
  DEBUG_TAB_LABELS,
  formatDurationMs,
} from '@/src/components/panel_debug/copy_debug';
import { buildTurnDebugReport } from '@/src/components/panel_debug/report_debug';
import { AnalysisTab } from '@/src/components/panel_debug/tab_debug_analysis';
import { ConfigurationTab } from '@/src/components/panel_debug/tab_debug_configuration';
import { DataTab } from '@/src/components/panel_debug/tab_debug_data';
import { OverviewTab } from '@/src/components/panel_debug/tab_debug_overview';
import { ResponseTab } from '@/src/components/panel_debug/tab_debug_response';
import { SynthesisTab } from '@/src/components/panel_debug/tab_debug_synthesis';
import { TimingTab } from '@/src/components/panel_debug/tab_debug_timing';
import { TokensTab } from '@/src/components/panel_debug/tab_debug_tokens';
import { TrajectoryTab } from '@/src/components/panel_debug/tab_debug_trajectory';
import {
  type DebugTabItem,
  DebugTabs,
  getDebugTabElementId,
  getDebugTabPanelElementId,
} from '@/src/components/panel_debug/tabs_debug';
import type { ChatTurn } from '@/src/hooks/use_sse_chat';

/** Identifiers for each tab in the turn debug panel. */
export type DebugTabId =
  | 'overview'
  | 'data'
  | 'trajectory'
  | 'analysis'
  | 'synthesis'
  | 'response'
  | 'timing'
  | 'tokens'
  | 'configuration';

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

  const totalDurationMs =
    turn.clientTimings?.totalMs ?? turn.serverReport?.durationMs;
  const timingBadge =
    totalDurationMs !== undefined
      ? formatDurationMs(totalDurationMs)
      : undefined;

  const tabs: readonly DebugTabItem<DebugTabId>[] = useMemo(
    () => [
      { id: 'overview', label: DEBUG_TAB_LABELS.overview },
      {
        id: 'data',
        label: DEBUG_TAB_LABELS.data,
        badge: turn.serverReport ? turn.serverReport.tables.length : undefined,
      },
      {
        id: 'trajectory',
        label: DEBUG_TAB_LABELS.trajectory,
        badge: Math.max(
          turn.toolCalls.length,
          turn.serverReport?.toolCalls.length ?? 0,
        ),
      },
      {
        id: 'analysis',
        label: DEBUG_TAB_LABELS.analysis,
        badge: turn.serverReport ? turn.serverReport.scripts.length : undefined,
      },
      {
        id: 'synthesis',
        label: DEBUG_TAB_LABELS.synthesis,
      },
      {
        id: 'response',
        label: DEBUG_TAB_LABELS.response,
        badge: turn.blocks.length,
      },
      {
        id: 'timing',
        label: DEBUG_TAB_LABELS.timing,
        badge: timingBadge,
      },
      {
        id: 'tokens',
        label: DEBUG_TAB_LABELS.tokens,
        badge: turn.serverReport
          ? turn.serverReport.tokens.totalTokenCount.toLocaleString()
          : undefined,
      },
      {
        id: 'configuration',
        label: DEBUG_TAB_LABELS.configuration,
      },
    ],
    [turn.serverReport, turn.toolCalls.length, turn.blocks.length, timingBadge],
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
        {activeTab === 'overview' && (
          <OverviewTab
            report={report}
            serverReport={turn.serverReport ?? null}
          />
        )}
        {activeTab === 'data' && (
          <DataTab serverReport={turn.serverReport ?? null} />
        )}
        {activeTab === 'trajectory' && (
          <TrajectoryTab
            thoughts={turn.thoughts}
            toolCalls={turn.toolCalls}
            serverReport={turn.serverReport ?? null}
          />
        )}
        {activeTab === 'analysis' && (
          <AnalysisTab serverReport={turn.serverReport ?? null} />
        )}
        {activeTab === 'synthesis' && (
          <SynthesisTab serverReport={turn.serverReport ?? null} />
        )}
        {activeTab === 'response' && (
          <ResponseTab outcome={report.outcome} response={report.response} />
        )}
        {activeTab === 'timing' && (
          <TimingTab
            clientTimings={turn.clientTimings ?? null}
            serverReport={turn.serverReport ?? null}
          />
        )}
        {activeTab === 'tokens' && (
          <TokensTab serverReport={turn.serverReport ?? null} />
        )}
        {activeTab === 'configuration' && (
          <ConfigurationTab serverReport={turn.serverReport ?? null} />
        )}
      </div>
    </>
  );
};
