import { formatDateRange } from '~/functions/format_date_range';
import type { FacetInfo } from '~/server/types';

/**
 * Formats facet metadata into an inline display string.
 *
 * - Combines source, formatted date range, and unit with commas.
 * - Omits missing or empty fields without trailing or consecutive separators.
 * - Returns an empty string if all formatting fields are absent.
 */
export const formatFacetLabel = (facet: Partial<FacetInfo>): string => {
  const dates = formatDateRange(facet.earliestDate, facet.latestDate);
  const parts = [facet.source, dates, facet.unit].filter(Boolean);
  return parts.join(', ');
};

/**
 * Formats facet metadata into a multi-line HTML block.
 *
 * - Joins non-empty lines (source, date range, measurement method, unit) with `<br>`.
 * - Omits missing or empty fields without consecutive or trailing `<br>` tags.
 * - Returns an empty string if all formatting fields are absent.
 */
export const formatFacetBlock = (facet: Partial<FacetInfo>): string => {
  const lines: string[] = [];
  if (facet.source) {
    lines.push(facet.source);
  }
  const dateRange = formatDateRange(facet.earliestDate, facet.latestDate);
  if (dateRange) {
    lines.push(dateRange);
  }
  if (facet.measurementMethod) {
    lines.push(facet.measurementMethod);
  }
  if (facet.unit) {
    lines.push(facet.unit);
  }
  return lines.join('<br>');
};
