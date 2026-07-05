/**
 * @fileoverview Fetches and normalizes per-instance branding config from the instance's config bucket.
 */

import { useEffect, useState } from "react";
import type { MetricsConfig } from "../types/metrics";

/**
 * Per-instance branding, in the UI's camelCase domain shape. Produced by
 * {@link mapRawToBranding} from the snake_case {@link RawBranding} wire format,
 * so components read one consistent field naming everywhere.
 */
export interface Branding {
  /** Branding schema version string. */
  schemaVersion?: string;
  /** Display name of the instance, e.g. "India Data Commons". */
  instanceName?: string;
  /** URL/path to the instance logo; empty falls back to the bundled logo. */
  logoUrl?: string;
  /** Primary interactive color (hex), applied as the `--brand-primary` CSS var. */
  primaryColor?: string;
  /** Accent color (hex), applied as the `--brand-accent` CSS var. */
  accentColor?: string;
  /** Body/primary text color (hex), applied as the `--brand-text` CSS var. */
  textColor?: string;
  /** Secondary/muted text color (hex), applied as the `--brand-text-muted` CSS var. */
  textMutedColor?: string;
  /** Elevated surface color (hex), applied as the `--brand-surface` CSS var. */
  surfaceColor?: string;
  /** Page background color (hex), applied as the `--brand-background` CSS var. */
  backgroundColor?: string;
  /** Hero-gradient start stop (hex), applied as the `--brand-gradient-start` CSS var. */
  gradientStart?: string;
  /** Hero-gradient end stop (hex), applied as the `--brand-gradient-end` CSS var. */
  gradientEnd?: string;
  /** Display/heading font family, applied as the `--brand-font` CSS var. */
  fontFamily?: string;
  /** Body font family, applied as the `--brand-font-body` CSS var. */
  fontBody?: string;
  /** Starter prompt suggestions shown on the empty Data Agent screen. */
  suggestions?: string[];
  /** Header navigation entries (label + href). */
  navigation?: Array<{ label: string; href: string }>;
  /** Footer text. */
  footerText?: string;
  /** Metrics dashboard composition; when absent MetricsPage uses its defaults. */
  metrics?: MetricsConfig;
}

/**
 * Raw branding.json wire format as served from the instance's config bucket.
 * snake_case matches the on-disk/API contract; {@link mapRawToBranding}
 * translates it into the camelCase {@link Branding} domain type. Colors/fonts
 * ship as nested blocks; the flat `*_color` / `font_*` keys are legacy aliases.
 */
interface RawBranding {
  /** Branding schema version string. */
  schema_version?: string;
  /** Display name of the instance. */
  instance_name?: string;
  /** URL/path to the instance logo. */
  logo_url?: string;
  /** Nested palette — the canonical shape shipped in branding.json. */
  colors?: {
    primary?: string;
    accent?: string;
    text?: string;
    text_muted?: string;
    background?: string;
    surface?: string;
    /** Hero-gradient stops (the "Data Agent" heading). */
    gradient_start?: string;
    gradient_end?: string;
  };
  /** Nested font families — `primary` is the display font, `body` the base. */
  fonts?: {
    primary?: string;
    body?: string;
  };
  /** Legacy flat color aliases, accepted for older branding.json files. */
  primary_color?: string;
  accent_color?: string;
  text_color?: string;
  text_muted_color?: string;
  surface_color?: string;
  background_color?: string;
  gradient_start?: string;
  gradient_end?: string;
  /** Legacy flat font aliases. */
  font_family?: string;
  font_body?: string;
  suggestions?: string[];
  /** Legacy alias for `suggestions` in older uploaded branding.json files. */
  suggestion_chips?: string[];
  navigation?: Array<{ label: string; href: string }>;
  footer_text?: string;
  metrics?: MetricsConfig;
}

/**
 * Translates a raw branding.json payload into the camelCase {@link Branding}
 * domain type. Reads the nested `colors`/`fonts` blocks first, falling back to
 * the legacy flat keys. Only fields present in `raw` are included so the result
 * can be spread over {@link DEFAULT_BRAND} without clobbering defaults with
 * undefined. The legacy `suggestion_chips` key is accepted as an alias for
 * `suggestions`.
 */
