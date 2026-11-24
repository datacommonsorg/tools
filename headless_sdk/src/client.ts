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
 * @fileoverview Main implementation of the Headless SDK client, containing
 * getMetadata and getObservations orchestration pipelines.
 */

import { DataCommonsError } from './errors';
import {
  ClientConfig,
  DataCommonsClient,
  RequestOptions,
  MetadataRequest,
  MetadataResponse,
  ObservationsRequest,
  ObservationsResponse,
  Facet,
} from './types';
import { V2ObservationResponse } from './types_api';
import { setCache } from './cache';
import { fetchV2 } from './api';
import {
  mapFacet,
  selectDefaultFacet,
  deepFreeze,
  resolveMetadataProperties,
  collectFacetDates,
  buildStatisticalVariableInfo,
  buildEntitiesMetadata,
  fetchWithPagination,
  alignObservations,
} from './helpers';

/**
 * Helper to generate a unique cache key for a set of variables and entities.
 */
function getCacheKey(variables: string[], entities: string[]): string {
  const sortedVars = [...variables].sort().join(',');
  const sortedEntities = [...entities].sort().join(',');
  return `${sortedVars}|${sortedEntities}`;
}

/**
 * Initializes and returns a new Data Commons client state.
 * This state holds configurations (endpoint base URL, API key, max pagination
 * page limit) and keeps a FIFO-evicting cache of raw API requests and resolved
 * domain responses to minimize redundant network calls.
 *
 * @param config Optional configuration overrides.
 * @returns The initialized DataCommonsClient state container.
 */
export function createDataCommonsClient(
  config?: Partial<ClientConfig>
): DataCommonsClient {
  return {
    config: {
      apiBaseUrl: config?.apiBaseUrl || 'https://api.datacommons.org',
      apiKey: config?.apiKey,
      maxPages: config?.maxPages || 5,
    },
    cache: new Map<string, unknown>(),
  };
}

/**
 * Retrieves all metadata associated with a statistical variable and entity
 * constraints. This resolves and formats localized names, descriptive
 * summaries, measurement methodologies, unit labels, provenance publishers,
 * and earliest/latest facet date ranges.
 *
 * @param state The current client state container.
 * @param request Query inputs including the statistical variable DCID and
 * entity constraint properties mapping.
 * @param options Optional request controls.
 * @returns A promise resolving to a detailed MetadataResponse object.
 * @throws {DataCommonsError} If network fetches fail.
 */
export async function getMetadata(
  state: DataCommonsClient,
  request: MetadataRequest,
  options?: RequestOptions
): Promise<MetadataResponse> {
  const cacheKey = JSON.stringify({ request, options });
  if (state.cache.has(cacheKey)) {
    return state.cache.get(cacheKey) as MetadataResponse;
  }

  const entitySet = new Set<string>();
  if (request.observationProperties) {
    request.observationProperties.forEach((props) => {
      Object.values(props).forEach((val) => entitySet.add(val));
    });
  }
  const entityDcids = Array.from(entitySet);

  const variables = [request.statisticalVariable];
  const denomVar = request.transform?.denominatorStatisticalVariable;
  if (denomVar) {
    variables.push(denomVar);
  }

  const queryCacheKey = getCacheKey(variables, entityDcids);
  let rawResponse = state.cache.get(
    `observations:${queryCacheKey}`
  ) as V2ObservationResponse | undefined;
  if (!rawResponse) {
    rawResponse = state.cache.get(`metadata:${queryCacheKey}`) as
      | V2ObservationResponse
      | undefined;
  }

  if (!rawResponse) {
    const path = '/v2/observation';
    const payload = {
      select: ['entity', 'variable', 'facet'],
      variable: { dcids: variables },
      entity: { dcids: entityDcids },
    };
    rawResponse = (await fetchV2(
      state,
      path,
      payload
    )) as V2ObservationResponse;
    setCache(state, `metadata:${queryCacheKey}`, rawResponse);
  }

  // Build the list of facets associated with primary and denominator variables
  const primaryFacetIds = new Set<string>();
  const denominatorFacetIds = new Set<string>();

  const byVariable = rawResponse?.byVariable || {};
  const primaryVarData = byVariable[request.statisticalVariable];
  if (primaryVarData && primaryVarData.byEntity) {
    Object.values(primaryVarData.byEntity).forEach((entityData) => {
      if (entityData.orderedFacets) {
        entityData.orderedFacets.forEach((f) => {
          if (f.facetId) primaryFacetIds.add(f.facetId);
        });
      }
    });
  }

  if (denomVar) {
    const denomVarData = byVariable[denomVar];
    if (denomVarData && denomVarData.byEntity) {
      Object.values(denomVarData.byEntity).forEach((entityData) => {
        if (entityData.orderedFacets) {
          entityData.orderedFacets.forEach((f) => {
            if (f.facetId) denominatorFacetIds.add(f.facetId);
          });
        }
      });
    }
  }

  // Fetch node properties & resolve provenance names in parallel
  const { nodeProperties, provNamesData } = await resolveMetadataProperties(
    state,
    rawResponse,
    request.statisticalVariable,
    entityDcids,
    denomVar
  );

  // Collect date ranges for facets
  const facetDates = collectFacetDates(byVariable);

  const facets: Facet[] = [];
  const denominatorFacets: Facet[] = [];
  const rawFacets = rawResponse?.facets || {};

  Object.entries(rawFacets).forEach(([id, rawFacet]) => {
    const mapped = mapFacet(
      id,
      rawFacet,
      nodeProperties,
      provNamesData,
      facetDates
    );
    if (primaryFacetIds.has(id)) {
      facets.push(mapped);
    }
    if (denomVar && denominatorFacetIds.has(id)) {
      denominatorFacets.push(mapped);
    }
  });

  // Fallback if no specific association was found in byVariable
  if (facets.length === 0) {
    Object.entries(rawFacets).forEach(([id, rawFacet]) => {
      facets.push(
        mapFacet(id, rawFacet, nodeProperties, provNamesData, facetDates)
      );
    });
  }

  const statisticalVariable = await buildStatisticalVariableInfo(
    state,
    request.statisticalVariable,
    nodeProperties
  );
  const entities = buildEntitiesMetadata(nodeProperties, entityDcids);

  const response: MetadataResponse = {
    observationProperties: request.observationProperties,
    statisticalVariable,
    facets,
    entities,
  };

  if (denomVar) {
    response.denominatorFacets = denominatorFacets;
  }

  deepFreeze(response);
  setCache(state, cacheKey, response);
  return response;
}

