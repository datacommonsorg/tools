/**
 * @fileoverview Fetches Data Commons observations via the instance's own /api proxy.
 *
 * Typed access to the Custom Data Commons observation endpoints. We use these
 * directly so charts render inside our own Recharts layer — no DC web
 * components, full Figma fidelity.
 */

// TODO: Add unit tests for all exported functions in this file.

/** One dated observation, matching an /api/observations/series entry. */
export interface SeriesPoint { date: string; value: number }

/**
 * Response shape of /api/observations/series: values keyed by variable DCID,
 * then entity DCID, plus the facet (source) metadata for attribution.
 */
export interface SeriesResponse {
  data: Record<string, Record<string, { series: SeriesPoint[] } | undefined>>;
  facets: Record<
    string,
    { importName?: string; provenanceUrl?: string; unit?: string }
  >;
}

/**
 * Response shape of /api/observations/point: a single dated value keyed by
 * variable DCID then entity DCID, plus facet (source) metadata.
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

/** Recharts dataset row: { date: "2020", "<dcid1>": 42, "<dcid2>": 7, ... } */
export type ChartRow = Record<string, string | number | undefined> & {
  date: string;
};

/**
 * Base origin for API URLs — the current page's origin in the browser
 * (the instance proxies /api itself), empty during SSR/tests.
 */
const ORIGIN =
  typeof window !== "undefined" ? window.location.origin : "";

/** Builds the /api/observations/series URL for the given variables and entities. */
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

/** Builds the /api/observations/point URL for the given variables, entities, and date. */
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
  if (date) url.searchParams.set("date", date);
  return url.toString();
}

/** Fetches observation time series for the given variables and entities. */
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

/** Fetches single-date observation points for the given variables and entities. */
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
 * Pivots a series response into the time-series chart shape (line/bar over
 * time, single place per variable): one row per date, with each variable as
 * a column. Variables that don't have a value on a given date are omitted
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
 * Pivots a point response into the bar-by-place chart shape (single variable,
 * single date, one row per place): rows keyed by place DCID.
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
 * Derives a primary source from the facets section of a response.
 * Falls back to undefined if nothing usable is present.
 */
export function pickSourceFromFacets(
  response: SeriesResponse | PointResponse,
): { name: string; url: string } | undefined {
  const facets = response?.facets;
  if (!facets) return undefined;
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
 * Gets a shorter display label for a place DCID.
 *
 * Strips the "country/", "geoId/", "dc/" prefix to get a shorter display
 * label. Falls back to the full DCID if no prefix.
 */
export function getPrettyPlaceName(dcid: string): string {
  const slashIndex = dcid.indexOf("/");
  return slashIndex >= 0 ? dcid.slice(slashIndex + 1) : dcid;
}

/**
 * Gets a heuristic readable name for a variable DCID when its canonical
 * title from the upstream catalog is unavailable. Splits on underscores and
 * forward slashes, then title-cases the first segment.
 */
export function getPrettyVariableName(dcid: string): string {
  if (!dcid) return "";
  // dc/abc123 → "dc abc123" → tidied
  const cleaned = dcid.replace(/[_/]/g, " ").trim();
  if (!cleaned) return dcid;
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}
