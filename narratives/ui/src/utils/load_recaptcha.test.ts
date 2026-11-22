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
import { resetRuntimeConfigForTests } from '@/src/config/runtime_config';
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

const writeRuntimeConfigSlot = (payload: Record<string, unknown>): void => {
  document.getElementById('runtime-config')?.remove();
  const slot = document.createElement('script');
  slot.id = 'runtime-config';
  slot.type = 'application/json';
  slot.textContent = JSON.stringify(payload);
  // Mount under `document.body` so the `document.head.appendChild` spy only
  // intercepts scripts injected by `ensureRecaptchaScript`.
  document.body.appendChild(slot);
  resetRuntimeConfigForTests();
};

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
  resetRuntimeConfigForTests();
  appendedScripts.length = 0;
  document.head.innerHTML = '';
  document.getElementById('runtime-config')?.remove();
  delete window.grecaptcha;
  vi.restoreAllMocks();
});

describe('ensureRecaptchaScript', () => {
  it('loads the WAF session URL when #runtime-config sets a session site key', async () => {
    // Test: Session-key script URL and resolution via `ready`.
    // Situation: `#runtime-config` sets a padded key needing URL encoding.
    // Expectation: Appends async `?render=<encoded>&waf=session` and resolves.
    writeRuntimeConfigSlot({
      recaptcha_session_site_key: '  6Lc+key/1  ',
    });
    const enterprise = createMockEnterprise();
    const pending = ensureRecaptchaScript();

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

  it.each<[string, Record<string, unknown> | null]>([
    ['absent', null],
    ['empty', { recaptcha_session_site_key: '' }],
    ['whitespace-only', { recaptcha_session_site_key: '   \t\n ' }],
  ])('loads the explicit render URL when the runtime session site key is %s', async (_, payload) => {
    // Test: Explicit fallback URL without a configured session site key.
    // Situation: `#runtime-config` is absent or sets an empty/whitespace key.
    // Expectation: Uses `?render=explicit` (no `waf=session`) and resolves.
    if (payload !== null) {
      writeRuntimeConfigSlot(payload);
    }
    const enterprise = createMockEnterprise();
    const pending = ensureRecaptchaScript();

    expect(appendedScripts).toHaveLength(1);
    expect(appendedScripts[0].src).toBe(
      'https://www.google.com/recaptcha/enterprise.js?render=explicit',
    );

    window.grecaptcha = { enterprise };
    appendedScripts[0].dispatchEvent(new Event('load'));

    await expect(pending).resolves.toBe(enterprise);
  });

  it('deduplicates concurrent callers onto a single in-flight script load', async () => {
    // Test: Concurrent and post-load caller deduplication.
    // Situation: Two calls overlap before `load`; a third runs after resolution.
    // Expectation: All callers share one promise and one `<script>` tag.
    writeRuntimeConfigSlot({
      recaptcha_session_site_key: '6Lc_session',
    });
    const enterprise = createMockEnterprise();
    const first = ensureRecaptchaScript();
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
    // Test: Pre-existing `window.grecaptcha.enterprise`.
    // Situation: `window.grecaptcha.enterprise` is set before calling the loader.
    // Expectation: Appends no `<script>`, invokes `ready`, and resolves.
    const enterprise = createMockEnterprise();
    window.grecaptcha = { enterprise };

    const resolved = await ensureRecaptchaScript();

    expect(resolved).toBe(enterprise);
    expect(enterprise.ready).toHaveBeenCalledTimes(1);
    expect(appendedScripts).toHaveLength(0);
  });

  it('clears the cached promise, removes the failed script, and retries in WAF session mode after a script error', async () => {
    // Test: Retry and mode consistency after a script load error.
    // Situation: `#runtime-config` sets a session key; the first `<script>`
    //   fires `error`, then a subsequent caller retries.
    // Expectation: Rejects, removes the failed tag, and retries with
    //   `?render=<key>&waf=session` before resolving.
    writeRuntimeConfigSlot({
      recaptcha_session_site_key: '6Lc_session',
    });
    const firstAttempt = ensureRecaptchaScript();
    const [failedScript] = appendedScripts;
    failedScript.dispatchEvent(new Event('error'));

    await expect(firstAttempt).rejects.toThrow(
      /Failed to load reCAPTCHA Enterprise SDK/,
    );
    expect(appendedScripts).toHaveLength(0);

    const enterprise = createMockEnterprise();
    const retryAttempt = ensureRecaptchaScript();
    expect(appendedScripts).toHaveLength(1);
    const [retryScript] = appendedScripts;
    expect(retryScript).not.toBe(failedScript);
    expect(retryScript.src).toBe(
      'https://www.google.com/recaptcha/enterprise.js?render=6Lc_session&waf=session',
    );

    window.grecaptcha = { enterprise };
    retryScript.dispatchEvent(new Event('load'));

    await expect(retryAttempt).resolves.toBe(enterprise);
  });

  it('rejects, cleans up, and allows retry when load fires without grecaptcha.enterprise', async () => {
    // Test: `load` fires without defining `window.grecaptcha.enterprise`.
    // Situation: `<script>` fires `load` while `window.grecaptcha` is unset.
    // Expectation: Rejects, removes the tag, and allows a clean retry.
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
    // Test: Synchronous throw from `enterprise.ready` on `load`.
    // Situation: First load defines a throwing `ready`; a retry loads cleanly.
    // Expectation: Rejects, removes the tag, and resolves on retry.
    const brokenEnterprise = createMockEnterprise(() => {
      throw new Error('ready failed');
    });
    const firstAttempt = ensureRecaptchaScript();
    const [firstScript] = appendedScripts;
    window.grecaptcha = { enterprise: brokenEnterprise };
    firstScript.dispatchEvent(new Event('load'));

    await expect(firstAttempt).rejects.toThrow('ready failed');
    expect(appendedScripts).toHaveLength(0);

    const healthyEnterprise = createMockEnterprise();
    delete window.grecaptcha;
    const retryAttempt = ensureRecaptchaScript();
    const [retryScript] = appendedScripts;
    window.grecaptcha = { enterprise: healthyEnterprise };
    retryScript.dispatchEvent(new Event('load'));

    await expect(retryAttempt).resolves.toBe(healthyEnterprise);
  });

  it('clears the cached promise when pre-existing enterprise.ready throws', async () => {
    // Test: Recovery when pre-existing `enterprise.ready` throws.
    // Situation: Pre-existing `ready` throws on call 1 and succeeds on call 2.
    // Expectation: Call 1 rejects and clears the cache so call 2 resolves.
    let shouldThrow = true;
    const enterprise = createMockEnterprise((callback) => {
      if (shouldThrow) {
        throw new Error('pre-existing ready failed');
      }
      callback();
    });
    window.grecaptcha = { enterprise };

    await expect(ensureRecaptchaScript()).rejects.toThrow(
      'pre-existing ready failed',
    );

    shouldThrow = false;
    await expect(ensureRecaptchaScript()).resolves.toBe(enterprise);
    expect(enterprise.ready).toHaveBeenCalledTimes(2);
  });

  it('rejects and cleans up when enterprise.ready does not fire before the timeout', async () => {
    // Test: Hung `enterprise.ready` timeout recovery.
    // Situation: `ready` never invokes its callback within the timeout window.
    // Expectation: Rejects on timeout, removes the tag, and allows retry.
    vi.useFakeTimers();
    const hungEnterprise = createMockEnterprise(() => undefined);

    const firstAttempt = ensureRecaptchaScript();
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
    const retryAttempt = ensureRecaptchaScript();
    const [retryScript] = appendedScripts;
    window.grecaptcha = { enterprise: healthyEnterprise };
    retryScript.dispatchEvent(new Event('load'));

    await expect(retryAttempt).resolves.toBe(healthyEnterprise);
  });

  it('does not let a stale script error clear a newer in-flight loadPromise', async () => {
    // Test: Late error from a superseded `<script>` after reset.
    // Situation: Load 1 starts, state resets, Load 2 starts, then Load 1 errors.
    // Expectation: Load 2 keeps its cached promise and resolves cleanly.
    writeRuntimeConfigSlot({ recaptcha_session_site_key: '6Lc_first' });
    const firstAttempt = ensureRecaptchaScript();
    const [staleScript] = appendedScripts;

    resetRecaptchaLoaderForTests();
    writeRuntimeConfigSlot({ recaptcha_session_site_key: '6Lc_second' });

    const secondAttempt = ensureRecaptchaScript();
    const [activeScript] = appendedScripts;

    staleScript.dispatchEvent(new Event('error'));
    await expect(firstAttempt).rejects.toThrow(
      /Failed to load reCAPTCHA Enterprise SDK/,
    );

    // Load 2 must still be cached in `loadPromise`.
    expect(ensureRecaptchaScript()).toBe(secondAttempt);
    expect(appendedScripts).toEqual([activeScript]);

    const enterprise = createMockEnterprise();
    window.grecaptcha = { enterprise };
    activeScript.dispatchEvent(new Event('load'));

    await expect(secondAttempt).resolves.toBe(enterprise);
  });
});
