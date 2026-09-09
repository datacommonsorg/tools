import { describe, expect, it } from 'vitest';
import { extractValidEntityKeys, resolveChartStyle } from './chart_style';

describe('extractValidEntityKeys', () => {
  // Test: Undefined and empty series handling.
  // Situation: Undefined series or empty array passed.
  // Expectation: Returns empty array.
  it('returns empty array when series is undefined or empty', () => {
    expect(extractValidEntityKeys(undefined)).toEqual([]);
    expect(extractValidEntityKeys([])).toEqual([]);
  });

  // Test: Default and empty key filtering.
  // Situation: Series containing 'default' key and empty string keys.
  // Expectation: Excludes 'default' and empty keys, keeping valid DCIDs.
  it('filters out default and empty keys', () => {
    const series = [
      { key: 'default' },
      { key: '' },
      { key: 'geoId/06' },
      { key: 'geoId/48' },
    ];
    expect(extractValidEntityKeys(series)).toEqual(['geoId/06', 'geoId/48']);
  });

  // Test: Key sorting.
  // Situation: Series keys provided in arbitrary order.
  // Expectation: Returns keys sorted alphabetically.
  it('sorts entity keys in ascending alphabetical order', () => {
    const series = [
      { key: 'geoId/48' },
      { key: 'geoId/06' },
      { key: 'country/USA' },
    ];
    expect(extractValidEntityKeys(series)).toEqual([
      'country/USA',
      'geoId/06',
      'geoId/48',
    ]);
  });
});

describe('resolveChartStyle', () => {
  // Test: Fallback style selection by point density.
  // Situation: No explicit style, entities < min threshold or geo unavailable.
  // Expectation: Chooses bar-vertical for <= 15 points, line for > 15 points.
  it('selects correct fallback style based on point density', () => {
    expect(
      resolveChartStyle({
        validEntityCount: 3,
        isGeoAvailable: false,
        totalPoints: 10,
      }),
    ).toBe('bar-vertical');

    expect(
      resolveChartStyle({
        validEntityCount: 3,
        isGeoAvailable: false,
        totalPoints: 20,
      }),
    ).toBe('line');
  });

  // Test: Choropleth default threshold.
  // Situation: Valid entity count >= 6 and geo is available.
  // Expectation: Defaults to choropleth.
  it('defaults to choropleth when entity count >= 6 and geo is available', () => {
    expect(
      resolveChartStyle({
        validEntityCount: 6,
        isGeoAvailable: true,
        totalPoints: 6,
      }),
    ).toBe('choropleth');
  });

  // Test: Choropleth unavailable fallback.
  // Situation: Choropleth candidate or requested style, but isGeoAvailable is false.
  // Expectation: Reverts to fallback style (line or bar-vertical).
  it('reverts choropleth to fallback when geometry is unavailable', () => {
    expect(
      resolveChartStyle({
        chartStyle: 'choropleth',
        validEntityCount: 10,
        isGeoAvailable: false,
        totalPoints: 25,
      }),
    ).toBe('line');

    expect(
      resolveChartStyle({
        chartStyle: 'choropleth',
        validEntityCount: 10,
        isGeoAvailable: false,
        totalPoints: 5,
      }),
    ).toBe('bar-vertical');
  });

  // Test: Explicit user style override preservation.
  // Situation: User selects bar-horizontal override.
  // Expectation: Respects override regardless of geo availability.
  it('respects user style overrides when valid', () => {
    expect(
      resolveChartStyle({
        selectedStyleOverride: 'bar-horizontal',
        validEntityCount: 10,
        isGeoAvailable: true,
        totalPoints: 20,
      }),
    ).toBe('bar-horizontal');
  });
});
