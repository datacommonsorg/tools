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
 * @fileoverview Vite dev-server helpers that copy the agent's chat
 * availability into the page the dev server serves. Only `vite.config.ts`
 * and this module's tests import it. `vite.config.ts` loads it in Node before
 * the `@/` alias exists, so its imports are relative (`biome.json` exempts
 * this file from the relative-import rule), and the modules it imports,
 * `runtime_config.ts` and `base_url.ts`, have no `@/` imports.
 */

import { trimTrailingSlashes } from './base_url';
import {
  parseRuntimeConfigText,
  RUNTIME_CONFIG_ELEMENT_ID,
  RUNTIME_CONFIG_LOG_PREFIX,
  type RuntimeConfig,
} from './runtime_config';

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

/** Hints appended to the warning when the agent shell cannot be read. */
const START_AGENT_HINT = 'Start the agent at AGENT_URL.';
const BUILD_AGENT_HINT =
  'A local agent serves index.html only after `pnpm build` has run once.';
const REDIRECT_HINT =
  'The dev server does not follow redirects, so it cannot read an agent ' +
  'behind a sign-in such as IAP.';

/** Why the agent shell could not be read, and what to do about it. */
interface ShellReadFailure {
  reason: string;
  hint: string;
}

/**
 * Returns the URL of the agent's HTML shell: the `AGENT_URL` origin and path
 * with one trailing slash, without its query or fragment. The Vite proxy
 * forwards `/agent/*` to the same path, so a subpath in `AGENT_URL` (for
 * example `https://host/narratives`) is kept.
 */
export const resolveAgentShellUrl = (agentUrl: string): string => {
  const url = new URL(agentUrl);
  return `${url.origin}${trimTrailingSlashes(url.pathname)}/`;
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
 * Describes a redirect response by its status and the origin of its
 * `Location` header.
 */
const describeRedirect = (response: Response, shellUrl: string): string => {
  const location = response.headers.get('location');
  if (location === null) {
    return `the agent answered HTTP ${response.status} without a Location header`;
  }
  let target: string;
  try {
    target = new URL(location, shellUrl).origin;
  } catch {
    target = 'an invalid location';
  }
  return `the agent answered HTTP ${response.status} with a redirect to ${target}`;
};

/**
 * Fetches the HTML shell at `shellUrl` without following redirects, and
 * returns the text of its stamped `#runtime-config` or a
 * {@link ShellReadFailure}.
 */
const fetchAgentRuntimeConfigText = async (
  shellUrl: string,
): Promise<string | ShellReadFailure> => {
  let response: Response;
  try {
    response = await fetch(shellUrl, {
      redirect: 'manual',
      signal: AbortSignal.timeout(AGENT_SHELL_TIMEOUT_MS),
    });
  } catch (error) {
    return {
      reason: `the request failed (${String(error)})`,
      hint: START_AGENT_HINT,
    };
  }
  if (response.status >= 300 && response.status < 400) {
    return {
      reason: describeRedirect(response, shellUrl),
      hint: REDIRECT_HINT,
    };
  }
  if (!response.ok) {
    return {
      reason: `the agent answered HTTP ${response.status}`,
      hint: response.status === 404 ? BUILD_AGENT_HINT : START_AGENT_HINT,
    };
  }
  const text = extractRuntimeConfigText(await response.text());
  if (text === undefined) {
    return {
      reason: `the page has no stamped #${RUNTIME_CONFIG_ELEMENT_ID}`,
      hint: BUILD_AGENT_HINT,
    };
  }
  return text;
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
  const result = await fetchAgentRuntimeConfigText(shellUrl);
  if (typeof result !== 'string') {
    console.warn(
      `${RUNTIME_CONFIG_LOG_PREFIX} cannot read chat availability from ` +
        `${shellUrl}: ${result.reason}. ${result.hint} ` +
        `Leaving #${RUNTIME_CONFIG_ELEMENT_ID} empty.`,
    );
    return html;
  }
  return stampRuntimeConfigHtml(html, parseRuntimeConfigText(result));
};
