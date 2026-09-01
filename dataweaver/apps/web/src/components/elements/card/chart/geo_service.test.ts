import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { GeoJsonFeatureCollection } from '~/app/api/geo/route';
import {
  clearGeoCache,
  fetchGeoJson,
  getCachedGeoJson,
  hasCompleteGeoJson,
  resolveGeoCacheKey,
} from './geo_service';

const mockFeatureCollection: GeoJsonFeatureCollection = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      id: 'country/FRA',
      properties: { dcid: 'country/FRA' },
      geometry: { type: 'MultiPolygon', coordinates: [] },
    },
  ],
  parentDcid: 'europe',
};

describe('geo_service', () => {
  beforeEach(() => {
    clearGeoCache();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    clearGeoCache();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  describe('resolveGeoCacheKey', () => {
    // Test: Parent-only key generation.
    // Situation: Only parentPlaceDcid is passed.
    // Expectation: Returns parent:place key format.
    it('returns parent-based key when parentPlaceDcid is present', () => {
      const key = resolveGeoCacheKey('europe');
      expect(key).toBe('parent:europe');
    });

    // Test: Combined parent and entities key.
    // Situation: Both parent and entity DCIDs are passed.
    // Expectation: Returns canonical combined key with sorted entity DCIDs.
    it('returns combined key when parentPlaceDcid and entityDcids are present', () => {
      const key = resolveGeoCacheKey('europe', [
        'country/FRA',
        'country/DEU',
        'default',
      ]);
      expect(key).toBe('parent:europe__entities:country/DEU,country/FRA');
    });

    // Test: Entities-only key.
    // Situation: Only entity DCIDs are passed.
    // Expectation: Returns sorted entities key.
    it('returns entity-based key when only entityDcids are present', () => {
      const key = resolveGeoCacheKey(undefined, ['country/FRA', 'country/DEU']);
      expect(key).toBe('entities:country/DEU,country/FRA');
    });

    // Test: Empty key fallback.
    // Situation: No valid parent or entity DCIDs.
    // Expectation: Returns empty string.
    it('returns empty string when no valid parent or entities are provided', () => {
      expect(resolveGeoCacheKey()).toBe('');
      expect(resolveGeoCacheKey('default', ['default'])).toBe('');
    });
  });

  describe('fetchGeoJson', () => {
    // Test: Cache hit and fetch.
    // Situation: Fetching geo data twice for the same key.
    // Expectation: Network fetch is called once; second call returns cached object from memory.
    it('fetches GeoJSON and populates LRU cache', async () => {
      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => mockFeatureCollection,
      } as Response);

      const result = await fetchGeoJson('europe', ['country/FRA']);
      expect(result).toEqual(mockFeatureCollection);
      expect(fetchSpy).toHaveBeenCalledTimes(1);

      const cacheKey = resolveGeoCacheKey('europe', ['country/FRA']);
      expect(getCachedGeoJson(cacheKey)).toEqual(mockFeatureCollection);

      // Second call should hit the cache and not trigger fetch
      const cachedResult = await fetchGeoJson('europe', ['country/FRA']);
      expect(cachedResult).toEqual(mockFeatureCollection);
      expect(fetchSpy).toHaveBeenCalledTimes(1);
    });

    // Test: Request deduplication.
    // Situation: Multiple concurrent fetch calls for the same key while request is in-flight.
    // Expectation: Only one network fetch is initiated and all callers receive the result.
    it('deduplicates in-flight concurrent requests for the same cache key', async () => {
      let resolveFetch!: (value: unknown) => void;
      const fetchPromise = new Promise((resolve) => {
        resolveFetch = resolve;
      });

      const fetchSpy = vi
        .spyOn(globalThis, 'fetch')
        .mockReturnValue(fetchPromise as Promise<Response>);

      const promise1 = fetchGeoJson('europe');
      const promise2 = fetchGeoJson('europe');

      expect(fetchSpy).toHaveBeenCalledTimes(1);

      resolveFetch({
        ok: true,
        json: async () => mockFeatureCollection,
      });

      const [res1, res2] = await Promise.all([promise1, promise2]);
      expect(res1).toEqual(mockFeatureCollection);
      expect(res2).toEqual(mockFeatureCollection);
      expect(fetchSpy).toHaveBeenCalledTimes(1);
    });

    // Test: Error recovery.
    // Situation: First fetch request rejects with a network error, subsequent retry succeeds.
    // Expectation: Failed promise is evicted from in-flight map and retry triggers a fresh network call.
    it('evicts failed in-flight requests so retries work', async () => {
      const fetchSpy = vi
        .spyOn(globalThis, 'fetch')
        .mockRejectedValueOnce(new Error('Network error'))
        .mockResolvedValueOnce({
          ok: true,
          json: async () => mockFeatureCollection,
        } as Response);

      await expect(fetchGeoJson('europe')).rejects.toThrow('Network error');

      // Retry should trigger a fresh fetch
      const result = await fetchGeoJson('europe');
      expect(result).toEqual(mockFeatureCollection);
      expect(fetchSpy).toHaveBeenCalledTimes(2);
    });
  });

  describe('hasCompleteGeoJson', () => {
    // Test: Full feature coverage.
    // Situation: Collection contains all requested entity DCIDs.
    // Expectation: Returns true.
    it('returns true when all requested entities have features', () => {
      const collection: GeoJsonFeatureCollection = {
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            id: 'country/FRA',
            properties: { dcid: 'country/FRA' },
            geometry: { type: 'Polygon', coordinates: [] },
          },
          {
            type: 'Feature',
            id: 'country/DEU',
            properties: { dcid: 'country/DEU' },
            geometry: { type: 'Polygon', coordinates: [] },
          },
        ],
      };

      expect(
        hasCompleteGeoJson(collection, ['country/FRA', 'country/DEU']),
      ).toBe(true);
    });

    // Test: Incomplete feature coverage.
    // Situation: Collection is missing 1 of the requested entities.
    // Expectation: Returns false.
    it('returns false when any requested entity lacks a feature', () => {
      const collection: GeoJsonFeatureCollection = {
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            id: 'country/FRA',
            properties: { dcid: 'country/FRA' },
            geometry: { type: 'Polygon', coordinates: [] },
          },
        ],
      };

      expect(
        hasCompleteGeoJson(collection, ['country/FRA', 'country/DEU']),
      ).toBe(false);
    });

    // Test: Empty or undefined collection.
    // Situation: Collection is empty or undefined.
    // Expectation: Returns false.
    it('returns false for empty or undefined collection', () => {
      expect(hasCompleteGeoJson(undefined, ['country/FRA'])).toBe(false);
      expect(
        hasCompleteGeoJson({ type: 'FeatureCollection', features: [] }, [
          'country/FRA',
        ]),
      ).toBe(false);
    });
  });
});
