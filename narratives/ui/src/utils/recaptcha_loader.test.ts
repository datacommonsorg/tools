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
 * @fileoverview Tests for ensureRecaptchaScript and resetRecaptchaLoaderForTest.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { GrecaptchaEnterprise } from '@/src/types/grecaptcha';
import {
  ensureRecaptchaScript,
  resetRecaptchaLoaderForTest,
} from '@/src/utils/recaptcha_loader';

const createMockEnterprise = (): GrecaptchaEnterprise => ({
  ready: vi.fn((callback: () => void) => {
    callback();
  }),
  render: vi.fn(() => 0),
  reset: vi.fn(),
});

const appendedScripts: HTMLScriptElement[] = [];

beforeEach(() => {
  appendedScripts.length = 0;
  // happy-dom rejects external `<script src>` elements synchronously inside
  // `appendChild` when JS file loading is disabled; intercepting `appendChild`
  // lets each test drive `load` and `error` events deterministically.
  vi.spyOn(document.head, 'appendChild').mockImplementation(
    <T extends Node>(node: T): T => {
      if (node instanceof HTMLScriptElement) {
        const script: HTMLScriptElement = node;
        appendedScripts.push(script);
        vi.spyOn(script, 'remove').mockImplementation(() => {
          const index = appendedScripts.indexOf(script);
          if (index !== -1) {
            appendedScripts.splice(index, 1);
          }
        });
      }
      return node;
    },
  );
});

