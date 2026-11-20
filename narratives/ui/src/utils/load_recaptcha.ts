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
 * @fileoverview Idempotent loader for the Google Cloud reCAPTCHA Enterprise
 * browser SDK (`enterprise.js`), supporting both WAF session-token mode and
 * explicit widget rendering.
 */

import { getRuntimeConfig } from '@/src/config/runtime_config';
import type { GrecaptchaEnterprise } from '@/src/types/grecaptcha';

const RECAPTCHA_ENTERPRISE_SCRIPT_URL =
  'https://www.google.com/recaptcha/enterprise.js';

/** Upper bound on waiting for `grecaptcha.enterprise.ready(...)` to fire. */
export const RECAPTCHA_READY_TIMEOUT_MS = 10_000;

let loadPromise: Promise<GrecaptchaEnterprise> | null = null;
let injectedScript: HTMLScriptElement | null = null;
let loadGeneration = 0;

const getEnterpriseClient = (): GrecaptchaEnterprise | null => {
  const enterprise = window.grecaptcha?.enterprise;
  return enterprise && typeof enterprise.ready === 'function'
    ? enterprise
    : null;
};

const buildRecaptchaScriptUrl = (sessionSiteKey: string): string => {
  const trimmedKey = sessionSiteKey.trim();
  if (trimmedKey !== '') {
    return `${RECAPTCHA_ENTERPRISE_SCRIPT_URL}?render=${encodeURIComponent(trimmedKey)}&waf=session`;
  }
  return `${RECAPTCHA_ENTERPRISE_SCRIPT_URL}?render=explicit`;
};

const waitForEnterpriseReady = (
  enterprise: GrecaptchaEnterprise,
  timeoutMs = RECAPTCHA_READY_TIMEOUT_MS,
): Promise<GrecaptchaEnterprise> =>
  new Promise<GrecaptchaEnterprise>((resolve, reject) => {
    let settled = false;
    const settle = (outcome: () => void): void => {
      if (settled) {
        return;
      }
      settled = true;
      window.clearTimeout(timerId);
      outcome();
    };

    const timerId = window.setTimeout(() => {
      settle(() =>
        reject(
          new Error(
            `Timed out after ${timeoutMs}ms waiting for window.grecaptcha.enterprise.ready.`,
          ),
        ),
      );
    }, timeoutMs);

    try {
      enterprise.ready(() => settle(() => resolve(enterprise)));
    } catch (error) {
      settle(() => reject(error));
    }
  });

const loadEnterpriseScript = (
  script: HTMLScriptElement,
  scriptUrl: string,
): Promise<GrecaptchaEnterprise> =>
  new Promise<GrecaptchaEnterprise>((resolve, reject) => {
    script.addEventListener(
      'load',
      () => {
        const enterprise = getEnterpriseClient();
        if (enterprise === null) {
          reject(
            new Error(
              `reCAPTCHA Enterprise SDK loaded from ${scriptUrl}, but window.grecaptcha.enterprise is unavailable.`,
            ),
          );
          return;
        }
        void waitForEnterpriseReady(enterprise).then(resolve, reject);
      },
      { once: true },
    );

    script.addEventListener(
      'error',
      () => {
        reject(
          new Error(
            `Failed to load reCAPTCHA Enterprise SDK from ${scriptUrl}.`,
          ),
        );
      },
      { once: true },
    );
  });

const clearCachedLoad = (
  generation: number,
  script: HTMLScriptElement | null,
): void => {
  if (loadGeneration === generation) {
    loadPromise = null;
    if (script !== null && injectedScript === script) {
      injectedScript = null;
    }
  }
  script?.remove();
};

/**
 * Loads `https://www.google.com/recaptcha/enterprise.js` at most once and
 * resolves with `window.grecaptcha.enterprise` after `ready(...)` fires.
 *
 * When `sessionSiteKey` is omitted or blank, falls back to
 * `getRuntimeConfig().recaptchaSessionSiteKey` so every caller resolves the
 * configured script mode consistently, including when retrying after an
 * earlier load failure. When the resolved key is non-empty, loads
 * `?render=<key>&waf=session` so the browser mints and refreshes the
 * `recaptcha-ca-t` session cookie; otherwise loads `?render=explicit` for
 * on-demand widget rendering. The first in-flight or resolved call selects the
 * script mode; subsequent calls reuse its cached promise.
 *
 * If script loading fails, `grecaptcha.enterprise` is missing after `load`,
 * `ready(...)` throws, or `ready(...)` does not fire before
 * {@link RECAPTCHA_READY_TIMEOUT_MS}, clears the cached promise and removes
 * the failed `<script>` element so subsequent callers can retry.
 */
export const ensureRecaptchaScript = (
  sessionSiteKey?: string,
): Promise<GrecaptchaEnterprise> => {
  if (loadPromise !== null) {
    return loadPromise;
  }

  loadGeneration += 1;
  const generation = loadGeneration;
  const existingEnterprise = getEnterpriseClient();

  let script: HTMLScriptElement | null = null;
  let rawLoad: Promise<GrecaptchaEnterprise>;

  if (existingEnterprise !== null) {
    rawLoad = waitForEnterpriseReady(existingEnterprise);
  } else {
    const resolvedSessionSiteKey =
      sessionSiteKey?.trim() || getRuntimeConfig().recaptchaSessionSiteKey;
    const scriptUrl = buildRecaptchaScriptUrl(resolvedSessionSiteKey);
    script = document.createElement('script');
    script.src = scriptUrl;
    script.async = true;
    injectedScript = script;
    rawLoad = loadEnterpriseScript(script, scriptUrl);
  }

  const pending = rawLoad.catch((error: unknown) => {
    clearCachedLoad(generation, script);
    throw error;
  });

  loadPromise = pending;
  // Append after assigning `loadPromise` so a synchronous `error` event during
  // insertion still clears the cached promise cleanly.
  if (script !== null) {
    document.head.appendChild(script);
  }
  return pending;
};

/** Resets cached loader state and removes any injected `<script>` for tests. */
export const resetRecaptchaLoaderForTests = (): void => {
  loadGeneration += 1;
  loadPromise = null;
  injectedScript?.remove();
  injectedScript = null;
};
