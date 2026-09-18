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
 * @fileoverview Adapter to format aligned Headless SDK observations into
 * Highcharts time-series configuration options.
 */

import { ObservationsResponse } from '../index';

export interface HighchartsSeries {
  name: string;
  data: Array<[number, number]>; // [year, value]
}

export interface HighchartsOptions {
  title?: { text: string };
  series: HighchartsSeries[];
  xAxis?: { type: string };
}

/**
 * Transforms ObservationsResponse data into a format suitable for Highcharts.
 */
export function toHighcharts(
  response: ObservationsResponse,
  options?: { title?: string }
): HighchartsOptions {
  const seriesMap: Record<string, HighchartsSeries> = {};

  response.observations.forEach(obs => {
    const timestamp = Date.parse(obs.date);
    const timeVal = isNaN(timestamp) ? parseInt(obs.date, 10) : timestamp;
    const value = obs.value;
    
    // Construct series key by sorting properties and joining entity values
    const props = Object.keys(obs.observationProperties).sort();
    const seriesKey =
      props.map(k => obs.observationProperties[k]).join('->') || 'default';
    
    if (!seriesMap[seriesKey]) {
      const names = props.map(k => {
        const entityId = obs.observationProperties[k];
        const entity = response.entities[entityId];
        return entity ? entity.name : entityId;
      });
      const seriesName = names.join(' to ') || seriesKey;

      seriesMap[seriesKey] = {
        name: seriesName,
        data: [],
      };
    }
    
    seriesMap[seriesKey].data.push([timeVal, value]);
  });

  // Sort data points by timestamp for each series
  Object.values(seriesMap).forEach(s => {
    s.data.sort((a, b) => a[0] - b[0]);
  });

  return {
    title: options?.title ? { text: options.title } : undefined,
    series: Object.values(seriesMap),
    xAxis: { type: 'datetime' },
  };
}
