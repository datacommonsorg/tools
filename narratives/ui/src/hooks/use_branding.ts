/**
 * @fileoverview Fetches and normalizes per-instance branding from the agent,
 * which holds it in memory after reading it from GCS at startup.
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
  /**
   * Wordmark rendered beside the logo. Absent means no text is shown — an
   * instance whose logo image already contains its name simply omits it.
   */
  logoText?: string;
  /**
   * Tab icon, as the agent's own asset path. Applied to the <link rel="icon">
   * in index.html rather than rendered, so it lives outside the React tree.
   */
  faviconUrl?: string;
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
  /** Narrative tile background (hex), applied as the `--brand-surface-narrative` CSS var. */
  surfaceNarrativeColor?: string;
  /** Skeleton loader bar color (hex), applied as the `--brand-skeleton-bar` CSS var. */
  skeletonBarColor?: string;
  /** Card border / divider color (hex), applied as the `--brand-border` CSS var. */
  borderColor?: string;
  /** User-message bubble color (hex), applied as the `--brand-user-msg` CSS var. */
  userMessageColor?: string;
  /** Tonal-button container (hex), applied as the `--brand-container` CSS var. */
  containerColor?: string;
  /** Tonal-button label/icon (hex), applied as the `--brand-on-container` CSS var. */
  onContainerColor?: string;
  /** Active header-tab label and underline (hex), applied as `--brand-nav-active`. */
  navActiveColor?: string;
  /** Card corner radius (CSS length), applied as the `--brand-radius-card` CSS var. */
  radiusCard?: string;
  /** Input-box corner radius (CSS length), applied as the `--brand-radius-input` CSS var. */
  radiusInput?: string;
  /** Suggestion-chip corner radius (CSS length), applied as the `--brand-radius-chip` CSS var. */
  radiusChip?: string;
  /** Header logo height (CSS length), applied as the `--brand-logo-height` CSS var. */
  logoHeight?: string;
  /** Display/heading font family, applied as the `--brand-font` CSS var. */
  fontFamily?: string;
  /** Body font family, applied as the `--brand-font-body` CSS var. */
  fontBody?: string;
  /** Hero heading on the empty Data Agent screen, e.g. "Data agent explorer". */
  headline?: string;
  /** Sub-heading under {@link headline}, e.g. "powered by Google's Data Commons". */
  tagline?: string;
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
  /**
   * Logo path. The agent rewrites this to its own asset route before serving,
   * so it arrives as a same-origin path, never a bucket URL. This is the key
   * `branding.schema.json` defines.
   */
  logo?: string;
  /** Legacy alias for `logo`, accepted for older branding.json files. */
  logo_url?: string;
  /** Wordmark rendered beside the logo; omit to show the mark alone. */
  logo_text?: string;
  /**
   * Tab-icon path. Rewritten to the agent's asset route alongside `logo`, so it
   * arrives same-origin and never as a bucket URL.
   */
  favicon?: string;
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
    /** Tile behind a rendered narrative (response card and its skeleton). */
    surface_narrative?: string;
    /** Skeleton ("ghost loader") bars shown while a narrative streams in. */
    skeleton_bar?: string;
    /** Card borders and divider rules. */
    border?: string;
    /** User-message bubble. */
    user_message?: string;
    /** Tonal-button container; defaults to a tint mixed from `primary`. */
    container?: string;
    /** Tonal-button label and icon; defaults to `primary`. */
    on_container?: string;
    /** Active header-tab label and underline; defaults to `text`. */
    nav_active?: string;
  };
  /**
   * Corner radii as CSS lengths (e.g. "16px"). Lets an instance move between
   * rounded and square without a code change.
   */
  radius?: {
    card?: string;
    input?: string;
    chip?: string;
  };
  /** Header logo height as a CSS length, e.g. "28px". */
  logo_height?: string;
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
  /** Hero heading on the empty Data Agent screen. */
  headline?: string;
  /** Sub-heading under `headline`. */
  tagline?: string;
  suggestions?: string[];
  /** Legacy alias for `suggestions` in older uploaded branding.json files. */
  suggestion_chips?: string[];
  navigation?: Array<{ label: string; href: string }>;
  /** Nested footer block — the shape branding.schema.json defines. */
  footer?: {
    text?: string;
    links?: Array<{ label: string; href: string }>;
  };
  /** Legacy flat alias for `footer.text`. */
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
  const logo = raw.logo ?? raw.logo_url;
  if (logo !== undefined) branding.logoUrl = logo;
  if (raw.logo_text !== undefined) branding.logoText = raw.logo_text;
  if (raw.favicon !== undefined) branding.faviconUrl = raw.favicon;

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
  if (raw.colors?.surface_narrative !== undefined) {
    branding.surfaceNarrativeColor = raw.colors.surface_narrative;
  }
  if (raw.colors?.skeleton_bar !== undefined) {
    branding.skeletonBarColor = raw.colors.skeleton_bar;
  }
  if (raw.colors?.border !== undefined) {
    branding.borderColor = raw.colors.border;
  }
  if (raw.colors?.user_message !== undefined) {
    branding.userMessageColor = raw.colors.user_message;
  }
  if (raw.colors?.container !== undefined) {
    branding.containerColor = raw.colors.container;
  }
  if (raw.colors?.on_container !== undefined) {
    branding.onContainerColor = raw.colors.on_container;
  }
  if (raw.colors?.nav_active !== undefined) {
    branding.navActiveColor = raw.colors.nav_active;
  }

  if (raw.radius?.card !== undefined) branding.radiusCard = raw.radius.card;
  if (raw.radius?.input !== undefined) branding.radiusInput = raw.radius.input;
  if (raw.radius?.chip !== undefined) branding.radiusChip = raw.radius.chip;
  if (raw.logo_height !== undefined) branding.logoHeight = raw.logo_height;

  const font = raw.fonts?.primary ?? raw.font_family;
  if (font !== undefined) branding.fontFamily = font;
  const fontBody = raw.fonts?.body ?? raw.font_body;
  if (fontBody !== undefined) branding.fontBody = fontBody;

  if (raw.headline !== undefined) branding.headline = raw.headline;
  if (raw.tagline !== undefined) branding.tagline = raw.tagline;

  const suggestions = raw.suggestions ?? raw.suggestion_chips;
  if (suggestions !== undefined) branding.suggestions = suggestions;
  if (raw.navigation !== undefined) branding.navigation = raw.navigation;
  // Nested `footer.text` is the schema's shape; `footer_text` is the legacy
  // flat alias. Reading only the latter silently dropped every configured
  // footer, since branding.json files ship the nested block.
  const footerText = raw.footer?.text ?? raw.footer_text;
  if (footerText !== undefined) branding.footerText = footerText;
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
  surfaceNarrativeColor: "#F9F9F9",
  skeletonBarColor: "#E3E3E3",
  borderColor: "#E3E3E3",
  userMessageColor: "#E8F2F4",
  radiusCard: "16px",
  radiusInput: "36px",
  radiusChip: "20px",
  fontFamily: "Google Sans",
  headline: "Data Agent",
  tagline: "powered by Google's Data Commons",
  suggestions: [
    "How has average annual wage changed over time in the United States?",
    "Compare GDP growth across G7 countries",
    "What is the gender wage gap in OECD countries?",
  ],
  // `navigation` is deliberately absent. resolveNavItems() treats an absent
  // value as "use the shipped tabs" (NAV_CONFIG) and an explicit [] as "no
  // header menu". Setting a default here would shadow NAV_CONFIG and pin every
  // instance to whatever single entry it held.
  footerText: "Powered by Data Commons, an initiative from Google.",
};

