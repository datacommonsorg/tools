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
 * @fileoverview Trajectory tab for the turn debug panel: presents streamed model
 * reasoning thoughts and tool call execution records.
 */

import {
  DEBUG_EMPTY_STATE_MESSAGES,
  formatThoughtsHeading,
} from '@/src/components/panel_debug/copy_debug';
import {
  DEBUG_MONO_TEXT_CLASSES,
  DebugSection,
} from '@/src/components/panel_debug/section_debug';
import { ToolCallsSection } from '@/src/components/panel_debug/section_debug_tool_calls';
import type { ThoughtEvent, ToolCallEvent } from '@/src/hooks/use_sse_chat';

/** Props for {@link TrajectoryTab}. */
export interface TrajectoryTabProps {
  thoughts: readonly ThoughtEvent[];
  toolCalls: readonly ToolCallEvent[];
}

/**
 * Renders ordered model thoughts and tool invocations, or an empty state when
 * neither was recorded.
 */
export const TrajectoryTab = ({ thoughts, toolCalls }: TrajectoryTabProps) => {
  const isEmpty = thoughts.length === 0 && toolCalls.length === 0;

  if (isEmpty) {
    return (
      <p className="text-body-medium text-on-surface-variant">
        {DEBUG_EMPTY_STATE_MESSAGES.trajectory}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {thoughts.length > 0 && (
        <DebugSection label={formatThoughtsHeading(thoughts.length)}>
          <div className="flex flex-col gap-3">
            {thoughts.map((thought, index) => (
              <div
                key={index}
                className="flex flex-col gap-1.5 p-3 rounded-lg bg-surface border border-outline"
              >
                <span className="text-label-small font-medium uppercase tracking-wider text-on-surface-variant">
                  {thought.phase}
                </span>
                <pre
                  className={`${DEBUG_MONO_TEXT_CLASSES} text-on-surface whitespace-pre-wrap break-words`}
                >
                  {thought.text}
                </pre>
              </div>
            ))}
          </div>
        </DebugSection>
      )}

      <ToolCallsSection toolCalls={toolCalls} />
    </div>
  );
};
