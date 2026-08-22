/**
 * Formats start and end dates into a display string.
 *
 * - Returns a single date if start and end dates are identical or only one exists.
 * - Returns a formatted range (`start – end`) if both are present and distinct.
 * - Returns an empty string if neither date is present.
 */
export const formatDateRange = (
  earliestDate?: string,
  latestDate?: string,
): string => {
  if (earliestDate && latestDate) {
    return earliestDate === latestDate
      ? earliestDate
      : `${earliestDate} – ${latestDate}`;
  }
  return earliestDate || latestDate || '';
};
