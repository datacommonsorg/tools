import { normalizePlaceType } from '~/functions/normalize_place_type';
import type { QueryResult } from '~/server/types';

/**
 * Derives a deterministic, collision-free scope key for a query result.
 * - Sub-region / child queries (e.g. countries in Africa): `${parentPlaceDcid}:${childPlaceType}` (e.g. "africa:Country")
 * - Single entity queries: entity DCID (e.g. "country/KEN", "africa", "Earth")
 * - Multi-entity comparisons: sorted concatenated DCIDs (e.g. "country/KEN+country/UGA")
 * - Variable place DCID fallback
 */
export const getResultScopeKey = (
  result: QueryResult,
  fallbackPlace?: string,
): string => {
  if (result.isChildQuery || result.parentPlaceDcid) {
    const parentDcid =
      result.parentPlaceDcid || result.placeDcid || fallbackPlace;
    const childType = normalizePlaceType(result.childPlaceType);
    if (parentDcid) {
      return `${parentDcid}:${childType}`;
    }
  }

  const childVar = result.variables.find(
    (v) => v.isChildQuery || !!v.childPlaceType,
  );
  if (childVar) {
    const parentDcid =
      childVar.parentPlaceDcid || childVar.placeDcid || fallbackPlace;
    const childType = normalizePlaceType(childVar.childPlaceType);
    if (parentDcid) {
      return `${parentDcid}:${childType}`;
    }
  }

  if (result.entities.length === 1 && result.entities[0]?.dcid) {
    return result.entities[0].dcid;
  }

  if (result.entities.length > 1) {
    const validDcids = result.entities
      .map((e) => e?.dcid)
      .filter(
        (dcid): dcid is string => typeof dcid === 'string' && dcid.length > 0,
      );
    if (validDcids.length > 0) {
      return validDcids.sort().join('+');
    }
  }

  if (result.variables[0]?.placeDcid) {
    return result.variables[0].placeDcid;
  }

  return fallbackPlace ?? 'unknown';
};

/**
 * Resolves a QueryResult from a HistoryNode's results map using bidirectional matching
 * across direct keys, composite sub-region keys (e.g. "africa:Country"), and place DCIDs.
 */
export const resolveResultForPlace = (
  results: Record<string, QueryResult> | undefined,
  placeDcid: string,
): QueryResult | undefined => {
  if (!results || !placeDcid || placeDcid === '__comparison') return undefined;

  // 1. Direct key match (e.g. "africa:Country" or "country/KEN")
  if (results[placeDcid]) {
    return results[placeDcid];
  }

  // 2. If placeDcid has a colon (e.g. "africa:Country"), try prefix (e.g. "africa")
  if (placeDcid.includes(':')) {
    const prefix = placeDcid.split(':')[0];
    if (prefix && results[prefix]) {
      return results[prefix];
    }
  }

  // 3. If placeDcid lacks a colon (e.g. "africa"), look for keys starting with `${placeDcid}:`
  const matchingKey = Object.keys(results).find((key) =>
    key.startsWith(`${placeDcid}:`),
  );
  if (matchingKey && results[matchingKey]) {
    return results[matchingKey];
  }

  // 4. Fallback: match by result.placeDcid or result.parentPlaceDcid
  const matchingResult = Object.values(results).find(
    (r) => r.placeDcid === placeDcid || r.parentPlaceDcid === placeDcid,
  );
  if (matchingResult) {
    return matchingResult;
  }

  return undefined;
};