afterEach(() => {
  resetRecaptchaLoaderForTest();
  appendedScripts.length = 0;
  document.head.innerHTML = '';
  delete window.grecaptcha;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('ensureRecaptchaScript', () => {
  it('loads the WAF session URL when a non-empty session site key is provided', async () => {
    // Test: Session-key script URL construction and resolution via `ready`.
    // Situation: `ensureRecaptchaScript` is called with a padded session site
    //   key containing URL-encoded characters, and the injected `<script>`
    //   populates `window.grecaptcha.enterprise` before firing `load`.
    // Expectation: One async `<script>` with `?render=<encoded>&waf=session` is
    //   appended to `document.head`, and the promise resolves with the
    //   `GrecaptchaEnterprise` instance once `ready` runs.
    const enterprise = createMockEnterprise();
    const pending = ensureRecaptchaScript('  6Lc+key/1  ');

    expect(appendedScripts).toHaveLength(1);
    expect(appendedScripts[0].async).toBe(true);
    expect(appendedScripts[0].src).toBe(
      'https://www.google.com/recaptcha/enterprise.js?render=6Lc%2Bkey%2F1&waf=session',
    );

    window.grecaptcha = { enterprise };
    appendedScripts[0].dispatchEvent(new Event('load'));

    await expect(pending).resolves.toBe(enterprise);
    expect(enterprise.ready).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['omitted', undefined],
    ['empty', ''],
    ['whitespace-only', '   \t\n '],
  ])('loads the explicit render URL when the session site key is %s', async (_, key) => {
    // Test: Explicit fallback URL when no session site key is configured.
    // Situation: `ensureRecaptchaScript` is called with `undefined`, `""`, or
    //   whitespace-only input.
    // Expectation: The `<script>` URL uses `?render=explicit` without
    //   `waf=session`, and resolves once `ready` fires.
    const enterprise = createMockEnterprise();
    const pending = ensureRecaptchaScript(key);

    expect(appendedScripts).toHaveLength(1);
    expect(appendedScripts[0].src).toBe(
      'https://www.google.com/recaptcha/enterprise.js?render=explicit',
    );

    window.grecaptcha = { enterprise };
    appendedScripts[0].dispatchEvent(new Event('load'));

    await expect(pending).resolves.toBe(enterprise);
  });

  it('deduplicates concurrent callers onto a single in-flight script load', async () => {
    // Test: Concurrent caller deduplication.
    // Situation: Two callers invoke `ensureRecaptchaScript` before the `<script>`
    //   element finishes loading, followed by a third caller after resolution.
    // Expectation: All callers receive the same promise and resolved enterprise
    //   client, and only one `<script>` element is appended to `document.head`.
    const enterprise = createMockEnterprise();
    const first = ensureRecaptchaScript('6Lc_session');
    const second = ensureRecaptchaScript();

    expect(second).toBe(first);
    expect(appendedScripts).toHaveLength(1);

    window.grecaptcha = { enterprise };
    appendedScripts[0].dispatchEvent(new Event('load'));

    const [firstResolved, secondResolved] = await Promise.all([first, second]);
    expect(firstResolved).toBe(enterprise);
    expect(secondResolved).toBe(enterprise);

    const third = ensureRecaptchaScript();
    expect(third).toBe(first);
    expect(appendedScripts).toHaveLength(1);
  });

  it('resolves directly via ready when window.grecaptcha.enterprise already exists', async () => {
    // Test: Pre-existing `window.grecaptcha.enterprise` on `window`.
    // Situation: `window.grecaptcha.enterprise` is already present before
    //   `ensureRecaptchaScript` is called.
    // Expectation: No `<script>` element is appended, `enterprise.ready` is
    //   invoked, and the promise resolves with the existing instance.
    const enterprise = createMockEnterprise();
    window.grecaptcha = { enterprise };

    const resolved = await ensureRecaptchaScript('6Lc_session');

    expect(resolved).toBe(enterprise);
    expect(enterprise.ready).toHaveBeenCalledTimes(1);
    expect(appendedScripts).toHaveLength(0);
  });

  it('clears the cached promise, removes the failed script, and retries after a script error', async () => {
    // Test: Recovery and retry after a network or content-blocker script error.
    // Situation: The first `<script>` dispatches `error` (for example, blocked
    //   by a browser extension), and a subsequent caller invokes
    //   `ensureRecaptchaScript` again.
    // Expectation: The first promise rejects with a descriptive Error, the
    //   failed `<script>` is removed from `document.head`, and the retry
    //   appends a fresh `<script>` that resolves cleanly on `load`.
    const firstAttempt = ensureRecaptchaScript('6Lc_session');
    const [failedScript] = appendedScripts;
    failedScript.dispatchEvent(new Event('error'));

    await expect(firstAttempt).rejects.toThrow(
      /Failed to load reCAPTCHA Enterprise SDK/,
    );
    expect(appendedScripts).toHaveLength(0);

    const enterprise = createMockEnterprise();
    const retryAttempt = ensureRecaptchaScript('6Lc_session');
    const [retryScript] = appendedScripts;
    expect(retryScript).toBeDefined();
    expect(retryScript).not.toBe(failedScript);

    window.grecaptcha = { enterprise };
    retryScript.dispatchEvent(new Event('load'));

    await expect(retryAttempt).resolves.toBe(enterprise);
  });

  it('rejects, cleans up, and allows retry when load fires without grecaptcha.enterprise', async () => {
    // Test: `load` event without `window.grecaptcha.enterprise` defined.
    // Situation: The `<script>` fires `load`, but `window.grecaptcha` is still
    //   undefined (for example, stubbed out by a privacy extension).
    // Expectation: The promise rejects with a descriptive Error, the `<script>`
    //   is removed from `document.head`, and a later call can retry cleanly.
    const firstAttempt = ensureRecaptchaScript();
    const [firstScript] = appendedScripts;
    firstScript.dispatchEvent(new Event('load'));

    await expect(firstAttempt).rejects.toThrow(
      /window\.grecaptcha\.enterprise is unavailable/,
    );
    expect(appendedScripts).toHaveLength(0);

    const enterprise = createMockEnterprise();
    const retryAttempt = ensureRecaptchaScript();
    const [retryScript] = appendedScripts;
    window.grecaptcha = { enterprise };
    retryScript.dispatchEvent(new Event('load'));

    await expect(retryAttempt).resolves.toBe(enterprise);
  });
});
