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
 * @fileoverview Domain model type definitions for the public Headless SDK
 * interface (clients, requests, responses).
 */

/**
 * Base configuration for the DataCommons client.
 */
export interface ClientConfig {
  /**
   * Base URL for the Data Commons API.
   * @default 'https://api.datacommons.org'
   */
  apiBaseUrl?: string;

  /**
   * API Key for the Data Commons API.
   * Optional.
   */
  apiKey?: string;

  /**
   * Maximum number of pages to fetch for paginated endpoints.
   * @default 5
   */
  maxPages?: number;
}

/**
 * State object representing an initialized client.
 */
export interface DataCommonsClient {
  config: ClientConfig;
  cache: Map<string, unknown>;
}

/**
 * Shared options for request formatting.
 */
export interface RequestOptions {
  language?: string; // BCP 47
}

/**
 * Metadata about a statistical variable.
 */
export interface StatisticalVariableInfo {
  dcid: string;
  name: string;
  description?: string;
  // TODO: Add other resolved propreties of a stat var.
  measurementQualifierDcid?: string;
  measurementQualifierName?: string;
  measurementDenominatorDcid?: string;
  measurementDenominatorName?: string;
}

/**
 * Metadata about a place or entity.
 */
export interface EntityMetadata {
  dcid: string;
  name: string;
  typeDcid: string;
}

/**
 * Flat representation of a facet (metadata about a
 * source/provenance/methodology).
 */
export interface Facet {
  facetDcid: string;
  provenanceName?: string;
  provenanceUrl?: string;
  importDcid: string;
  importName?: string;
  measurementMethodDcid?: string;
  measurementMethodName?: string;
  measurementMethodDesc?: string;
  observationPeriod?: string;
  dateRangeStart?: string;
  dateRangeEnd?: string;
  unitDcid?: string;
  unitName?: string;
}

/**
 * Request structure for getMetadata.
 */
export interface MetadataRequest {
  statisticalVariable: string;
  observationProperties: Record<string, string>[];
  transform?: {
    denominatorStatisticalVariable?: string;
  };
}

/**
 * Response structure for getMetadata.
 */
export interface MetadataResponse {
  observationProperties: Record<string, string>[];
  statisticalVariable: StatisticalVariableInfo;
  facets: Facet[];
  denominatorFacets?: Facet[];
  entities: Record<string, EntityMetadata>;
}

/**
 * Request structure for getObservations.
 */
export interface ObservationsRequest {
  statisticalVariableDcid: string;
  observationProperties: Record<string, string>[];
  startDate?: string;
  endDate?: string;
  facetDcid?: string;
  transform?: {
    denominatorDcid?: string;
    denominatorFacetDcid?: string;
  };
}

/**
 * Response structure for getObservations.
 */
export interface ObservationsResponse {
  header: {
    statisticalVariableInfo: StatisticalVariableInfo;
    observationProperties: Record<string, string>[];
    facet: Facet;
    denominatorFacet?: Facet;
  };
  observations: ObservationPoint[];
  entities: Record<string, EntityMetadata>;
}

/**
 * Observation point.
 */
export interface ObservationPoint {
  date: string;
  value: number;
  observationProperties: Record<string, string>;
  attributes?: Record<string, string>;
}
