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
 * @fileoverview Debug panel section listing the data sources that supplied
 * an answer's figures.
 */

import {
  DEBUG_FACET_DETAIL_LABELS,
  DEBUG_SECTION_HEADINGS,
  UNNAMED_SOURCE_LABEL,
} from '@/src/components/panel_debug/copy_debug';
import {
  DebugDetail,
  DebugSection,
} from '@/src/components/panel_debug/section_debug';
import type { FacetInfo } from '@/src/utils/inspect_turn';

interface ProvenanceSectionProps {
  /** Every facet the turn's tool calls revealed, used or not. */
  facets: FacetInfo[];
}

/**
 * Lists the facets that supplied data, with their coverage, size, unit,
 * license, id, and URL. Renders nothing when no facet supplied data.
 *
 * Only sources that actually supplied figures are listed: the candidates the
 * server ranked below them are part of how the answer was reached, not part
 * of what it rests on. inspectTurn still records them, so widening this
 * filter is a one-line change.
 */
export const ProvenanceSection = ({ facets }: ProvenanceSectionProps) => {
  const usedFacets = facets.filter((facet) => facet.used);
  if (usedFacets.length === 0) {
    return null;
  }
  return (
    <DebugSection label={DEBUG_SECTION_HEADINGS.provenances}>
      <ul className="m-0 p-0 list-none flex flex-col gap-3">
        {usedFacets.map((facet) => (
          <li
            key={facet.facetId}
            className="flex flex-col gap-0.5 pl-3 border-l-3 border-theme-primary"
          >
            <span className="text-body-medium">
              <strong>{facet.provenance ?? UNNAMED_SOURCE_LABEL}</strong>
            </span>
            <span className="flex flex-wrap gap-x-4 gap-y-0.5">
              <DebugDetail
                label={DEBUG_FACET_DETAIL_LABELS.coverage}
                value={facet.dateRange}
              />
              <DebugDetail
                label={DEBUG_FACET_DETAIL_LABELS.observations}
                value={facet.obsCount}
              />
              <DebugDetail
                label={DEBUG_FACET_DETAIL_LABELS.unit}
                value={facet.unit}
              />
              <DebugDetail
                label={DEBUG_FACET_DETAIL_LABELS.license}
                value={facet.license}
              />
            </span>
            <DebugDetail
              label={DEBUG_FACET_DETAIL_LABELS.facet}
              value={facet.facetId}
            />
            {facet.url && (
              // Provenance URLs can contain very long query strings; keep the
              // link on one line and expose the full URL via href and title.
              <a
                href={facet.url}
                target="_blank"
                rel="noreferrer"
                title={facet.url}
                className="text-body-medium block text-theme-primary truncate"
              >
                {facet.url}
              </a>
            )}
          </li>
        ))}
      </ul>
    </DebugSection>
  );
};
