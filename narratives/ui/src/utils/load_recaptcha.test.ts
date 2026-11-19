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
 * @fileoverview Tests for ensureRecaptchaScript and resetRecaptchaLoaderForTests.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { GrecaptchaEnterprise } from '@/src/types/grecaptcha';
import {
  ensureRecaptchaScript,
  RECAPTCHA_READY_TIMEOUT_MS,
  resetRecaptchaLoaderForTests,
} from '@/src/utils/load_recaptcha';

const createMockEnterprise = (
  ready: GrecaptchaEnterprise['ready'] = (callback) => {
    callback();
  },
): GrecaptchaEnterprise => ({
  ready: vi.fn(ready),
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
  vi.useRealTimers();
  resetRecaptchaLoaderForTests();
  appendedScripts.length = 0;
  document.head.innerHTML = '';
  delete window.grecaptcha;
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

  it('rejects, cleans up, and allows retry when enterprise.ready throws on script load', async () => {
    // Test: Synchronous throw from `enterprise.ready` inside the `load` handler.
    // Situation: The script loads and defines a broken `grecaptcha.enterprise`
    //   whose `ready` throws synchronously, then a retry loads a healthy client.
    // Expectation: The first promise rejects with the thrown error, the failed
    //   `<script>` is removed, and the retry appends a new script and resolves.
    const brokenEnterprise = createMockEnterprise(() => {
      throw new Error('ready failed');
    });
    const firstAttempt = ensureRecaptchaScript('6Lc_session');
    const [firstScript] = appendedScripts;
    window.grecaptcha = { enterprise: brokenEnterprise };
    firstScript.dispatchEvent(new Event('load'));

    await expect(firstAttempt).rejects.toThrow('ready failed');
    expect(appendedScripts).toHaveLength(0);

    const healthyEnterprise = createMockEnterprise();
    delete window.grecaptcha;
    const retryAttempt = ensureRecaptchaScript('6Lc_session');
    const [retryScript] = appendedScripts;
    window.grecaptcha = { enterprise: healthyEnterprise };
    retryScript.dispatchEvent(new Event('load'));

    await expect(retryAttempt).resolves.toBe(healthyEnterprise);
  });

  it('clears the cached promise when pre-existing enterprise.ready throws', async () => {
    // Test: Synchronous throw from a pre-existing `window.grecaptcha.enterprise`.
    // Situation: `window.grecaptcha.enterprise.ready` throws on the first call
    //   and succeeds on the next call.
    // Expectation: The first call rejects and clears `loadPromise` so the next
    //   call re-invokes `ready` and resolves instead of returning a cached error.
    let shouldThrow = true;
    const enterprise = createMockEnterprise((callback) => {
      if (shouldThrow) {
        throw new Error('pre-existing ready failed');
      }
      callback();
    });
    window.grecaptcha = { enterprise };

    await expect(ensureRecaptchaScript('6Lc_session')).rejects.toThrow(
      'pre-existing ready failed',
    );

    shouldThrow = false;
    await expect(ensureRecaptchaScript('6Lc_session')).resolves.toBe(
      enterprise,
    );
    expect(enterprise.ready).toHaveBeenCalledTimes(2);
  });

  it('rejects and cleans up when enterprise.ready does not fire before the timeout', async () => {
    // Test: Hung `enterprise.ready` (for example, blocked `gstatic.com` script).
    // Situation: `enterprise.js` fires `load` and installs a `ready` stub that
    //   never invokes its callback before `RECAPTCHA_READY_TIMEOUT_MS`.
    // Expectation: The promise rejects with a timeout error, the `<script>` is
    //   removed, and `loadPromise` is cleared so callers are not wedged forever.
    vi.useFakeTimers();
    const hungEnterprise = createMockEnterprise(() => undefined);

    const firstAttempt = ensureRecaptchaScript('6Lc_session');
    const [firstScript] = appendedScripts;
    window.grecaptcha = { enterprise: hungEnterprise };
    firstScript.dispatchEvent(new Event('load'));

    const rejection = expect(firstAttempt).rejects.toThrow(
      /Timed out after \d+ms waiting for window\.grecaptcha\.enterprise\.ready/,
    );
    await vi.advanceTimersByTimeAsync(RECAPTCHA_READY_TIMEOUT_MS);
    await rejection;
    expect(appendedScripts).toHaveLength(0);

    delete window.grecaptcha;
    const healthyEnterprise = createMockEnterprise();
    const retryAttempt = ensureRecaptchaScript('6Lc_session');
    const [retryScript] = appendedScripts;
    window.grecaptcha = { enterprise: healthyEnterprise };
    retryScript.dispatchEvent(new Event('load'));

    await expect(retryAttempt).resolves.toBe(healthyEnterprise);
  });

  it('does not let a stale script error clear a newer in-flight loadPromise', async () => {
    // Test: Late event from a superseded `<script>` after reset and restart.
    // Situation: Load 1 starts, `resetRecaptchaLoaderForTests()` resets state,
    //   Load 2 starts, and then Load 1's detached `<script>` dispatches `error`.
    // Expectation: Load 2's cached `loadPromise` stays intact (deduplicating a
    //   concurrent caller) and resolves cleanly when Load 2's script loads.
    const firstAttempt = ensureRecaptchaScript('6Lc_first');
    const [staleScript] = appendedScripts;

    resetRecaptchaLoaderForTests();

    const secondAttempt = ensureRecaptchaScript('6Lc_second');
    const [activeScript] = appendedScripts;

    staleScript.dispatchEvent(new Event('error'));
    await expect(firstAttempt).rejects.toThrow(
      /Failed to load reCAPTCHA Enterprise SDK/,
    );

    // Load 2 must still be cached in `loadPromise`.
    expect(ensureRecaptchaScript('6Lc_second')).toBe(secondAttempt);
    expect(appendedScripts).toEqual([activeScript]);

    const enterprise = createMockEnterprise();
    window.grecaptcha = { enterprise };
    activeScript.dispatchEvent(new Event('load'));

    await expect(secondAttempt).resolves.toBe(enterprise);
  });
});
