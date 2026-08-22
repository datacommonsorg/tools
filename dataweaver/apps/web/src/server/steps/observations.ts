import { fetchChildPlaces, fetchObservations } from '~/server/clients/dc_api';
import { callMcp } from '~/server/clients/mcp';
import type { Entity, FacetInfo, TimeSeries } from '~/server/types';

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

/** Fetch time-series observations and metadata in a batch for multiple variables and entities. */
export const fetchTimeSeriesBatch = async (
  variableDcids: string[],
  entityDcids: string | string[],
  signal?: AbortSignal,
): Promise<TimeSeries[]> => {
  const targetEntityDcids = Array.isArray(entityDcids)
    ? entityDcids
    : [entityDcids];
  if (variableDcids.length === 0 || targetEntityDcids.length === 0) return [];

  try {
    // Fetch time series data from REST API and structural metadata from MCP concurrently
    const [obsResponse, metadataResult] = await Promise.all([
      fetchObservations(variableDcids, targetEntityDcids, signal),
      callMcp<McpMetadataResult>(
        'tools/call',
        {
          name: 'get_variable_metadata',
          arguments: {
            variable_dcids: variableDcids,
            entity_dcids: targetEntityDcids,
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
    const results: TimeSeries[] = [];

    for (const entityDcid of targetEntityDcids) {
      for (const variableDcid of variableDcids) {
        const variableData =
          obsResponse.byVariable?.[variableDcid]?.byEntity?.[entityDcid];
        const orderedFacets = variableData?.orderedFacets || [];

        const facets: FacetInfo[] = orderedFacets.map((facet) => {
          const facetData = facetsMap[facet.facetId] || {};
          const metadata = metadataMap[facet.facetId];

          // Data Commons API does not guarantee chronological ordering of the
          // observations array within a facet. Sort ascending by date so downstream
          // consumers (charts, comparisons, latest value lookups) have a guaranteed order.
          const observations = (facet.observations || [])
            .slice()
            .sort((a, b) => a.date.localeCompare(b.date));

          return {
            facetId: facet.facetId,
            source: metadata?.source || facetData.importName || '',
            sourceUrl: metadata?.url || facetData.provenanceUrl || '',
            unit: facetData.unit || '',
            earliestDate: facet.earliestDate || '',
            latestDate: facet.latestDate || '',
            observationCount: observations.length,
            measurementMethod: facetData.measurementMethod,
            observations,
          };
        });

        results.push({ variableDcid, entityDcid, facets });
      }
    }

    return results;
  } catch (err) {
    console.warn('[observations] Failed to fetch time-series batch:', err);
    return targetEntityDcids.flatMap((entityDcid) =>
      variableDcids.map((variableDcid) => ({
        variableDcid,
        entityDcid,
        facets: [],
      })),
    );
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

/** Fetch child places and time-series observations for child places of a parent place. */
export const fetchChildTimeSeries = async (
  variableDcids: string[],
  parentPlaceDcid: string,
  childPlaceType: string,
  signal?: AbortSignal,
): Promise<{ entities: Entity[]; timeSeries: TimeSeries[] }> => {
  try {
    const childPlaces = await fetchChildPlaces(
      parentPlaceDcid,
      childPlaceType,
      signal,
    );

    if (childPlaces.length === 0) {
      return { entities: [], timeSeries: [] };
    }

    const childEntityDcids = childPlaces.map((p) => p.dcid);
    const childNameMap = new Map(childPlaces.map((p) => [p.dcid, p.name]));

    const timeSeriesList = await fetchTimeSeriesBatch(
      variableDcids,
      childEntityDcids,
      signal,
    );

    // Attach entityName to each TimeSeries
    const timeSeriesWithNames = timeSeriesList.map((ts) => ({
      ...ts,
      entityName: childNameMap.get(ts.entityDcid) || ts.entityDcid,
    }));

    const entities: Entity[] = childPlaces.map((p) => ({
      dcid: p.dcid,
      name: p.name,
    }));

    return {
      entities,
      timeSeries: timeSeriesWithNames,
    };
  } catch (err) {
    console.warn('[observations] Failed to fetch child time-series:', err);
    return { entities: [], timeSeries: [] };
  }
};
