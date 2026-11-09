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
 * @fileoverview Locates <main>, the app's scroll container, and its sticky
 * chrome, and scripts eased scrolls within it.
 */

/** Returns <main>, the app's scroll container (see App), if mounted. */
export function getScrollContainer(): HTMLElement | null {
  return document.querySelector('main');
}

/** Returns the sticky header at the top of <main>, if mounted. */
export function getScrollHeader(): HTMLElement | null {
  return document.querySelector<HTMLElement>('main > header');
}

/** Returns the sticky header's height, or 0 when there is no header. */
export function getScrollHeaderHeight(): number {
  return getScrollHeader()?.offsetHeight ?? 0;
}

/** Maps linear progress to ease-out cubic; progress past 1 clamps to 1. */
export function easeOutCubic(progress: number): number {
  return 1 - (1 - Math.min(1, progress)) ** 3;
}

/** The part of <main> not covered by its sticky chrome, in viewport pixels. */
export interface VisibleBand {
  scroller: HTMLElement;
  top: number;
  bottom: number;
}

/**
 * Returns <main> and the viewport span of its visible band: below the sticky
 * header and above the sticky prompt. The prompt's height comes from the
 * `--chrome-h` property (header plus prompt) that DataAgent sets on an
 * ancestor of `element`; without it, only the header is subtracted.
 */
export function getVisibleBand(element: HTMLElement): VisibleBand | undefined {
  const scroller = getScrollContainer();
  if (!scroller) return undefined;
  const headerHeight = getScrollHeaderHeight();
  const chromeHeight =
    Number.parseFloat(
      getComputedStyle(element).getPropertyValue('--chrome-h'),
    ) || headerHeight;
  const scrollerTop = scroller.getBoundingClientRect().top;
  return {
    scroller,
    top: scrollerTop + headerHeight,
    bottom: scrollerTop + scroller.clientHeight - (chromeHeight - headerHeight),
  };
}

/**
 * Scrolls `scroller` from its current position to `target` over `durationMs`
 * with ease-out cubic, setting the position on every animation frame. Unlike
 * a native smooth scroll, the glide is not canceled when a layout change
 * clamps `scrollTop` partway through.
 */
export function glideScrollTo(
  scroller: HTMLElement,
  target: number,
  durationMs: number,
): void {
  const from = scroller.scrollTop;
  const start = performance.now();
  const tick = () => {
    const progress = (performance.now() - start) / durationMs;
    scroller.scrollTo(0, from + (target - from) * easeOutCubic(progress));
    if (progress < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}
