import { describe, expect, it } from 'vitest';
import {
  createColorInterpolator,
  getSeriesColor,
  interpolateMonotonic,
  SCALE_MONOTONIC,
} from './palette';

describe('palette', () => {
  // Test: Color indexing cycle.
  // Situation: Accessing series color beyond palette length.
  // Expectation: Wraps around cyclically modulo palette size.
  it('returns cyclic series colors from getSeriesColor', () => {
    const color0 = getSeriesColor(0);
    const color6 = getSeriesColor(6);
    expect(color0).toBe(color6);
  });

  describe('createColorInterpolator', () => {
    // Test: 9-stop interpolation.
    // Situation: Evaluating interpolator at 0, 0.5, and 1.
    // Expectation: Matches start, midpoint, and end color stops.
    it('interpolates 9-stop monotonic scale matching D3 Blues', () => {
      const interpolator = createColorInterpolator(SCALE_MONOTONIC[0]);
      expect(interpolator(0)).toBe(SCALE_MONOTONIC[0][0]);
      expect(interpolator(0.5)).toBe(SCALE_MONOTONIC[0][4]);
      expect(interpolator(1)).toBe(SCALE_MONOTONIC[0][8]);
    });

    // Test: Multi-stop blend.
    // Situation: Creating interpolator from custom 5-stop array.
    // Expectation: Returns linearly interpolated RGB colors at quarter points.
    it('interpolates multi-stop color blends (e.g. Viridis)', () => {
      const viridisStops = [
        '#440154',
        '#3b528b',
        '#21918c',
        '#5ec962',
        '#fde725',
      ];
      const viridis = createColorInterpolator(viridisStops);

      expect(viridis(0)).toBe('rgb(68, 1, 84)');
      expect(viridis(0.25)).toBe('rgb(59, 82, 139)');
      expect(viridis(0.5)).toBe('rgb(33, 145, 140)');
      expect(viridis(0.75)).toBe('rgb(94, 201, 98)');
      expect(viridis(1.0)).toBe('rgb(253, 231, 37)');
    });

    // Test: Empty stops fallback.
    // Situation: Empty array passed to factory.
    // Expectation: Returns function returning empty string without throwing.
    it('handles empty stops array safely', () => {
      const empty = createColorInterpolator([]);
      expect(empty(0)).toBe('');
      expect(empty(0.5)).toBe('');
    });

    // Test: Single stop fallback.
    // Situation: 1-stop color array passed to factory.
    // Expectation: Returns constant function returning that color without NaN errors.
    it('handles single stop without error', () => {
      const single = createColorInterpolator(['#ff0000']);
      expect(single(0)).toBe('#ff0000');
      expect(single(0.5)).toBe('#ff0000');
      expect(single(1)).toBe('#ff0000');
    });

    // Test: Domain clamping.
    // Situation: Input values less than 0 or greater than 1.
    // Expectation: Clamps output to min and max color stops.
    it('clamps values below 0 and above 1', () => {
      const interpolator = createColorInterpolator(SCALE_MONOTONIC[0]);
      expect(interpolator(-1)).toBe(SCALE_MONOTONIC[0][0]);
      expect(interpolator(2)).toBe(SCALE_MONOTONIC[0][8]);
    });
  });

  describe('interpolateMonotonic', () => {
    // Test: Default monotonic interpolator endpoints.
    // Situation: Evaluating predefined interpolateMonotonic function.
    // Expectation: Returns tokens accurately.
    it('evaluates endpoints accurately with theme tokens', () => {
      expect(interpolateMonotonic(0)).toBe(SCALE_MONOTONIC[0][0]);
      expect(interpolateMonotonic(0.5)).toBe(SCALE_MONOTONIC[0][4]);
      expect(interpolateMonotonic(1)).toBe(SCALE_MONOTONIC[0][8]);
    });
  });
});
