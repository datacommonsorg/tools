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
 * @fileoverview Renders the empty-state landing view: heading, prompt box, and suggestion chips.
 */

import { domAnimation, LazyMotion, m, useReducedMotion } from 'motion/react';
import { SuggestionChip } from '@/src/components/chip_suggestion';
import { PromptInput } from '@/src/components/input_prompt';
import { getInstanceConfig } from '@/src/config/instance_config';
import {
  INTRO_CASCADE_VARIANTS,
  INTRO_FADE_UP_VARIANTS,
} from '@/src/config/motion';

interface InitialViewProps {
  query: string;
  setQuery: (val: string) => void;
  // Accepts an optional explicit message — used by suggestion chips so the
  // chip text is submitted immediately rather than waiting on a React state
  // update of `query`.
  onSend: (override?: string) => void;
}

/** Empty-state landing view: hero heading, prompt input, and suggestion chips. */
export function InitialView({ query, setQuery, onSend }: InitialViewProps) {
  const { headline, tagline, suggestions } = getInstanceConfig();
  const reduceMotion = useReducedMotion();

  return (
    <LazyMotion features={domAnimation} strict>
      <m.div
        variants={INTRO_CASCADE_VARIANTS}
        // Reduced motion: no initial/animate, so everything renders at rest.
        {...(!reduceMotion && { initial: 'hidden', animate: 'show' })}
        className="flex-1 flex flex-col items-center justify-start sm:justify-center w-full max-w-5xl mx-auto px-4 lg:px-12 pt-8 sm:pt-0 pb-8 sm:pb-24 relative"
      >
        <m.h1
          variants={INTRO_FADE_UP_VARIANTS}
          className="text-display-small-gradient mb-1 tracking-tight text-center"
        >
          {headline}
        </m.h1>
        <m.p
          variants={INTRO_FADE_UP_VARIANTS}
          className="text-label-large text-subtle mb-8 text-center"
        >
          {tagline}
        </m.p>

        <m.div variants={INTRO_FADE_UP_VARIANTS} className="w-full">
          <PromptInput
            value={query}
            placeholder="Ask a question to explore relevant statistical data"
            onValueChange={setQuery}
            onSubmit={() => onSend()}
          />
        </m.div>

        {/* Place suggestion chips inline on narrow screens so they are not
            clipped by the virtual keyboard, and dock them to the bottom of the
            hero container on wider screens. */}
        <m.div
          variants={INTRO_CASCADE_VARIANTS}
          className="static sm:absolute sm:bottom-6 sm:left-0 sm:right-0 mt-8 sm:mt-0 w-full flex flex-wrap justify-center gap-3 sm:gap-4 px-2 sm:px-6"
        >
          {suggestions.map((text, index) => (
            <m.div key={index} variants={INTRO_FADE_UP_VARIANTS}>
              <SuggestionChip
                text={text}
                // Clicking a chip submits immediately — saves the user a second
                // click on the send button. We still mirror the text into the
                // input briefly so the question is visible while the request
                // kicks off and the InitialView is replaced by the chat surface.
                onClick={(suggestion) => {
                  setQuery(suggestion);
                  onSend(suggestion);
                }}
              />
            </m.div>
          ))}
        </m.div>
      </m.div>
    </LazyMotion>
  );
}
