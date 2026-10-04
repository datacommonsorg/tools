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

import { describe, it, expect, vi } from 'vitest';
import {
  createDataCommonsClient,
  getMetadata,
  getObservations,
  DataCommonsError,
} from '../src/index';
import { sampleV2ObservationResponse } from './sample_v2_responses';

describe('DataCommonsClient state factory', () => {
  it('should initialize with default config', () => {
    const client = createDataCommonsClient({ apiKey: 'test-key' });
    expect(client.config).toEqual({
      apiBaseUrl: 'https://api.datacommons.org',
      apiKey: 'test-key',
      maxPages: 5,
    });
  });

  it('should allow overriding config', () => {
    const client = createDataCommonsClient({
      apiBaseUrl: 'https://custom.api.org',
      apiKey: 'test-key',
      maxPages: 10,
    });
    expect(client.config).toEqual({
      apiBaseUrl: 'https://custom.api.org',
      apiKey: 'test-key',
      maxPages: 10,
    });
  });
});

describe('getMetadata', () => {
  it('should fetch metadata and map response from V2 API with name resolution', async () => {
    const mockFetch = vi.fn().mockImplementation((url) => {
      if (url.includes('/v2/observation')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            byVariable: {
              Count_Person: {
                byEntity: {
                  'country/USA': {
                    orderedFacets: [
                      { facetId: 'f1', earliestDate: '2000', latestDate: '2020', obsCount: 21 }
                    ]
                  }
                }
              }
            },
            facets: {
              f1: { provenanceUrl: 'https://census.gov', measurementMethod: 'CensusDC' }
            }
          }),
        });
      }
      if (url.includes('/v2/node')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            data: {
              'CensusDC': { arcs: { name: { nodes: [{ value: 'United States Census Bureau' }] } } },
              'Count_Person': { arcs: { name: { nodes: [{ value: 'Population' }] }, description: { nodes: [{ value: 'Total population' }] } } },
              'country/USA': { arcs: { name: { nodes: [{ value: 'United States' }] }, typeOf: { nodes: [{ dcid: 'Country' }] } } }
            }
          }),
        });
      }
      return Promise.resolve({ ok: false, status: 404 });
    });
    vi.stubGlobal('fetch', mockFetch);

    const client = createDataCommonsClient({ apiKey: 'test-key' });
    const result = await getMetadata(client, {
      statisticalVariable: 'Count_Person',
      observationProperties: [{ entity: 'country/USA' }]
    });

    expect(result.statisticalVariable.name).toBe('Population');
    expect(result.statisticalVariable.description).toBe('Total population');
    expect(result.facets).toHaveLength(1);
    expect(result.facets[0].facetDcid).toBe('f1');
    expect(result.facets[0].measurementMethodName).toBe('United States Census Bureau');
    expect(result.facets[0].dateRangeStart).toBe('2000');
    expect(result.facets[0].dateRangeEnd).toBe('2020');
    expect(result.entities['country/USA'].name).toBe('United States');
    expect(result.entities['country/USA'].typeDcid).toBe('Country');
  });

  it('should use cache for repeated metadata requests', async () => {
    const mockResponse = {
      byVariable: {
        Count_Person: {
          byEntity: {
            'country/USA': {
              orderedFacets: [{ facetId: 'f1' }]
            }
          }
        }
      },
      facets: {
        f1: { provenanceUrl: 'https://census.gov', measurementMethod: 'Census' }
      }
    };

    const mockFetch = vi.fn().mockImplementation((url) => {
      if (url.includes('/v2/observation')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockResponse),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });
    vi.stubGlobal('fetch', mockFetch);

    const client = createDataCommonsClient({ apiKey: 'test-key' });
    
    // First call
    await getMetadata(client, {
      statisticalVariable: 'Count_Person',
      observationProperties: [{ entity: 'country/USA' }]
    });
    expect(mockFetch).toHaveBeenCalled();
    const callsBefore = mockFetch.mock.calls.length;

    // Second call with same params
    await getMetadata(client, {
      statisticalVariable: 'Count_Person',
      observationProperties: [{ entity: 'country/USA' }]
    });
    // Cache hit, no new fetches
    expect(mockFetch.mock.calls.length).toBe(callsBefore);
  });
});

