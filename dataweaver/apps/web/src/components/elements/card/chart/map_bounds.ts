import type { GeoGeometryObjects, GeoPath } from 'd3-geo';
import type { GeoJsonFeature, GeoJsonGeometry } from '~/app/api/geo/route';

/**
 * Calculates the 2D polygon ring area using the surveyor's formula.
 */
export function calculatePolygonRingArea(ring: number[][]): number {
  if (!ring || ring.length < 3) return 0;
  let area = 0;
  for (let i = 0; i < ring.length - 1; i++) {
    const p1 = ring[i];
    const p2 = ring[i + 1];
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
  return Math.abs(area) / 2;
}

/**
 * Measure 2: Primary Landmass Filtering.
 * For MultiPolygon geometries (e.g. France with overseas territories, Norway with remote islands),
 * filters out outlying island sub-polygons whose area is less than 5% of the entity's primary polygon
 * specifically for camera bounds fitting, so small outlying territories do not distort the zoom scale.
 */
export function getFittingGeometry(geom: GeoJsonGeometry): GeoJsonGeometry {
  if (geom.type !== 'MultiPolygon') return geom;
  const multiCoords = geom.coordinates as number[][][][];
  if (!Array.isArray(multiCoords) || multiCoords.length <= 1) return geom;

  const areas = multiCoords.map((polygon) => {
    const exteriorRing = polygon[0];
    return exteriorRing ? calculatePolygonRingArea(exteriorRing) : 0;
  });

  const maxArea = Math.max(...areas);
  if (maxArea <= 0) return geom;

  // Filter out sub-polygons smaller than 5% of the largest polygon
  const filtered = multiCoords.filter(
    (_, idx) => (areas[idx] ?? 0) >= maxArea * 0.05,
  );

  return {
    type: 'MultiPolygon',
    coordinates: filtered.length > 0 ? filtered : multiCoords,
  };
}

/**
 * Measure 3: Centroid Quantile / Spatial Outlier Filtering.
 * When calculating the combined bounding box across multiple discrete features,
 * calculates individual feature centroids and ignores extreme spatial outliers (> 2.5x IQR)
 * so that a distant outlier (e.g. Russia spanning to 180° in Europe, or Alaska in North America)
 * does not collapse the central framing of the primary group.
 */
export function calculateFitBounds(
  features: GeoJsonFeature[],
  pathGenerator: GeoPath<unknown, GeoGeometryObjects>,
): [[number, number], [number, number]] | null {
  if (features.length === 0) return null;

  if (features.length === 1 && features[0]) {
    const geom = getFittingGeometry(features[0].geometry);
    // @ts-expect-error - d3-geo geometry compatibility
    return pathGenerator.bounds(geom);
  }

  interface FeatureBoundInfo {
    bounds: [[number, number], [number, number]];
    cx: number;
    cy: number;
  }

  const boundsList: FeatureBoundInfo[] = [];

  for (const f of features) {
    const geom = getFittingGeometry(f.geometry);
    // @ts-expect-error - d3-geo geometry compatibility
    const b = pathGenerator.bounds(geom);
    const w = b[1][0] - b[0][0];
    const h = b[1][1] - b[0][1];
    if (
      !Number.isFinite(w) ||
      !Number.isFinite(h) ||
      w <= 0 ||
      h <= 0 ||
      !Number.isFinite(b[0][0]) ||
      !Number.isFinite(b[0][1]) ||
      !Number.isFinite(b[1][0]) ||
      !Number.isFinite(b[1][1])
    ) {
      continue;
    }
    const cx = (b[0][0] + b[1][0]) / 2;
    const cy = (b[0][1] + b[1][1]) / 2;
    boundsList.push({ bounds: b, cx, cy });
  }

  if (boundsList.length === 0) return null;

  if (boundsList.length < 5) {
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const item of boundsList) {
      minX = Math.min(minX, item.bounds[0][0]);
      minY = Math.min(minY, item.bounds[0][1]);
      maxX = Math.max(maxX, item.bounds[1][0]);
      maxY = Math.max(maxY, item.bounds[1][1]);
    }
    return [
      [minX, minY],
      [maxX, maxY],
    ];
  }

  const sortedX = boundsList.map((b) => b.cx).sort((a, b) => a - b);
  const sortedY = boundsList.map((b) => b.cy).sort((a, b) => a - b);

  const q1X = sortedX[Math.floor(sortedX.length * 0.15)] ?? sortedX[0] ?? 0;
  const q3X =
    sortedX[Math.floor(sortedX.length * 0.85)] ??
    sortedX[sortedX.length - 1] ??
    0;
  const iqrX = Math.max(10, q3X - q1X);

  const q1Y = sortedY[Math.floor(sortedY.length * 0.15)] ?? sortedY[0] ?? 0;
  const q3Y =
    sortedY[Math.floor(sortedY.length * 0.85)] ??
    sortedY[sortedY.length - 1] ??
    0;
  const iqrY = Math.max(10, q3Y - q1Y);

  const thresholdXMin = q1X - 2.5 * iqrX;
  const thresholdXMax = q3X + 2.5 * iqrX;
  const thresholdYMin = q1Y - 2.5 * iqrY;
  const thresholdYMax = q3Y + 2.5 * iqrY;

  const inliers = boundsList.filter(
    (item) =>
      item.cx >= thresholdXMin &&
      item.cx <= thresholdXMax &&
      item.cy >= thresholdYMin &&
      item.cy <= thresholdYMax,
  );

  const finalItems = inliers.length > 0 ? inliers : boundsList;

  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const item of finalItems) {
    minX = Math.min(minX, item.bounds[0][0]);
    minY = Math.min(minY, item.bounds[0][1]);
    maxX = Math.max(maxX, item.bounds[1][0]);
    maxY = Math.max(maxY, item.bounds[1][1]);
  }

  return [
    [minX, minY],
    [maxX, maxY],
  ];
}