/** Shape of the /agent/brand response that points at the config bucket. */
interface BrandConfigResponse {
  /** Instance id the agent was configured with; informational. */
  instance?: string;
  /**
   * branding.json as the agent read it from GCS at startup and has held in
   * memory since. Null when no branding is configured, or when the document was
   * missing or corrupt — in which case the UI keeps {@link DEFAULT_BRAND}.
   *
   * The config bucket URL is deliberately not part of this payload: the browser
   * never reads the bucket, and asset paths arrive already rewritten to the
   * agent's own `/brand/assets/...` route.
   */
  branding?: RawBranding | null;
}

declare global {
  interface Window {
    /**
     * Branding published by `/agent/brand.js`, the blocking script in
     * index.html's <head>. Set before the bundle evaluates, so the first render
     * can already be this instance's.
     *
     * Three states, and the difference matters: `undefined` means the script did
     * not run (404, network failure, or a stale index.html that predates it), so
     * the /agent/brand fetch is still needed; `null` means it ran and this
     * instance has no branding configured; an object is the document itself.
     */
    __BRAND__?: RawBranding | null;
  }
}

/**
 * Reads the pre-paint global, distinguishing "script did not run" (`undefined`)
 * from "ran, nothing configured" (`null`). Guarded for non-browser callers
 * (tests, any future SSR) where `window` is absent.
 */
function readPrePaintBranding(): RawBranding | null | undefined {
  return typeof window === "undefined" ? undefined : window.__BRAND__;
}

/**
 * Applies branding to the parts of the document that sit outside the React tree
 * and so cannot be set by rendering: the tab title and the favicon.
 *
 * Both are deliberately left alone when the instance omits them, so index.html's
 * shipped title and bundled mark stand rather than being blanked.
 */
function applyDocumentChrome(branding: Branding) {
  if (branding.instanceName) {
    document.title = branding.instanceName;
  }
  if (branding.faviconUrl) {
    const icon = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
    if (icon) icon.href = branding.faviconUrl;
  }
}

