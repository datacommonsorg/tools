import type { ChartSeries } from './chart';

export interface MergedRow {
  date: string;
  [key: string]: string | number | null;
}

/**
 * Merges multiple series into a unified row array keyed by `date`.
 * Each series' values are stored under `value_<index>`.
 * Missing values for a given date are `null`.
 */
export const mergeSeriesData = (series: ChartSeries[]): MergedRow[] => {
  const dateSet = new Set<string>();
  const seriesMaps: Map<string, number>[] = [];

  for (const s of series) {
    const map = new Map<string, number>();
    for (const d of s.data) {
      dateSet.add(d.date);
      map.set(d.date, d.value);
    }
    seriesMaps.push(map);
  }

  const dates = Array.from(dateSet).sort();
  const rows: MergedRow[] = [];

  for (const date of dates) {
    const row: MergedRow = { date };
    for (let i = 0; i < series.length; i++) {
      const map = seriesMaps[i];
      row[`value_${i}`] = map?.get(date) ?? null;
    }
    rows.push(row);
  }

  return rows;
};

/**
 * Detects whether dual Y-axes are needed by comparing the max absolute values
 * of each series. Returns axis assignment per series index.
 * If the ratio between the largest and smallest max exceeds `threshold` (default 10),
 * the smaller-scale series are assigned to the right axis.
 */
export const detectAxisAssignment = (
  series: ChartSeries[],
  threshold = 10,
): ('left' | 'right')[] => {
  if (series.length <= 1) return series.map(() => 'left');

  const maxValues = series.map((s) => {
    let max = 0;
    for (const d of s.data) {
      const abs = Math.abs(d.value);
      if (abs > max) max = abs;
    }
    return max;
  });

  const globalMax = Math.max(...maxValues);
  if (globalMax === 0) return series.map(() => 'left');

  return maxValues.map((max) =>
    max > 0 && globalMax / max >= threshold ? 'right' : 'left',
  );
};
