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

import { describe, it, expect } from 'vitest';
import { toRecharts } from './recharts';
import { toHighcharts } from './highcharts';
import { samplePopulationData } from '../../tests/sample_data';

describe('Adapters', () => {
  it('should transform to Recharts format', () => {
    const result = toRecharts(samplePopulationData);
    expect(result.data).toHaveLength(2); // 2020, 2021
    expect(result.series).toHaveLength(2); // USA, CHN
    expect(result.data[0]).toHaveProperty('country/USA');
    expect(result.data[0]).toHaveProperty('country/CHN');
    expect(result.data[0].date).toBe('2020');
  });

  it('should transform to Highcharts format with datetime timestamps', () => {
    const result = toHighcharts(samplePopulationData, { title: 'Test Title' });
    expect(result.title?.text).toBe('Test Title');
    expect(result.series).toHaveLength(2); // USA, CHN
    expect(result.series[0].data).toHaveLength(2); // 2020, 2021
    expect(result.series[0].data[0][0]).toBe(Date.parse('2020'));
    expect(result.series[0].data[1][0]).toBe(Date.parse('2021'));
    expect(result.xAxis?.type).toBe('datetime');
  });

  it('should correctly parse high-frequency ISO 8601 dates (e.g. daily, monthly)', () => {
    const mockDailyData = {
      header: {
        statisticalVariableInfo: { dcid: 'Count_Person', name: 'Population' },
        observationProperties: [{ entity: 'country/USA' }],
        facet: { facetDcid: 'facet1', importDcid: '', provenanceUrl: 'https://example.org' },
      },
      observations: [
        { date: '2020-04-01', value: 100, observationProperties: { entity: 'country/USA' } },
        { date: '2020-04-02', value: 105, observationProperties: { entity: 'country/USA' } },
        { date: '2020-05', value: 110, observationProperties: { entity: 'country/USA' } },
      ],
      entities: {
        'country/USA': { dcid: 'country/USA', name: 'United States', typeDcid: 'Country' },
      },
    };

    const result = toHighcharts(mockDailyData);
    expect(result.series).toHaveLength(1);
    expect(result.series[0].data).toHaveLength(3);
    
    // Check that dates are resolved to accurate millisecond epoch times
    expect(result.series[0].data[0][0]).toBe(Date.parse('2020-04-01'));
    expect(result.series[0].data[1][0]).toBe(Date.parse('2020-04-02'));
    expect(result.series[0].data[2][0]).toBe(Date.parse('2020-05'));
    expect(result.xAxis?.type).toBe('datetime');
  });

  it('should correctly parse ISO 8601 dates that include time and timezone offsets', () => {
    const mockTimeData = {
      header: {
        statisticalVariableInfo: { dcid: 'Count_Person', name: 'Population' },
        observationProperties: [{ entity: 'country/USA' }],
        facet: { facetDcid: 'facet1', importDcid: '', provenanceUrl: 'https://example.org' },
      },
      observations: [
        { date: '2020-04-01T12:00:00Z', value: 100, observationProperties: { entity: 'country/USA' } },
        { date: '2020-04-01T15:30:00+05:30', value: 105, observationProperties: { entity: 'country/USA' } },
      ],
      entities: {
        'country/USA': { dcid: 'country/USA', name: 'United States', typeDcid: 'Country' },
      },
    };

    const result = toHighcharts(mockTimeData);
    expect(result.series).toHaveLength(1);
    expect(result.series[0].data).toHaveLength(2);
    
    // Validate parsing accuracy down to the millisecond
    // (chronologically sorted)
    expect(result.series[0].data[0][0]).toBe(Date.parse('2020-04-01T15:30:00+05:30'));
    expect(result.series[0].data[1][0]).toBe(Date.parse('2020-04-01T12:00:00Z'));
  });
});
