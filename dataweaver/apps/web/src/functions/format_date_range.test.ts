import { describe, expect, it } from 'vitest';
import { formatDateRange } from '~/functions/format_date_range';

describe('formatDateRange', () => {
  it('formats distinct start and end dates with a spaced en-dash', () => {
    expect(formatDateRange('2010', '2020')).toBe('2010 – 2020');
    expect(formatDateRange('2020-01-01', '2020-12-31')).toBe(
      '2020-01-01 – 2020-12-31',
    );
  });

  it('returns a single date when earliest and latest dates are identical', () => {
    expect(formatDateRange('2020', '2020')).toBe('2020');
    expect(formatDateRange('2022-05', '2022-05')).toBe('2022-05');
  });

  it('returns only earliestDate when latestDate is missing or empty', () => {
    expect(formatDateRange('2010', undefined)).toBe('2010');
    expect(formatDateRange('2010', '')).toBe('2010');
  });

  it('returns only latestDate when earliestDate is missing or empty', () => {
    expect(formatDateRange(undefined, '2020')).toBe('2020');
    expect(formatDateRange('', '2020')).toBe('2020');
  });

  it('returns an empty string when neither date is provided', () => {
    expect(formatDateRange()).toBe('');
    expect(formatDateRange('', '')).toBe('');
    expect(formatDateRange(undefined, undefined)).toBe('');
  });
});
