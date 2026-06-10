import { useEffect, useState } from "react";

// ---------------------------------------------------------------------------
// Metrics composition — config-driven (M-5..M-12 in architecture/ui-tracker.csv)
// ---------------------------------------------------------------------------

export type MetricsTileType =
  | "line"
  | "bar"
  | "map"
  | "ranking"
  | "highlight"
  | "scatter"
  | "pie"
  | "gauge"
  | "slider";

// A tile maps 1:1 onto a <datacommons-${type}> web component. The MetricsPage
// <Tile> wrapper shows `title` as its chrome header; everything else passes
// through as attributes to the DC component. See
// website/packages/web-components/docs/components/*.md for the per-type
// required/optional attribute set.
//
// Highlight cards are just `type: "highlight"` tiles — they render with the
// DC component's native light-blue chip styling (no custom gradient wrapper).
export interface MetricsTile {
  type: MetricsTileType;
  title: string;
  header?: string;
  variable?: string;
  variables?: string;
  place?: string;
  places?: string;
  parentPlace?: string;
  childPlaceType?: string;
  date?: string;
  rankingCount?: number;
  showHighestLowest?: boolean;
  showLowest?: boolean;
  showPlaceLabels?: boolean;
  sort?:
    | "ascending"
    | "descending"
    | "ascendingPopulation"
    | "descendingPopulation";
  colors?: string;
  unit?: string;
  min?: number;
  max?: number;
  startDate?: string;
  endDate?: string;
}

export interface MetricsTab {
  id: string;
  label: string;
  tiles: MetricsTile[];
}

export interface MetricsConfig {
  tabs: MetricsTab[];
}

// ---------------------------------------------------------------------------
// Branding — per-instance config fetched from the bucket at page mount
// ---------------------------------------------------------------------------

export interface Branding {
  schema_version?: string;
  instance_name?: string;
  logo_url?: string;
  primary_color?: string;
  accent_color?: string;
  font_family?: string;
  suggestions?: string[];
  navigation?: Array<{ label: string; href: string }>;
  footer_text?: string;
  // When absent, MetricsPage falls back to DEFAULT_METRICS_TABS — see
  // src/components/MetricsPage.tsx.
  metrics?: MetricsConfig;
}

// Bundled fallback used if the agent's /agent/brand endpoint returns an
// empty URL, or the fetch of branding.json fails. Keep in sync with
// brands/default/branding.json (the canonical copy lives in the deployment
// repo so per-instance uploads have a reference schema to copy from).
export const DEFAULT_BRAND: Branding = {
  schema_version: "1",
  instance_name: "Custom Data Commons",
  logo_url: "",
  primary_color: "#1A73E8",
  accent_color: "#34A853",
  font_family: "Google Sans",
  suggestions: [
    "How has average annual wage changed over time in the United States?",
    "Compare GDP growth across G7 countries",
    "What is the gender wage gap in OECD countries?",
  ],
  navigation: [{ label: "Data Agent", href: "/" }],
  footer_text: "Powered by Data Commons, an initiative from Google.",
};

interface BrandConfigResponse {
  brand_config_url?: string;
}

// Apply branding values as CSS custom properties so the existing index.css
// @theme block can pick them up at render time.
function applyCssVars(b: Branding) {
  const root = document.documentElement;
  if (b.primary_color) {
    root.style.setProperty("--brand-primary", b.primary_color);
  }
  if (b.accent_color) {
    root.style.setProperty("--brand-accent", b.accent_color);
  }
  if (b.font_family) {
    root.style.setProperty("--brand-font", b.font_family);
  }
}

export function useBranding(): { branding: Branding; loaded: boolean; error: string | null } {
  const [branding, setBranding] = useState<Branding>(DEFAULT_BRAND);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        // 1. Ask the agent sidecar where this instance's branding lives.
        const brandResp = await fetch("/agent/brand", {
          // 15s: cross-origin GCS fetches on a cold connection can take
          // 5-10s — earlier 5s timeout was firing falsely, falling back to
          // DEFAULT_BRAND even when the bucket eventually responded 200.
          signal: AbortSignal.timeout(15000),
        });
        if (!brandResp.ok) {
          throw new Error(`/agent/brand HTTP ${brandResp.status}`);
        }
        const { brand_config_url } =
          (await brandResp.json()) as BrandConfigResponse;
        if (!brand_config_url) {
          // Configured intentionally empty => use DEFAULT_BRAND.
          if (!cancelled) {
            applyCssVars(DEFAULT_BRAND);
            setLoaded(true);
          }
          return;
        }

        // 2. Fetch branding.json from the per-instance directory.
        const bResp = await fetch(`${brand_config_url}/branding.json`, {
          // 15s: cross-origin GCS fetches on a cold connection can take
          // 5-10s — earlier 5s timeout was firing falsely, falling back to
          // DEFAULT_BRAND even when the bucket eventually responded 200.
          signal: AbortSignal.timeout(15000),
        });
        if (!bResp.ok) {
          throw new Error(
            `branding.json HTTP ${bResp.status} from ${brand_config_url}`,
          );
        }
        const fetched = (await bResp.json()) as Branding;
        const merged = { ...DEFAULT_BRAND, ...fetched };
        if (!cancelled) {
          setBranding(merged);
          applyCssVars(merged);
          setLoaded(true);
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        if (!cancelled) {
          console.warn(`[branding] falling back to DEFAULT_BRAND: ${msg}`);
          applyCssVars(DEFAULT_BRAND);
          setError(msg);
          setLoaded(true);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return { branding, loaded, error };
}
