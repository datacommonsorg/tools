import { LRUCache } from 'lru-cache';
import type { GeoJsonFeatureCollection } from '~/app/api/geo/route';

/**
 * Maximum total memory budget allocated for cached GeoJSON geometries (25 MB).
 */
const GEO_CACHE_MAX_BYTES = 25 * 1024 * 1024;

/**
 * Calculates estimated byte footprint for a GeoJsonFeatureCollection.
 * Traverses geometry coordinates to compute memory size without expensive serialization.
 */
const calculateGeoJsonByteSize = (
  collection: GeoJsonFeatureCollection,
): number => {
  let totalPoints = 0;
  for (const feature of collection.features) {
    const geom = feature.geometry;
    if (!geom || !geom.coordinates) continue;
    if (geom.type === 'Polygon') {
      const rings = geom.coordinates as number[][][];
      for (const ring of rings) totalPoints += ring.length;
    } else if (geom.type === 'MultiPolygon') {
      const polys = geom.coordinates as number[][][][];
      for (const poly of polys) {
        for (const ring of poly) totalPoints += ring.length;
      }
    }
  }
  // Approximate ~24 bytes per coordinate pair in memory + base object overhead
  return Math.max(1024, totalPoints * 24 + collection.features.length * 200);
};

const geoJsonCache = new LRUCache<string, GeoJsonFeatureCollection>({
  maxSize: GEO_CACHE_MAX_BYTES,
  sizeCalculation: calculateGeoJsonByteSize,
});

const inFlightRequests = new Map<string, Promise<GeoJsonFeatureCollection>>();

/**
 * Derives a canonical cache key for geographic boundaries.
 * Prioritizes parent place hierarchy when available and canonicalizes entity lists.
 */
export const resolveGeoCacheKey = (
  parentPlaceDcid?: string,
  entityDcids?: string[],
): string => {
  const sortedEntities = Array.from(new Set(entityDcids ?? []))
    .filter((d): d is string => !!d && d !== 'default')
    .sort();

  const normalizedParent = parentPlaceDcid?.trim();
  const hasParent = !!normalizedParent && normalizedParent !== 'default';

  if (hasParent && sortedEntities.length > 0) {
    return `parent:${normalizedParent}__entities:${sortedEntities.join(',')}`;
  }

  if (hasParent) {
    return `parent:${normalizedParent}`;
  }

  if (sortedEntities.length > 0) {
    return `entities:${sortedEntities.join(',')}`;
  }

  return '';
};

/**
 * Returns cached GeoJSON if available in memory.
 */
export const getCachedGeoJson = (
  cacheKey: string,
): GeoJsonFeatureCollection | undefined => {
  if (!cacheKey) return undefined;
  return geoJsonCache.get(cacheKey);
};

/**
 * Checks whether a GeoJsonFeatureCollection contains features for all requested entity DCIDs (100% coverage).
 */
export const hasCompleteGeoJson = (
  collection: GeoJsonFeatureCollection | undefined,
  entityDcids?: string[],
): boolean => {
  if (!collection || collection.features.length === 0) return false;
  const validEntities = (entityDcids ?? []).filter(
    (d): d is string => !!d && d !== 'default',
  );
  if (validEntities.length === 0) return false;
  const featureIds = new Set(collection.features.map((f) => f.id));
  return validEntities.every((dcid) => featureIds.has(dcid));
};

/**
 * Clears the geographic boundary cache (useful for testing or full resets).
 */
export const clearGeoCache = (): void => {
  geoJsonCache.clear();
  inFlightRequests.clear();
};

/**
 * Fetches geographic boundaries with in-flight request deduplication and LRU caching.
 * Uncouples the shared network fetch from individual component lifecycle aborts.
 */
export const fetchGeoJson = async (
  parentPlaceDcid?: string,
  entityDcids?: string[],
): Promise<GeoJsonFeatureCollection> => {
  const cacheKey = resolveGeoCacheKey(parentPlaceDcid, entityDcids);
  if (!cacheKey) {
    throw new Error('Missing parent place DCID or entity DCIDs for geo query');
  }

  const cached = geoJsonCache.get(cacheKey);
  if (cached) {
    return cached;
  }

  const inFlight = inFlightRequests.get(cacheKey);
  if (inFlight) {
    return inFlight;
  }

  const sortedEntities = Array.from(new Set(entityDcids ?? []))
    .filter((d): d is string => !!d && d !== 'default')
    .sort();

  const normalizedParent = parentPlaceDcid?.trim();
  const hasParent = !!normalizedParent && normalizedParent !== 'default';

  const params = new URLSearchParams();
  if (sortedEntities.length > 0) {
    params.set('entities', sortedEntities.join(','));
  }
  if (hasParent) {
    params.set('parent', normalizedParent);
  }
  params.set('v', 'd3_norm');

  const url = `/api/geo?${params.toString()}`;

  const fetchPromise = (async () => {
    try {
      const res = await fetch(url);
      if (!res.ok) {
        throw new Error(`Failed to fetch geography boundaries (${res.status})`);
      }
      const data: GeoJsonFeatureCollection = await res.json();
      geoJsonCache.set(cacheKey, data);
      return data;
    } finally {
      inFlightRequests.delete(cacheKey);
    }
  })();

  inFlightRequests.set(cacheKey, fetchPromise);
  return fetchPromise;
};
