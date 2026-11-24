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
 * @fileoverview Runtime settings: chat availability, Data Commons chart web
 * component hosts, and optional reCAPTCHA Enterprise site keys.
 * {@link getRuntimeConfig} reads the JSON that the agent server stamps into
 * `<script id="runtime-config">`. `runtime_config_dev.ts` imports this module,
 * and `vite.config.ts` loads that module in Node before the `@/` alias exists,
 * so this module has no imports.
 */

/**
 * Heading of the unavailable note while chat is disabled when no other title is
 * configured. Matches `DEFAULT_UNAVAILABLE_TITLE` in the agent's
 * `config_model.py`.
 */
export const DEFAULT_UNAVAILABLE_TITLE = 'High demand right now';

/**
 * Message shown while chat is disabled when no other message is configured.
 * Matches `DEFAULT_UNAVAILABLE_MESSAGE` in the agent's `config_model.py`.
 */
export const DEFAULT_UNAVAILABLE_MESSAGE =
  'Due to high traffic, this feature is temporarily paused. Capacity is ' +
  'being scaled to restore service as quickly as possible. Please try again ' +
  'later, or explore other [tools in Data Commons](https://datacommons.org).';

export interface RuntimeConfig {
  /** Whether the interactive Data Agent chat surface is active. */
  isChatEnabled: boolean;
  /** Heading displayed on the unavailable note when chat is disabled. */
  unavailableTitle: string;
  /** Message displayed when chat is disabled. */
  unavailableMessage: string;
  /**
   * URL that `datacommons.js` is loaded from (`DC_WEB_COMPONENT_URL`), or
   * `""` when unconfigured or invalid.
   */
  webComponentUrl: string;
  /**
   * Origin the chart web components fetch their data from, passed as their
   * `apiroot` (`DC_WEB_COMPONENT_API_ROOT`), or `""` when unconfigured or
   * invalid.
   */
  webComponentApiRoot: string;
  /** Optional reCAPTCHA Enterprise session-token site key (`waf=session`). */
  recaptchaSessionSiteKey: string;
  /** Optional reCAPTCHA Enterprise checkbox challenge site key. */
  recaptchaCheckboxSiteKey: string;
}

/**
 * Settings used when the page carries no runtime configuration. Chart hosts
 * and reCAPTCHA site keys remain empty until injected by the agent so no
 * script or chart data loads from an unconfigured origin.
 */
export const DEFAULT_RUNTIME_CONFIG: Readonly<RuntimeConfig> = Object.freeze({
  isChatEnabled: true,
  unavailableTitle: DEFAULT_UNAVAILABLE_TITLE,
  unavailableMessage: DEFAULT_UNAVAILABLE_MESSAGE,
  webComponentUrl: '',
  webComponentApiRoot: '',
  recaptchaSessionSiteKey: '',
  recaptchaCheckboxSiteKey: '',
});

/**
 * Settings used when a runtime configuration is present but malformed. Chat
 * is disabled and chart hosts and reCAPTCHA keys remain empty.
 */
const DISABLED_RUNTIME_CONFIG: Readonly<RuntimeConfig> = Object.freeze({
  ...DEFAULT_RUNTIME_CONFIG,
  isChatEnabled: false,
});

/** The id of the `<script>` element that carries the runtime JSON. */
export const RUNTIME_CONFIG_ELEMENT_ID = 'runtime-config';
/** Prefix for every console message about the runtime configuration. */
export const RUNTIME_CONFIG_LOG_PREFIX = '[runtime-config]';

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

/**
 * Returns `enable_chat`: `true` when absent, the value when it is a boolean,
 * and `false` with a warning otherwise, so a malformed off switch never
 * leaves chat on.
 */
const readEnabled = (value: unknown): boolean => {
  if (value === undefined) {
    return true;
  }
  if (typeof value === 'boolean') {
    return value;
  }
  console.warn(
    `${RUNTIME_CONFIG_LOG_PREFIX} "enable_chat" is not a boolean; disabling chat.`,
  );
  return false;
};

/**
 * Returns the trimmed string for `key`, or `fallback` when absent, or with a
 * warning when blank or not a string.
 */
const readNonBlankString = (
  key: string,
  value: unknown,
  fallback: string,
  label: string,
): string => {
  if (value === undefined) {
    return fallback;
  }
  if (typeof value === 'string' && value.trim() !== '') {
    return value.trim();
  }
  console.warn(
    `${RUNTIME_CONFIG_LOG_PREFIX} "${key}" is blank or not a string; using the default ${label}.`,
  );
  return fallback;
};

const HTTP_SCHEME_PREFIX = /^https?:\/\//i;
const WHITESPACE_PATTERN = /\s/;
const QUERY_OR_FRAGMENT_PATTERN = /[?#]/;
const MAX_ASCII_C0_CODE = 0x1f;
const ASCII_DEL_CODE = 0x7f;

const hasAsciiControlChar = (value: string): boolean => {
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    if (code <= MAX_ASCII_C0_CODE || code === ASCII_DEL_CODE) {
      return true;
    }
  }
  return false;
};

/**
 * Parses `value` as an absolute `http:` or `https:` URL without credentials,
 * whitespace, backslashes, or ASCII control characters, or returns `null`.
 */
