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
 * landing heading and the configured unavailable title and message, with no
 * prompt.
 */

import { domAnimation, LazyMotion, m, useReducedMotion } from 'motion/react';
import { useId } from 'react';
import { createPortal } from 'react-dom';
import { MessageText } from '@/src/components/text_message';
import { getInstanceConfig } from '@/src/config/instance_config';
import {
  INTRO_CASCADE_VARIANTS,
  INTRO_FADE_UP_VARIANTS,
} from '@/src/config/motion';
import { getRuntimeConfig } from '@/src/config/runtime_config';

/**
 * Unavailable view: the landing view's heading and tagline under a scrim,
 * with the configured unavailable title and message centered over it like a
 * modal window. It sends no requests; its only controls are links in the
 * message. The app shell is `inert` while this view shows, so the layer is
 * portaled to `<body>`.
 */
export function UnavailableView() {
  const { headline, tagline } = getInstanceConfig();
  const { unavailableTitle, unavailableMessage } = getRuntimeConfig();
  const shouldReduceMotion = useReducedMotion();
  const titleId = useId();

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
          className="text-display-medium text-headline mb-1 text-center"
        >
          {headline}
        </m.h1>
        {tagline && (
          <m.p
            variants={INTRO_FADE_UP_VARIANTS}
            className="text-body-regular text-subtle mt-2 mb-6 text-center"
          >
            {tagline}
          </m.p>
        )}
        {/* A modal-style backdrop over the inert page. It scrolls when the
            note is taller than the viewport; `m-auto` centers the note
            without clipping its top. */}
        {createPortal(
          <div className="fixed inset-0 z-50 flex overflow-y-auto p-4 bg-scrim/30 motion-safe:animate-fade-in">
            <m.div
              variants={INTRO_FADE_UP_VARIANTS}
              role="note"
              aria-labelledby={titleId}
              className="m-auto w-full max-w-198 rounded-dialog unavailable-art shadow-elevated text-left"
            >
              {/* Keeps the text below the artwork's figures at any note width. */}
              <div aria-hidden="true" className="aspect-unavailable-art" />
              <div className="flex flex-col gap-3 px-11 pb-11">
                <h2
                  id={titleId}
                  className="text-headline-large-emphasized text-headline"
                >
                  {unavailableTitle}
                </h2>
                <p className="text-headline-small text-on-surface-variant">
                  <MessageText message={unavailableMessage} />
                </p>
              </div>
            </m.div>
          </div>,
          document.body,
        )}
      </m.div>
    </LazyMotion>
  );
}
