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
 * @fileoverview Runtime chat availability. {@link getRuntimeConfig} reads the
 * JSON that the agent server stamps into `<script id="runtime-config">`, and
 * {@link copyAgentRuntimeConfig} copies that JSON from the agent into the
 * page the Vite dev server serves. The module has no imports, so
 * `vite.config.ts` can load it in Node before the `@/` alias exists.
 */

/**
 * Message shown while chat is disabled when no other message is configured.
 * Matches `DEFAULT_UNAVAILABLE_MESSAGE` in the agent's `config_model.py`.
 */
export const DEFAULT_UNAVAILABLE_MESSAGE =
  'Due to high traffic, the application is currently unavailable.';

export interface RuntimeConfig {
  /** Whether the interactive Data Agent chat surface is active. */
  isChatEnabled: boolean;
  /** Message displayed when chat is disabled. */
  unavailableMessage: string;
}

/** Availability used when the page carries no runtime configuration. */
export const DEFAULT_RUNTIME_CONFIG: Readonly<RuntimeConfig> = Object.freeze({
  isChatEnabled: true,
  unavailableMessage: DEFAULT_UNAVAILABLE_MESSAGE,
});

/** Availability used when a runtime configuration is present but malformed. */
const DISABLED_RUNTIME_CONFIG: Readonly<RuntimeConfig> = Object.freeze({
  isChatEnabled: false,
  unavailableMessage: DEFAULT_UNAVAILABLE_MESSAGE,
});

const RUNTIME_CONFIG_ELEMENT_ID = 'runtime-config';
const LOG_PREFIX = '[runtime-config]';

/** Upper bound on the dev server's request for the agent's HTML shell. */
const AGENT_SHELL_TIMEOUT_MS = 5_000;

/** The empty element in `ui/index.html` that receives the runtime JSON. */
const RUNTIME_CONFIG_OPEN_TAG = `<script id="${RUNTIME_CONFIG_ELEMENT_ID}" type="application/json">`;
const SCRIPT_CLOSE_TAG = '</script>';
const RUNTIME_CONFIG_SLOT = `${RUNTIME_CONFIG_OPEN_TAG}${SCRIPT_CLOSE_TAG}`;

/**
 * Escapes for JSON embedded in a `<script>` element, matching
 * `_HTML_JSON_ESCAPES` in the agent's `spa.py`: `<`, `>`, and `&` cannot close
 * the element or start markup, and U+2028 and U+2029 cannot end a string if
 * the payload is evaluated as JavaScript.
 */
const HTML_JSON_ESCAPES: Readonly<Record<string, string>> = {
  '<': '\\u003c',
  '>': '\\u003e',
  '&': '\\u0026',
  '\u2028': '\\u2028',
  '\u2029': '\\u2029',
};
const HTML_JSON_ESCAPE_PATTERN = /[<>&\u2028\u2029]/g;

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
  console.warn(`${LOG_PREFIX} "enable_chat" is not a boolean; disabling chat.`);
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
    `${LOG_PREFIX} "unavailable_message" is blank or not a string; using the default message.`,
  );
  return DEFAULT_UNAVAILABLE_MESSAGE;
};

/**
 * Parses the text of `#runtime-config`. Empty or absent text gives
 * {@link DEFAULT_RUNTIME_CONFIG}; text that is not a JSON object, or an
 * `enable_chat` that is not a boolean, disables chat.
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
      `${LOG_PREFIX} malformed JSON in #${RUNTIME_CONFIG_ELEMENT_ID}; disabling chat.`,
      error,
    );
    return DISABLED_RUNTIME_CONFIG;
  }
  if (!isRecord(parsed)) {
    console.warn(
      `${LOG_PREFIX} #${RUNTIME_CONFIG_ELEMENT_ID} is not a JSON object; disabling chat.`,
    );
    return DISABLED_RUNTIME_CONFIG;
  }
  return Object.freeze({
    isChatEnabled: readEnabled(parsed.enable_chat),
    unavailableMessage: readUnavailableMessage(parsed.unavailable_message),
  });
};

let cachedConfig: Readonly<RuntimeConfig> | null = null;

/**
 * Returns the runtime chat availability, reading and caching
 * `#runtime-config` on the first call. An absent or empty element gives
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

/**
 * Returns the trimmed text of the first `#runtime-config` element in `html`,
 * or `undefined` when the element is absent, unterminated, or empty.
 */
