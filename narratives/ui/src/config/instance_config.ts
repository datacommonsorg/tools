/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
 * implied. See the License for the specific language governing
 * permissions and limitations under the License.
 */

/**
 * @fileoverview Per-instance UI configuration. This module provides the Base
 * Data Commons defaults and merges any theme JSON present in
 * `<script id="instance-config">` on the first call to {@link getInstanceConfig}.
 */

import { classifyLinkHref } from '@/src/components/link';
import { withBaseUrl } from '@/src/config/base_url';
import type {
  MetricsConfig,
  MetricsTile,
  MetricsTileType,
} from '@/src/types/metrics';

export interface NavLink {
  label: string;
  href: string;
}

/** One headed section of the tagline dialog. */
export interface TaglineLinkSection {
  title: string;
  body: string;
}

/** A phrase in the tagline that opens a modal dialog. */
export interface TaglineLink {
  /** Exact phrase in the tagline that becomes the link. */
  text: string;
  /** Dialog sections; the first title also names the dialog. */
  sections: TaglineLinkSection[];
  /** Optional link to the data sources, shown in the dialog's action bar. */
  sources?: NavLink;
}

export interface InstanceConfig {
  /** Name of the deployment, usually the organization name. */
  instanceName: string;
  /** URL of the header logo image. */
  logoUrl: string;
  /** Wordmark text rendered next to the header logo, or empty to hide it. */
  logoText: string;
  /** Alternative text for the header logo when no wordmark is displayed. */
  logoAlt: string;
  /** Link target of the header logo, usually the instance's home page. */
  logoHref: string;
  /** URL of the animated indicator shown while the agent is streaming. */
  thinkingIndicatorUrl: string;
  /** URL of the static indicator shown after the agent finishes streaming. */
  doneIndicatorUrl: string;
  /** Primary heading displayed on the landing view. */
  headline: string;
  /** Subtitle displayed below the headline on the landing view. */
  tagline: string;
  /** Tagline phrase that opens a dialog, or null for plain text. */
  taglineLink: TaglineLink | null;
  /** Primary navigation links rendered in the header and mobile drawer. */
  navigation: NavLink[];
  /** Starter prompt queries rendered as suggestion chips on the landing view. */
  suggestions: string[];
  /** Tab and tile definitions for the Key Metrics dashboard. */
  metrics: MetricsConfig;
}

export const DEFAULT_INSTANCE_CONFIG: Readonly<InstanceConfig> = {
  instanceName: 'Data Commons',
  logoUrl: '/dc-logo.svg',
  logoText: 'Data Commons by Google',
  logoAlt: 'Data Commons by Google',
  logoHref: '/',
  thinkingIndicatorUrl: '/agent-thinking.svg',
  doneIndicatorUrl: '/agent-done-thinking.svg',
  headline: 'Explore global public data in one place',
  tagline:
    'Answers draw from organized datasets in the Data Commons Knowledge Graph',
  taglineLink: {
    text: 'Data Commons Knowledge Graph',
    sections: [
      {
        title: 'Data Commons Knowledge Graph',
        body: 'The Data Commons Knowledge Graph is an open library of public data collected and standardized in advance, turning agency tables and reports into consistent, machine-readable series. It brings together datasets on population, the economy, health, education, crime, and the environment from institutions such as the U.S. Census Bureau, World Bank, United Nations, CDC, and NOAA. Each figure links to both its Data Commons record and the original agency release.',
      },
      {
        title: 'About this tool',
        body: 'Gemini synthesizes data overviews from indicators available in the Data Commons Knowledge Graph, covering historical trends, rankings, regional comparisons, and breakdowns of totals. It calculates basic descriptive figures (such as medians, highs, lows, and changes over time) rather than running regressions, correlation tests, or custom data groupings. It does not offer opinions, policy analysis, or forecasts, and coverage depends on what agencies publish and which releases have been added to the graph so far. Please verify AI-generated summaries against the linked source records.',
      },
    ],
    sources: {
      label: 'See all the data sources',
      href: 'https://datacommons.org/data',
    },
  },
  navigation: [],
  suggestions: [
    'How has renewable energy adoption changed in Spain?',
    'Compare infant mortality rates between Kenya and Ghana',
    'How has agricultural land area changed in the USA?',
  ],
  metrics: { tabs: [] },
};

