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

import { useState } from 'react';
import {
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
const CODE_BLOCK_CLASSES = `m-0 p-2 rounded ${DEBUG_MONO_TEXT_CLASSES} bg-surface-soft whitespace-pre-wrap wrap-anywhere`;

interface ToolCallsSectionProps {
  toolCalls: ToolCallEvent[];
}

/**
 * Lists each tool call's name, error state, and arguments, with its raw
 * response behind a toggle. At most one raw response is open at a time.
 * Renders nothing without tool calls.
 *
 * Raw responses stay behind a per-call toggle: they are untruncated and can
 * run to tens of kilobytes.
 */
export const ToolCallsSection = ({ toolCalls }: ToolCallsSectionProps) => {
  const [openResultIndex, setOpenResultIndex] = useState<number | null>(null);

  if (toolCalls.length === 0) {
    return null;
  }

  const toggleResult = (index: number) => {
    setOpenResultIndex(openResultIndex === index ? null : index);
  };

  return (
    <DebugSection label={formatToolCallsHeading(toolCalls.length)}>
      <ol className="m-0 pl-5 flex flex-col gap-3">
        {toolCalls.map((call, index) => {
          const isResultOpen = openResultIndex === index;
          return (
            <li key={index} className="flex flex-col gap-1">
              <span className="text-body-medium">
                <span className="font-mono">{call.name}</span>
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
                    onClick={() => toggleResult(index)}
                    className="self-start min-h-11 inline-flex items-center text-label-large cursor-pointer bg-transparent p-0 text-theme-primary"
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
    </DebugSection>
  );
};
