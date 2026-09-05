import type { NextRequest } from 'next/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as dcApi from '~/server/clients/dc_api';
import { GET, type GeoJsonGeometry, normalizeGeometryForD3 } from './route';

describe('normalizeGeometryForD3', () => {
  // Test: Polygon preservation.
  // Situation: Valid Polygon geometry input.
  // Expectation: Preserves type and coordinate dimensions.
  it('preserves Polygon geometry type and 3D coordinate dimensionality', () => {
    // Counter-clockwise polygon (RFC 7946 standard)
    const polygon: GeoJsonGeometry = {
      type: 'Polygon',
      coordinates: [
        [
          [0, 0],
          [10, 0],
          [10, 10],
          [0, 10],
          [0, 0],
        ],
      ],
    };

    const normalized = normalizeGeometryForD3(polygon);
    expect(normalized.type).toBe('Polygon');
    expect(Array.isArray(normalized.coordinates)).toBe(true);

    const coords = normalized.coordinates as number[][][];
    expect(coords.length).toBe(1);
    expect(coords[0]?.length).toBe(5);
  });

  // Test: Winding order standardization.
  // Situation: Counter-clockwise exterior ring in Polygon.
  // Expectation: Reverses coordinates to clockwise for D3 spherical rendering.
  it('normalizes exterior rings to clockwise for D3 spherical projection', () => {
    // Counter-clockwise ring: area is negative using ringArea surveyor formula
    const ccwPolygon: GeoJsonGeometry = {
      type: 'Polygon',
      coordinates: [
        [
          [0, 0],
          [10, 0],
          [10, 10],
          [0, 10],
          [0, 0],
        ],
      ],
    };

    const normalized = normalizeGeometryForD3(ccwPolygon);
    const coords = normalized.coordinates as number[][][];
    const ring = coords[0] ?? [];

    // The ring should be reversed to be clockwise
    expect(ring[0]).toEqual([0, 0]);
    expect(ring[1]).toEqual([0, 10]);
    expect(ring[2]).toEqual([10, 10]);
    expect(ring[3]).toEqual([10, 0]);
    expect(ring[4]).toEqual([0, 0]);
  });

  // Test: MultiPolygon coordinate normalization.
  // Situation: MultiPolygon geometry with multiple disjoint polygons.
  // Expectation: Preserves MultiPolygon type and 4D coordinate structure.
  it('preserves MultiPolygon geometry type and 4D coordinate dimensionality', () => {
    const multiPolygon: GeoJsonGeometry = {
      type: 'MultiPolygon',
      coordinates: [
        [
          [
            [0, 0],
            [10, 0],
            [10, 10],
            [0, 10],
            [0, 0],
          ],
        ],
        [
          [
            [20, 20],
            [30, 20],
            [30, 30],
            [20, 30],
            [20, 20],
          ],
        ],
      ],
    };

    const normalized = normalizeGeometryForD3(multiPolygon);
    expect(normalized.type).toBe('MultiPolygon');
    const coords = normalized.coordinates as number[][][][];
    expect(coords.length).toBe(2);
    expect(coords[0]?.[0]?.length).toBe(5);
    expect(coords[1]?.[0]?.length).toBe(5);
  });

  // Test: Unsupported geometry pass-through.
  // Situation: Point geometry passed into normalizer.
  // Expectation: Returns unmodified geometry.
  it('passes through unsupported geometry types unmodified', () => {
    const point: GeoJsonGeometry = {
      type: 'Point',
      coordinates: [10, 20],
    };

    expect(normalizeGeometryForD3(point)).toEqual(point);
  });
});

describe('GET /api/geo', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  // Test: Parameter validation.
  // Situation: Request has neither entities nor parent parameter.
  // Expectation: Responds with 400 and error message.
  it('returns 400 when no entity or parent is provided', async () => {
    const req = new Request(
      'http://localhost/api/geo',
    ) as unknown as NextRequest;
    const res = await GET(req);
    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error).toBe('Missing entities or parent parameter');
  });

  // Test: Successful GeoJSON retrieval.
  // Situation: Valid entity DCID requested, Data Commons API returns coordinates.
  // Expectation: Returns 200 FeatureCollection with public cache headers and normalized geometry.
  it('fetches coordinates for requested entities and returns GeoJSON collection', async () => {
    vi.spyOn(dcApi, 'fetchNodes').mockResolvedValue({
      data: {
        'country/FRA': {
          arcs: {
            geoJsonCoordinates: {
              nodes: [
                {
                  value: JSON.stringify({
                    type: 'Polygon',
                    coordinates: [
                      [
                        [0, 0],
                        [5, 0],
                        [5, 5],
                        [0, 5],
                        [0, 0],
                      ],
                    ],
                  }),
                },
              ],
            },
          },
        },
      },
    });

    const req = new Request(
      'http://localhost/api/geo?entities=country/FRA',
    ) as unknown as NextRequest;
    const res = await GET(req);
    expect(res.status).toBe(200);
    expect(res.headers.get('Cache-Control')).toContain('public, max-age=86400');

    const json = await res.json();
    expect(json.type).toBe('FeatureCollection');
    expect(json.features.length).toBe(1);
    expect(json.features[0].id).toBe('country/FRA');
    expect(json.features[0].geometry.type).toBe('Polygon');
  });
});
