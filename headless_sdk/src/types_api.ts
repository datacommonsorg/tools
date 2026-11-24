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
 * @fileoverview Data Commons V2 REST API contract types and raw node models.
 */

export interface V2FacetData {
  provenanceUrl?: string;
  measurementMethod?: string;
  unit?: string;
  importName?: string;
  observationPeriod?: string;
}

export interface V2ObservationPoint {
  date: string;
  value: number;
  attributes?: Record<string, string>;
}

export interface V2OrderedFacet {
  facetId?: string;
  earliestDate?: string;
  latestDate?: string;
  obsCount?: number;
  observations?: V2ObservationPoint[];
}

export interface V2EntityData {
  orderedFacets?: V2OrderedFacet[];
}

export interface V2VariableData {
  byEntity?: Record<string, V2EntityData>;
}

export interface V2ObservationResponse {
  byVariable?: Record<string, V2VariableData>;
  facets?: Record<string, V2FacetData>;
  nextToken?: string;
  next_token?: string;
}

export interface V2NodePropertyValue {
  value?: string;
  name?: string;
  dcid?: string;
  provenance?: string | { dcid: string };
}

export interface V2NodePropertyArc {
  nodes?: V2NodePropertyValue[];
}

export interface V2NodeData {
  arcs?: Record<string, V2NodePropertyArc>;
  provenance?: string | { dcid: string } | Array<{ dcid: string }>;
}

export interface V2NodeResponse {
  data?: Record<string, V2NodeData>;
}
