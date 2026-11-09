/**
 * @fileoverview Shared motion and scroll tokens for animations and scripted
 * scrolling.
 */

/** Decelerating ease for elements entering the screen. */
export const EASE_OUT = [0.2, 0, 0, 1] as const;

/** Media query for the user's reduced-motion preference. */
export const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)';

/** Duration of the reasoning body's expand and collapse transition. */
export const REASONING_COLLAPSE_MS = 200;

/** Gap between the sticky header and content scrolled up to meet it. */
export const SCROLL_PIN_OFFSET_PX = 8;
