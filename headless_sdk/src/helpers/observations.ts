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
 * @fileoverview Helpers for aligning time series observations, computing
 * per-capita scaling, and selecting default facets.
 */

import { ObservationsRequest, ObservationPoint } from '../types';
import {
  V2VariableData,
  V2OrderedFacet,
  V2ObservationPoint,
  V2EntityData,
} from '../types_api';

/**
 * Heuristically selects the most robust facet ID from entity observations.
 * Compares cumulative observation points across entities and breaks ties by
 * choosing the facet with the latest recorded observation date.
 *
 * @param byEntityData Record mapping entities to their facets.
 * @returns The heuristically chosen default facet ID string.
 */
export function selectDefaultFacet(
  byEntityData: Record<string, V2EntityData>
): string {
  const facetCounts: Record<
    string,
    { obsCount: number; latestDate: string }
  > = {};
  Object.values(byEntityData).forEach((entityData) => {
    if (entityData.orderedFacets) {
      entityData.orderedFacets.forEach((f) => {
        const facetId = f.facetId || 'default';
        const count = f.obsCount || f.observations?.length || 0;
        const latest = f.latestDate || '';
        if (!facetCounts[facetId]) {
          facetCounts[facetId] = { obsCount: 0, latestDate: '' };
        }
        facetCounts[facetId].obsCount += count;
        if (latest > facetCounts[facetId].latestDate) {
          facetCounts[facetId].latestDate = latest;
        }
      });
    }
  });

  const sortedFacets = Object.entries(facetCounts).sort((a, b) => {
    if (b[1].obsCount !== a[1].obsCount) {
      return b[1].obsCount - a[1].obsCount;
    }
    return b[1].latestDate.localeCompare(a[1].latestDate);
  });

  return sortedFacets[0]?.[0] || 'default';
}

/**
 * Aligns primary time-series observations across entities, projects them into
 * a tidy flat array, and scales values by matching denominator observations
 * (per-capita transformation) if specified.
 *
 * @param request Query criteria containing observation property names.
 * @param primaryVarData Observations mapping for primary variable.
 * @param primaryFacetDcid Chosen facet ID to filter primary observations.
 * @param denomVar Optional denominator variable DCID.
 * @param byVariable Record mapping variables to their entity facets list.
 * @param denomFacetDcid Optional denominator facet ID.
 * @returns A list of aligned ObservationPoint configurations.
 */
export function alignObservations(
  request: ObservationsRequest,
  primaryVarData: V2VariableData,
  primaryFacetDcid: string,
  denomVar?: string,
  byVariable?: Record<string, V2VariableData>,
  denomFacetDcid?: string
): ObservationPoint[] {
  // Group denominator observations by entity and date (for denomFacetDcid)
  const denomDataByEntityDate: Record<string, Record<string, number>> = {};
  if (denomVar && denomFacetDcid && byVariable) {
    const denomVarData = byVariable[denomVar];
    if (denomVarData && denomVarData.byEntity) {
      Object.entries(denomVarData.byEntity).forEach(
        ([entityId, entityData]) => {
          denomDataByEntityDate[entityId] = {};
          if (entityData.orderedFacets) {
            entityData.orderedFacets.forEach((f) => {
              if (f.facetId === denomFacetDcid && f.observations) {
                f.observations.forEach((obs) => {
                  denomDataByEntityDate[entityId][obs.date] = obs.value;
                });
              }
            });
          }
        }
      );
    }
  }

  // Construct flat tidy observations
  const observations: ObservationPoint[] = [];

  const findMatchingProperties = (
    entityId: string
  ): Record<string, string> => {
    const found = request.observationProperties.find((props) =>
      Object.values(props).includes(entityId)
    );
    return found || { entity: entityId };
  };

  if (primaryVarData.byEntity) {
    Object.entries(primaryVarData.byEntity).forEach(
      ([entityId, entityData]) => {
        if (entityData.orderedFacets) {
          entityData.orderedFacets.forEach((facetData: V2OrderedFacet) => {
            if (
              facetData.facetId === primaryFacetDcid &&
              facetData.observations
            ) {
              facetData.observations.forEach((obs: V2ObservationPoint) => {
              const rawVal = obs.value;
              let finalValue = rawVal;

              if (denomVar) {
                const denomVal = denomDataByEntityDate[entityId]?.[obs.date];
                if (
                  typeof denomVal === 'number' &&
                  !isNaN(denomVal) &&
                  denomVal !== 0
                ) {
                  finalValue = rawVal / denomVal;
                } else {
                  // Omit point if denominator is missing or invalid
                  return;
                }
              }

              observations.push({
                date: obs.date,
                value: finalValue,
                observationProperties: findMatchingProperties(entityId),
                attributes: obs.attributes,
              });
            });
          }
        });
      }
    });
  }

  return observations;
}
