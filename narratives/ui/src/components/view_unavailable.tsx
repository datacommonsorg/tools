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
 * @fileoverview Renders the Data Agent route while chat is disabled: the
 * landing heading and the configured unavailable message, with no prompt.
 */

import {
  domAnimation,
  LazyMotion,
  m,
  useReducedMotion,
  type Variants,
} from 'motion/react';
import { getInstanceConfig } from '@/src/config/instance_config';
import { EASE_OUT } from '@/src/config/motion';
import { getRuntimeConfig } from '@/src/config/runtime_config';

/** Delay between successive children of the intro cascade, in seconds. */
const CASCADE_STAGGER_S = 0.08;
/** Distance each element rises from while fading in, in pixels. */
const FADE_UP_OFFSET_PX = 12;
/** Duration of each element's fade-up, in seconds. */
const FADE_UP_DURATION_S = 0.4;

const cascade: Variants = {
  show: { transition: { staggerChildren: CASCADE_STAGGER_S } },
};
const fadeUp: Variants = {
  hidden: { opacity: 0, y: FADE_UP_OFFSET_PX },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: FADE_UP_DURATION_S, ease: EASE_OUT },
  },
};

/**
 * Unavailable view: the landing view's heading and tagline above a notice
 * card holding the configured unavailable message. It renders no controls
 * and sends no requests.
 */
export function UnavailableView() {
  const { headline, tagline } = getInstanceConfig();
  const { unavailableMessage } = getRuntimeConfig();
  const shouldReduceMotion = useReducedMotion();
  // Without a tagline, the heading carries the spacing above the card.
  const headlineMarginClass = tagline ? 'mb-1' : 'mb-8';

  return (
    <LazyMotion features={domAnimation} strict>
      <m.div
        variants={cascade}
        // Reduced motion: no initial/animate, so everything renders at rest.
        {...(!shouldReduceMotion && { initial: 'hidden', animate: 'show' })}
        className="flex-1 flex flex-col items-center justify-start sm:justify-center w-full max-w-5xl mx-auto px-4 lg:px-12 pt-8 sm:pt-0 pb-8 sm:pb-24"
      >
        <m.h1
          variants={fadeUp}
          className={`text-display-small-gradient ${headlineMarginClass} tracking-tight text-center`}
        >
          {headline}
        </m.h1>
        {tagline && (
          <m.p
            variants={fadeUp}
            className="text-label-large text-subtle mb-8 text-center"
          >
            {tagline}
          </m.p>
        )}
        <m.div
          variants={fadeUp}
          role="status"
          className="w-full max-w-prompt rounded-card border border-border bg-surface-soft px-6 py-6 sm:px-8 sm:py-7 text-center"
        >
          <p className="text-body-large text-on-surface-variant">
            {unavailableMessage}
          </p>
        </m.div>
      </m.div>
    </LazyMotion>
  );
}
