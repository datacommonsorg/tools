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
 * @fileoverview Helpers for translating raw node attributes, resolving facets,
 * and generating header metadata.
 */

import {
  Facet,
  DataCommonsClient,
  StatisticalVariableInfo,
  EntityMetadata,
} from '../types';
import {
  V2FacetData,
  V2NodePropertyValue,
  V2ObservationResponse,
} from '../types_api';
import { fetchNodeProperties } from '../api';
import { getFirstPropertyValue } from './utils';

/**
 * Translates a URL string to a user-friendly organization name (e.g.
 * 'census.gov' ➔ 'US Census Bureau'). Fallbacks to capitalizing the domain
 * suffix if unrecognized.
 * TODO(beets): Get this data from the graph.
 *
 * @param url The provenance Url.
 * @returns A friendly organization name if recognized, or undefined.
 */
export function getProvenanceNameFromUrl(url: string): string | undefined {
  if (!url) return undefined;
  try {
    const hostname = new URL(url).hostname.replace('www.', '');
    if (hostname.includes('census.gov')) return 'US Census Bureau';
    if (hostname.includes('worldbank.org')) return 'World Bank';
    if (hostname.includes('wikidata.org')) return 'Wikidata';
    if (hostname.includes('eurostat')) return 'Eurostat';
    if (hostname.includes('oecd.org')) return 'OECD';
    if (hostname.includes('cdc.gov')) return 'CDC';
    if (hostname.includes('stats.gov.cn')) {
      return 'National Bureau of Statistics of China';
    }
    if (hostname.includes('inegi.org.mx')) return 'INEGI (Mexico)';
    if (hostname.includes('statcan.gc.ca')) return 'Statistics Canada';
    const parts = hostname.split('.');
    const name = parts[parts.length - 2] || parts[0];
    return name.charAt(0).toUpperCase() + name.slice(1);
  } catch {
    return undefined;
  }
}

/**
 * Maps a raw REST API facet representation into a clean public-domain
 * Facet model. Resolves measurement methods, unit descriptions, and dates.
 *
 * @param id The facet ID string.
 * @param rawFacet Raw REST API facet data.
 * @param nodeProperties Resolved property names and attributes for nodes.
 * @param provNamesData Resolved provenance publisher names.
 * @param facetDates Aggregated date ranges map.
 * @returns The formatted Facet structure.
 */
export function mapFacet(
  id: string,
  rawFacet: V2FacetData,
  nodeProperties: Record<string, Record<string, V2NodePropertyValue[]>>,
  provNamesData: Record<string, Record<string, V2NodePropertyValue[]>>,
  facetDates: Record<string, { start?: string; end?: string }>
): Facet {
  const methodDcid = rawFacet.measurementMethod;
  const unitDcid = rawFacet.unit;
  const importDcid = rawFacet.importName || '';

  const resolvedMethod = methodDcid ? getFirstPropertyValue(nodeProperties[methodDcid], 'name') : undefined;
  const resolvedUnit = unitDcid ? getFirstPropertyValue(nodeProperties[unitDcid], 'name') : undefined;
  const resolvedImportName = importDcid ? getFirstPropertyValue(nodeProperties[importDcid], 'name') : undefined;

  const methodName = resolvedMethod || methodDcid;
  const unitName = resolvedUnit || unitDcid;
  const importName = resolvedImportName || importDcid;

  let provenanceName = undefined;
  if (importDcid) {
    const prov = nodeProperties[importDcid]?.['provenance'];
    const provDcid = prov?.[0]?.dcid;
    if (provDcid) {
      provenanceName = getFirstPropertyValue(provNamesData[provDcid], 'name');
    }
  }
  if (!provenanceName && rawFacet.provenanceUrl) {
    provenanceName = getProvenanceNameFromUrl(rawFacet.provenanceUrl);
  }
  if (!provenanceName) {
    provenanceName = importName;
  }

  const dates = facetDates[id] || {};

  return {
    facetDcid: id,
    provenanceName,
    provenanceUrl: rawFacet.provenanceUrl,
    importDcid,
    importName,
    measurementMethodDcid: methodDcid,
    measurementMethodName: methodName,
    measurementMethodDesc: methodDcid
      ? getFirstPropertyValue(nodeProperties[methodDcid], 'description')
      : undefined,
    observationPeriod: rawFacet.observationPeriod,
    dateRangeStart: dates.start,
    dateRangeEnd: dates.end,
    unitDcid,
    unitName,
  };
}

/**
 * Resolves node attributes (like names, units, measurement qualifiers)
 * and provenance names in parallel for a given list of variable and entity
 * DCIDs.
 *
 * @param state The current client state container.
 * @param rawResponse The raw API response to extract facet IDs from.
 * @param statisticalVariable The primary variable DCID.
 * @param entityDcids The list of entity DCIDs.
 * @param denomVar The optional denominator variable DCID.
 * @returns Node properties and provenance publisher names maps.
 */
