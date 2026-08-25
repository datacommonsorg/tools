import { normalizePlaceType } from '~/functions/normalize_place_type';
import { getServiceConfig } from '~/server/config';

export interface ChildPlace {
  dcid: string;
  name: string;
  types?: string[];
}

export interface NodeResponse {
  data?: Record<
    string,
    {
      arcs?: Record<
        string,
        {
          nodes?: Array<{
            dcid?: string;
            name?: string;
            value?: string;
            types?: string[];
          }>;
        }
      >;
    }
  >;
}

export interface ObservationResponse {
  byVariable: Record<
    string,
    {
      byEntity: Record<
        string,
        {
          orderedFacets?: Array<{
            facetId: string;
            earliestDate?: string;
            latestDate?: string;
            observations?: Array<{
              date: string;
              value: number;
            }>;
          }>;
        }
      >;
    }
  >;
  facets?: Record<
    string,
    {
      importName?: string;
      provenanceUrl?: string;
      measurementMethod?: string;
      unit?: string;
    }
  >;
}

/** Fetch direct child places contained within a parent place using Data Commons V2 /v2/node. */
export const fetchChildPlaces = async (
  parentDcid: string,
  childPlaceType?: string,
  signal?: AbortSignal,
): Promise<ChildPlace[]> => {
  const apiKey = process.env.DATA_COMMONS_API_KEY;
  if (!apiKey)
    throw new Error('DATA_COMMONS_API_KEY environment variable is not set');

  const config = getServiceConfig();
  const baseUrl = config.api.dataCommons.baseUrl;

  const normalizedType = childPlaceType
    ? normalizePlaceType(childPlaceType)
    : undefined;

  const property = normalizedType
    ? `<-containedInPlace+{typeOf:${normalizedType}}`
    : '<-containedInPlace+';

  const res = await fetch(`${baseUrl}/v2/node`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': apiKey,
    },
    body: JSON.stringify({
      nodes: [parentDcid],
      property,
    }),
    signal,
  });

  if (!res.ok) throw new Error(`DC API Error: ${res.status} ${res.statusText}`);
  const json: NodeResponse = await res.json();

  const nodeArcs = json.data?.[parentDcid]?.arcs;
  if (!nodeArcs) return [];

  const arcKey =
    Object.keys(nodeArcs).find((k) => k.includes('containedInPlace')) ||
    Object.keys(nodeArcs)[0];
  const rawNodes = arcKey ? nodeArcs[arcKey]?.nodes : [];
  if (!Array.isArray(rawNodes)) return [];

  return rawNodes
    .filter(
      (n): n is { dcid: string; name?: string; types?: string[] } => !!n.dcid,
    )
    .map((n) => ({
      dcid: n.dcid,
      name: n.name || n.dcid,
      types: n.types,
    }));
};

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
