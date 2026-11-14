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
 * JSON that the agent server stamps into `<script id="runtime-config">`.
 * `runtime_config_dev.ts` imports this module, and `vite.config.ts` loads that
 * module in Node before the `@/` alias exists, so this module has no imports.
 */

/**
 * Message shown while chat is disabled when no other message is configured.
 * Matches `DEFAULT_UNAVAILABLE_MESSAGE` in the agent's `config_model.py`.
 */
export const DEFAULT_UNAVAILABLE_MESSAGE =
  'This Data Commons tool is temporarily unavailable due to high traffic.';

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
