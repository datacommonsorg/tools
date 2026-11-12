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
 * @fileoverview Timing tab for the turn debug panel: presents client-observed
 * submission time and elapsed milestone durations, alongside authoritative
 * server-measured phase durations.
 */

import {
  DEBUG_EMPTY_STATE_MESSAGES,
  DEBUG_MILESTONE_LABELS,
  DEBUG_PANEL_COPY,
  DEBUG_SECTION_HEADINGS,
  formatDurationMs,
  formatServerPhaseLabel,
} from '@/src/components/panel_debug/copy_debug';
import {
  DEBUG_MONO_TEXT_CLASSES,
  DebugField,
  DebugSection,
} from '@/src/components/panel_debug/section_debug';
import type {
  ClientTurnTimings,
  TimingMilestone,
} from '@/src/hooks/turn_timings';
import type { ServerDebugReport } from '@/src/types/debug_report';

/** Props for {@link TimingTab}. */
export interface TimingTabProps {
  clientTimings: ClientTurnTimings | null;
  serverReport?: ServerDebugReport | null;
}

interface MilestoneDescriptor {
  key: TimingMilestone;
  label: string;
}

const MILESTONES: readonly MilestoneDescriptor[] = [
  { key: 'headersReceivedMs', label: DEBUG_MILESTONE_LABELS.headersReceivedMs },
  { key: 'firstThoughtMs', label: DEBUG_MILESTONE_LABELS.firstThoughtMs },
  { key: 'firstBlockMs', label: DEBUG_MILESTONE_LABELS.firstBlockMs },
  { key: 'terminalMs', label: DEBUG_MILESTONE_LABELS.terminalMs },
  { key: 'followUpsMs', label: DEBUG_MILESTONE_LABELS.followUpsMs },
  { key: 'totalMs', label: DEBUG_MILESTONE_LABELS.totalMs },
];

/**
 * Renders client-measured milestones and server phase timings, or an empty
 * state when both are absent.
 */
export const TimingTab = ({
  clientTimings,
  serverReport = null,
}: TimingTabProps) => {
  if (!clientTimings && !serverReport) {
    return (
      <p className="text-body-medium text-on-surface-variant">
        {DEBUG_EMPTY_STATE_MESSAGES.timing}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2 text-on-surface">
      {clientTimings && (
        <>
          <DebugSection label={DEBUG_SECTION_HEADINGS.submissionTime}>
            <p className={`${DEBUG_MONO_TEXT_CLASSES} text-on-surface`}>
              {clientTimings.submittedAt}
            </p>
          </DebugSection>

          <DebugSection label={DEBUG_SECTION_HEADINGS.milestones}>
            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2 text-body-medium">
              {MILESTONES.map(({ key, label }) => {
                const value = clientTimings[key];
                const formatted =
                  value !== undefined
                    ? formatDurationMs(value)
                    : DEBUG_PANEL_COPY.notRecordedFallback;
                return (
                  <DebugField
                    key={key}
                    label={label}
                    value={formatted}
                    valueClassName="font-medium"
                  />
                );
              })}
            </dl>
          </DebugSection>
        </>
      )}

      {serverReport && (
        <DebugSection label={DEBUG_SECTION_HEADINGS.serverTimings}>
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2 text-body-medium">
            <DebugField
              label={DEBUG_PANEL_COPY.serverTurnDuration}
              value={formatDurationMs(serverReport.durationMs)}
              valueClassName="font-medium"
            />
            {Object.entries(serverReport.phaseDurationsMs).map(
              ([phase, durationMs]) => {
                const parentPhase = serverReport.nestedPhases[phase];
                return (
                  <DebugField
                    key={phase}
                    label={formatServerPhaseLabel(phase, parentPhase)}
                    value={formatDurationMs(durationMs)}
                    valueClassName="font-medium"
                  />
                );
              },
            )}
          </dl>
        </DebugSection>
      )}
    </div>
  );
};
