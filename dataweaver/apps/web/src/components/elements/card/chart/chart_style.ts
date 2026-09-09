import type { ChartStyle } from '~/server/types';
import { CHOROPLETH_DEFAULT_MIN_ENTITIES } from './geo_service';

/**
 * Extracts and sorts non-default entity keys from a series collection.
 */
export function extractValidEntityKeys(
  series?: Array<{ key: string }>,
): string[] {
  return (
    series
      ?.map((s) => s.key)
      .filter((k) => k && k !== 'default')
      .sort() ?? []
  );
}

export interface ResolveChartStyleParams {
  chartStyle?: ChartStyle;
  selectedStyleOverride?: ChartStyle;
  validEntityCount: number;
  isGeoAvailable: boolean | null;
  totalPoints: number;
}

/**
 * Resolves the active chart style considering user preferences, entity count,
 * point density, and geographic boundary availability.
 */
export function resolveChartStyle({
  chartStyle,
  selectedStyleOverride,
  validEntityCount,
  isGeoAvailable,
  totalPoints,
}: ResolveChartStyleParams): ChartStyle {
  // Revert to line/bar fallback when boundary geometry is unavailable (100% coverage check)
  // or when comparing fewer entities than the choropleth threshold.
  const fallbackStyle: ChartStyle = totalPoints > 15 ? 'line' : 'bar-vertical';
  const defaultStyle: ChartStyle =
    validEntityCount >= CHOROPLETH_DEFAULT_MIN_ENTITIES &&
    isGeoAvailable === true
      ? 'choropleth'
      : fallbackStyle;
  const candidateStyle = chartStyle ?? selectedStyleOverride ?? defaultStyle;
  return candidateStyle === 'choropleth' && isGeoAvailable === false
    ? fallbackStyle
    : candidateStyle;
}