const getDefaultInstanceConfig = (): Readonly<InstanceConfig> => ({
  ...DEFAULT_INSTANCE_CONFIG,
  logoUrl: withBaseUrl(DEFAULT_INSTANCE_CONFIG.logoUrl),
  thinkingIndicatorUrl: withBaseUrl(
    DEFAULT_INSTANCE_CONFIG.thinkingIndicatorUrl,
  ),
  doneIndicatorUrl: withBaseUrl(DEFAULT_INSTANCE_CONFIG.doneIndicatorUrl),
});

const INSTANCE_CONFIG_ELEMENT_ID = 'instance-config';
const LOG_PREFIX = '[instance-config]';

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const isString = (value: unknown): value is string => typeof value === 'string';

const isStringArray = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every(isString);

/**
 * Returns true if `value` is a safe `http(s)` URL or a single-slash
 * root-relative path.
 */
const isSafeUrl = (value: string): boolean => {
  const kind = classifyLinkHref(value);
  return kind === 'external' || (kind === 'internal' && !value.startsWith('#'));
};

/**
 * Returns `value` when it is a safe asset URL, or logs a warning and returns
 * `fallback`.
 */
export const sanitizeUrl = (value: unknown, fallback: string): string => {
  if (!isString(value) || value === '') {
    return fallback;
  }
  if (isSafeUrl(value)) {
    return value;
  }
  console.warn(
    `${LOG_PREFIX} ignoring unsafe URL ${JSON.stringify(value)}; using the built-in asset.`,
  );
  return fallback;
};

const isNavHref = (value: unknown): value is string =>
  isString(value) && classifyLinkHref(value) !== 'unsafe';

const isNavLink = (value: unknown): value is NavLink =>
  isRecord(value) && isString(value.label) && isNavHref(value.href);

const isTaglineLink = (value: unknown): value is TaglineLink =>
  isRecord(value) &&
  isString(value.text) &&
  Array.isArray(value.sections) &&
  value.sections.length > 0 &&
  value.sections.every(
    (section) =>
      isRecord(section) && isString(section.title) && isString(section.body),
  ) &&
  (value.sources === undefined || isNavLink(value.sources));

const isNavLinkArray = (value: unknown): value is NavLink[] =>
  Array.isArray(value) && value.every(isNavLink);

/**
 * The chart types that a Key Metrics tile can render. The set matches the
 * `metricsTile.type` enum in `theme.schema.json`.
 */
const METRICS_TILE_TYPES: ReadonlySet<string> = new Set<MetricsTileType>([
  'line',
  'bar',
  'map',
  'ranking',
  'highlight',
  'scatter',
  'pie',
  'gauge',
  'slider',
]);

type MetricsTileAttributeName = Exclude<keyof MetricsTile, 'type' | 'title'>;

const METRICS_SORT_ORDERS: ReadonlySet<string> = new Set<
  NonNullable<MetricsTile['sort']>
>(['ascending', 'descending', 'ascendingPopulation', 'descendingPopulation']);

const isBoolean = (value: unknown): value is boolean =>
  typeof value === 'boolean';

const isInteger = (value: unknown): value is number =>
  typeof value === 'number' && Number.isInteger(value);

const isFiniteNumber = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value);

const isMetricsSortOrder = (
  value: unknown,
): value is NonNullable<MetricsTile['sort']> =>
  isString(value) && METRICS_SORT_ORDERS.has(value);

const METRICS_TILE_ATTRIBUTE_VALIDATORS: {
  readonly [K in MetricsTileAttributeName]: (
    value: unknown,
  ) => value is NonNullable<MetricsTile[K]>;
} = {
  header: isString,
  variable: isString,
  variables: isString,
  place: isString,
  places: isString,
  parentPlace: isString,
  childPlaceType: isString,
  date: isString,
  rankingCount: isInteger,
  showHighestLowest: isBoolean,
  showLowest: isBoolean,
  showPlaceLabels: isBoolean,
  sort: isMetricsSortOrder,
  colors: isString,
  unit: isString,
  min: isFiniteNumber,
  max: isFiniteNumber,
  startDate: isString,
  endDate: isString,
};

