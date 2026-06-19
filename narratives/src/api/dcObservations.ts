// Typed access to the Custom Data Commons observation endpoints.
// We use these directly so charts render inside our own Recharts layer —
// no DC web components, full Figma fidelity.

export type SeriesPoint = { date: string; value: number };

export type SeriesResponse = {
  data: Record<string, Record<string, { series: SeriesPoint[] } | undefined>>;
  facets: Record<
    string,
    { importName?: string; provenanceUrl?: string; unit?: string }
  >;
};

export type PointResponse = {
  data: Record<
    string,
    Record<string, { date?: string; value?: number } | undefined>
  >;
  facets: Record<
    string,
    { importName?: string; provenanceUrl?: string; unit?: string }
  >;
};

// Recharts dataset row: { date: "2020", "<dcid1>": 42, "<dcid2>": 7, ... }
export type ChartRow = Record<string, string | number | undefined> & {
  date: string;
};

const ORIGIN =
  typeof window !== "undefined" ? window.location.origin : "";

function buildSeriesUrl(
  variableDcids: string[],
  entityDcids: string[],
): string {
  const u = new URL("/api/observations/series", ORIGIN);
  for (const v of variableDcids) {
    u.searchParams.append("variables", v);
  }
  for (const e of entityDcids) {
    u.searchParams.append("entities", e);
  }
  return u.toString();
}

function buildPointUrl(
  variableDcids: string[],
  entityDcids: string[],
  date: string,
): string {
  const u = new URL("/api/observations/point", ORIGIN);
  for (const v of variableDcids) {
    u.searchParams.append("variables", v);
  }
  for (const e of entityDcids) {
    u.searchParams.append("entities", e);
  }
  if (date) {
    u.searchParams.set("date", date);
  }
  return u.toString();
}

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

// Time-series shape (line/bar over time, single place per variable):
// pivots the API response into one row per date, with each variable as a
// column. Variables that don't have a value on a given date are omitted
// from that row.
export function pivotSeriesToRows(
  response: SeriesResponse,
  variableDcids: string[],
  place: string,
): ChartRow[] {
  const byDate = new Map<string, ChartRow>();
  for (const v of variableDcids) {
    const series = response?.data?.[v]?.[place]?.series ?? [];
    for (const point of series) {
      let row = byDate.get(point.date);
      if (!row) {
        row = { date: point.date };
        byDate.set(point.date, row);
      }
      row[v] = point.value;
    }
  }
  return Array.from(byDate.values()).sort((a, b) =>
    a.date.localeCompare(b.date),
  );
}

// Bar-by-place shape (single variable, single date, one row per place):
// returns rows keyed by place DCID for a single variable.
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

// Try to derive a primary source from the facets section of a response.
// Falls back to undefined if nothing usable is present.
export function pickSourceFromFacets(
  response: SeriesResponse | PointResponse,
): { name: string; url: string } | undefined {
  const facets = response?.facets;
  if (!facets) {
    return undefined;
  }
  for (const f of Object.values(facets)) {
    if (f?.provenanceUrl) {
      return {
        name: f.importName || f.provenanceUrl,
        url: f.provenanceUrl,
      };
    }
  }
  return undefined;
}

// Strip the "country/", "geoId/", "dc/" prefix to get a shorter display
// label. Falls back to the full DCID if no prefix.
export function prettyPlaceName(dcid: string): string {
  const i = dcid.indexOf("/");
  return i >= 0 ? dcid.slice(i + 1) : dcid;
}

// Heuristic readable name for a variable DCID when we don't have its
// canonical title from the upstream catalog. Splits on underscores and
// title-cases the first segment.
export function prettyVariableName(dcid: string): string {
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
