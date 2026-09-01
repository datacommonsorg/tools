import { COLORS } from '@package/tokens/ts';
import { scaleLinear } from 'd3-scale';

const SERIES_COLORS = [
  `rgb(${COLORS['card-chart-series-0']})`,
  `rgb(${COLORS['card-chart-series-1']})`,
  `rgb(${COLORS['card-chart-series-2']})`,
  `rgb(${COLORS['card-chart-series-3']})`,
  `rgb(${COLORS['card-chart-series-4']})`,
  `rgb(${COLORS['card-chart-series-5']})`,
] as const;

export const PALETTE_SIZE = SERIES_COLORS.length;

export const getSeriesColor = (index: number): string =>
  SERIES_COLORS[index % PALETTE_SIZE] as string;

export const SCALE_MONOTONIC = [
  [
    `rgb(${COLORS['card-chart-scale-monotonic-0-0']})`,
    `rgb(${COLORS['card-chart-scale-monotonic-0-1']})`,
    `rgb(${COLORS['card-chart-scale-monotonic-0-2']})`,
    `rgb(${COLORS['card-chart-scale-monotonic-0-3']})`,
    `rgb(${COLORS['card-chart-scale-monotonic-0-4']})`,
    `rgb(${COLORS['card-chart-scale-monotonic-0-5']})`,
    `rgb(${COLORS['card-chart-scale-monotonic-0-6']})`,
    `rgb(${COLORS['card-chart-scale-monotonic-0-7']})`,
    `rgb(${COLORS['card-chart-scale-monotonic-0-8']})`,
  ],
] as const;

/**
 * Creates a D3 scaleLinear-based color interpolator function given an array of color stops.
 * Supports 2-stop monotonic scales and N-stop multi-color blends (e.g. Viridis).
 */
export const createColorInterpolator = (
  stops: readonly string[] = SCALE_MONOTONIC[0],
) => {
  if (stops.length === 0) {
    return () => '';
  }
  if (stops.length === 1) {
    const single = stops[0] as string;
    return () => single;
  }
  const domain = stops.map((_, i) => i / (stops.length - 1));
  return scaleLinear<string>()
    .domain(domain)
    .range(stops as string[])
    .clamp(true);
};

export const interpolateMonotonic = createColorInterpolator(SCALE_MONOTONIC[0]);
