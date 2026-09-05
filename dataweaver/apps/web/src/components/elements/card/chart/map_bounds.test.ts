import { geoEquirectangular, geoPath } from 'd3-geo';
import { describe, expect, it } from 'vitest';
import type { GeoJsonFeature } from '~/app/api/geo/route';
import {
  calculateFitBounds,
  calculatePolygonRingArea,
  getFittingGeometry,
} from './map_bounds';
import { getMapProjection } from './map_projection';

describe('calculatePolygonRingArea', () => {
  // Test: Square area calculation.
  // Situation: Coordinates defining a 10x10 square.
  // Expectation: Surveyor formula computes exact area of 100.
  it('calculates the area of a square polygon ring', () => {
    const square = [
      [0, 0],
      [10, 0],
      [10, 10],
      [0, 10],
      [0, 0],
    ];
    expect(calculatePolygonRingArea(square)).toBe(100);
  });

  // Test: Degenerate rings.
  // Situation: Empty array or single point coordinate array.
  // Expectation: Returns 0 without errors.
  it('returns 0 for empty or degenerate rings', () => {
    expect(calculatePolygonRingArea([])).toBe(0);
    expect(calculatePolygonRingArea([[0, 0]])).toBe(0);
  });
});

describe('getFittingGeometry', () => {
  // Test: Single polygon pass-through.
  // Situation: Polygon type geometry.
  // Expectation: Returned as-is.
  it('preserves single polygon geometries as-is', () => {
    const polygon = {
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
    };
    expect(getFittingGeometry(polygon)).toEqual(polygon);
  });

  // Test: Landmass filtering.
  // Situation: MultiPolygon with large mainland (area 10,000) and tiny island (area 1).
  // Expectation: Filters out the tiny island (< 5% of max) so only mainland is used for bounds fitting.
  it('filters out tiny island polygons from multi-polygons', () => {
    const mainLandmass = [
      [
        [0, 0],
        [100, 0],
        [100, 100],
        [0, 100],
        [0, 0],
      ], // Area = 10000
    ];
    const tinyIsland = [
      [
        [500, 500],
        [501, 500],
        [501, 501],
        [500, 501],
        [500, 500],
      ], // Area = 1 (< 0.05 * 10000 = 500)
    ];

    const multiPoly = {
      type: 'MultiPolygon',
      coordinates: [mainLandmass, tinyIsland],
    };

    const fitting = getFittingGeometry(multiPoly);
    expect(fitting.type).toBe('MultiPolygon');
    expect(fitting.coordinates).toEqual([mainLandmass]);
  });
});

describe('calculateFitBounds', () => {
  const proj = geoEquirectangular();
  const pathGenerator = geoPath().projection(proj);

  // Test: Single feature bounds.
  // Situation: One feature polygon provided.
  // Expectation: Returns valid bounding box with min < max coordinates.
  it('calculates bounds for a single feature', () => {
    const feature: GeoJsonFeature = {
      type: 'Feature',
      id: 'test',
      properties: { dcid: 'test' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [10, 10],
            [10, 20],
            [20, 20],
            [20, 10],
            [10, 10],
          ],
        ],
      },
    };

    const bounds = calculateFitBounds([feature], pathGenerator);
    expect(bounds).not.toBeNull();
    if (!bounds) throw new Error('Bounds should not be null');
    expect(bounds[0][0]).toBeLessThan(bounds[1][0]);
    expect(bounds[0][1]).toBeLessThan(bounds[1][1]);
  });

  // Test: Outlier suppression.
  // Situation: 6 clustered features plus 1 distant spatial outlier feature.
  // Expectation: Outlier is filtered out of bounding box via IQR thresholding.
  it('suppresses extreme spatial centroid outliers in clusters of >= 5 features', () => {
    const makeSquare = (id: string, x: number, y: number): GeoJsonFeature => ({
      type: 'Feature',
      id,
      properties: { dcid: id },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [x, y],
            [x, y + 1],
            [x + 1, y + 1],
            [x + 1, y],
            [x, y],
          ],
        ],
      },
    });

    const cluster = [
      makeSquare('1', 0, 0),
      makeSquare('2', 1, 0),
      makeSquare('3', 2, 0),
      makeSquare('4', 0, 1),
      makeSquare('5', 1, 1),
      makeSquare('6', 2, 1),
    ];

    // Outlier far away (e.g. at longitude 170)
    const outlier = makeSquare('outlier', 170, 0);

    const boundsWithOutlier = calculateFitBounds(
      [...cluster, outlier],
      pathGenerator,
    );
    expect(boundsWithOutlier).not.toBeNull();
    if (!boundsWithOutlier) throw new Error('Bounds should not be null');

    // The outlier at x=170 should have been filtered out of the fitting box
    // So the maxX should be around x=3, not x=171
    const projOutlierX = proj([170, 0])?.[0] ?? 0;
    expect(boundsWithOutlier[1][0]).toBeLessThan(projOutlierX - 50);
  });
});

describe('getMapProjection', () => {
  // Test: Regional projection mapping.
  // Situation: Querying projections for europe, asia, country/USA, and generic places.
  // Expectation: Returns optimal projection types and fitted status.
  it('returns fixed Lambert Azimuthal projection for Europe', () => {
    const res = getMapProjection('europe', 600, 400);
    expect(res.isMapFitted).toBe(true);
    expect(res.projection).toBeDefined();
  });

  it('returns fixed Equirectangular projection rotated for Asia', () => {
    const res = getMapProjection('asia', 600, 400);
    expect(res.isMapFitted).toBe(true);
    expect(res.projection).toBeDefined();
  });

  it('returns Albers USA projection for US states', () => {
    const res = getMapProjection('country/USA', 600, 400, [
      'geoId/06',
      'geoId/36',
    ]);
    expect(res.isMapFitted).toBe(true);
    expect(res.projection).toBeDefined();
  });

  it('returns standard Equirectangular projection for general places', () => {
    const res = getMapProjection('africa', 600, 400);
    expect(res.isMapFitted).toBe(false);
  });
});
