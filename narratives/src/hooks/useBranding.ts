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

/**
 * Configuration for a single data commons visualization card/tile.
 */
export interface MetricsTile {
  /** The type of web component to render (e.g. line, bar, map). */
  type: MetricsTileType;
  /** Title shown as the card header. */
  title: string;
  /** Custom header override. */
  header?: string;
  /** Variable DCID for single-variable charts. */
  variable?: string;
  /** Comma-separated variable DCIDs for multi-variable charts. */
  variables?: string;
  /** Place DCID for single-place charts. */
  place?: string;
  /** Comma-separated place DCIDs. */
  places?: string;
  /** Parent place DCID (useful for map navigation). */
  parentPlace?: string;
  /** Child place type filter. */
  childPlaceType?: string;
  /** Specific date filter. */
  date?: string;
  /** Maximum number of places to show in ranking charts. */
  rankingCount?: number;
  /** Whether to show both highest and lowest in ranking. */
  showHighestLowest?: boolean;
  /** Whether to show only lowest in ranking. */
  showLowest?: boolean;
  /** Whether to show place labels on maps/charts. */
  showPlaceLabels?: boolean;
  /** Sort order for ranking charts. */
  sort?:
    | "ascending"
    | "descending"
    | "ascendingPopulation"
    | "descendingPopulation";
  /** Custom color palette override. */
  colors?: string;
  /** Unit override. */
  unit?: string;
  /** Minimum range value. */
  min?: number;
  /** Maximum range value. */
  max?: number;
  /** Start date filter range. */
  startDate?: string;
  /** End date filter range. */
  endDate?: string;
}

/**
 * Represents a tab group inside the Key Metrics Dashboard page.
 */
export interface MetricsTab {
  /** Unique ID for the tab. */
  id: string;
  /** Label text displayed on the tab selector. */
  label: string;
  /** Set of metric visualization cards to render within the tab. */
  tiles: MetricsTile[];
}

/**
 * Complete Key Metrics Dashboard configuration.
 */
export interface MetricsConfig {
  /** List of tabs containing visualizations. */
  tabs: MetricsTab[];
}

// ---------------------------------------------------------------------------
// Branding — per-instance config fetched from the bucket at page mount
// ---------------------------------------------------------------------------

/**
 * Branding configuration schema for customizing the instance layout and style.
 */
export interface Branding {
  /** The version of the branding schema configuration. */
  schemaVersion?: string;
  /** The name of this Custom Data Commons instance. */
  instanceName?: string;
  /** The URL of the brand logo image. */
  logoUrl?: string;
  /** Primary brand color used for key elements and buttons. */
  primaryColor?: string;
  /** Accent color used for highlighting selected tabs or callouts. */
  accentColor?: string;
  /** Custom Google Font family name applied to the site typography. */
  fontFamily?: string;
  /** A list of sample starter questions shown on the home page. */
  suggestions?: string[];
  /** Custom navigation links shown in the footer or sidebar. */
  navigation?: Array<{ label: string; href: string }>;
  /** Copyright or disclaimer text displayed in the footer. */
  footerText?: string;
  /** Optional customized key metrics dashboard tabs configuration. */
  metrics?: MetricsConfig;
}

/**
 * Raw branding response representation directly from the JSON files.
 */
interface RawBranding {
  schema_version?: string;
  instance_name?: string;
  logo_url?: string;
  primary_color?: string;
  accent_color?: string;
  font_family?: string;
  suggestions?: string[];
  navigation?: Array<{ label: string; href: string }>;
  footer_text?: string;
  metrics?: MetricsConfig;
}

export const DEFAULT_BRAND: Branding = {
  schemaVersion: "1",
  instanceName: "Custom Data Commons",
  logoUrl: "",
  primaryColor: "#1A73E8",
  accentColor: "#34A853",
  fontFamily: "Google Sans",
  suggestions: [
    "How has average annual wage changed over time in the United States?",
    "Compare GDP growth across G7 countries",
    "What is the gender wage gap in OECD countries?",
  ],
  navigation: [{ label: "Data Agent", href: "/" }],
  footerText: "Powered by Data Commons, an initiative from Google.",
};

interface BrandConfigResponse {
  brand_config_url?: string;
}

function mapRawToBranding(raw: RawBranding): Branding {
  return {
    schemaVersion: raw.schema_version,
    instanceName: raw.instance_name,
    logoUrl: raw.logo_url,
    primaryColor: raw.primary_color,
    accentColor: raw.accent_color,
    fontFamily: raw.font_family,
    suggestions: raw.suggestions,
    navigation: raw.navigation,
    footerText: raw.footer_text,
    metrics: raw.metrics,
  };
}

/**
 * Applies branding custom property values onto the root HTML element.
 */
function applyCssVars(brandingConfig: Branding) {
  const root = document.documentElement;
  if (brandingConfig.primaryColor) {
    root.style.setProperty("--brand-primary", brandingConfig.primaryColor);
  }
  if (brandingConfig.accentColor) {
    root.style.setProperty("--brand-accent", brandingConfig.accentColor);
  }
  if (brandingConfig.fontFamily) {
    root.style.setProperty("--brand-font", brandingConfig.fontFamily);
  }
}

/**
 * Hook to dynamically load branding custom configurations.
 */
export function useBranding(): { branding: Branding; loaded: boolean; error: string | null } {
  const [branding, setBranding] = useState<Branding>(DEFAULT_BRAND);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const brandResp = await fetch("/agent/brand", {
          signal: AbortSignal.timeout(15000),
        });
        if (!brandResp.ok) {
          throw new Error(`/agent/brand HTTP ${brandResp.status}`);
        }
        const { brand_config_url } =
          (await brandResp.json()) as BrandConfigResponse;
        if (!brand_config_url) {
          if (!cancelled) {
            applyCssVars(DEFAULT_BRAND);
            setLoaded(true);
          }
          return;
        }

        const bResp = await fetch(`${brand_config_url}/branding.json`, {
          signal: AbortSignal.timeout(15000),
        });
        if (!bResp.ok) {
          throw new Error(
            `branding.json HTTP ${bResp.status} from ${brand_config_url}`,
          );
        }
        const rawFetched = (await bResp.json()) as RawBranding;
        const fetched = mapRawToBranding(rawFetched);
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
