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
      try {
        let rawMetadata = metadataResult.structuredContent;
        if (!rawMetadata && metadataResult.content?.[0]?.text) {
          try {
            rawMetadata = JSON.parse(metadataResult.content[0].text);
          } catch {
            // Ignore JSON parse errors
          }
        }

        if (
          rawMetadata?.provenances &&
          rawMetadata?.variables &&
          typeof rawMetadata.variables === 'object'
        ) {
          for (const variableMetadata of Object.values(rawMetadata.variables)) {
            const metadataFacets = variableMetadata?.facets;
            if (Array.isArray(metadataFacets)) {
              for (const metadataFacet of metadataFacets) {
                if (metadataFacet?.id && metadataFacet?.provenanceId) {
                  const provenance =
                    rawMetadata.provenances[metadataFacet.provenanceId]
                      ?.properties;
                  if (provenance) {
                    const sourceName = provenance.isPartOf || provenance.source;
                    if (sourceName) {
                      metadataMap[metadataFacet.id] = {
                        source: sourceName,
                        url: provenance.url || '',
                      };
                    }
                  }
                }
              }
            }
          }
        }
      } catch (err) {
        console.warn('[observations] Failed to parse MCP metadata:', err);
      }
    }

    const facetsMap = obsResponse.facets || {};

    return variableDcids.map((variableDcid) => {
      const variableData =
        obsResponse.byVariable?.[variableDcid]?.byEntity?.[entityDcid];
      const orderedFacets = variableData?.orderedFacets || [];

      const facets: FacetInfo[] = orderedFacets.map((facet) => {
        const facetData = facetsMap[facet.facetId] || {};
        const metadata = metadataMap[facet.facetId];
        return {
          facetId: facet.facetId,
          source: metadata?.source || facetData.importName || '',
          sourceUrl: metadata?.url || facetData.provenanceUrl || '',
          unit: facetData.unit || '',
          earliestDate: facet.earliestDate || '',
          latestDate: facet.latestDate || '',
          observationCount: facet.observations?.length || 0,
          measurementMethod: facetData.measurementMethod,
          observations: facet.observations || [],
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
