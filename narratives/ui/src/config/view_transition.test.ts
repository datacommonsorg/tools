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
 * @fileoverview Tests for isOutsideApp and registerViewTransitionFilter.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  isOutsideApp,
  registerViewTransitionFilter,
} from '@/src/config/view_transition';

const ORIGIN = 'https://datacommons.org';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('isOutsideApp', () => {
  it.each([
    [`${ORIGIN}/`, '/labs/discover', true],
    [`${ORIGIN}/explore#q=india`, '/labs/discover', true],
    [`${ORIGIN}/labs/discovery`, '/labs/discover', true],
    [`${ORIGIN}/labs/discover`, '/labs/discover', false],
    [`${ORIGIN}/labs/discover/`, '/labs/discover', false],
    [`${ORIGIN}/labs/discover/index.html`, '/labs/discover', false],
    [`${ORIGIN}/explore`, '', false],
    [null, '/labs/discover', false],
  ])('treats %j under base %j as outside: %j', (url, basePath, expected) => {
    // Test: Classification of a navigation URL against the app's base path.
    // Situation: The URL is a Data Commons page, a sibling path sharing the
    //            base as a prefix, the app itself, or missing; the app is
    //            mounted under a subpath or at the root.
    // Expectation: Only same-origin paths outside the base path count, and
    //              nothing counts when the app is mounted at the root.
    expect(isOutsideApp(url, basePath)).toBe(expected);
  });
});

describe('registerViewTransitionFilter', () => {
  const dispatchPageSwap = (url: string | null) => {
    const skipTransition = vi.fn();
    const event = Object.assign(new Event('pageswap'), {
      viewTransition: { skipTransition },
      activation: url === null ? null : { entry: { url } },
    });
    window.dispatchEvent(event);
    return skipTransition;
  };

  it.each([
    [`${ORIGIN}/explore`, false],
    [`${ORIGIN}/labs/discover/#/metrics`, true],
    [null, true],
  ])('leaving for %j skips the transition: %j', (url, expectedSkip) => {
    // Test: Outgoing view transition filtering on `pageswap`.
    // Situation: The app is mounted at `/labs/discover/` and navigates to a
    //            Data Commons page, to itself, or cross-origin (null
    //            activation).
    // Expectation: Only the navigation to the Data Commons page animates.
    vi.stubGlobal('location', new URL(`${ORIGIN}/labs/discover/`));
    const unregister = registerViewTransitionFilter();

    const skipTransition = dispatchPageSwap(url);

    unregister();
    expect(skipTransition).toHaveBeenCalledTimes(expectedSkip ? 1 : 0);
  });
});