/**
 * The tile keys that are forwarded as attributes to the tile's
 * `<datacommons-*>` element. The list matches `metricsTile.properties` in
 * `theme.schema.json`, except for `type` and `title`. Every other key or
 * mismatched value type is dropped so that a theme cannot set an arbitrary or
 * malformed attribute, such as `onclick` or `"showLowest": "false"`, on the
 * chart element.
 */
export const METRICS_TILE_ATTRIBUTE_NAMES = Object.keys(
  METRICS_TILE_ATTRIBUTE_VALIDATORS,
) as readonly MetricsTileAttributeName[];

const METRICS_TILE_ATTRIBUTE_NAME_SET: ReadonlySet<string> = new Set<string>(
  METRICS_TILE_ATTRIBUTE_NAMES,
);

const isMetricsTileAttributeName = (
  name: string,
): name is MetricsTileAttributeName =>
  METRICS_TILE_ATTRIBUTE_NAME_SET.has(name);

const setValidTileAttribute = <K extends MetricsTileAttributeName>(
  target: MetricsTile,
  name: K,
  value: unknown,
): boolean => {
  const validator = METRICS_TILE_ATTRIBUTE_VALIDATORS[name];
  if (!validator(value)) {
    return false;
  }
  target[name] = value;
  return true;
};

/** A tile as read from the theme, before its type and keys are checked. */
interface RawMetricsTile {
  type: string;
  title: string;
  [name: string]: unknown;
}

interface RawMetricsTab {
  id: string;
  label: string;
  tiles: RawMetricsTile[];
}

interface RawMetricsConfig {
  tabs: RawMetricsTab[];
}

const isRawMetricsTile = (value: unknown): value is RawMetricsTile =>
  isRecord(value) && isString(value.type) && isString(value.title);

const isRawMetricsTab = (value: unknown): value is RawMetricsTab =>
  isRecord(value) &&
  isString(value.id) &&
  isString(value.label) &&
  Array.isArray(value.tiles) &&
  value.tiles.every(isRawMetricsTile);

const isRawMetricsConfig = (value: unknown): value is RawMetricsConfig =>
  isRecord(value) &&
  Array.isArray(value.tabs) &&
  value.tabs.every(isRawMetricsTab);

const isMetricsTileType = (value: string): value is MetricsTileType =>
  METRICS_TILE_TYPES.has(value);

/**
 * Returns a copy of `tile` that keeps only allowlisted attributes whose values
 * match their schema types, or `null` when `tile.type` is not a known chart
 * type. Logs a warning for each dropped key, invalid value, and dropped tile.
 */
const toMetricsTile = (tile: RawMetricsTile): MetricsTile | null => {
  const { type, title, ...attributes } = tile;
  if (!isMetricsTileType(type)) {
    console.warn(
      `${LOG_PREFIX} ignoring metrics tile ${JSON.stringify(title)}: unknown type ${JSON.stringify(type)}.`,
    );
    return null;
  }
  const validatedTile: MetricsTile = { type, title };
  for (const [name, value] of Object.entries(attributes)) {
    if (!isMetricsTileAttributeName(name)) {
      console.warn(
        `${LOG_PREFIX} ignoring attribute ${JSON.stringify(name)} of metrics tile ${JSON.stringify(title)}.`,
      );
      continue;
    }
    if (!setValidTileAttribute(validatedTile, name, value)) {
      console.warn(
        `${LOG_PREFIX} ignoring attribute ${JSON.stringify(name)} of metrics tile ${JSON.stringify(title)}: invalid value ${JSON.stringify(value)}.`,
      );
    }
  }
  return validatedTile;
};

const toMetricsConfig = (raw: RawMetricsConfig): MetricsConfig => ({
  tabs: raw.tabs.map((tab) => ({
    id: tab.id,
    label: tab.label,
    tiles: tab.tiles
      .map(toMetricsTile)
      .filter((tile): tile is MetricsTile => tile !== null),
  })),
});

