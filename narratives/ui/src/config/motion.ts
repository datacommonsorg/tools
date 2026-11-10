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
 * @fileoverview Shared motion and scroll tokens for animations and scripted
 * scrolling.
 */

import type { Variants } from 'motion/react';

/** Decelerating ease for elements entering the screen. */
export const EASE_OUT = [0.2, 0, 0, 1] as const;

/** Delay between successive children of the intro cascade, in seconds. */
const INTRO_CASCADE_STAGGER_S = 0.08;
/** Distance each intro element rises from while fading in, in pixels. */
const INTRO_FADE_UP_OFFSET_PX = 12;
/** Duration of each intro element's fade-up, in seconds. */
const INTRO_FADE_UP_DURATION_S = 0.4;

/**
 * Intro cascade for the landing and unavailable views: the container staggers
 * its children, and each child (including a nested cascade, such as the
 * suggestion chip row) starts when its turn comes.
 */
export const INTRO_CASCADE_VARIANTS: Variants = {
  show: { transition: { staggerChildren: INTRO_CASCADE_STAGGER_S } },
};

/** Intro fade-up for each child of {@link INTRO_CASCADE_VARIANTS}. */
export const INTRO_FADE_UP_VARIANTS: Variants = {
  hidden: { opacity: 0, y: INTRO_FADE_UP_OFFSET_PX },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: INTRO_FADE_UP_DURATION_S, ease: EASE_OUT },
  },
};

/** Media query for the user's reduced-motion preference. */
export const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)';

/** Duration of the reasoning body's expand and collapse transition. */
export const REASONING_COLLAPSE_MS = 200;

/** Gap between the sticky header and content scrolled up to meet it. */
export const SCROLL_PIN_OFFSET_PX = 8;