const parseWebComponentUrl = (value: string): URL | null => {
  if (
    !HTTP_SCHEME_PREFIX.test(value) ||
    value.includes('\\') ||
    WHITESPACE_PATTERN.test(value) ||
    hasAsciiControlChar(value)
  ) {
    return null;
  }
  try {
    const parsed = new URL(value);
    if (
      (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') ||
      parsed.username !== '' ||
      parsed.password !== ''
    ) {
      return null;
    }
    return parsed;
  } catch {
    // new URL throws TypeError on unparseable URLs or out-of-range ports.
    return null;
  }
};

/**
 * Returns `web_component_url` when it is an absolute http(s) URL without
 * credentials. Otherwise returns `""`, logging a warning when a value was
 * provided.
 */
const readWebComponentUrl = (value: unknown): string => {
  if (value === undefined) {
    return '';
  }
  if (typeof value === 'string' && parseWebComponentUrl(value) !== null) {
    return value;
  }
  console.warn(
    `${RUNTIME_CONFIG_LOG_PREFIX} "web_component_url" is not a valid http(s) URL; disabling chart script loading.`,
  );
  return '';
};

/**
 * Returns `web_component_api_root` normalized to its origin when it is an
 * http(s) origin without credentials, path, query, or fragment. Otherwise
 * returns `""`, logging a warning when a value was provided.
 */
const readWebComponentApiRoot = (value: unknown): string => {
  if (value === undefined) {
    return '';
  }
  const url =
    typeof value === 'string' && !QUERY_OR_FRAGMENT_PATTERN.test(value)
      ? parseWebComponentUrl(value)
      : null;
  if (url !== null && url.pathname === '/') {
    return url.origin;
  }
  console.warn(
    `${RUNTIME_CONFIG_LOG_PREFIX} "web_component_api_root" is not a valid http(s) origin; omitting chart apiroot.`,
  );
  return '';
};

/**
 * Returns the trimmed optional reCAPTCHA site key, or `""` when absent,
 * `null`, or non-string (logging a warning on non-string values without
 * disabling chat).
 */
const readOptionalSiteKey = (key: string, value: unknown): string => {
  if (value === undefined || value === null) {
    return '';
  }
  if (typeof value === 'string') {
    return value.trim();
  }
  console.warn(
    `${RUNTIME_CONFIG_LOG_PREFIX} "${key}" is not a string; ignoring.`,
  );
  return '';
};

/**
 * Parses the text of `#runtime-config`. Empty or absent text gives
 * {@link DEFAULT_RUNTIME_CONFIG}; text that is not a JSON object, or an
 * `enable_chat` that is not a boolean, disables chat. Missing or invalid
 * chart hosts and reCAPTCHA site keys resolve to `""` without affecting chat.
 */
export const parseRuntimeConfigText = (
  text: string | undefined,
): Readonly<RuntimeConfig> => {
  if (!text) {
    return DEFAULT_RUNTIME_CONFIG;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    console.warn(
      `${RUNTIME_CONFIG_LOG_PREFIX} malformed JSON in #${RUNTIME_CONFIG_ELEMENT_ID}; disabling chat.`,
      error,
    );
    return DISABLED_RUNTIME_CONFIG;
  }
  if (!isRecord(parsed)) {
    console.warn(
      `${RUNTIME_CONFIG_LOG_PREFIX} #${RUNTIME_CONFIG_ELEMENT_ID} is not a JSON object; disabling chat.`,
    );
    return DISABLED_RUNTIME_CONFIG;
  }
  return Object.freeze({
    isChatEnabled: readEnabled(parsed.enable_chat),
    unavailableTitle: readNonBlankString(
      'unavailable_title',
      parsed.unavailable_title,
      DEFAULT_UNAVAILABLE_TITLE,
      'title',
    ),
    unavailableMessage: readNonBlankString(
      'unavailable_message',
      parsed.unavailable_message,
      DEFAULT_UNAVAILABLE_MESSAGE,
      'message',
    ),
    webComponentUrl: readWebComponentUrl(parsed.web_component_url),
    webComponentApiRoot: readWebComponentApiRoot(parsed.web_component_api_root),
    recaptchaSessionSiteKey: readOptionalSiteKey(
      'recaptcha_session_site_key',
      parsed.recaptcha_session_site_key,
    ),
    recaptchaCheckboxSiteKey: readOptionalSiteKey(
      'recaptcha_checkbox_site_key',
      parsed.recaptcha_checkbox_site_key,
    ),
  });
};

let cachedConfig: Readonly<RuntimeConfig> | null = null;

/**
 * Returns the runtime settings, reading and caching `#runtime-config` on the
 * first call. An absent or empty element gives
 * {@link DEFAULT_RUNTIME_CONFIG}; a malformed payload, or an `enable_chat`
 * that is not a boolean, disables chat.
 */
export const getRuntimeConfig = (): Readonly<RuntimeConfig> => {
  if (cachedConfig === null) {
    cachedConfig = parseRuntimeConfigText(
      document.getElementById(RUNTIME_CONFIG_ELEMENT_ID)?.textContent?.trim(),
    );
  }
  return cachedConfig;
};

/** Clears the cached configuration between tests. */
export const resetRuntimeConfigForTests = (): void => {
  cachedConfig = null;
};