/**
 * Applies configured branding values as CSS custom properties. Only pass values
 * that came from branding.json: anything omitted must fall through to
 * /agent/brand.css and then index.css's `var(--brand-*, <fallback>)` defaults,
 * and an inline property here would outrank both.
 *
 * Sets them so the index.css `@theme`
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
  set("--brand-surface-narrative", branding.surfaceNarrativeColor);
  set("--brand-skeleton-bar", branding.skeletonBarColor);
  set("--brand-border", branding.borderColor);
  set("--brand-user-msg", branding.userMessageColor);
  set("--brand-container", branding.containerColor);
  set("--brand-on-container", branding.onContainerColor);
  set("--brand-nav-active", branding.navActiveColor);
  set("--brand-radius-card", branding.radiusCard);
  set("--brand-radius-input", branding.radiusInput);
  set("--brand-radius-chip", branding.radiusChip);
  set("--brand-logo-height", branding.logoHeight);
  set("--brand-font", branding.fontFamily);
  set("--brand-font-body", branding.fontBody);
}

/**
 * Reads this instance's branding from the agent, normalizes it to
 * {@link Branding}, and applies the color, radius and font CSS variables.
 *
 * The agent loaded the document from GCS once at its own startup and serves it
 * from memory, so this is a single same-origin request; the browser never
 * touches the config bucket. Falls back to {@link DEFAULT_BRAND} on any failure,
 * so a missing or corrupt config degrades to the shipped design rather than a
 * broken page.
 */
export function useBranding(): { branding: Branding; loaded: boolean; error: string | null } {
  // Seeded synchronously from the pre-paint global, so the first render is
  // already this instance's. Starting at DEFAULT_BRAND unconditionally is what
  // produced the visible flip on load: the shipped neutral headline, wordmark,
  // logo, nav tabs and chips painted, then the fetch swapped them out a second
  // or so later.
  const [branding, setBranding] = useState<Branding>(() => {
    const raw = readPrePaintBranding();
    return raw ? { ...DEFAULT_BRAND, ...mapRawToBranding(raw) } : DEFAULT_BRAND;
  });
  const [loaded, setLoaded] = useState(() => readPrePaintBranding() !== undefined);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const prePaint = readPrePaintBranding();
    if (prePaint !== undefined) {
      // brand.js ran, so the state above is already correct and fetching would
      // only re-request the very same startup-loaded document. Re-assert the CSS
      // variables it implies: brand.css normally applied them before first
      // paint, but if that request was the one that failed, this keeps the
      // colours consistent with the content rather than leaving them mismatched.
      if (prePaint) applyCssVars(mapRawToBranding(prePaint));
      return;
    }

    let cancelled = false;

    async function load() {
      try {
        // The agent read branding.json from GCS once, at its own startup, and
        // answers from memory. It is the only source consulted here: the
        // browser must never read the config bucket, and is not told where it
        // is. Asset paths arrive already rewritten to the agent's own route.
        const brandResp = await fetch("/agent/brand", {
          signal: AbortSignal.timeout(15000),
        });
        if (!brandResp.ok) {
          throw new Error(`/agent/brand HTTP ${brandResp.status}`);
        }
        const { branding: rawBranding } =
          (await brandResp.json()) as BrandConfigResponse;

        if (!rawBranding) {
          // No branding configured, or the agent could not read it. Apply
          // nothing: /agent/brand.css and index.css's own fallbacks already
          // describe this state, and writing DEFAULT_BRAND inline here would
          // outrank the stylesheet and undo a correct pre-paint render.
          if (!cancelled) {
            setLoaded(true);
          }
          return;
        }

        // Translate the snake_case wire format into the camelCase domain type,
        // then fill any gaps from DEFAULT_BRAND (mapRawToBranding omits absent
        // fields so defaults aren't clobbered with undefined).
        const configured = mapRawToBranding(rawBranding);
        const merged = { ...DEFAULT_BRAND, ...configured };
        if (!cancelled) {
          setBranding(merged);
          // Only what branding.json actually set. Passing `merged` would write
          // DEFAULT_BRAND's values inline for every key the instance omitted,
          // shadowing the design tokens those keys are meant to fall through to.
          applyCssVars(configured);
          setLoaded(true);
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        if (!cancelled) {
          console.warn(`[branding] falling back to the shipped design: ${msg}`);
          // Deliberately no applyCssVars here. The pre-paint stylesheet may
          // already have applied correct values; writing DEFAULT_BRAND inline
          // would override them and turn a failed refresh into a visibly wrong
          // theme. `branding` state still holds DEFAULT_BRAND for the non-CSS
          // fields components read directly.
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

  // The tab title and favicon are not rendered, so they need applying as a side
  // effect — for the seeded path as much as the fetched one.
  useEffect(() => {
    applyDocumentChrome(branding);
  }, [branding]);

  return { branding, loaded, error };
}
