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

import type { GrecaptchaEnterprise } from '@/src/types/grecaptcha';

const RECAPTCHA_ENTERPRISE_SCRIPT_URL =
  'https://www.google.com/recaptcha/enterprise.js';

let loadPromise: Promise<GrecaptchaEnterprise> | null = null;
let injectedScript: HTMLScriptElement | null = null;

const buildRecaptchaScriptUrl = (sessionSiteKey?: string): string => {
  const trimmedKey = sessionSiteKey?.trim() ?? '';
  if (trimmedKey !== '') {
    return `${RECAPTCHA_ENTERPRISE_SCRIPT_URL}?render=${encodeURIComponent(trimmedKey)}&waf=session`;
  }
  return `${RECAPTCHA_ENTERPRISE_SCRIPT_URL}?render=explicit`;
};

const waitForEnterpriseReady = (
  enterprise: GrecaptchaEnterprise,
): Promise<GrecaptchaEnterprise> =>
  new Promise<GrecaptchaEnterprise>((resolve) => {
    enterprise.ready(() => {
      resolve(enterprise);
    });
  });

/**
 * Loads `https://www.google.com/recaptcha/enterprise.js` at most once and
 * resolves with `window.grecaptcha.enterprise` after `ready(...)` fires.
 *
 * When `sessionSiteKey` is non-empty after trimming, loads the SDK with
 * `?render=<key>&waf=session` so the browser mints and refreshes the
 * `recaptcha-ca-t` session cookie. Otherwise loads `?render=explicit` for
 * on-demand widget rendering. If script loading fails or `grecaptcha.enterprise`
 * is missing after `load`, clears the cached promise and removes the failed
 * `<script>` element so subsequent callers can retry.
 */
export const ensureRecaptchaScript = (
  sessionSiteKey?: string,
): Promise<GrecaptchaEnterprise> => {
  if (loadPromise !== null) {
    return loadPromise;
  }

  const existingEnterprise = window.grecaptcha?.enterprise;
  if (existingEnterprise && typeof existingEnterprise.ready === 'function') {
    loadPromise = waitForEnterpriseReady(existingEnterprise);
    return loadPromise;
  }

  const scriptUrl = buildRecaptchaScriptUrl(sessionSiteKey);
  loadPromise = new Promise<GrecaptchaEnterprise>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = scriptUrl;
    script.async = true;
    injectedScript = script;

    script.addEventListener(
      'load',
      () => {
        const enterprise = window.grecaptcha?.enterprise;
        if (!enterprise || typeof enterprise.ready !== 'function') {
          loadPromise = null;
          if (injectedScript === script) {
            injectedScript = null;
          }
          script.remove();
          reject(
            new Error(
              `reCAPTCHA Enterprise SDK loaded from ${scriptUrl}, but window.grecaptcha.enterprise is unavailable.`,
            ),
          );
          return;
        }
        enterprise.ready(() => {
          resolve(enterprise);
        });
      },
      { once: true },
    );

    script.addEventListener(
      'error',
      () => {
        loadPromise = null;
        if (injectedScript === script) {
          injectedScript = null;
        }
        script.remove();
        reject(
          new Error(
            `Failed to load reCAPTCHA Enterprise SDK from ${scriptUrl}.`,
          ),
        );
      },
      { once: true },
    );

    document.head.appendChild(script);
  });

  return loadPromise;
};

/** Resets cached loader state and removes any injected `<script>` for tests. */
export const resetRecaptchaLoaderForTest = (): void => {
  loadPromise = null;
  injectedScript?.remove();
  injectedScript = null;
};
