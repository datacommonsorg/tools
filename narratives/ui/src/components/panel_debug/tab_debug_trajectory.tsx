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
 * reasoning thoughts and tool call execution records, grouped by discovery round
 * when rounds are recorded.
 */

import { useMemo, useState } from 'react';
import {
  DEBUG_EMPTY_STATE_MESSAGES,
  DEBUG_SECTION_HEADINGS,
  formatDiscoveryRoundHeading,
  formatThoughtsHeading,
} from '@/src/components/panel_debug/copy_debug';
import {
  DEBUG_MONO_TEXT_CLASSES,
  DebugSection,
} from '@/src/components/panel_debug/section_debug';
import { ToolCallsSection } from '@/src/components/panel_debug/section_debug_tool_calls';
import type { ThoughtEvent, ToolCallEvent } from '@/src/hooks/use_sse_chat';
import type { ServerDebugReport } from '@/src/types/debug_report';

/** Props for {@link TrajectoryTab}. */
export interface TrajectoryTabProps {
  thoughts: readonly ThoughtEvent[];
  toolCalls: readonly ToolCallEvent[];
  serverReport?: ServerDebugReport | null;
}

const renderThoughtCards = (thoughtsList: readonly ThoughtEvent[]) => (
  <div className="flex flex-col gap-3">
    {thoughtsList.map((thought, index) => (
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
);

/**
 * Renders ordered model thoughts and tool invocations, or an empty state when
 * neither was recorded. Interleaves discovery thoughts and tool calls by round
 * when round metadata is present.
 */
export const TrajectoryTab = ({
  thoughts,
  toolCalls,
  serverReport = null,
}: TrajectoryTabProps) => {
  const [openResultKey, setOpenResultKey] = useState<string | null>(null);

  const handleToggleKey = (key: string) => {
    setOpenResultKey((prev) => (prev === key ? null : key));
  };

  const effectiveThoughts: readonly ThoughtEvent[] = useMemo(() => {
    if (serverReport && serverReport.thoughts.length > 0) {
      return serverReport.thoughts.map((t) => ({
        phase: t.phase,
        text: t.text,
        round: t.round ?? undefined,
      }));
    }
    return thoughts;
  }, [serverReport, thoughts]);

  const effectiveToolCalls: readonly ToolCallEvent[] = useMemo(() => {
    if (
      toolCalls.length === 0 &&
      serverReport &&
      serverReport.toolCalls.length > 0
    ) {
      return serverReport.toolCalls.map((call) => ({
        name: call.name,
        arguments: call.arguments as Record<string, unknown>,
        status: call.status,
        result: call.result,
        round: call.round,
        duration_ms: call.durationMs,
      }));
    }
    return toolCalls;
  }, [serverReport, toolCalls]);

  const rounds = useMemo(() => {
    const roundSet = new Set<number>();
    for (const thought of effectiveThoughts) {
      if (
        thought.phase === 'discovery' &&
        typeof thought.round === 'number' &&
        Number.isInteger(thought.round) &&
        thought.round > 0
      ) {
        roundSet.add(thought.round);
      }
    }
    for (const call of effectiveToolCalls) {
      if (
        typeof call.round === 'number' &&
        Number.isInteger(call.round) &&
        call.round > 0
      ) {
        roundSet.add(call.round);
      }
    }
    return Array.from(roundSet).sort((a, b) => a - b);
  }, [effectiveThoughts, effectiveToolCalls]);

  if (effectiveThoughts.length === 0 && effectiveToolCalls.length === 0) {
    return (
      <p className="text-body-medium text-on-surface-variant">
        {DEBUG_EMPTY_STATE_MESSAGES.trajectory}
      </p>
    );
  }

  if (rounds.length === 0) {
    return (
      <div className="flex flex-col gap-2">
        {effectiveThoughts.length > 0 && (
          <DebugSection label={formatThoughtsHeading(effectiveThoughts.length)}>
            {renderThoughtCards(effectiveThoughts)}
          </DebugSection>
        )}
        <ToolCallsSection
          toolCalls={effectiveToolCalls}
          openKey={openResultKey}
          onToggleKey={handleToggleKey}
          keyPrefix="unrounded"
        />
      </div>
    );
  }

  const unroundedDiscoveryThoughts = effectiveThoughts.filter(
    (t) =>
      t.phase === 'discovery' &&
      (t.round === undefined || t.round <= 0 || !Number.isInteger(t.round)),
  );
  const unroundedToolCalls = effectiveToolCalls.filter(
    (c) => c.round === undefined || c.round <= 0 || !Number.isInteger(c.round),
  );
  const synthesisThoughts = effectiveThoughts.filter(
    (t) => t.phase === 'synthesis',
  );

  return (
    <div className="flex flex-col gap-2">
      {rounds.map((round) => {
        const roundThoughts = effectiveThoughts.filter(
          (t) => t.phase === 'discovery' && t.round === round,
        );
        const roundToolCalls = effectiveToolCalls.filter(
          (c) => c.round === round,
        );
        return (
          <DebugSection
            key={`round-${round}`}
            label={formatDiscoveryRoundHeading(round)}
          >
            <div className="flex flex-col gap-3">
              {roundThoughts.length > 0 && renderThoughtCards(roundThoughts)}
              {roundToolCalls.length > 0 && (
                <ToolCallsSection
                  toolCalls={roundToolCalls}
                  openKey={openResultKey}
                  onToggleKey={handleToggleKey}
                  keyPrefix={`round-${round}`}
                  nested
                />
              )}
            </div>
          </DebugSection>
        );
      })}

      {unroundedDiscoveryThoughts.length > 0 && (
        <DebugSection
          label={formatThoughtsHeading(unroundedDiscoveryThoughts.length)}
        >
          {renderThoughtCards(unroundedDiscoveryThoughts)}
        </DebugSection>
      )}

      {unroundedToolCalls.length > 0 && (
        <ToolCallsSection
          toolCalls={unroundedToolCalls}
          openKey={openResultKey}
          onToggleKey={handleToggleKey}
          keyPrefix="unrounded"
        />
      )}

      {synthesisThoughts.length > 0 && (
        <DebugSection label={DEBUG_SECTION_HEADINGS.synthesisThoughts}>
          {renderThoughtCards(synthesisThoughts)}
        </DebugSection>
      )}
    </div>
  );
};
