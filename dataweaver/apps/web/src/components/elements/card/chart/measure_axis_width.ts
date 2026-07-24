import { formatChartValue } from '~/functions/format_chart_value';

import type { MergedRow } from './merge_series_data';

const AXIS_FONT = '10px sans-serif';
const AXIS_PADDING = 12;
const MAX_AXIS_WIDTH = 150;
const DEFAULT_WIDTH = 40;

let cachedCanvas: HTMLCanvasElement | null = null;

function getContext(): CanvasRenderingContext2D | null {
  if (typeof document === 'undefined') return null;
  if (!cachedCanvas) cachedCanvas = document.createElement('canvas');
  return cachedCanvas.getContext('2d');
}

/**
 * Measures the pixel width needed to display the widest label in the list.
 * Returns a fixed value derived solely from the label content — never from
 * the chart/container width — so the result is stable during resizes.
 */
export function measureAxisWidth(labels: string[]): number {
  if (labels.length === 0) return DEFAULT_WIDTH;

  const ctx = getContext();
  if (!ctx) {
    const charWidth = labels.reduce(
      (max, label) => Math.max(max, label.length * 6),
      0,
    );
    return Math.min(charWidth + AXIS_PADDING, MAX_AXIS_WIDTH);
  }

  ctx.font = AXIS_FONT;
  let maxWidth = 0;
  for (const label of labels) {
    const textWidth = ctx.measureText(label).width;
    if (textWidth > maxWidth) maxWidth = textWidth;
  }
  return Math.min(maxWidth + AXIS_PADDING, MAX_AXIS_WIDTH);
}

/** Round to the nearest "nice" number (same style Recharts picks for ticks). */
function niceNum(value: number): number {
  if (value === 0) return 0;
  const abs = Math.abs(value);
  const exp = 10 ** Math.floor(Math.log10(abs));
  return Math.sign(value) * Math.ceil(abs / exp) * exp;
}

/**
 * Generates representative axis label strings from merged chart data
 * so `measureAxisWidth` can size the Y axis without rendering.
 */
export function numericAxisLabels(
  data: MergedRow[],
  seriesCount: number,
  unit: string | undefined,
): string[] {
  let min = Infinity;
  let max = -Infinity;
  for (const row of data) {
    for (let index = 0; index < seriesCount; index++) {
      const value = row[`value_${index}`];
      if (typeof value === 'number') {
        if (value < min) min = value;
        if (value > max) max = value;
      }
    }
  }
  if (!Number.isFinite(min)) return [];
  const candidates = [0, niceNum(min), niceNum(max)];
  return candidates.map((candidate) => formatChartValue(candidate, unit));
}
