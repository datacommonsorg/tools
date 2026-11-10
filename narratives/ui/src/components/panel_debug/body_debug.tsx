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
 * @fileoverview Debug panel body: inspects a turn once and composes its
 * sections, without any chrome.
 */

import { ChartsSection } from '@/src/components/panel_debug/section_debug_charts';
import { PlacesSection } from '@/src/components/panel_debug/section_debug_places';
import { ProvenanceSection } from '@/src/components/panel_debug/section_debug_provenance';
import { ToolCallsSection } from '@/src/components/panel_debug/section_debug_tool_calls';
import { VariablesSection } from '@/src/components/panel_debug/section_debug_variables';
import { type ChatTurn, getTurnCharts } from '@/src/hooks/use_sse_chat';
import { inspectTurn } from '@/src/utils/inspect_turn';

interface DebugPanelBodyProps {
  turn: ChatTurn;
}

/**
 * Renders the turn's sections in order: provenances used, variables, places,
 * charts requested, and tool calls. Each section renders nothing when it has
 * nothing to list.
 *
 * "Which provenances were used" is the question this view exists to answer,
 * so that section leads.
 */
export const DebugPanelBody = ({ turn }: DebugPanelBodyProps) => {
  const inspection = inspectTurn(
    turn.toolCalls,
    getTurnCharts(turn),
    turn.provenance,
  );

  return (
    <div className="flex flex-col gap-5">
      <ProvenanceSection facets={inspection.facets} />
      <VariablesSection variables={inspection.variables} />
      <PlacesSection places={inspection.places} />
      <ChartsSection charts={inspection.charts} />
      <ToolCallsSection toolCalls={turn.toolCalls} />
    </div>
  );
};
