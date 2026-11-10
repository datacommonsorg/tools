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

/** Decelerating ease for elements entering the screen. */
export const EASE_OUT = [0.2, 0, 0, 1] as const;

/** Media query for the user's reduced-motion preference. */
export const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)';

/** Duration of the reasoning body's expand and collapse transition. */
export const REASONING_COLLAPSE_MS = 200;

/** Gap between the sticky header and content scrolled up to meet it. */
export const SCROLL_PIN_OFFSET_PX = 8;
