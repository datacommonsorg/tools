/*
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/**
 * @fileoverview Helpers for parsing, merging, and paginated fetching of V2
 * observation responses.
 */

import { DataCommonsClient } from '../types';
import { V2ObservationResponse, V2VariableData } from '../types_api';
import { fetchV2 } from '../api';

/**
 * Merges a paginated V2 REST API observations response into a target
 * accumulator object. This mutates the target object, concatenating observation
 * data points for matching facet IDs and entities, while merging new facet
 * metadata entries.
 *
 * @param target The accumulator V2ObservationResponse object being mutated.
 * @param source Incremental page V2ObservationResponse containing new points.
 */
export function mergeV2Responses(
  target: V2ObservationResponse,
  source: V2ObservationResponse | undefined
): void {
  if (!source) return;

  if (source.facets) {
    if (!target.facets) target.facets = {};
    Object.assign(target.facets, source.facets);
  }

  if (source.byVariable) {
    if (!target.byVariable) target.byVariable = {};
    Object.entries(source.byVariable).forEach(([varDcid, varData]) => {
      if (!target.byVariable) return;
      if (!target.byVariable[varDcid]) {
        target.byVariable[varDcid] = { byEntity: {} };
      }
      const targetVar = target.byVariable[varDcid];
      if (!targetVar.byEntity) {
        targetVar.byEntity = {};
      }
      const targetEntityData = targetVar.byEntity;
      const sourceEntityData = varData.byEntity || {};

      Object.entries(sourceEntityData).forEach(([entityId, entityData]) => {
        if (!targetEntityData[entityId]) {
          targetEntityData[entityId] = { orderedFacets: [] };
        }
        const targetFacets = targetEntityData[entityId].orderedFacets || [];
        const sourceFacets = entityData.orderedFacets || [];

        sourceFacets.forEach((sourceFacet) => {
          const matchingFacet = targetFacets.find(
            (tf) => tf.facetId === sourceFacet.facetId
          );
          if (matchingFacet) {
            if (sourceFacet.observations) {
              if (!matchingFacet.observations) {
                matchingFacet.observations = [];
              }
              matchingFacet.observations.push(...sourceFacet.observations);
            }
          } else {
            targetFacets.push(JSON.parse(JSON.stringify(sourceFacet)));
          }
        });
      });
    });
  }
}

/**
 * Traverses a variable observations mapping to extract the minimum earliest
 * date and maximum latest date recorded across all entity observations,
 * grouped by facet ID.
 *
 * @param byVariable Record mapping variable DCIDs to entity facets list.
 * @returns A mapping from facet IDs to start and end ISO-8601 date bounds.
 */
export function collectFacetDates(
  byVariable: Record<string, V2VariableData>
): Record<string, { start?: string; end?: string }> {
  const facetDates: Record<string, { start?: string; end?: string }> = {};
  Object.values(byVariable).forEach((varData) => {
    if (varData.byEntity) {
      Object.values(varData.byEntity).forEach((entityData) => {
        if (entityData.orderedFacets) {
          entityData.orderedFacets.forEach((f) => {
            const fid = f.facetId || 'default';
            if (!facetDates[fid]) {
              facetDates[fid] = {};
            }
            if (
              f.earliestDate &&
              (!facetDates[fid].start || f.earliestDate < facetDates[fid].start)
            ) {
              facetDates[fid].start = f.earliestDate;
            }
            if (
              f.latestDate &&
              (!facetDates[fid].end || f.latestDate > facetDates[fid].end)
            ) {
              facetDates[fid].end = f.latestDate;
            }
          });
        }
      });
    }
  });
  return facetDates;
}

/**
 * Executes a V2 observation query loop, automatically paginating requests
 * using nextToken and stitching intermediate JSON pages together. Includes
 * safety limit safeguards to prevent memory exhaustion from infinite API pages.
 *
 * @param state The current client state container.
 * @param path The URL endpoint path (e.g. '/v2/observation').
 * @param payload The request parameters body.
 * @returns consolidated V2ObservationResponse object.
 */
export async function fetchWithPagination(
  state: DataCommonsClient,
  path: string,
  payload: Record<string, unknown>
): Promise<V2ObservationResponse> {
  let pageCount = 0;
  const maxPages = state.config.maxPages || 5;
  const currentPayload = { ...payload };
  let stitchedResponse: V2ObservationResponse | null = null;
  let nextToken: string | undefined = undefined;

  do {
    if (nextToken) {
      currentPayload.nextToken = nextToken;
    }
    const pageResponse = (await fetchV2(
      state,
      path,
      currentPayload
    )) as V2ObservationResponse;
    pageCount++;

    if (!stitchedResponse) {
      stitchedResponse = pageResponse;
    } else {
      mergeV2Responses(stitchedResponse, pageResponse);
    }

    nextToken = pageResponse?.nextToken || pageResponse?.next_token;

    if (nextToken && pageCount >= maxPages) {
      console.warn(
        `DataCommonsClient: Observations fetch truncated after ${maxPages} ` +
          `pages to prevent memory exhaustion.`
      );
      break;
    }
  } while (nextToken);

  return stitchedResponse || {};
}
