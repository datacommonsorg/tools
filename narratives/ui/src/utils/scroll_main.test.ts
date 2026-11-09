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
 * @fileoverview Tests for the <main> scroll helpers.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  easeOutCubic,
  getScrollHeaderHeight,
  getVisibleBand,
  glideScrollTo,
} from '@/src/utils/scroll_main';

afterEach(() => {
  document.body.replaceChildren();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/** Mounts a <main> of `clientHeight`, with a header of `headerHeight`. */
const mountMain = (clientHeight: number, headerHeight?: number) => {
  const main = document.createElement('main');
  Object.defineProperty(main, 'clientHeight', { value: clientHeight });
  if (headerHeight !== undefined) {
    const header = document.createElement('header');
    Object.defineProperty(header, 'offsetHeight', { value: headerHeight });
    main.appendChild(header);
  }
  document.body.appendChild(main);
  return main;
};

describe('easeOutCubic', () => {
  it('eases from 0 to 1 and clamps progress past the end', () => {
    // Test: Ease-out cubic curve.
    // Situation: Progress at the start, midpoint, end, and past the end.
    // Expectation: 0, 0.875, 1, and 1.
    expect([0, 0.5, 1, 2].map(easeOutCubic)).toEqual([0, 0.875, 1, 1]);
  });
});

describe('getVisibleBand', () => {
  it('returns undefined without a <main>', () => {
    // Test: No scroll container mounted.
    // Situation: The document has no <main>.
    // Expectation: No band is returned.
    expect(getVisibleBand(document.body)).toBeUndefined();
  });

  it('excludes the header and the prompt published in --chrome-h', () => {
    // Test: Band between the sticky header and the sticky prompt.
    // Situation: A 600px <main> with a 64px header; the element carries a
    //            --chrome-h of 164px (header plus a 100px prompt).
    // Expectation: The band runs from 64px to 500px.
    const main = mountMain(600, 64);
    const element = document.createElement('div');
    element.style.setProperty('--chrome-h', '164px');
    main.appendChild(element);

    const band = getVisibleBand(element);
    expect(band?.scroller).toBe(main);
    expect([band?.top, band?.bottom]).toEqual([64, 500]);
  });

  it('subtracts only the header when --chrome-h is unset', () => {
    // Test: Fallback before DataAgent publishes --chrome-h.
    // Situation: A 600px <main> with a 64px header and no --chrome-h.
    // Expectation: The band runs from 64px to the bottom of <main>.
    const main = mountMain(600, 64);

    const band = getVisibleBand(main);
    expect([band?.top, band?.bottom]).toEqual([64, 600]);
    expect(getScrollHeaderHeight()).toBe(64);
  });
});

describe('glideScrollTo', () => {
  it('lands exactly on the target once the duration elapses', () => {
    // Test: Frame-by-frame glide.
    // Situation: <main> sits at 500px and glides to 100px over 200ms; frames
    //            run at 100ms and 300ms.
    // Expectation: The midpoint frame is eased past halfway (150px) and the
    //              last frame lands on 100px, after which no frame is queued.
    const frames: FrameRequestCallback[] = [];
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      frames.push(callback);
      return frames.length;
    });
    const now = vi.spyOn(performance, 'now').mockReturnValue(1_000);
    const main = mountMain(600);
    Object.defineProperty(main, 'scrollTop', { value: 500 });
    const scrollTo = vi.fn();
    main.scrollTo = scrollTo;

    glideScrollTo(main, 100, 200);
    now.mockReturnValue(1_100);
    frames.shift()?.(1_100);
    now.mockReturnValue(1_300);
    frames.shift()?.(1_300);

    expect(scrollTo.mock.calls).toEqual([
      [0, 150],
      [0, 100],
    ]);
    expect(frames).toHaveLength(0);
  });
});
