/**
 * @fileoverview Renders the empty-state landing view: heading, prompt box, and suggestion chips.
 */

import { ChangeEvent, useRef } from "react";
import { LazyMotion, domAnimation, m, useReducedMotion, type Variants } from "motion/react";
import { SendIcon } from "./icons";
import { SuggestionChip } from "./chip_suggestion";
import { Tooltip } from "./tooltip";
import { useBrand } from "../hooks/branding_context";
import { useTextareaAutosize } from "../hooks/use_textarea_autosize";
import { EASE_OUT } from "../config/motion";

// Intro cascade: each child fades up in turn; the chip row cascades its own
// chips when its turn comes.
/** Delay between successive children of the intro cascade, in seconds. */
const CASCADE_STAGGER_S = 0.08;
/** Distance each element rises from while fading in, in pixels. */
const FADE_UP_OFFSET_PX = 12;
/** Duration of each element's fade-up, in seconds. */
const FADE_UP_DURATION_S = 0.4;

const cascade: Variants = { show: { transition: { staggerChildren: CASCADE_STAGGER_S } } };
const fadeUp: Variants = {
  hidden: { opacity: 0, y: FADE_UP_OFFSET_PX },
  show: { opacity: 1, y: 0, transition: { duration: FADE_UP_DURATION_S, ease: EASE_OUT } },
};

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
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isExpanded = useTextareaAutosize(textareaRef, query);
  const brand = useBrand();
  const suggestions = brand.suggestions ?? [];
  const reduceMotion = useReducedMotion();

  return (
    <LazyMotion features={domAnimation} strict>
      <m.div
        variants={cascade}
        // Reduced motion: no initial/animate, so everything renders at rest.
        {...(!reduceMotion && { initial: "hidden", animate: "show" })}
        className="flex-1 flex flex-col items-center justify-start sm:justify-center w-full max-w-5xl mx-auto px-4 lg:px-12 pt-8 sm:pt-0 pb-8 sm:pb-24 relative overflow-y-auto">

        <m.h1 variants={fadeUp} className="text-display-small-gradient mb-1 tracking-tight text-center">
          {brand.headline}
        </m.h1>
        <m.p variants={fadeUp} className="text-label-large text-subtle mb-8 text-center">
          {brand.tagline}
        </m.p>

        {/* GM3 Search Box */}
        <m.div
          variants={fadeUp}
          className={`w-full max-w-[720px] bg-surface border border-outline shadow-[0_2px_12px_rgba(0,0,0,0.06)] hover:shadow-[0_4px_16px_rgba(0,0,0,0.1)] motion-safe:transition-[border-radius,box-shadow] duration-200 ease-out flex flex-row items-start min-h-14 px-4 py-[7px] ${
            // The 56px pill is 7px padding + 40px button + 7px padding + 2px
            // border; py-2 would overshoot to 58px. The button sits at the top
            // so it stays on the first row as the box grows.
            // Pill radius is exactly half the 56px min-height, not rounded-full:
            // a 9999px radius stays visually round for the whole transition
            // and snaps to rounded-input at the end.
            isExpanded ? "rounded-input" : "rounded-[28px]"
          }`}
        >
          <textarea
            ref={textareaRef}
            value={query}
            onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setQuery(e.target.value)}
            placeholder="Ask a question to explore relevant statistical data"
            className="bg-transparent w-full outline-none text-body-large text-on-surface placeholder:text-placeholder resize-none overflow-hidden leading-6 pl-4 my-2 motion-safe:transition-[height] duration-200 ease-out"
            rows={1}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), onSend())}
          />
          {/* Action Button */}
          <Tooltip label="Submit">
            <button
              type="button"
              onClick={() => onSend()}
              aria-label="Submit"
              className="w-10 h-10 rounded-full flex items-center justify-center bg-surface-blue hover:bg-button-hover transition-colors shrink-0 group ml-2"
            >
              <SendIcon size="xs" />
            </button>
          </Tooltip>
        </m.div>

        {/* Prompt Chips (from branding.json suggestions, fallback DEFAULT_BRAND).
            On mobile (< sm) we sit inline so the chips don't get clipped under the
            virtual keyboard / browser chrome; from sm: up they dock to the bottom
            of the hero per the Figma spec. */}
        <m.div variants={cascade} className="static sm:absolute sm:bottom-6 sm:left-0 sm:right-0 mt-8 sm:mt-0 w-full flex flex-wrap justify-center gap-3 sm:gap-4 px-2 sm:px-6">
          {suggestions.map((text, index) => (
            <m.div key={index} variants={fadeUp}>
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
