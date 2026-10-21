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
 * @fileoverview Tests for trimTrailingSlashes, normalizeBasePath, and
 * withBaseUrl.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  normalizeBasePath,
  trimTrailingSlashes,
  withBaseUrl,
} from './base_url';

afterEach(() => {
  vi.unstubAllEnvs();
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

describe('normalizeBasePath', () => {
  it.each([
    [undefined, '/'],
    ['', '/'],
    ['   ', '/'],
    ['/', '/'],
    ['///', '/'],
    ['/narratives', '/narratives/'],
    ['/narratives/', '/narratives/'],
    ['narratives', '/narratives/'],
    ['  //narratives//  ', '/narratives/'],
  ])('normalizes %j to %j', (raw, expected) => {
    // Test: Normalization of `VITE_BASE_PATH` values into Vite's `base` format.
    // Situation: `normalizeBasePath` receives undefined, blank, root, or
    //            subpath strings with varying leading/trailing slashes.
    // Expectation: Subpaths resolve to `/<subpath>/` and empty/root values
    //              resolve to `/`.
    expect(normalizeBasePath(raw)).toBe(expected);
  });
});

describe('withBaseUrl', () => {
  it('resolves paths at the root when BASE_URL is default', () => {
    // Test: Path resolution under the default `/` base URL.
    // Situation: `import.meta.env.BASE_URL` is `/` and `withBaseUrl` is called
    //            with and without a leading slash.
    // Expectation: Both inputs resolve to `/<path>`.
    vi.stubEnv('BASE_URL', '/');
    expect(withBaseUrl('/dc-logo.svg')).toBe('/dc-logo.svg');
    expect(withBaseUrl('agent/chat/stream')).toBe('/agent/chat/stream');
  });

  it('prefixes paths with BASE_URL when mounted under a subpath', () => {
    // Test: Path resolution under a subpath `BASE_URL`.
    // Situation: `import.meta.env.BASE_URL` is `/narratives/` and `withBaseUrl`
    //            is called with a root-relative asset path and API endpoint.
    // Expectation: Both inputs resolve under `/narratives/`.
    vi.stubEnv('BASE_URL', '/narratives/');
    expect(withBaseUrl('/dc-logo.svg')).toBe('/narratives/dc-logo.svg');
    expect(withBaseUrl('/agent/chat/stream')).toBe(
      '/narratives/agent/chat/stream',
    );
  });
});