export async function resolveMetadataProperties(
  state: DataCommonsClient,
  rawResponse: V2ObservationResponse,
  statisticalVariable: string,
  entityDcids: string[],
  denomVar?: string
): Promise<{
  nodeProperties: Record<string, Record<string, V2NodePropertyValue[]>>;
  provNamesData: Record<string, Record<string, V2NodePropertyValue[]>>;
}> {
  const nodeDcids = new Set<string>();
  nodeDcids.add(statisticalVariable);
  if (denomVar) {
    nodeDcids.add(denomVar);
  }
  entityDcids.forEach((e) => nodeDcids.add(e));

  const rawFacets = rawResponse.facets || {};
  Object.values(rawFacets).forEach((facet) => {
    if (facet.measurementMethod) nodeDcids.add(facet.measurementMethod);
    if (facet.unit) nodeDcids.add(facet.unit);
    if (facet.importName) nodeDcids.add(facet.importName);
  });

  const nodeProperties = await fetchNodeProperties(
    state,
    Array.from(nodeDcids),
    [
      'name',
      'description',
      'measurementQualifier',
      'measurementDenominator',
      'provenance',
      'typeOf',
    ]
  );

  // Second level resolution for Provenance names
  const provDcids = new Set<string>();
  Object.values(rawFacets).forEach((facet) => {
    if (facet.importName) {
      const prov = nodeProperties[facet.importName]?.['provenance'];
      if (prov) {
        const provDcid = prov[0]?.dcid;
        if (provDcid) provDcids.add(provDcid);
      }
    }
  });

  let provNamesData: Record<
    string,
    Record<string, V2NodePropertyValue[]>
  > = {};
  if (provDcids.size > 0) {
    provNamesData = await fetchNodeProperties(
      state,
      Array.from(provDcids),
      ['name']
    );
  }

  return { nodeProperties, provNamesData };
}

/**
 * Builds a StatisticalVariableInfo object, resolving its name, description,
 * measurement qualifier, and measurement denominator metadata.
 *
 * @param state The current client state container.
 * @param dcid The statistical variable DCID.
 * @param nodeProperties The resolved properties map of DCID properties.
 * @returns A promise resolving to the StatisticalVariableInfo description.
 */
export async function buildStatisticalVariableInfo(
  state: DataCommonsClient,
  dcid: string,
  nodeProperties: Record<string, Record<string, V2NodePropertyValue[]>>
): Promise<StatisticalVariableInfo> {
  const svData = nodeProperties[dcid] || {};
  const qualifierObj = svData['measurementQualifier']?.[0];
  const qualifierDcid =
    typeof qualifierObj === 'string' ? qualifierObj : qualifierObj?.dcid;
  const svDenomObj = svData['measurementDenominator']?.[0];
  const svDenomDcid =
    typeof svDenomObj === 'string' ? svDenomObj : svDenomObj?.dcid;

  const extraDcids = new Set<string>();
  if (qualifierDcid) extraDcids.add(qualifierDcid);
  if (svDenomDcid) extraDcids.add(svDenomDcid);

  let extraNames: Record<string, Record<string, V2NodePropertyValue[]>> = {};
  if (extraDcids.size > 0) {
    extraNames = await fetchNodeProperties(
      state,
      Array.from(extraDcids),
      ['name']
    );
  }

  return {
    dcid,
    name: getFirstPropertyValue(svData, 'name') || dcid,
    description: getFirstPropertyValue(svData, 'description'),
    measurementQualifierDcid: qualifierDcid,
    measurementQualifierName: qualifierDcid
      ? getFirstPropertyValue(extraNames[qualifierDcid], 'name')
      : undefined,
    measurementDenominatorDcid: svDenomDcid,
    measurementDenominatorName: svDenomDcid
      ? getFirstPropertyValue(extraNames[svDenomDcid], 'name')
      : undefined,
  };
}

/**
 * Compiles a dictionary of EntityMetadata descriptions for a list of
 * entity DCIDs.
 *
 * @param nodeProperties Resolved properties map containing names and types.
 * @param entityDcids The list of entity DCIDs.
 * @returns A mapping from entity DCIDs to EntityMetadata descriptors.
 */
export function buildEntitiesMetadata(
  nodeProperties: Record<string, Record<string, V2NodePropertyValue[]>>,
  entityDcids: string[]
): Record<string, EntityMetadata> {
  const entities: Record<string, EntityMetadata> = {};
  entityDcids.forEach((dcid) => {
    const data = nodeProperties[dcid] || {};
    entities[dcid] = {
      dcid,
      name: getFirstPropertyValue(data, 'name') || dcid,
      typeDcid: getFirstPropertyValue(data, 'typeOf') || 'Unknown',
    };
  });
  return entities;
}