export const extractRuntimeConfigText = (html: string): string | undefined => {
  const start = html.indexOf(RUNTIME_CONFIG_OPEN_TAG);
  if (start === -1) {
    return undefined;
  }
  const textStart = start + RUNTIME_CONFIG_OPEN_TAG.length;
  const end = html.indexOf(SCRIPT_CLOSE_TAG, textStart);
  if (end === -1) {
    return undefined;
  }
  const text = html.slice(textStart, end).trim();
  return text === '' ? undefined : text;
};

/**
 * Serializes `config` to the wire JSON that the agent stamps,
 * `{"enable_chat":<bool>,"unavailable_message":"<str>"}`, escaped for a
 * `<script>` element.
 */
const serializeRuntimeConfig = (config: Readonly<RuntimeConfig>): string =>
  JSON.stringify({
    enable_chat: config.isChatEnabled,
    unavailable_message: config.unavailableMessage,
  }).replace(
    HTML_JSON_ESCAPE_PATTERN,
    (character) => HTML_JSON_ESCAPES[character],
  );

/**
 * Returns `html` with `config` stamped into the first empty
 * `#runtime-config` element, as the agent's `spa.py` does. HTML without the
 * empty element is returned unchanged.
 */
export const stampRuntimeConfigHtml = (
  html: string,
  config: Readonly<RuntimeConfig>,
): string => {
  if (!html.includes(RUNTIME_CONFIG_SLOT)) {
    return html;
  }
  // A replacer function keeps `$` sequences in the message literal.
  return html.replace(
    RUNTIME_CONFIG_SLOT,
    () =>
      `${RUNTIME_CONFIG_OPEN_TAG}${serializeRuntimeConfig(config)}${SCRIPT_CLOSE_TAG}`,
  );
};

/**
 * Fetches the HTML shell at `shellUrl` and returns the text of its stamped
 * `#runtime-config`, or `undefined` with one warning when the request fails,
 * times out, answers a non-2xx status, or the shell has no stamped element.
 */
const readAgentRuntimeConfigText = async (
  shellUrl: string,
): Promise<string | undefined> => {
  let failure: string;
  try {
    const response = await fetch(shellUrl, {
      signal: AbortSignal.timeout(AGENT_SHELL_TIMEOUT_MS),
    });
    if (response.ok) {
      const text = extractRuntimeConfigText(await response.text());
      if (text !== undefined) {
        return text;
      }
      failure = `the page has no stamped #${RUNTIME_CONFIG_ELEMENT_ID}`;
    } else {
      failure = `the agent answered HTTP ${response.status}`;
    }
  } catch (error) {
    failure = `the request failed (${String(error)})`;
  }
  console.warn(
    `${LOG_PREFIX} cannot read chat availability from ${shellUrl}: ${failure}. ` +
      'Start the agent at AGENT_URL; a local agent serves index.html only ' +
      `after \`pnpm build\` has run once. Leaving #${RUNTIME_CONFIG_ELEMENT_ID} empty.`,
  );
  return undefined;
};

/**
 * Returns `html` with the chat availability of the agent whose HTML shell is
 * at `shellUrl` stamped into its empty `#runtime-config`, so the Vite dev
 * server shows the same availability as the agent. The copied text is parsed
 * with {@link parseRuntimeConfigText} and re-serialized, so a malformed
 * payload disables chat and escaping is always applied here. When the shell
 * cannot be read, `html` is returned unchanged with one warning.
 */
export const copyAgentRuntimeConfig = async (
  html: string,
  shellUrl: string,
): Promise<string> => {
  const text = await readAgentRuntimeConfigText(shellUrl);
  if (text === undefined) {
    return html;
  }
  return stampRuntimeConfigHtml(html, parseRuntimeConfigText(text));
};
