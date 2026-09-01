import {
  type GeoProjection,
  geoAlbersUsa,
  geoAzimuthalEqualArea,
  geoConicConformal,
  geoEquirectangular,
} from 'd3-geo';

const PROJECTION_MAPPING: Record<string, string> = {
  'country/USA': 'country/USA',
  europe: 'europe',
  eu: 'europe',
  northern_europe: 'europe',
  western_europe: 'europe',
  easterneurope: 'europe',
  southerneurope: 'europe',
  asia: 'asia',
  oceania: 'oceania',
  australasia: 'oceania',
  northamerica: 'northamerica',
};

export interface MapProjectionResult {
  projection: GeoProjection;
  isMapFitted: boolean;
}

/**
 * Measure 1: Regional Projections & Rotations (aligning with Data Commons website).
 * Selects an optimal projection, meridian rotation, and center for the enclosing geographic region.
 * Europe and Asia use curated fixed-scale projections that bypass dynamic bounding-box scaling
 * so that transcontinental territories (e.g. Siberia/Russia in Europe) and 180° antimeridian wrapping
 * do not compress the map.
 */
export function getMapProjection(
  enclosingPlaceDcid: string | undefined,
  width: number,
  height: number,
  entities?: string[],
): MapProjectionResult {
  const normalizedKey = enclosingPlaceDcid?.toLowerCase() || '';
  const projectionTarget =
    PROJECTION_MAPPING[normalizedKey] ||
    PROJECTION_MAPPING[enclosingPlaceDcid ?? ''] ||
    (entities &&
    entities.length > 0 &&
    entities.every((e) => e.startsWith('geoId/'))
      ? 'country/USA'
      : undefined);

  switch (projectionTarget) {
    case 'europe': {
      // Lambert Azimuthal Equal-Area projection centered on Europe.
      // isMapFitted = true locks the scale to continental Europe and ignores Siberian Russia.
      const proj = geoAzimuthalEqualArea()
        .rotate([-20.0, -52.0])
        .translate([width / 2, height / 2])
        .scale(Math.min(width / 1.5, height / 0.75))
        .precision(0.1);
      return { projection: proj, isMapFitted: true };
    }

    case 'asia': {
      // Central meridian rotated by -85° so the antimeridian seam does not cross East Asia.
      // Math.min constrains by both dimensions so the wide continent fits within narrow card widths.
      const proj = geoEquirectangular()
        .rotate([-85, 0])
        .center([0, 35])
        .translate([width / 2, height / 2])
        .scale(Math.min(width / 2.7, height / 1.6))
        .precision(0.1);
      return { projection: proj, isMapFitted: true };
    }

    case 'northamerica': {
      const proj = geoConicConformal().rotate([100, 0]).precision(0.1);
      return { projection: proj, isMapFitted: false };
    }

    case 'oceania': {
      // Rotated by -100° to render the Pacific basin contiguously without antimeridian cuts.
      const proj = geoEquirectangular().rotate([-100, 0]).precision(0.1);
      return { projection: proj, isMapFitted: false };
    }

    case 'country/USA': {
      // Standard Albers projection with Alaska, Hawaii, and Puerto Rico insets.
      const proj = geoAlbersUsa()
        .translate([width / 2, height / 2])
        .scale(width * 1.25);
      return { projection: proj, isMapFitted: true };
    }

    default: {
      const proj = geoEquirectangular().precision(0.1);
      return { projection: proj, isMapFitted: false };
    }
  }
}
