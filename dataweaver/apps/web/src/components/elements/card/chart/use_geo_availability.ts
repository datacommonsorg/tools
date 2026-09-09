import { useEffect, useState } from 'react';
import {
  fetchGeoJson,
  getCachedGeoJson,
  hasCompleteGeoJson,
  resolveGeoCacheKey,
} from './geo_service';

/**
 * Hook to manage geographic boundary availability state for choropleth charts.
 * Checks cache synchronously on mount and triggers async fetch when un-cached.
 */
export function useGeoAvailability(
  parentPlaceDcid?: string,
  entityKeys?: string[],
): [boolean | null, (available: boolean | null) => void] {
  const [isGeoAvailable, setIsGeoAvailable] = useState<boolean | null>(() => {
    if (!entityKeys || entityKeys.length <= 1) return false;
    const cacheKey = resolveGeoCacheKey(parentPlaceDcid, entityKeys);
    const cached = getCachedGeoJson(cacheKey);
    if (!cached) return null;
    return hasCompleteGeoJson(cached, entityKeys);
  });

  useEffect(() => {
    if (!entityKeys || entityKeys.length <= 1) {
      setIsGeoAvailable(false);
      return;
    }

    const cacheKey = resolveGeoCacheKey(parentPlaceDcid, entityKeys);
    const cached = getCachedGeoJson(cacheKey);
    if (cached) {
      setIsGeoAvailable(hasCompleteGeoJson(cached, entityKeys));
      return;
    }

    let isCurrent = true;
    fetchGeoJson(parentPlaceDcid, entityKeys)
      .then((data) => {
        if (!isCurrent) return;
        setIsGeoAvailable(hasCompleteGeoJson(data, entityKeys));
      })
      .catch(() => {
        if (!isCurrent) return;
        setIsGeoAvailable(false);
      });

    return () => {
      isCurrent = false;
    };
  }, [parentPlaceDcid, entityKeys]);

  return [isGeoAvailable, setIsGeoAvailable];
}
