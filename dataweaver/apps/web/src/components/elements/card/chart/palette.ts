import { COLORS } from '@package/tokens/ts';

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
