import { fetchObservations } from '~/server/clients/dc_api';
import type { FacetInfo } from '~/server/types';

export interface VariableMetadata {
  variableDcid: string;
  entityDcid: string;
  facets: FacetInfo[];
}

/** Fetch observation metadata for a single variable + entity pair. */
export const fetchVariableMetadata = async (
  variableDcid: string,
  entityDcid: string,
  signal?: AbortSignal,
): Promise<VariableMetadata> => {
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
      const meta = facetsMap[f.facetId] || {};
      return {
        facetId: f.facetId,
        source: meta.importName || 'Data Commons',
        sourceUrl: meta.provenanceUrl || '',
        unit: meta.unit || 'Dimensionless',
        earliestDate: f.earliestDate || '',
        latestDate: f.latestDate || '',
        observationCount: f.observations?.length || 0,
        measurementMethod: meta.measurementMethod,
        observations: f.observations || [],
      };
    });

    return { variableDcid, entityDcid, facets };
  } catch {
    return { variableDcid, entityDcid, facets: [] };
  }
};
