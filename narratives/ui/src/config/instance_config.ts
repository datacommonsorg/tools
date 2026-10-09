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

import type { MetricsConfig, MetricsTab } from '@/src/types/metrics';

export interface NavLink {
  label: string;
  href: string;
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
  /** URL of the animated indicator shown while the agent is streaming. */
  thinkingIndicatorUrl: string;
  /** URL of the static indicator shown after the agent finishes streaming. */
  doneIndicatorUrl: string;
  /** Primary heading displayed on the landing view. */
  headline: string;
  /** Subtitle displayed below the headline on the landing view. */
  tagline: string;
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
  logoText: 'Data Commons',
  logoAlt: 'Data Commons',
  thinkingIndicatorUrl: '/agent-thinking.svg',
  doneIndicatorUrl: '/agent-done-thinking.svg',
  headline: 'Data agent explorer',
  tagline: "powered by Google's Data Commons",
  navigation: [],
  suggestions: [
    'How big is the financial sector in Vietnam',
    'How is India doing in agricultural practices',
    'How is Africa doing combating HIV/AIDS',
  ],
  metrics: { tabs: [] },
};

const INSTANCE_CONFIG_ELEMENT_ID = 'instance-config';
const LOG_PREFIX = '[instance-config]';

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const isString = (value: unknown): value is string => typeof value === 'string';

const isStringArray = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every(isString);

/**
 * Returns true if `value` is an `http(s)` URL or a root-relative path on the
 * current origin.
 */
const isSafeUrl = (value: string): boolean => {
  let parsed: URL;
  try {
    parsed = new URL(value, window.location.origin);
  } catch {
    return false;
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    return false;
  }
  if (/^https?:\/\//i.test(value)) {
    return true;
  }
  return value.startsWith('/') && parsed.origin === window.location.origin;
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
  isString(value) && (value.startsWith('#') || isSafeUrl(value));

const isNavLink = (value: unknown): value is NavLink =>
  isRecord(value) && isString(value.label) && isNavHref(value.href);

const isNavLinkArray = (value: unknown): value is NavLink[] =>
  Array.isArray(value) && value.every(isNavLink);

// Validate only the fields that MetricsPage reads; remaining tile attributes are
// forwarded directly to the Data Commons web component.
const isMetricsTab = (value: unknown): value is MetricsTab =>
  isRecord(value) &&
  isString(value.id) &&
  isString(value.label) &&
  Array.isArray(value.tiles) &&
  value.tiles.every(
    (tile) => isRecord(tile) && isString(tile.type) && isString(tile.title),
  );

const isMetricsConfig = (value: unknown): value is MetricsConfig =>
  isRecord(value) &&
  Array.isArray(value.tabs) &&
  value.tabs.every(isMetricsTab);

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
  const defaults = DEFAULT_INSTANCE_CONFIG;
  const splashAssets = pick('splash_assets', raw.splash_assets, isRecord, {});
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
    // When a custom theme document omits `logo_text` or `logo_alt`, default to
    // an empty string so the custom logo does not inherit the "Data Commons"
    // wordmark or alternative text.
    logoText: pick('logo_text', raw.logo_text, isString, ''),
    logoAlt: pick('logo_alt', raw.logo_alt, isString, ''),
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
    metrics: pick('metrics', raw.metrics, isMetricsConfig, defaults.metrics),
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
      overrides === null ? DEFAULT_INSTANCE_CONFIG : mergeOverrides(overrides);
  }
  return cachedConfig;
};

/** Clears the cached configuration between tests. */
export const resetInstanceConfigForTests = (): void => {
  cachedConfig = null;
};