function mapRawToBranding(raw: RawBranding): Branding {
  const branding: Branding = {};
  if (raw.schema_version !== undefined) branding.schemaVersion = raw.schema_version;
  if (raw.instance_name !== undefined) branding.instanceName = raw.instance_name;
  if (raw.logo_url !== undefined) branding.logoUrl = raw.logo_url;

  const primary = raw.colors?.primary ?? raw.primary_color;
  if (primary !== undefined) branding.primaryColor = primary;
  const accent = raw.colors?.accent ?? raw.accent_color;
  if (accent !== undefined) branding.accentColor = accent;
  const text = raw.colors?.text ?? raw.text_color;
  if (text !== undefined) branding.textColor = text;
  const textMuted = raw.colors?.text_muted ?? raw.text_muted_color;
  if (textMuted !== undefined) branding.textMutedColor = textMuted;
  const surface = raw.colors?.surface ?? raw.surface_color;
  if (surface !== undefined) branding.surfaceColor = surface;
  const background = raw.colors?.background ?? raw.background_color;
  if (background !== undefined) branding.backgroundColor = background;
  const gradientStart = raw.colors?.gradient_start ?? raw.gradient_start;
  if (gradientStart !== undefined) branding.gradientStart = gradientStart;
  const gradientEnd = raw.colors?.gradient_end ?? raw.gradient_end;
  if (gradientEnd !== undefined) branding.gradientEnd = gradientEnd;

  const font = raw.fonts?.primary ?? raw.font_family;
  if (font !== undefined) branding.fontFamily = font;
  const fontBody = raw.fonts?.body ?? raw.font_body;
  if (fontBody !== undefined) branding.fontBody = fontBody;

  const suggestions = raw.suggestions ?? raw.suggestion_chips;
  if (suggestions !== undefined) branding.suggestions = suggestions;
  if (raw.navigation !== undefined) branding.navigation = raw.navigation;
  if (raw.footer_text !== undefined) branding.footerText = raw.footer_text;
  if (raw.metrics !== undefined) branding.metrics = raw.metrics;
  return branding;
}

/**
 * Bundled fallback used if the agent's /agent/brand endpoint returns an empty
 * URL, or the fetch of branding.json fails. Keep in sync with
 * config/branding.example.json (the canonical reference template) and its JSON
 * Schema config/branding.schema.json.
 *
 * Color/font values intentionally mirror the design tokens hardcoded as
 * fallbacks in index.css (`--color-brand-primary`, `--color-on-surface`, etc.) so an
 * instance with no branding.json — or a failed fetch — stays pixel-identical to
 * the shipped design, while a real branding.json overrides them via
 * applyCssVars(). Do NOT change these to arbitrary brand colors.
 */
export const DEFAULT_BRAND: Branding = {
  schemaVersion: "1",
  instanceName: "Custom Data Commons",
  logoUrl: "",
  primaryColor: "#175C75",
  accentColor: "#65A782",
  textColor: "#1B1C1D",
  textMutedColor: "#444746",
  surfaceColor: "#F9F9F9",
  backgroundColor: "#FFFFFF",
  gradientStart: "#65A782",
  gradientEnd: "#6FAEC0",
  fontFamily: "Google Sans",
  suggestions: [
    "How has average annual wage changed over time in the United States?",
    "Compare GDP growth across G7 countries",
    "What is the gender wage gap in OECD countries?",
  ],
  navigation: [{ label: "Data Agent", href: "/" }],
  footerText: "Powered by Data Commons, an initiative from Google.",
};

/** Shape of the /agent/brand response that points at the config bucket. */
interface BrandConfigResponse {
  brand_config_url?: string;
  /**
   * branding.json proxied by the agent. Present when the config bucket is
   * private (the agent reads it server-side with a service-account token), so
   * the browser never fetches the bucket directly. Absent for the public-bucket
   * model, where the browser fetches `${brand_config_url}/branding.json` itself.
   */
  branding?: RawBranding;
}

