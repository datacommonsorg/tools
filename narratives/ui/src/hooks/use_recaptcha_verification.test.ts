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
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/**
 * @fileoverview Tests for `useRecaptchaVerification`: modal state transitions,
 * in-memory action-token TTL caching, eviction, and unmount/abort cleanup.
 */

import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  RECAPTCHA_ACTION_TOKEN_TTL_MS,
  useRecaptchaVerification,
  type VerificationOutcome,
} from '@/src/hooks/use_recaptcha_verification';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('useRecaptchaVerification', () => {
  it('opens on requestVerification, caches the trimmed token for 25 minutes, and evicts on expiry or clearToken', async () => {
    // Test: Token verification, TTL boundary, and manual eviction.
    // Situation: Verification is requested, completed with a padded token, read
    //   just before TTL expiry, read at TTL expiry, and later cleared manually.
    // Expectation: The trimmed token is cached and returned before expiry,
    //   evicted at `RECAPTCHA_ACTION_TOKEN_TTL_MS`, and cleared by `clearToken`.
    let nowMs = 1_700_000_000_000;
    vi.spyOn(Date, 'now').mockImplementation(() => nowMs);

    const { result } = renderHook(() => useRecaptchaVerification());
    expect(result.current.verificationModal).toEqual({ status: 'closed' });
    expect(result.current.getActiveToken()).toBeNull();

    let pending!: Promise<VerificationOutcome>;
    act(() => {
      pending = result.current.requestVerification('6Lc_site');
    });
    expect(result.current.verificationModal).toEqual({
      status: 'open',
      checkboxSiteKey: '6Lc_site',
    });

    act(() => {
      result.current.completeVerification('  tok-123  ');
    });
    expect(await pending).toEqual({ status: 'verified', token: 'tok-123' });
    expect(result.current.verificationModal).toEqual({ status: 'closed' });

    nowMs += RECAPTCHA_ACTION_TOKEN_TTL_MS - 1;
    expect(result.current.getActiveToken()).toBe('tok-123');

    nowMs += 1;
    expect(result.current.getActiveToken()).toBeNull();

    // Verify clearToken evicts an unexpired token immediately.
    act(() => {
      pending = result.current.requestVerification('6Lc_site');
    });
    act(() => {
      result.current.completeVerification('tok-456');
    });
    await pending;
    expect(result.current.getActiveToken()).toBe('tok-456');

    act(() => {
      result.current.clearToken();
    });
    expect(result.current.getActiveToken()).toBeNull();
  });

  it('ignores blank tokens, calls while closed, and duplicate completeVerification calls', async () => {
    // Test: Guard rails on `completeVerification`.
    // Situation: `completeVerification` is invoked while closed, then invoked
    //   with whitespace while open, then invoked twice with valid tokens.
    // Expectation: Closed and whitespace calls neither close the modal nor
    //   cache a token; only the first valid token resolves and is cached.
    const { result } = renderHook(() => useRecaptchaVerification());

    act(() => {
      result.current.completeVerification('stale-token');
    });
    expect(result.current.getActiveToken()).toBeNull();

    let pending!: Promise<VerificationOutcome>;
    act(() => {
      pending = result.current.requestVerification('6Lc_site');
    });

    act(() => {
      result.current.completeVerification('   ');
    });
    expect(result.current.verificationModal.status).toBe('open');
    expect(result.current.getActiveToken()).toBeNull();

    act(() => {
      result.current.completeVerification('first-token');
      result.current.completeVerification('second-token');
    });
    expect(await pending).toEqual({
      status: 'verified',
      token: 'first-token',
    });
    expect(result.current.getActiveToken()).toBe('first-token');
  });

  it('settles as canceled, aborted, or aborted-on-unmount and aborts superseded requests', async () => {
    // Test: Cancellation, abort, superseding request, and unmount teardown.
    // Situation: Requests are resolved via `cancelVerification`,
    //   `abortVerification`, a second `requestVerification`, and hook unmount.
    // Expectation: Every suspended promise settles cleanly with its exact
    //   discriminated outcome and leaves no closed-state mismatch.
    const { result, unmount } = renderHook(() => useRecaptchaVerification());

    let canceled!: Promise<VerificationOutcome>;
    act(() => {
      canceled = result.current.requestVerification('6Lc_site');
    });
    act(() => {
      result.current.cancelVerification();
    });
    expect(await canceled).toEqual({ status: 'canceled' });
    expect(result.current.verificationModal).toEqual({ status: 'closed' });

    let first!: Promise<VerificationOutcome>;
    let second!: Promise<VerificationOutcome>;
    act(() => {
      first = result.current.requestVerification('6Lc_site_1');
      second = result.current.requestVerification('6Lc_site_2');
    });
    expect(await first).toEqual({ status: 'aborted' });
    expect(result.current.verificationModal).toEqual({
      status: 'open',
      checkboxSiteKey: '6Lc_site_2',
    });

    act(() => {
      result.current.abortVerification();
    });
    expect(await second).toEqual({ status: 'aborted' });
    expect(result.current.verificationModal).toEqual({ status: 'closed' });

    let onUnmount!: Promise<VerificationOutcome>;
    act(() => {
      onUnmount = result.current.requestVerification('6Lc_site_3');
    });
    unmount();
    expect(await onUnmount).toEqual({ status: 'aborted' });
  });
});
