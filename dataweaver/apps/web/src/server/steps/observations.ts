import { fetchObservations } from '~/server/clients/dc_api';
import { callMcp } from '~/server/clients/mcp';
import type { FacetInfo, TimeSeries } from '~/server/types';

interface McpMetadataResult {
  content?: Array<{ text: string }>;
  structuredContent?: {
    status?: string;
    variables?: Record<
      string,
      {
        facets?: Array<{
          id: string;
          provenanceId?: string;
        }>;
      }
    >;
    provenances?: Record<
      string,
      {
        properties?: {
          source?: string;
          isPartOf?: string;
          url?: string;
        };
      }
    >;
  };
}

/** Fetch time-series observations and metadata in a batch for multiple variables. */
export const fetchTimeSeriesBatch = async (
  variableDcids: string[],
  entityDcid: string,
  signal?: AbortSignal,
): Promise<TimeSeries[]> => {
  if (variableDcids.length === 0) return [];

  try {
    // Fetch time series data from REST API and structural metadata from MCP concurrently
    const [obsResponse, metadataResult] = await Promise.all([
      fetchObservations(variableDcids, [entityDcid], signal),
      callMcp<McpMetadataResult>(
        'tools/call',
        {
          name: 'get_variable_metadata',
          arguments: {
            variable_dcids: variableDcids,
            entity_dcids: [entityDcid],
          },
        },
        signal,
      ).catch(() => null),
    ]);

    // Parse metadata map (facetId -> { source, url }) across all variables
    const metadataMap: Record<string, { source: string; url: string }> = {};
    if (metadataResult) {
      let rawMeta = metadataResult.structuredContent;
      if (!rawMeta && metadataResult.content?.[0]?.text) {
        try {
          rawMeta = JSON.parse(metadataResult.content[0].text);
        } catch {
          // Ignore JSON parse errors
        }
      }

      if (rawMeta?.provenances && rawMeta?.variables) {
        for (const varMeta of Object.values(rawMeta.variables)) {
          const metaFacets = varMeta?.facets || [];
          for (const mf of metaFacets) {
            if (mf.id && mf.provenanceId) {
              const prov = rawMeta.provenances[mf.provenanceId]?.properties;
              if (prov) {
                const sourceName = prov.isPartOf || prov.source;
                if (sourceName) {
                  metadataMap[mf.id] = {
                    source: sourceName,
                    url: prov.url || '',
                  };
                }
              }
            }
          }
        }
      }
    }

    const facetsMap = obsResponse.facets || {};

    return variableDcids.map((variableDcid) => {
      const varData =
        obsResponse.byVariable?.[variableDcid]?.byEntity?.[entityDcid];
      const orderedFacets = varData?.orderedFacets || [];

      const facets: FacetInfo[] = orderedFacets.map((f) => {
        const data = facetsMap[f.facetId] || {};
        const meta = metadataMap[f.facetId];
        return {
          facetId: f.facetId,
          source: meta?.source || data.importName || '',
          sourceUrl: meta?.url || data.provenanceUrl || '',
          unit: data.unit || '',
          earliestDate: f.earliestDate || '',
          latestDate: f.latestDate || '',
          observationCount: f.observations?.length || 0,
          measurementMethod: data.measurementMethod,
          observations: f.observations || [],
        };
      });

      return { variableDcid, entityDcid, facets };
    });
  } catch {
    return variableDcids.map((variableDcid) => ({
      variableDcid,
      entityDcid,
      facets: [],
    }));
  }
};

/** Fetch time-series observations for a single variable + entity pair. */
export const fetchTimeSeries = async (
  variableDcid: string,
  entityDcid: string,
  signal?: AbortSignal,
): Promise<TimeSeries> => {
  const results = await fetchTimeSeriesBatch(
    [variableDcid],
    entityDcid,
    signal,
  );
  return results[0] ?? { variableDcid, entityDcid, facets: [] };
};
