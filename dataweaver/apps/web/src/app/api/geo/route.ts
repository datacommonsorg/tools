import type { NextRequest } from 'next/server';
import { fetchNodes } from '~/server/clients/dc_api';

export interface GeoJsonGeometry {
  type: string;
  coordinates: unknown;
}

export interface GeoJsonFeature {
  type: 'Feature';
  id: string;
  properties: {
    dcid: string;
    [key: string]: unknown;
  };
  geometry: GeoJsonGeometry;
}

export interface GeoJsonFeatureCollection {
  type: 'FeatureCollection';
  features: GeoJsonFeature[];
  parentFeature?: GeoJsonFeature;
  parentDcid?: string;
}

function ringArea(coords: number[][]): number {
  let area = 0;
  for (let i = 0; i < coords.length - 1; i++) {
    const p1 = coords[i];
    const p2 = coords[i + 1];
    if (
      p1 &&
      p2 &&
      typeof p1[0] === 'number' &&
      typeof p1[1] === 'number' &&
      typeof p2[0] === 'number' &&
      typeof p2[1] === 'number'
    ) {
      area += (p2[0] - p1[0]) * (p2[1] + p1[1]);
    }
  }
  return area;
}

function rewindRing(coords: number[][], clockwise: boolean): number[][] {
  const isClockwise = ringArea(coords) >= 0;
  if (isClockwise !== clockwise) {
    return coords.slice().reverse();
  }
  return coords;
}

/**
 * Standardize polygon winding order for D3 rendering.
 * D3 spherical geometry requires clockwise exterior rings (reverse of RFC 7946).
 */
export function normalizeGeometryForD3(geom: GeoJsonGeometry): GeoJsonGeometry {
  if (geom.type === 'Polygon') {
    const coords = geom.coordinates as number[][][];
    const normalized = coords.map((ring, i) => rewindRing(ring, i === 0));
    return {
      type: 'Polygon',
      coordinates: normalized,
    };
  }
  if (geom.type === 'MultiPolygon') {
    const multiCoords = geom.coordinates as number[][][][];
    const normalized = multiCoords.map((polygon) => {
      return polygon.map((ring, i) => rewindRing(ring, i === 0));
    });
    return {
      type: 'MultiPolygon',
      coordinates: normalized,
    };
  }
  return geom;
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const entitiesParam = searchParams.get('entities');
  const parentParam = searchParams.get('parent')?.trim();

  const requestedEntities = (entitiesParam ? entitiesParam.split(',') : [])
    .map((e) => e.split(':')[0]?.trim())
    .filter((e): e is string => !!e && e.length > 0 && e !== 'default');

  // If no specific child entities were provided, use parentParam as the target entity
  const targetEntities =
    requestedEntities.length > 0
      ? requestedEntities
      : parentParam
        ? [parentParam]
        : [];

  if (targetEntities.length === 0) {
    return new Response(
      JSON.stringify({ error: 'Missing entities or parent parameter' }),
      {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      },
    );
  }

  try {
    const nodesToQuery = Array.from(
      new Set([...targetEntities, ...(parentParam ? [parentParam] : [])]),
    );

    // 1. Direct ->geoJsonCoordinates query
    const data = await fetchNodes(
      nodesToQuery,
      '->geoJsonCoordinates',
      request.signal,
    );

    const nodeMap = data.data ?? {};
    const featureMap = new Map<string, GeoJsonFeature>();
    const missingDcids: string[] = [];

    for (const dcid of targetEntities) {
      const record = nodeMap[dcid];
      const rawGeoJson = record?.arcs?.geoJsonCoordinates?.nodes?.[0]?.value;
      if (rawGeoJson) {
        try {
          const rawGeometry = JSON.parse(rawGeoJson) as GeoJsonGeometry;
          const geometry = normalizeGeometryForD3(rawGeometry);
          if (!featureMap.has(dcid)) {
            featureMap.set(dcid, {
              type: 'Feature',
              id: dcid,
              properties: { dcid },
              geometry,
            });
          }
        } catch {
          // Skip invalid JSON geometry
        }
      } else {
        missingDcids.push(dcid);
      }
    }

    // 2. If some entities (e.g. 'europe', 'africa') lack direct geo coordinates, resolve their contained child places
    if (missingDcids.length > 0) {
      try {
        const childData = await fetchNodes(
          missingDcids,
          '<-containedInPlace+',
          request.signal,
        );

        const childDcids: string[] = [];

        for (const parentDcid of missingDcids) {
          const arcMap = childData.data?.[parentDcid]?.arcs;
          if (!arcMap) continue;
          const arcKey =
            Object.keys(arcMap).find((k) => k.includes('containedInPlace')) ||
            Object.keys(arcMap)[0];
          const childNodes = arcKey ? arcMap[arcKey]?.nodes || [] : [];
          for (const n of childNodes) {
            if (
              n.dcid &&
              !featureMap.has(n.dcid) &&
              (n.types?.includes('Country') ||
                n.types?.includes('State') ||
                n.types?.includes('County') ||
                n.types?.includes('Place') ||
                n.types?.includes('AdministrativeArea1') ||
                n.types?.includes('AdministrativeArea2'))
            ) {
              childDcids.push(n.dcid);
            }
          }
        }

        if (childDcids.length > 0) {
          const childGeoData = await fetchNodes(
            childDcids,
            '->geoJsonCoordinates',
            request.signal,
          );
          const childNodeMap = childGeoData.data ?? {};

          for (const cdcid of childDcids) {
            const rawGeoJson =
              childNodeMap[cdcid]?.arcs?.geoJsonCoordinates?.nodes?.[0]?.value;
            if (rawGeoJson && !featureMap.has(cdcid)) {
              try {
                const rawGeometry = JSON.parse(rawGeoJson) as GeoJsonGeometry;
                const geometry = normalizeGeometryForD3(rawGeometry);
                featureMap.set(cdcid, {
                  type: 'Feature',
                  id: cdcid,
                  properties: { dcid: cdcid },
                  geometry,
                });
              } catch {
                // Skip invalid JSON geometry
              }
            }
          }
        }
      } catch {
        // Child resolution fallback best-effort
      }
    }

    const features = Array.from(featureMap.values());

    let parentFeature: GeoJsonFeature | undefined;
    if (parentParam) {
      const parentRecord = nodeMap[parentParam];
      const rawParentGeoJson =
        parentRecord?.arcs?.geoJsonCoordinates?.nodes?.[0]?.value;
      if (rawParentGeoJson) {
        try {
          const rawGeometry = JSON.parse(rawParentGeoJson) as GeoJsonGeometry;
          parentFeature = {
            type: 'Feature',
            id: parentParam,
            properties: { dcid: parentParam },
            geometry: normalizeGeometryForD3(rawGeometry),
          };
        } catch {
          // Ignore invalid JSON geometry
        }
      }
    }

    const featureCollection: GeoJsonFeatureCollection = {
      type: 'FeatureCollection',
      features,
      parentFeature,
      parentDcid: parentParam ?? undefined,
    };

    // TODO (nick-nlb): Explore GeoJSON or TopoJSON polygon simplification or TopoJSON
    // i.e. what resolution do we really need?
    return new Response(JSON.stringify(featureCollection), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': 'public, max-age=86400, stale-while-revalidate=604800',
      },
    });
  } catch (err: unknown) {
    if (request.signal.aborted) {
      return new Response(null, { status: 499 });
    }
    const message =
      err instanceof Error ? err.message : 'Internal server error';
    return new Response(JSON.stringify({ error: message }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