/**
 * Retrieves aligned time-series observations matching a primary variable and
 * entity list, automatically handling page-by-page fetching auto-pagination,
 * parallel name/source lookup resolutions, and per-capita scaling divisions.
 *
 * @param state The current client state container.
 * @param request Data criteria, including entity constraint properties list,
 * statistical variable ID, facet selectors, and per-capita scaling parameters.
 * @param _options Optional configuration overrides.
 * @returns A promise resolving to a clean tidy-formatted response.
 * @throws {DataCommonsError} If observations are missing or fetches fail.
 */
export async function getObservations(
  state: DataCommonsClient,
  request: ObservationsRequest,
  _options?: RequestOptions
): Promise<ObservationsResponse> {
  if (_options) {
    // Reserved for future option handling (e.g. localization)
  }
  if (
    !request.observationProperties ||
    !Array.isArray(request.observationProperties)
  ) {
    throw new DataCommonsError(
      'observationProperties is required and must be an array.',
      'INVALID_ARGUMENT'
    );
  }
  const entitySet = new Set<string>();
  request.observationProperties.forEach((props) => {
    Object.values(props).forEach((val) => entitySet.add(val));
  });
  const entityDcids = Array.from(entitySet);

  const variables = [request.statisticalVariableDcid];
  const denomVar = request.transform?.denominatorDcid;
  if (denomVar) {
    variables.push(denomVar);
  }

  const queryCacheKey = getCacheKey(variables, entityDcids);
  let rawResponse = state.cache.get(`observations:${queryCacheKey}`) as V2ObservationResponse | undefined;

  if (!rawResponse) {
    const path = '/v2/observation';
    const payload = {
      select: ['entity', 'variable', 'date', 'value', 'facet'],
      variable: { dcids: variables },
      entity: { dcids: entityDcids },
      date: '',
    };
    rawResponse = await fetchWithPagination(state, path, payload);
    setCache(state, `observations:${queryCacheKey}`, rawResponse);
  }

  const byVariable = rawResponse?.byVariable || {};

  // Determine facet for primary variable
  const primaryVarData = byVariable[request.statisticalVariableDcid];
  if (!primaryVarData || !primaryVarData.byEntity) {
    throw new DataCommonsError(
      `No observation data found for statistical variable ${request.statisticalVariableDcid}`,
      'NO_DATA_FOUND'
    );
  }

  let primaryFacetDcid = request.facetDcid;
  if (!primaryFacetDcid) {
    primaryFacetDcid = selectDefaultFacet(primaryVarData.byEntity);
  }

  const rawFacets = rawResponse?.facets || {};
  const primaryFacetData = rawFacets[primaryFacetDcid];
  if (!primaryFacetData) {
    throw new DataCommonsError(
      `Facet ${primaryFacetDcid} not found in response`,
      'MISSING_FACET'
    );
  }

  // Determine facet for denominator variable
  const denomFacetDcid = request.transform?.denominatorFacetDcid;
  if (denomVar && !denomFacetDcid) {
    throw new DataCommonsError(
      'Per-capita transformations require an explicit denominator facet ' +
        '(transform.denominatorFacetDcid must be specified).',
      'MISSING_DENOMINATOR_FACET'
    );
  }

  // Fetch node properties & resolve provenance names in parallel
  const { nodeProperties, provNamesData } = await resolveMetadataProperties(
    state,
    rawResponse,
    request.statisticalVariableDcid,
    entityDcids,
    denomVar
  );

  // Collect date ranges for facets
  const facetDates = collectFacetDates(byVariable);

  const primaryFacetMapped = mapFacet(
    primaryFacetDcid,
    primaryFacetData,
    nodeProperties,
    provNamesData,
    facetDates
  );
  const denominatorFacetMapped =
    denomFacetDcid && rawFacets[denomFacetDcid]
      ? mapFacet(
          denomFacetDcid,
          rawFacets[denomFacetDcid],
          nodeProperties,
          provNamesData,
          facetDates
        )
      : undefined;

  const entitiesMetadata = buildEntitiesMetadata(nodeProperties, entityDcids);
  const primarySvInfo = await buildStatisticalVariableInfo(
    state,
    request.statisticalVariableDcid,
    nodeProperties
  );

  const observations = alignObservations(
    request,
    primaryVarData,
    primaryFacetDcid,
    denomVar,
    byVariable,
    denomFacetDcid
  );

  const response = {
    header: {
      statisticalVariableInfo: primarySvInfo,
      observationProperties: request.observationProperties,
      facet: primaryFacetMapped,
      denominatorFacet: denominatorFacetMapped,
    },
    observations,
    entities: entitiesMetadata,
  };

  deepFreeze(response);
  return response;
}