/**
 * Resolves a possibly-relative asset path (e.g. "assets/logo.png") against the
 * config bucket base URL, so a logo declared in branding.json loads from the
 * bucket rather than the app origin. Absolute URLs and data: URIs pass through.
 */
function resolveAssetUrl(path: string | undefined, baseUrl: string): string | undefined {
  if (!path) return path;
  if (/^(https?:)?\/\//.test(path) || path.startsWith("data:")) return path;
  if (!baseUrl) return path;
  return `${baseUrl.replace(/\/$/, "")}/${path.replace(/^\//, "")}`;
}

/**
 * Applies branding values as CSS custom properties so the index.css `@theme`
 * block picks them up at render time. Each maps to a `var(--brand-*, <fallback>)`
 * design token, so setting these recolors every Tailwind utility (bg-brand-primary,
 * text-on-surface, …) and the hero gradient at runtime.
 */
function applyCssVars(branding: Branding) {
  const root = document.documentElement;
  const set = (name: string, value?: string) => {
    if (value) root.style.setProperty(name, value);
  };
  set("--brand-primary", branding.primaryColor);
  set("--brand-accent", branding.accentColor);
  set("--brand-text", branding.textColor);
  set("--brand-text-muted", branding.textMutedColor);
  set("--brand-surface", branding.surfaceColor);
  set("--brand-background", branding.backgroundColor);
  set("--brand-gradient-start", branding.gradientStart);
  set("--brand-gradient-end", branding.gradientEnd);
  set("--brand-font", branding.fontFamily);
  set("--brand-font-body", branding.fontBody);
}

/**
 * Fetches this instance's branding: asks the agent sidecar where the config
 * bucket lives, then loads branding.json from it, normalizes to {@link Branding},
 * and applies the color/font CSS variables. Falls back to {@link DEFAULT_BRAND}
 * on any failure.
 */
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
        const { brand_config_url, branding: directBranding } =
          (await brandResp.json()) as BrandConfigResponse;
        const baseUrl = brand_config_url ?? "";

        // 2a. Private-bucket path: the agent already proxied branding.json
        // (read server-side with a service-account token). Use it directly so
        // the browser never has to read a private bucket. Relative logo paths
        // are resolved against the bucket URL.
        if (directBranding) {
          const mapped = mapRawToBranding(directBranding);
          mapped.logoUrl = resolveAssetUrl(mapped.logoUrl, baseUrl);
          const merged = { ...DEFAULT_BRAND, ...mapped };
          if (!cancelled) {
            setBranding(merged);
            applyCssVars(merged);
            setLoaded(true);
          }
          return;
        }

        if (!brand_config_url) {
          // Configured intentionally empty => use DEFAULT_BRAND.
          if (!cancelled) {
            applyCssVars(DEFAULT_BRAND);
            setLoaded(true);
          }
          return;
        }

        // 2b. Public-bucket path: fetch branding.json directly from the bucket.
        const brandingConfigResponse = await fetch(
          `${brand_config_url}/branding.json`,
          {
            // 15s: cross-origin GCS fetches on a cold connection can take
            // 5-10s — earlier 5s timeout was firing falsely, falling back to
            // DEFAULT_BRAND even when the bucket eventually responded 200.
            signal: AbortSignal.timeout(15000),
          },
        );
        if (!brandingConfigResponse.ok) {
          throw new Error(
            `branding.json HTTP ${brandingConfigResponse.status} from ${brand_config_url}`,
          );
        }
        const raw = (await brandingConfigResponse.json()) as RawBranding;
        // Translate the snake_case wire format into the camelCase domain type,
        // then fill any gaps from DEFAULT_BRAND (mapRawToBranding omits absent
        // fields so defaults aren't clobbered with undefined).
        const mapped = mapRawToBranding(raw);
        mapped.logoUrl = resolveAssetUrl(mapped.logoUrl, baseUrl);
        const merged = { ...DEFAULT_BRAND, ...mapped };
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
