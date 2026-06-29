import { fetchObservations } from '~/server/clients/dc_api';
import type { FacetInfo, TimeSeries } from '~/server/types';

/** Fetch time-series observations for a single variable + entity pair. */
export const fetchTimeSeries = async (
  variableDcid: string,
  entityDcid: string,
  signal?: AbortSignal,
): Promise<TimeSeries> => {
  try {
    const obsResponse = await fetchObservations(
      [variableDcid],
      [entityDcid],
      signal,
    );

    const varData =
      obsResponse.byVariable?.[variableDcid]?.byEntity?.[entityDcid];
    const facetsMap = obsResponse.facets || {};
    const orderedFacets = varData?.orderedFacets || [];

    const facets: FacetInfo[] = orderedFacets.map((f) => {
      const data = facetsMap[f.facetId] || {};
      return {
        facetId: f.facetId,
        source: data.importName || 'Data Commons',
        sourceUrl: data.provenanceUrl || '',
        unit: data.unit || 'Dimensionless',
        earliestDate: f.earliestDate || '',
        latestDate: f.latestDate || '',
        observationCount: f.observations?.length || 0,
        measurementMethod: data.measurementMethod,
        observations: f.observations || [],
      };
    });

    return { variableDcid, entityDcid, facets };
  } catch {
    return { variableDcid, entityDcid, facets: [] };
  }
};
