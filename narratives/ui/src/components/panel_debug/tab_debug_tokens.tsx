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
 * @fileoverview Tokens tab for the turn debug panel: presents token totals and
 * per-call token breakdown from authoritative server debug metrics.
 */

import {
  DEBUG_EMPTY_STATE_MESSAGES,
  DEBUG_SECTION_HEADINGS,
  formatRoundLabel,
  formatTokenCallsHeading,
} from '@/src/components/panel_debug/copy_debug';
import {
  DEBUG_MONO_TEXT_CLASSES,
  DebugField,
  DebugSection,
} from '@/src/components/panel_debug/section_debug';
import type { ServerDebugReport } from '@/src/types/debug_report';

/** Props for {@link TokensTab}. */
export interface TokensTabProps {
  serverReport: ServerDebugReport | null;
}

/**
 * Renders aggregate token usage and per-call breakdowns from a server report.
 */
export const TokensTab = ({ serverReport }: TokensTabProps) => {
  if (serverReport === null) {
    return (
      <p className="text-body-medium text-on-surface-variant">
        {DEBUG_EMPTY_STATE_MESSAGES.noServerReport}
      </p>
    );
  }

  const { tokens } = serverReport;

  return (
    <div className="flex flex-col gap-2 text-on-surface">
      <DebugSection label={DEBUG_SECTION_HEADINGS.tokenTotals}>
        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-2 text-body-medium">
          <DebugField
            label="Prompt tokens"
            value={tokens.promptTokenCount.toLocaleString()}
            valueClassName="font-medium"
          />
          <DebugField
            label="Candidate tokens"
            value={tokens.candidatesTokenCount.toLocaleString()}
            valueClassName="font-medium"
          />
          <DebugField
            label="Thought tokens"
            value={tokens.thoughtsTokenCount.toLocaleString()}
            valueClassName="font-medium"
          />
          <DebugField
            label="Total tokens"
            value={tokens.totalTokenCount.toLocaleString()}
            valueClassName="font-medium"
          />
        </dl>
      </DebugSection>

      <DebugSection label={formatTokenCallsHeading(tokens.calls.length)}>
        {tokens.calls.length === 0 ? (
          <p className="text-body-medium text-on-surface-variant">
            {DEBUG_EMPTY_STATE_MESSAGES.tokenCalls}
          </p>
        ) : (
          <ol className="list-none flex flex-col gap-2">
            {tokens.calls.map((call, index) => {
              const callKey = `${call.phase}-${call.round ?? 'none'}-${call.model}-${index}`;
              return (
                <li
                  key={callKey}
                  className="p-3 rounded-lg bg-surface border border-outline flex flex-col gap-2 text-body-medium"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-on-surface">
                        {call.phase}
                      </span>
                      {call.round !== null && (
                        <span className="text-body-medium text-on-surface-variant">
                          ({formatRoundLabel(call.round)})
                        </span>
                      )}
                    </div>
                    <span
                      className={`${DEBUG_MONO_TEXT_CLASSES} text-on-surface-variant`}
                    >
                      {call.model}
                    </span>
                  </div>
                  <dl className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-body-medium">
                    <DebugField
                      label="Prompt"
                      value={call.promptTokenCount.toLocaleString()}
                      valueClassName="font-medium"
                    />
                    <DebugField
                      label="Candidates"
                      value={call.candidatesTokenCount.toLocaleString()}
                      valueClassName="font-medium"
                    />
                    <DebugField
                      label="Thoughts"
                      value={call.thoughtsTokenCount.toLocaleString()}
                      valueClassName="font-medium"
                    />
                    <DebugField
                      label="Total"
                      value={call.totalTokenCount.toLocaleString()}
                      valueClassName="font-medium"
                    />
                  </dl>
                </li>
              );
            })}
          </ol>
        )}
      </DebugSection>
    </div>
  );
};
