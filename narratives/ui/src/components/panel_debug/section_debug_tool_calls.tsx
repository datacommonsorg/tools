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
 * @fileoverview Debug panel section listing a turn's tool calls with their
 * arguments and raw responses.
 */

import {
  formatDurationMs,
  formatRawResponseToggleLabel,
  formatToolCallsHeading,
  TOOL_CALL_ERROR_MARKER,
} from '@/src/components/panel_debug/copy_debug';
import {
  DEBUG_MONO_TEXT_CLASSES,
  DebugSection,
} from '@/src/components/panel_debug/section_debug';
import type { ToolCallEvent } from '@/src/hooks/use_sse_chat';

/** Classes shared by the argument and raw response blocks. */
const CODE_BLOCK_CLASSES = `p-2 rounded ${DEBUG_MONO_TEXT_CLASSES} bg-surface border border-outline whitespace-pre-wrap wrap-anywhere`;

export interface ToolCallsSectionProps {
  toolCalls: readonly ToolCallEvent[];
  openKey: string | null;
  onToggleKey: (key: string) => void;
  keyPrefix: string;
  nested?: boolean;
}

/**
 * Lists each tool call's name, error state, and arguments, with its raw
 * response behind a toggle. At most one raw response is open at a time across
 * the parent tab. Renders nothing without tool calls.
 *
 * Raw responses stay behind a per-call toggle: they are untruncated and can
 * run to tens of kilobytes.
 */
export const ToolCallsSection = ({
  toolCalls,
  openKey,
  onToggleKey,
  keyPrefix,
  nested = false,
}: ToolCallsSectionProps) => {
  if (toolCalls.length === 0) {
    return null;
  }

  const heading = formatToolCallsHeading(toolCalls.length);
  const list = (
    <ol className="pl-5 flex flex-col gap-3">
      {toolCalls.map((call, index) => {
        const callKey = `${keyPrefix}:${index}`;
        const isResultOpen = openKey === callKey;
        return (
          <li key={index} className="flex flex-col gap-1">
            <span className="text-body-medium">
              <span className="font-mono">{call.name}</span>
              {call.duration_ms !== undefined && (
                <span className="text-on-surface-variant font-mono">
                  {` (${formatDurationMs(call.duration_ms)})`}
                </span>
              )}
              {call.status === 'error' && (
                <span className="text-error-strong">
                  {TOOL_CALL_ERROR_MARKER}
                </span>
              )}
            </span>
            <pre className={`${CODE_BLOCK_CLASSES} overflow-x-auto`}>
              {JSON.stringify(call.arguments, null, 2)}
            </pre>
            {call.result && (
              <>
                <button
                  type="button"
                  aria-expanded={isResultOpen}
                  onClick={() => onToggleKey(callKey)}
                  className="self-start min-h-11 inline-flex items-center text-label-large text-theme-primary"
                >
                  {formatRawResponseToggleLabel(
                    isResultOpen,
                    call.result.length,
                  )}
                </button>
                {isResultOpen && (
                  <pre
                    className={`${CODE_BLOCK_CLASSES} max-h-75 overflow-auto`}
                  >
                    {call.result}
                  </pre>
                )}
              </>
            )}
          </li>
        );
      })}
    </ol>
  );

  if (nested) {
    return (
      <div className="flex flex-col gap-1.5">
        <h5 className="text-label-small font-medium uppercase tracking-wide text-on-surface-variant">
          {heading}
        </h5>
        {list}
      </div>
    );
  }

  return <DebugSection label={heading}>{list}</DebugSection>;
};
