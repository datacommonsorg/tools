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
 * @fileoverview Overview tab for the turn debug panel: presents query text,
 * outcome details, turn indexing, summary counts, and conversation context.
 */

import {
  DEBUG_PANEL_COPY,
  DEBUG_SECTION_HEADINGS,
} from '@/src/components/panel_debug/copy_debug';
import type { TurnDebugReport } from '@/src/components/panel_debug/report_debug';
import {
  DEBUG_MONO_TEXT_CLASSES,
  DebugField,
  DebugSection,
} from '@/src/components/panel_debug/section_debug';

/** Props for {@link OverviewTab}. */
export interface OverviewTabProps {
  report: TurnDebugReport;
}

/**
 * Renders the top-level metadata and outcome classification of a chat turn.
 */
export const OverviewTab = ({ report }: OverviewTabProps) => {
  const { outcome, context } = report;

  return (
    <div className="flex flex-col gap-2 text-on-surface">
      <DebugSection label={DEBUG_SECTION_HEADINGS.userQuery}>
        <p className="text-body-medium text-on-surface break-words">
          {report.userMessage}
        </p>
      </DebugSection>

      <DebugSection label={DEBUG_SECTION_HEADINGS.turnOutcome}>
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2 text-body-medium">
          <DebugField
            label="Kind"
            value={outcome.kind}
            valueClassName="font-medium"
          />
          {'reason' in outcome && (
            <DebugField
              label="Terminal reason"
              value={outcome.reason ?? DEBUG_PANEL_COPY.noneFallback}
            />
          )}
          {outcome.kind === 'done' && (
            <DebugField
              label="Truncated"
              value={outcome.truncated ? 'Yes' : 'No'}
            />
          )}
          {outcome.kind === 'refused' && (
            <DebugField
              label="Refusal message"
              value={outcome.message}
              spanTwo
              valueClassName="break-words"
            />
          )}
          {outcome.kind === 'error' && (
            <DebugField
              label="Error detail"
              value={outcome.error}
              spanTwo
              valueClassName="break-words text-error"
            />
          )}
          {outcome.kind === 'in_progress' && (
            <DebugField label="Pipeline phase" value={outcome.phase} />
          )}
        </dl>
      </DebugSection>

      <DebugSection label={DEBUG_SECTION_HEADINGS.turnIdentifiers}>
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2 text-body-medium">
          <DebugField
            label="Turn index"
            value={
              report.turnIndex !== null
                ? report.turnIndex
                : DEBUG_PANEL_COPY.noneFallback
            }
          />
          <DebugField
            label="Idempotency key"
            value={report.idempotencyKey ?? DEBUG_PANEL_COPY.noneFallback}
            valueClassName={`${DEBUG_MONO_TEXT_CLASSES} break-all`}
          />
        </dl>
      </DebugSection>

      <DebugSection label={DEBUG_SECTION_HEADINGS.summaryCounts}>
        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-2 text-body-medium">
          <DebugField
            label="Tool calls"
            value={report.trajectory.toolCalls.length}
            valueClassName="font-medium"
          />
          <DebugField
            label="Thoughts"
            value={report.trajectory.thoughts.length}
            valueClassName="font-medium"
          />
          <DebugField
            label="Answer blocks"
            value={report.response.blocks.length}
            valueClassName="font-medium"
          />
          <DebugField
            label="Citations"
            value={report.response.provenance.length}
            valueClassName="font-medium"
          />
        </dl>
      </DebugSection>

      <DebugSection label={DEBUG_SECTION_HEADINGS.conversationContext}>
        <dl className="flex flex-col gap-2 text-body-medium">
          <DebugField
            label="Signed in window"
            value={context.signedInWindow ? 'Yes' : 'No'}
          />
          <DebugField
            label="Compacted summary"
            value={context.compactedSummary ?? DEBUG_PANEL_COPY.noneFallback}
          />
          <DebugField
            label="State slots"
            value={
              context.stateSlots &&
              Object.keys(context.stateSlots).length > 0 ? (
                <pre
                  className={`p-3 rounded-lg bg-surface border border-outline text-on-surface ${DEBUG_MONO_TEXT_CLASSES} overflow-x-auto whitespace-pre-wrap`}
                >
                  {JSON.stringify(context.stateSlots, null, 2)}
                </pre>
              ) : (
                DEBUG_PANEL_COPY.noneFallback
              )
            }
          />
        </dl>
      </DebugSection>
    </div>
  );
};