const pick = <T>(
  key: string,
  value: unknown,
  guard: (value: unknown) => value is T,
  fallback: T,
): T => {
  if (value === undefined) {
    return fallback;
  }
  if (guard(value)) {
    return value;
  }
  console.warn(
    `${LOG_PREFIX} ignoring "${key}": unexpected shape; using the built-in default.`,
  );
  return fallback;
};

const mergeOverrides = (raw: Record<string, unknown>): InstanceConfig => {
  const defaults = getDefaultInstanceConfig();
  const splashAssets = pick('splash_assets', raw.splash_assets, isRecord, {});
  const hasCustomIdentity =
    raw.logo !== undefined || raw.instance_name !== undefined;
  const rawMetrics = pick<RawMetricsConfig | null>(
    'metrics',
    raw.metrics,
    isRawMetricsConfig,
    null,
  );
  return {
    instanceName: pick(
      'instance_name',
      raw.instance_name,
      isString,
      defaults.instanceName,
    ),
    logoUrl: sanitizeUrl(
      pick('logo', raw.logo, isString, defaults.logoUrl),
      defaults.logoUrl,
    ),
    // When a custom theme document overrides `logo` or `instance_name` and omits
    // `logo_text` or `logo_alt`, default to an empty string so the custom logo
    // does not inherit the "Data Commons" wordmark or alternative text.
    logoText: pick(
      'logo_text',
      raw.logo_text,
      isString,
      hasCustomIdentity ? '' : defaults.logoText,
    ),
    logoAlt: pick(
      'logo_alt',
      raw.logo_alt,
      isString,
      hasCustomIdentity ? '' : defaults.logoAlt,
    ),
    logoHref: pick('logo_href', raw.logo_href, isNavHref, defaults.logoHref),
    thinkingIndicatorUrl: sanitizeUrl(
      pick(
        'splash_assets.thinking_indicator',
        splashAssets.thinking_indicator,
        isString,
        defaults.thinkingIndicatorUrl,
      ),
      defaults.thinkingIndicatorUrl,
    ),
    doneIndicatorUrl: sanitizeUrl(
      pick(
        'splash_assets.done_indicator',
        splashAssets.done_indicator,
        isString,
        defaults.doneIndicatorUrl,
      ),
      defaults.doneIndicatorUrl,
    ),
    headline: pick('headline', raw.headline, isString, defaults.headline),
    tagline: pick('tagline', raw.tagline, isString, defaults.tagline),
    taglineLink: pick(
      'tagline_link',
      raw.tagline_link,
      isTaglineLink,
      defaults.taglineLink,
    ),
    navigation: pick(
      'navigation',
      raw.navigation,
      isNavLinkArray,
      defaults.navigation,
    ),
    suggestions: pick(
      'suggestions',
      raw.suggestions,
      isStringArray,
      defaults.suggestions,
    ),
    metrics:
      rawMetrics === null ? defaults.metrics : toMetricsConfig(rawMetrics),
  };
};

const readOverrides = (): Record<string, unknown> | null => {
  const text = document
    .getElementById(INSTANCE_CONFIG_ELEMENT_ID)
    ?.textContent?.trim();
  if (!text) {
    return null;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    console.warn(
      `${LOG_PREFIX} ignoring malformed JSON in #${INSTANCE_CONFIG_ELEMENT_ID}; using the built-in defaults.`,
      error,
    );
    return null;
  }
  if (isRecord(parsed)) {
    return parsed;
  }
  console.warn(
    `${LOG_PREFIX} ignoring #${INSTANCE_CONFIG_ELEMENT_ID}: expected a JSON object; using the built-in defaults.`,
  );
  return null;
};

let cachedConfig: Readonly<InstanceConfig> | null = null;

/**
 * Returns the instance configuration, reading and caching `#instance-config` on
 * the first call.
 */
export const getInstanceConfig = (): Readonly<InstanceConfig> => {
  if (cachedConfig === null) {
    const overrides = readOverrides();
    cachedConfig =
      overrides === null
        ? getDefaultInstanceConfig()
        : mergeOverrides(overrides);
  }
  return cachedConfig;
};

/** Clears the cached configuration between tests. */
export const resetInstanceConfigForTests = (): void => {
  cachedConfig = null;
};
