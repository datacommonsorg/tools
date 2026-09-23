import type { FacetInfo } from '~/server/types';

/**
 * Resolves the facet a series should render: the user's selection when it
 * still matches, otherwise the first facet that actually has observations,
 * otherwise the first facet.
 *
 * Shared by the plotted data and the facet selector so the selector can never
 * report a different source than the chart draws.
 */
export const resolveActiveFacet = (
  facets: FacetInfo[] | undefined,
  selectedFacetId: string | undefined,
): FacetInfo | undefined =>
  facets?.find((facet) => facet.facetId === selectedFacetId) ??
  facets?.find((facet) => facet.observations.length > 0) ??
  facets?.[0];
