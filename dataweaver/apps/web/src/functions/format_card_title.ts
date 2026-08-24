import type { QueryResult } from '~/server/types';

/**
 * Resolves the primary place or region display name from a QueryResult.
 */
export const resolvePlaceName = (result: QueryResult): string => {
  if (result.placeName) return result.placeName;
  if (result.variables[0]?.placeName) return result.variables[0].placeName;
  if (result.isChildQuery && result.title) {
    const cleaned = result.title.replace(/^Metrics (across|for) /i, '').trim();
    if (cleaned) return cleaned;
  }
  if (result.entities[0]?.name) return result.entities[0].name;
  return 'Region';
};

/**
 * Formats the title for a Table card.
 */
export const formatTableCardTitle = (
  placeName: string,
  isChildQuery?: boolean,
): string => {
  return isChildQuery
    ? `Metrics across ${placeName}`
    : `Metrics for ${placeName}`;
};

/**
 * Formats the title for a Chart card.
 */
export const formatChartCardTitle = (
  varName: string | undefined,
  placeName: string,
  isChildQuery?: boolean,
): string => {
  if (!varName) return formatTableCardTitle(placeName, isChildQuery);
  return isChildQuery
    ? `${varName} across ${placeName}`
    : `${varName} in ${placeName}`;
};

/**
 * Formats the title for a Notes card.
 */
export const formatNotesCardTitle = (placeName: string): string => {
  return `Relevant insights on ${placeName}`;
};
