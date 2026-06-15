import { getServiceConfig } from '~/server/config';

export interface ObservationResponse {
  byVariable: Record<
    string,
    {
      byEntity: Record<
        string,
        {
          orderedFacets: Array<{
            facetId: string;
            earliestDate?: string;
            latestDate?: string;
            observations: Array<{ date: string; value: number }>;
          }>;
        }
      >;
    }
  >;
  facets: Record<
    string,
    {
      importName?: string;
      provenanceUrl?: string;
      measurementMethod?: string;
      unit?: string;
    }
  >;
}

export const fetchObservations = async (
  variableDcids: string[],
  entityDcids: string[],
  signal?: AbortSignal,
): Promise<ObservationResponse> => {
  const apiKey = process.env.DATA_COMMONS_API_KEY;
  if (!apiKey)
    throw new Error('DATA_COMMONS_API_KEY environment variable is not set');

  const config = getServiceConfig();
  const baseUrl = config.api.dataCommons.baseUrl;

  const res = await fetch(`${baseUrl}/v2/observation`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': apiKey,
    },
    body: JSON.stringify({
      variable: { dcids: variableDcids },
      entity: { dcids: entityDcids },
      select: ['variable', 'entity', 'date', 'value', 'facet'],
    }),
    signal,
  });

  if (!res.ok) throw new Error(`DC API Error: ${res.status} ${res.statusText}`);
  return res.json();
};
