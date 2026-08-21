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
 * @fileoverview Adapter to format and pivot aligned Headless SDK observations
 * into Recharts data series.
 */

import { ObservationsResponse } from '../index';

export interface RechartsSeries {
  id: string;
  name: string;
  color?: string;
}

export interface RechartsData {
  // Pivoted data: [{ date: '2020', 'country/USA': 10, 'country/CHN': 20 }]
  data: Array<Record<string, unknown>>;
  series: RechartsSeries[];
}

/**
 * Pivots ObservationsResponse data into a wide format suitable for Recharts.
 */
export function toRecharts(response: ObservationsResponse): RechartsData {
  const dataMap: Record<string, Record<string, unknown>> = {};
  const seriesMap: Record<string, RechartsSeries> = {};

  response.observations.forEach(obs => {
    const date = obs.date;
    const value = obs.value;
    
    // Construct series key by sorting properties and joining entity values
    const props = Object.keys(obs.observationProperties).sort();
    const seriesKey =
      props.map(k => obs.observationProperties[k]).join('->') || 'default';
    
    if (!dataMap[date]) {
      dataMap[date] = { date };
    }
    dataMap[date][seriesKey] = value;

    if (!seriesMap[seriesKey]) {
      const names = props.map(k => {
        const entityId = obs.observationProperties[k];
        const entity = response.entities[entityId];
        return entity ? entity.name : entityId;
      });
      const seriesName = names.join(' to ') || seriesKey;

      seriesMap[seriesKey] = {
        id: seriesKey,
        name: seriesName,
      };
    }
  });

  const data = Object.values(dataMap).sort((a, b) =>
    (a.date as string).localeCompare(b.date as string)
  );
  const series = Object.values(seriesMap);

  return { data, series };
}
