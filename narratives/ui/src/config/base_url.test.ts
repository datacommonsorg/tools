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
 * @fileoverview Tests for trimTrailingSlashes and withBaseUrl.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { trimTrailingSlashes, withBaseUrl } from '@/src/config/base_url';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('trimTrailingSlashes', () => {
  it.each([
    ['https://autopush.datacommons.org/', 'https://autopush.datacommons.org'],
    [
      '  https://autopush.datacommons.org///  ',
      'https://autopush.datacommons.org',
    ],
    ['/', ''],
    ['   ', ''],
  ])('normalizes %j to %j', (raw, expected) => {
    // Test: Whitespace and trailing-slash trimming on origins and paths.
    // Situation: `trimTrailingSlashes` is called with surrounding whitespace
    //            and zero or more trailing slashes.
    // Expectation: Surrounding whitespace and trailing slashes are removed.
    expect(trimTrailingSlashes(raw)).toBe(expected);
  });
});

describe('withBaseUrl', () => {
  it.each([
    ['https://autopush.datacommons.org/', ''],
    ['https://autopush.datacommons.org/index.html', ''],
    ['https://autopush.datacommons.org/narratives/', '/narratives'],
    ['https://autopush.datacommons.org/labs/discover/', '/labs/discover'],
    ['https://autopush.datacommons.org/labs/discover', '/labs/discover'],
    [
      'https://autopush.datacommons.org/labs/discover/index.html',
      '/labs/discover',
    ],
    [
      'https://autopush.datacommons.org/labs/discover/?q=india#/metrics',
      '/labs/discover',
    ],
    ['https://autopush.datacommons.org//labs/discover/', '/labs/discover'],
  ])('resolves paths under %s to prefix %j', (href, expectedPrefix) => {
    // Test: Runtime path resolution against `window.location.pathname`.
    // Situation: The document is served at the root, a single- or multi-segment
    //            subpath (with or without a trailing slash), an explicit
    //            `index.html`, repeated leading slashes, or query/hash params.
    // Expectation: Assets and API endpoints resolve under a single-slash mount
    //              prefix without generating protocol-relative `//` URLs.
    vi.stubGlobal('location', new URL(href));
    expect(withBaseUrl('/dc-logo.svg')).toBe(`${expectedPrefix}/dc-logo.svg`);
    expect(withBaseUrl('agent/chat/stream')).toBe(
      `${expectedPrefix}/agent/chat/stream`,
    );
  });

  it('falls back to a root-relative path when window is undefined', () => {
    // Test: Non-browser fallback when `window` is absent.
    // Situation: `window` is undefined and `withBaseUrl` is called with and
    //            without a leading slash.
    // Expectation: Both inputs return `/<cleanPath>`.
    vi.stubGlobal('window', undefined);
    expect(withBaseUrl('/dc-logo.svg')).toBe('/dc-logo.svg');
    expect(withBaseUrl('agent/chat/stream')).toBe('/agent/chat/stream');
  });
});
