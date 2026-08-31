import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchChildPlaces, fetchNodes } from './dc_api';

describe('dc_api client', () => {
  beforeEach(() => {
    vi.stubEnv('DATA_COMMONS_API_KEY', 'test-key');
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  describe('fetchNodes', () => {
    // Test: Missing API key handling.
    // Situation: DATA_COMMONS_API_KEY is not set in environment.
    // Expectation: fetchNodes throws an error indicating the missing API key.
    it('throws if DATA_COMMONS_API_KEY is not configured', async () => {
      vi.stubEnv('DATA_COMMONS_API_KEY', '');
      await expect(
        fetchNodes(['country/FRA'], '->geoJsonCoordinates'),
      ).rejects.toThrow('DATA_COMMONS_API_KEY environment variable is not set');
    });

    // Test: Successful node query.
    // Situation: Valid API key, querying nodes and property.
    // Expectation: Sends POST request to /v2/node with correct payload and headers and returns parsed JSON.
    it('queries /v2/node with correct headers and payload', async () => {
      const mockResponse = {
        data: {
          'country/FRA': {
            arcs: {
              geoJsonCoordinates: {
                nodes: [{ value: '{"type":"Polygon","coordinates":[]}' }],
              },
            },
          },
        },
      };

      const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => mockResponse,
      } as Response);

      const result = await fetchNodes(['country/FRA'], '->geoJsonCoordinates');
      expect(result).toEqual(mockResponse);
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/v2/node'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            'X-API-Key': 'test-key',
          }),
          body: JSON.stringify({
            nodes: ['country/FRA'],
            property: '->geoJsonCoordinates',
          }),
        }),
      );
    });
  });

  describe('fetchChildPlaces', () => {
    // Test: Child place extraction.
    // Situation: /v2/node returns child place graph arcs for a parent place.
    // Expectation: Extracts and returns an array of ChildPlace objects.
    it('extracts child place nodes from /v2/node response', async () => {
      const mockResponse = {
        data: {
          europe: {
            arcs: {
              '<-containedInPlace+': {
                nodes: [
                  { dcid: 'country/FRA', name: 'France', types: ['Country'] },
                  { dcid: 'country/DEU', name: 'Germany', types: ['Country'] },
                ],
              },
            },
          },
        },
      };

      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => mockResponse,
      } as Response);

      const children = await fetchChildPlaces('europe');
      expect(children).toEqual([
        { dcid: 'country/FRA', name: 'France', types: ['Country'] },
        { dcid: 'country/DEU', name: 'Germany', types: ['Country'] },
      ]);
    });
  });
});
