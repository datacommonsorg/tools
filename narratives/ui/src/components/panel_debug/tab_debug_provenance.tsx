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
 * @fileoverview Provenance tab for the turn debug panel: lists provenances used,
 * variables, places, and charts requested from turn inspection data.
 */

import { DEBUG_EMPTY_STATE_MESSAGES } from '@/src/components/panel_debug/copy_debug';
import { ChartsSection } from '@/src/components/panel_debug/section_debug_charts';
import { PlacesSection } from '@/src/components/panel_debug/section_debug_places';
import { ProvenanceSection } from '@/src/components/panel_debug/section_debug_provenance';
import { VariablesSection } from '@/src/components/panel_debug/section_debug_variables';
import type { TurnInspection } from '@/src/utils/inspect_turn';

/** Props for {@link ProvenanceTab}. */
export interface ProvenanceTabProps {
  inspection: TurnInspection;
}

/**
 * Renders the provenance sections (provenance, variables, places, charts)
 * or a single empty-state paragraph when all four are empty.
 */
export const ProvenanceTab = ({ inspection }: ProvenanceTabProps) => {
  const isEmpty =
    inspection.facets.length === 0 &&
    inspection.variables.length === 0 &&
    inspection.places.length === 0 &&
    inspection.charts.length === 0;

  if (isEmpty) {
    return (
      <p className="text-body-medium text-on-surface-variant">
        {DEBUG_EMPTY_STATE_MESSAGES.provenance}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <ProvenanceSection facets={inspection.facets} />
      <VariablesSection variables={inspection.variables} />
      <PlacesSection places={inspection.places} />
      <ChartsSection charts={inspection.charts} />
    </div>
  );
};
