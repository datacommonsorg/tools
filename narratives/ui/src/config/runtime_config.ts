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
 * @fileoverview Runtime settings: the chat availability and the hosts of the
 * Data Commons chart web components. {@link getRuntimeConfig} reads the JSON
 * that the agent server stamps into `<script id="runtime-config">`.
 * `runtime_config_dev.ts` imports this module, and `vite.config.ts` loads that
 * module in Node before the `@/` alias exists, so this module has no imports.
 */

/**
 * Message shown while chat is disabled when no other message is configured.
 * Matches `DEFAULT_UNAVAILABLE_MESSAGE` in the agent's `config_model.py`.
 */
export const DEFAULT_UNAVAILABLE_MESSAGE =
  'This Data Commons tool is temporarily unavailable due to high traffic.';

/**
 * URL of `datacommons.js` when none is configured. It matches
 * `DEFAULT_WEB_COMPONENT_URL` in the agent's `settings.py`.
 */
export const DEFAULT_WEB_COMPONENT_URL =
  'https://datacommons.org/datacommons.js';

/**
 * Origin the chart web components fetch their data from when none is
 * configured. It matches `DEFAULT_WEB_COMPONENT_API_ROOT` in the agent's
 * `settings.py`.
 */
export const DEFAULT_WEB_COMPONENT_API_ROOT = 'https://datacommons.org';

export interface RuntimeConfig {
  /** Whether the interactive Data Agent chat surface is active. */
  isChatEnabled: boolean;
  /** Message displayed when chat is disabled. */
  unavailableMessage: string;
  /** URL that `datacommons.js` is loaded from (`DC_WEB_COMPONENT_URL`). */
  webComponentUrl: string;
  /**
   * Origin the chart web components fetch their data from, passed as their
   * `apiroot` (`DC_WEB_COMPONENT_API_ROOT`).
   */
  webComponentApiRoot: string;
}

/** Settings used when the page carries no runtime configuration. */
export const DEFAULT_RUNTIME_CONFIG: Readonly<RuntimeConfig> = Object.freeze({
  isChatEnabled: true,
  unavailableMessage: DEFAULT_UNAVAILABLE_MESSAGE,
  webComponentUrl: DEFAULT_WEB_COMPONENT_URL,
  webComponentApiRoot: DEFAULT_WEB_COMPONENT_API_ROOT,
});

/**
 * Settings used when a runtime configuration is present but malformed. Chat
 * is disabled, and the charts keep their default hosts.
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
 * Returns the trimmed `unavailable_message`, or the default message when it
 * is absent, or with a warning when it is blank or not a string.
 */
const readUnavailableMessage = (value: unknown): string => {
  if (value === undefined) {
    return DEFAULT_UNAVAILABLE_MESSAGE;
  }
  if (typeof value === 'string' && value.trim() !== '') {
    return value.trim();
  }
  console.warn(
    `${RUNTIME_CONFIG_LOG_PREFIX} "unavailable_message" is blank or not a string; using the default message.`,
  );
  return DEFAULT_UNAVAILABLE_MESSAGE;
};

/**
 * Matches an absolute `http:` or `https:` URL, in any case, and captures its
 * authority: the text between `//` and the first `/`, `?`, or `#`.
 */
const HTTP_URL_AUTHORITY_PATTERN = /^https?:\/\/([^/?#]*)/i;

/**
 * Matches an authority the agent accepts for a chart host: a hostname of
 * dot-separated letter, digit, and hyphen labels with an optional numeric
 * port. It excludes user information, wildcards (`*`), percent-encoding,
 * IPv6 literals, non-ASCII hosts, and an empty port.
 */
const CHART_HOST_AUTHORITY_PATTERN =
  /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*(?::\d+)?$/i;

/** Matches the `?` or `#` that starts a query or a fragment. */
const QUERY_OR_FRAGMENT_PATTERN = /[?#]/;

/**
 * Matches characters that the agent rejects in a chart host because the
 * value enters a response header: whitespace, `;`, `,`, and quotes. Control
 * and non-ASCII characters are checked by code point in {@link isHeaderSafe}.
 */
const HEADER_UNSAFE_CHARACTER_PATTERN = /[\s;,'"]/;

/** Highest code point of the C0 control characters. */
const LAST_C0_CONTROL_CODE_POINT = 0x1f;
/** Code point of DEL, the control character after the printable ASCII. */
const DELETE_CODE_POINT = 0x7f;

/**
 * Returns whether `value` is printable ASCII without a character that cannot
 * enter a header.
 */
const isHeaderSafe = (value: string): boolean =>
  !HEADER_UNSAFE_CHARACTER_PATTERN.test(value) &&
  [...value].every((character) => {
    const codePoint = character.codePointAt(0) ?? 0;
    return (
      codePoint > LAST_C0_CONTROL_CODE_POINT && codePoint < DELETE_CODE_POINT
    );
  });

/**
 * Parses `value` as a chart host URL by the agent's rules, or returns
 * `null`. A valid value is an absolute http(s) URL on a hostname of letters,
 * digits, hyphens, and dots, with a valid port if it has one.
 */
const parseWebComponentUrl = (value: string): URL | null => {
  const authority = HTTP_URL_AUTHORITY_PATTERN.exec(value)?.[1];
  if (
    authority === undefined ||
    !CHART_HOST_AUTHORITY_PATTERN.test(authority) ||
    !isHeaderSafe(value)
  ) {
    return null;
  }
  try {
    return new URL(value);
  } catch {
    // A port above 65535 fails to parse.
    return null;
  }
};

/**
 * Returns `web_component_url` when it is an absolute http(s) URL. Otherwise
 * returns the default, with a warning when the value is invalid and without
 * one when the value is absent.
 */
const readWebComponentUrl = (value: unknown): string => {
  if (value === undefined) {
    return DEFAULT_WEB_COMPONENT_URL;
  }
  if (typeof value === 'string' && parseWebComponentUrl(value) !== null) {
    return value;
  }
  console.warn(
    `${RUNTIME_CONFIG_LOG_PREFIX} "web_component_url" is not an http(s) URL; using the default.`,
  );
  return DEFAULT_WEB_COMPONENT_URL;
};

/**
 * Returns `web_component_api_root` as an origin when it is an http(s) origin
 * with no path other than a trailing slash and no query or fragment.
 * Otherwise returns the default, with a warning when the value is invalid
 * and without one when the value is absent.
 */
const readWebComponentApiRoot = (value: unknown): string => {
  if (value === undefined) {
    return DEFAULT_WEB_COMPONENT_API_ROOT;
  }
  const url =
    typeof value === 'string' && !QUERY_OR_FRAGMENT_PATTERN.test(value)
      ? parseWebComponentUrl(value)
      : null;
  if (url !== null && url.pathname === '/') {
    return url.origin;
  }
  console.warn(
    `${RUNTIME_CONFIG_LOG_PREFIX} "web_component_api_root" is not an http(s) origin; using the default.`,
  );
  return DEFAULT_WEB_COMPONENT_API_ROOT;
};

/**
 * Parses the text of `#runtime-config`. Empty or absent text gives
 * {@link DEFAULT_RUNTIME_CONFIG}; text that is not a JSON object, or an
 * `enable_chat` that is not a boolean, disables chat. A missing or invalid
 * chart host takes its default and leaves chat unaffected.
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
    unavailableMessage: readUnavailableMessage(parsed.unavailable_message),
    webComponentUrl: readWebComponentUrl(parsed.web_component_url),
    webComponentApiRoot: readWebComponentApiRoot(parsed.web_component_api_root),
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
