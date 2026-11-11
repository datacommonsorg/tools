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
 * submission time and elapsed milestone durations.
 */

import {
  DEBUG_EMPTY_STATE_MESSAGES,
  DEBUG_PANEL_COPY,
  DEBUG_SECTION_HEADINGS,
  formatDurationMs,
} from '@/src/components/panel_debug/copy_debug';
import {
  DEBUG_MONO_TEXT_CLASSES,
  DebugSection,
} from '@/src/components/panel_debug/section_debug';
import type {
  ClientTurnTimings,
  TimingMilestone,
} from '@/src/hooks/turn_timings';

/** Props for {@link TimingTab}. */
export interface TimingTabProps {
  clientTimings: ClientTurnTimings | null;
}

interface MilestoneDescriptor {
  key: TimingMilestone;
  label: string;
}

const MILESTONES: readonly MilestoneDescriptor[] = [
  { key: 'headersReceivedMs', label: 'Headers received' },
  { key: 'firstThoughtMs', label: 'First thought' },
  { key: 'firstBlockMs', label: 'First answer block' },
  { key: 'terminalMs', label: 'Terminal frame' },
  { key: 'followUpsMs', label: 'Follow-up suggestions' },
  { key: 'totalMs', label: 'Total duration' },
];

/**
 * Renders client-measured milestones or an empty state when timings are absent.
 */
export const TimingTab = ({ clientTimings }: TimingTabProps) => {
  if (!clientTimings) {
    return (
      <p className="text-body-medium text-on-surface-variant">
        {DEBUG_EMPTY_STATE_MESSAGES.timing}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2 text-on-surface">
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
              <div key={key}>
                <dt className="text-label-small text-on-surface-variant">
                  {label}
                </dt>
                <dd className="font-medium">{formatted}</dd>
              </div>
            );
          })}
        </dl>
      </DebugSection>
    </div>
  );
};
