const compactFormatter = new Intl.NumberFormat(undefined, {
  notation: 'compact',
});

const standardFormatter = new Intl.NumberFormat(undefined, {
  notation: 'standard',
  maximumFractionDigits: 2,
});

const usdCompactFormatter = new Intl.NumberFormat(undefined, {
  style: 'currency',
  currency: 'USD',
  notation: 'compact',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const usdStandardFormatter = new Intl.NumberFormat(undefined, {
  style: 'currency',
  currency: 'USD',
  notation: 'standard',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

// TODO: Ideally this formatter will handle all possible units, but currently
// it's a placeholder that only handles percent, USD, and InternationalDollar.
export const formatChartValue = (
  value: number,
  unit?: string,
  notation: 'compact' | 'standard' = 'compact',
): string => {
  const unitLower = unit?.toLowerCase() ?? '';
  const isPercent = unitLower.includes('percent');
  const isUSD = unitLower.includes('usd');
  const isInternational = unitLower.includes('internationaldollar');

  if (isUSD) {
    return notation === 'compact'
      ? usdCompactFormatter.format(value)
      : usdStandardFormatter.format(value);
  }

  if (isInternational) {
    return notation === 'compact'
      ? usdCompactFormatter.format(value)
      : usdStandardFormatter.format(value);
  }

  const formatted =
    notation === 'compact'
      ? compactFormatter.format(value)
      : standardFormatter.format(value);

  return isPercent ? `${formatted}%` : formatted;
};
