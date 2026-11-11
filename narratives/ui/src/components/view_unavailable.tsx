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

import { domAnimation, LazyMotion, m, useReducedMotion } from 'motion/react';
import { getInstanceConfig } from '@/src/config/instance_config';
import {
  INTRO_CASCADE_VARIANTS,
  INTRO_FADE_UP_VARIANTS,
} from '@/src/config/motion';
import { getRuntimeConfig } from '@/src/config/runtime_config';

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
        variants={INTRO_CASCADE_VARIANTS}
        // Reduced motion: no initial/animate, so everything renders at rest.
        {...(!shouldReduceMotion && { initial: 'hidden', animate: 'show' })}
        className="flex-1 flex flex-col items-center justify-start sm:justify-center w-full max-w-5xl mx-auto px-4 lg:px-12 pt-8 sm:pt-0 pb-8 sm:pb-24"
      >
        <m.h1
          variants={INTRO_FADE_UP_VARIANTS}
          className={`text-display-small-gradient ${headlineMarginClass} tracking-tight text-center`}
        >
          {headline}
        </m.h1>
        {tagline && (
          <m.p
            variants={INTRO_FADE_UP_VARIANTS}
            className="text-label-large text-subtle mb-8 text-center"
          >
            {tagline}
          </m.p>
        )}
        <m.div
          variants={INTRO_FADE_UP_VARIANTS}
          role="note"
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
