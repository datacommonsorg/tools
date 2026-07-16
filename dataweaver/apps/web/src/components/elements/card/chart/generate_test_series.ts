/**
 * Dev-only utility: generates dummy multi-series data so you can visually test
 * how the chart handles multiple variables and/or multiple places.
 *
 * Import and call `generateTestSeries(chartSeries)` in chart.tsx behind the
 * `USE_TEST_DATA` flag. Remove / leave dead when not needed.
 */

import type { ChartDatum, ChartSeries } from './chart';

// --- Label pools (picked sequentially, then wrap) ---

const PLACE_LABELS = [
  'California',
  'Texas',
  'New York',
  'Florida',
  'Illinois',
  'Pennsylvania',
  'Ohio',
  'Georgia',
];

const VARIABLE_LABELS = [
  'Population',
  'GDP per Capita',
  'Employment Rate',
  'Median Income',
  'CO₂ Emissions',
  'Life Expectancy',
];

export type TestSeriesMode = 'places' | 'variables';

export interface GenerateTestSeriesOptions {
  /** How many extra series to generate (default: 3). */
  count?: number;
  /** Whether dummy labels represent different places or different variables. */
  mode?: TestSeriesMode;
  /**
   * Multiplier range for random values relative to existing data.
   * Values are generated as `existingValue * randomInRange(min, max)`.
   * Default: [0.4, 1.6].
   */
  scaleRange?: [number, number];
  /** Optional seed for reproducible randomness (simple LCG). */
  seed?: number;
}

// --- Simple seeded PRNG (LCG) ---

const createRng = (seed: number) => {
  let s = seed;
  return () => {
    s = (s * 1664525 + 1013904223) & 0xffffffff;
    return (s >>> 0) / 0xffffffff;
  };
};

// --- Core ---

/**
 * Takes existing chart series and returns a new array that includes the
 * originals plus N additional dummy series with semi-random data aligned to the
 * same date axis.
 */
export const generateTestSeries = (
  existing: ChartSeries[] | undefined,
  options: GenerateTestSeriesOptions = {},
): ChartSeries[] | undefined => {
  if (!existing || existing.length === 0) return existing;

  const {
    count = 3,
    mode = 'places',
    scaleRange = [0.4, 1.6],
    seed = 42,
  } = options;

  const rng = createRng(seed);
  const [scaleMin, scaleMax] = scaleRange;

  // Collect the union of all dates from existing series (preserves order).
  const dateSet = new Set<string>();
  for (const series of existing) {
    for (const d of series.data) {
      dateSet.add(d.date);
    }
  }
  const dates = [...dateSet];

  // Build a reference value for each date (average across existing series).
  const refValues = new Map<string, number>();
  for (const date of dates) {
    let sum = 0;
    let n = 0;
    for (const series of existing) {
      const point = series.data.find((d) => d.date === date);
      if (point) {
        sum += point.value;
        n++;
      }
    }
    refValues.set(date, n > 0 ? sum / n : 100);
  }

  const labels = mode === 'places' ? PLACE_LABELS : VARIABLE_LABELS;

  // Filter out labels that are already used in existing series.
  const existingLabels = new Set(existing.map((s) => s.label));
  const availableLabels = labels.filter((l) => !existingLabels.has(l));

  const generated: ChartSeries[] = [];

  for (let i = 0; i < count; i++) {
    const label =
      availableLabels[i % availableLabels.length] ?? `${mode} ${i + 1}`;
    const key = `test-${mode}-${i}`;

    // Per-series bias so each series has a distinct general level.
    const seriesBias = scaleMin + rng() * (scaleMax - scaleMin);

    const data: ChartDatum[] = dates.map((date) => {
      const ref = refValues.get(date) ?? 100;
      // Apply series bias + per-point jitter (±15%).
      const jitter = 0.85 + rng() * 0.3;
      const value = Math.round(ref * seriesBias * jitter);
      return { date, value };
    });

    generated.push({ key, label, data });
  }

  return [...existing, ...generated];
};