describe('getObservations', () => {
  it('should fetch observations and flatten response from V2 API with metadata enrichment', async () => {
    const mockFetch = vi.fn().mockImplementation((url) => {
      if (url.includes('/v2/observation')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(sampleV2ObservationResponse),
        });
      }
      if (url.includes('/v2/node')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            data: {
              'country/USA': { arcs: { name: { nodes: [{ value: 'United States' }] }, typeOf: { nodes: [{ dcid: 'Country' }] } } },
              'country/CHN': { arcs: { name: { nodes: [{ value: 'China' }] }, typeOf: { nodes: [{ dcid: 'Country' }] } } },
              'Count_Person': { arcs: { name: { nodes: [{ value: 'Population' }] } } }
            }
          }),
        });
      }
      return Promise.resolve({ ok: false, status: 404 });
    });
    vi.stubGlobal('fetch', mockFetch);

    const client = createDataCommonsClient({ apiKey: 'test-key' });
    const result = await getObservations(client, {
      statisticalVariableDcid: 'Count_Person',
      observationProperties: [{ entity: 'country/USA' }, { entity: 'country/CHN' }],
      facetDcid: '20254455'
    });

    // only 20254455 observations for USA
    expect(result.observations).toHaveLength(2);
    expect(result.observations[0].observationProperties.entity).toBe('country/USA');
    expect(result.entities['country/USA'].name).toBe('United States');
    expect(result.header.statisticalVariableInfo.name).toBe('Population');
    expect(result.header.facet.facetDcid).toBe('20254455');
  });

  it('should calculate per-capita observations when denominator is requested', async () => {
    const mockFetch = vi.fn().mockImplementation((url) => {
      if (url.includes('/v2/observation')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            byVariable: {
              Count_CriminalActivities: {
                byEntity: {
                  'country/USA': {
                    orderedFacets: [{
                      facetId: 'crime_facet',
                      observations: [
                        { date: '2020', value: 1000 },
                        { date: '2021', value: 1200 }
                      ]
                    }]
                  }
                }
              },
              Count_Person: {
                byEntity: {
                  'country/USA': {
                    orderedFacets: [{
                      facetId: 'pop_facet',
                      observations: [
                        { date: '2020', value: 100 },
                        { date: '2021', value: 200 }
                      ]
                    }]
                  }
                }
              }
            },
            facets: {
              crime_facet: { provenanceUrl: 'https://fbi.gov', unit: 'Count' },
              pop_facet: { provenanceUrl: 'https://census.gov', unit: 'Person' }
            }
          }),
        });
      }
      if (url.includes('/v2/node')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            data: {
              'country/USA': { arcs: { name: { nodes: [{ value: 'United States' }] }, typeOf: { nodes: [{ dcid: 'Country' }] } } },
              'Count_CriminalActivities': { arcs: { name: { nodes: [{ value: 'Crimes' }] } } },
              'Count_Person': { arcs: { name: { nodes: [{ value: 'Population' }] } } }
            }
          }),
        });
      }
      return Promise.resolve({ ok: false, status: 404 });
    });
    vi.stubGlobal('fetch', mockFetch);

    const client = createDataCommonsClient({ apiKey: 'test-key' });
    const result = await getObservations(client, {
      statisticalVariableDcid: 'Count_CriminalActivities',
      observationProperties: [{ entity: 'country/USA' }],
      facetDcid: 'crime_facet',
      transform: {
        denominatorDcid: 'Count_Person',
        denominatorFacetDcid: 'pop_facet'
      }
    });

    expect(result.observations).toHaveLength(2);
    // 2020: 1000 / 100 = 10
    expect(result.observations[0].date).toBe('2020');
    expect(result.observations[0].value).toBe(10);
    // 2021: 1200 / 200 = 6
    expect(result.observations[1].date).toBe('2021');
    expect(result.observations[1].value).toBe(6);

    expect(result.header.facet.facetDcid).toBe('crime_facet');
    expect(result.header.denominatorFacet?.facetDcid).toBe('pop_facet');
  });

  it('should throw DataCommonsError when denominator is requested without an explicit denominatorFacetDcid', async () => {
    const client = createDataCommonsClient({ apiKey: 'test-key' });
    await expect(
      getObservations(client, {
        statisticalVariableDcid: 'Count_CriminalActivities',
        observationProperties: [{ entity: 'country/USA' }],
        facetDcid: 'crime_facet',
        transform: {
          denominatorDcid: 'Count_Person'
        }
      })
    ).rejects.toThrowError(/Per-capita transformations require an explicit denominator facet/);
  });

  it('should return deeply frozen, immutable outputs', async () => {
    const mockFetch = vi.fn().mockImplementation((url) => {
      if (url.includes('/v2/observation')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            byVariable: {
              Count_Person: {
                byEntity: {
                  'country/USA': {
                    orderedFacets: [{ facetId: 'f1', observations: [{ date: '2020', value: 100 }] }]
                  }
                }
              }
            },
            facets: { f1: { provenanceUrl: 'https://census.gov' } }
          }),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });
    vi.stubGlobal('fetch', mockFetch);

    const client = createDataCommonsClient({ apiKey: 'test-key' });
    const response = await getObservations(client, {
      statisticalVariableDcid: 'Count_Person',
      observationProperties: [{ entity: 'country/USA' }],
      facetDcid: 'f1'
    });

    expect(Object.isFrozen(response)).toBe(true);
    expect(Object.isFrozen(response.header)).toBe(true);
    expect(Object.isFrozen(response.observations)).toBe(true);
    expect(Object.isFrozen(response.observations[0])).toBe(true);
  });

  it(
    'should throw DataCommonsError if observationProperties is missing',
    async () => {
      const client = createDataCommonsClient({ apiKey: 'test-key' });
      await expect(
        getObservations(client, {
          statisticalVariableDcid: 'Count_Person',
        } as unknown as ObservationsRequest)
      ).rejects.toThrow(DataCommonsError);
    }
  );
});

describe('DataCommonsError', () => {
  it('should create an error with code', () => {
    const err = new DataCommonsError('Something bad', 'bad_request');
    expect(err.message).toBe('Something bad');
    expect(err.code).toBe('bad_request');
    expect(err.name).toBe('DataCommonsError');
  });
});
