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
