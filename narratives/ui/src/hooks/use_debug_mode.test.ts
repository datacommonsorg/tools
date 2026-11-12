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
 * @fileoverview Unit tests for `use_debug_mode.ts`: URL query parameter
 * evaluation, lazy `/agent/health` fetching, caching, and fallback handling.
 */

import { cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  isDebugUrlEnabled,
  resetDebugModeCacheForTests,
  useDebugMode,
} from '@/src/hooks/use_debug_mode';

let originalUrl = '';

beforeEach(() => {
  originalUrl = window.location.href;
  resetDebugModeCacheForTests();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetDebugModeCacheForTests();
  window.history.replaceState(null, '', originalUrl);
});

describe('isDebugUrlEnabled', () => {
  it('returns true for enabling query values and false for other values', () => {
    // Test: Query parameter parsing.
    // Situation: Variations of the debug query parameter.
    // Expectation: Returns true for '', 'true', and '1', false otherwise.
    expect(isDebugUrlEnabled('?debug')).toBe(true);
    expect(isDebugUrlEnabled('?debug=')).toBe(true);
    expect(isDebugUrlEnabled('?debug=true')).toBe(true);
    expect(isDebugUrlEnabled('?debug=1')).toBe(true);

    expect(isDebugUrlEnabled('')).toBe(false);
    expect(isDebugUrlEnabled('?debug=false')).toBe(false);
    expect(isDebugUrlEnabled('?debug=provenance')).toBe(false);
    expect(isDebugUrlEnabled('?debug=0')).toBe(false);
  });
});

describe('useDebugMode', () => {
  it('returns true immediately without calling fetch when ?debug is present', () => {
    // Test: URL debug precedence over server fetch.
    // Situation: window.location.search has ?debug=1.
    // Expectation: Hook returns true synchronously and fetch is never called.
    window.history.replaceState(null, '', '/?debug=1');
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useDebugMode(true));

    expect(result.current).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('falls back to the server mode when ?debug is removed after mount', async () => {
    // Test: URL debug does not leak into the server debug state.
    // Situation: The hook mounts with ?debug, the URL then loses ?debug, and
    //   /agent/health returns { debug_report: 'off' }.
    // Expectation: The hook returns true with ?debug, then false once the
    //   server mode is fetched.
    window.history.replaceState(null, '', '/?debug');
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ status: 'ok', debug_report: 'off' }),
    }));
    vi.stubGlobal('fetch', fetchMock);

    const { result, rerender } = renderHook(() => useDebugMode(true));
    expect(result.current).toBe(true);

    window.history.replaceState(null, '', '/');
    rerender();

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
    expect(result.current).toBe(false);
  });

  it('does not fetch /agent/health while enabled is false', () => {
    // Test: Gating on the enabled parameter.
    // Situation: URL debug is absent and enabled is passed as false.
    // Expectation: Hook returns false and fetch is not invoked.
    window.history.replaceState(null, '', '/');
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useDebugMode(false));

    expect(result.current).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('fetches /agent/health once when enabled becomes true without ?debug and returns true for on', async () => {
    // Test: Successful server debug mode detection and caching.
    // Situation: enabled is true, URL debug is absent, and /agent/health returns { debug_report: 'on' }.
    // Expectation: fetch is called once with /agent/health, returns true, and caches across remounts.
    window.history.replaceState(null, '', '/');
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith('/agent/health')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ status: 'ok', debug_report: 'on' }),
        };
      }
      throw new Error(`Unexpected url: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    const { result, unmount } = renderHook(() => useDebugMode(true));

    await waitFor(() => {
      expect(result.current).toBe(true);
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // Remounting should use the cached value without a second fetch
    unmount();
    const { result: remountResult } = renderHook(() => useDebugMode(true));
    expect(remountResult.current).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['flag', { debug_report: 'flag' }, 200],
    ['off', { debug_report: 'off' }, 200],
    ['500', { error: 'Internal Error' }, 500],
  ])('returns false when /agent/health returns %s', async (_label, body, status) => {
    // Test: Server debug report modes other than on.
    // Situation: /agent/health returns non-on mode or non-200 status.
    // Expectation: Hook resolves to false without error.
    window.history.replaceState(null, '', '/');
    const fetchMock = vi.fn(async () => ({
      ok: status === 200,
      status,
      json: async () => body,
    }));
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useDebugMode(true));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
    expect(result.current).toBe(false);
  });

  it('returns false when /agent/health network request rejects', async () => {
    // Test: Network failure handling.
    // Situation: fetch fails with network error.
    // Expectation: Hook resolves to false gracefully without throwing.
    window.history.replaceState(null, '', '/');
    const fetchMock = vi.fn(async () => {
      throw new Error('Network failure');
    });
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useDebugMode(true));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
    expect(result.current).toBe(false);
  });
});
