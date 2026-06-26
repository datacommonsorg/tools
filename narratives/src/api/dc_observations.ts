/**
 * Typed access to the Custom Data Commons observation endpoints.
 * We use these directly so charts render inside our own Recharts layer —
 * no DC web components, full Figma fidelity.
 */

/**
 * Represents a single observation point in a timeseries.
 */
export interface SeriesPoint {
  date: string;
  value: number;
}

/**
 * Represents the response structure returned by the /api/observations/series endpoint.
 */
export interface SeriesResponse {
  data: Record<string, Record<string, { series: SeriesPoint[] } | undefined>>;
  facets: Record<
    string,
    { importName?: string; provenanceUrl?: string; unit?: string }
  >;
}

/**
 * Represents the response structure returned by the /api/observations/point endpoint.
 */
export interface PointResponse {
  data: Record<
    string,
    Record<string, { date?: string; value?: number } | undefined>
  >;
  facets: Record<
    string,
    { importName?: string; provenanceUrl?: string; unit?: string }
  >;
}

/**
 * Recharts dataset row: { date: "2020", "<dcid1>": 42, "<dcid2>": 7, ... }
 */
export interface ChartRow {
  date: string;
  [key: string]: string | number | undefined;
}

/**
 * Represents the page's host origin, dynamically set to window.location.origin
 * in the browser, or fallback empty string in node/test environments.
 */
const ORIGIN =
  typeof window !== "undefined" ? window.location.origin : "";

function buildSeriesUrl(
  variableDcids: string[],
  entityDcids: string[],
): string {
  const url = new URL("/api/observations/series", ORIGIN);
  for (const variableDcid of variableDcids) {
    url.searchParams.append("variables", variableDcid);
  }
  for (const entityDcid of entityDcids) {
    url.searchParams.append("entities", entityDcid);
  }
  return url.toString();
}

function buildPointUrl(
  variableDcids: string[],
  entityDcids: string[],
  date: string,
): string {
  const url = new URL("/api/observations/point", ORIGIN);
  for (const variableDcid of variableDcids) {
    url.searchParams.append("variables", variableDcid);
  }
  for (const entityDcid of entityDcids) {
    url.searchParams.append("entities", entityDcid);
  }
  if (date) {
    url.searchParams.set("date", date);
  }
  return url.toString();
}

/**
 * Fetches series observations for the given variables and entities.
 */
export async function fetchSeries(
  variableDcids: string[],
  entityDcids: string[],
  signal?: AbortSignal,
): Promise<SeriesResponse> {
  const res = await fetch(buildSeriesUrl(variableDcids, entityDcids), {
    signal,
  });
  if (!res.ok) throw new Error(`series fetch failed: HTTP ${res.status}`);
  return (await res.json()) as SeriesResponse;
}

/**
 * Fetches point observations for the given variables and entities on a specific date.
 */
export async function fetchPoint(
  variableDcids: string[],
  entityDcids: string[],
  date: string,
  signal?: AbortSignal,
): Promise<PointResponse> {
  const res = await fetch(buildPointUrl(variableDcids, entityDcids, date), {
    signal,
  });
  if (!res.ok) throw new Error(`point fetch failed: HTTP ${res.status}`);
  return (await res.json()) as PointResponse;
}

/**
 * Pivots the time-series API response into one row per date, with each variable as a
 * column. Variables that don't have a value on a given date are omitted
 * from that row.
 */
export function pivotSeriesToRows(
  response: SeriesResponse,
  variableDcids: string[],
  place: string,
): ChartRow[] {
  const byDate = new Map<string, ChartRow>();
  for (const variableDcid of variableDcids) {
    const series = response?.data?.[variableDcid]?.[place]?.series ?? [];
    for (const point of series) {
      let row = byDate.get(point.date);
      if (!row) {
        row = { date: point.date };
        byDate.set(point.date, row);
      }
      row[variableDcid] = point.value;
    }
  }
  return Array.from(byDate.values()).sort((a, b) =>
    a.date.localeCompare(b.date),
  );
}

/**
 * Pivots the point API response into rows keyed by place DCID for a single variable.
 */
export function pivotPointToRowsByPlace(
  response: PointResponse,
  variable: string,
): Array<{ place: string; value: number }> {
  const out: Array<{ place: string; value: number }> = [];
  const placesMap = response?.data?.[variable] ?? {};
  for (const [place, point] of Object.entries(placesMap)) {
    if (point && typeof point.value === "number") {
      out.push({ place, value: point.value });
    }
  }
  return out;
}

/**
 * Tries to derive a primary source from the facets section of a response.
 * Falls back to undefined if nothing usable is present.
 */
export function pickSourceFromFacets(
  response: SeriesResponse | PointResponse,
): { name: string; url: string } | undefined {
  const facets = response?.facets;
  if (!facets) {
    return undefined;
  }
  for (const facet of Object.values(facets)) {
    if (facet?.provenanceUrl) {
      return {
        name: facet.importName || facet.provenanceUrl,
        url: facet.provenanceUrl,
      };
    }
  }
  return undefined;
}

/**
 * Gets a shorter display label for a place DCID by stripping the "country/",
 * "geoId/", "dc/" prefix. Falls back to the full DCID if no prefix is found.
 */
export function getPrettyPlaceName(dcid: string): string {
  const index = dcid.indexOf("/");
  return index >= 0 ? dcid.slice(index + 1) : dcid;
}

/**
 * Generates a heuristic readable name for a variable DCID when we don't have its
 * canonical title from the upstream catalog. Splits on both underscores and
 * forward slashes, and title-cases the first segment.
 */
export function getPrettyVariableName(dcid: string): string {
  if (!dcid) {
    return "";
  }
  // dc/abc123 → "dc abc123" → tidied
  const cleaned = dcid.replace(/[_/]/g, " ").trim();
  if (!cleaned) {
    return dcid;
  }
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}
