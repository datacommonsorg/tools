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
 * @fileoverview Renders the agent's collapsible reasoning/thoughts block for a turn.
 */

import { type RefObject, useEffect, useRef, useState } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ChevronDownIcon } from '@/src/components/icons';
import {
  CLOSE_REASONING_LABEL,
  REASONING_DEFAULT_PHASE_LABEL,
  REASONING_DONE_LABEL,
  REASONING_PHASE_LABELS,
  REASONING_PLACEHOLDER_CLASSIFY,
  REASONING_PLACEHOLDER_DONE,
  REASONING_PLACEHOLDER_STREAMING,
} from '@/src/config/copy_chat';
import { getInstanceConfig } from '@/src/config/instance_config';
import {
  REASONING_COLLAPSE_MS,
  REDUCED_MOTION_QUERY,
  SCROLL_PIN_OFFSET_PX,
} from '@/src/config/motion';
import type { ThoughtEvent, TurnStatus } from '@/src/hooks/use_sse_chat';
import {
  calculateStreamDurationMs,
  rehypeStreamWords,
  STREAM_WORD_CLASS,
} from '@/src/utils/rehype_stream_words';
import { getScrollContainer, getVisibleBand } from '@/src/utils/scroll_main';

/**
 * Figma "Sparkle + Extension chip" (node 3427:16720) + "Content" (3427:16723).
 * Header row: Gemini sparkle icon (left) + "Reasoning ▾" chip (right of it).
 * Body: model reasoning text, collapsed by default.
 *
 * Tokens:
 *   Header gap 12, items centered
 *   Label "Reasoning" — Google Sans Text Medium 14/20 (Type scale - Desktop/Label L)
 *   Chevron — Material keyboard_arrow_down
 *   Default collapsed; chevron rotates 180° when expanded
 */

/** Renders a reasoning section heading — bold and upright, unlike the italic body. */
const ReasoningHeading = ({ children }: { children?: React.ReactNode }) => (
  <h3 className="font-semibold text-sm">{children}</h3>
);

/** Minimal shape of the hast node react-markdown hands each renderer. */
interface HastNode {
  type: string;
  tagName?: string;
  value?: string;
  children?: HastNode[];
}

/**
 * Reports whether a paragraph node is really a standalone bold line the model
 * wrote as a heading — e.g. `**Plan**` arrives as `<p><strong>…</strong></p>`,
 * not a real heading. These are styled as headings, since models rarely emit
 * `##` here.
 */
function isBoldOnlyParagraph(node?: HastNode): boolean {
  const kids = (node?.children ?? []).filter(
    (child) => !(child.type === 'text' && !(child.value ?? '').trim()),
  );
  return (
    kids.length === 1 &&
    kids[0].type === 'element' &&
    kids[0].tagName === 'strong'
  );
}

/**
 * Markdown overrides for the reasoning body. Module-level so their identity is
 * stable: rebuilt on each render, every thought would remount and replay its
 * entrance animation whenever a new one streamed in.
 */
const REASONING_COMPONENTS: Components = {
  h1: ReasoningHeading,
  h2: ReasoningHeading,
  h3: ReasoningHeading,
  h4: ReasoningHeading,
  h5: ReasoningHeading,
  h6: ReasoningHeading,
  // A lone-bold paragraph is really a section heading; everything else is a
  // body paragraph.
  p: ({ node, children }) =>
    isBoldOnlyParagraph(node as unknown as HastNode) ? (
      <ReasoningHeading>{children}</ReasoningHeading>
    ) : (
      <p className="text-on-surface-variant italic text-sm leading-5.5">
        {children}
      </p>
    ),
  strong: ({ children }) => (
    <strong className="font-semibold">{children}</strong>
  ),
  ul: ({ children }) => (
    <ul className="list-disc space-y-0.5 pl-9.5 text-on-surface-variant italic text-sm leading-5.5">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="list-decimal space-y-0.5 pl-9.5 text-on-surface-variant italic text-sm leading-5.5">
      {children}
    </ol>
  ),
  code: ({ children }) => (
    <code className="px-1 rounded font-mono bg-code-surface text-[0.92em]">
      {children}
    </code>
  ),
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-theme-primary hover:underline"
    >
      {children}
    </a>
  ),
};

interface ReasoningBlockProps {
  thoughts: ThoughtEvent[];
  // Whether the body starts expanded. Collapsed by default: the header alone
  // carries the phase label and spinner, which is the affordance that matters
  // while streaming — the thinking text is opt-in.
  defaultOpen?: boolean;
  // True while the chat turn is still streaming. Lets the placeholder
  // body adapt ("Reasoning…" vs. final fallback) when the agent emits
  // no `thought` events (e.g. simple queries with low thinking level).
  streaming?: boolean;
  // True once the turn is finished (status === "done"). Together with
  // an empty thoughts array, controls whether we show a "completed"
  // fallback message.
  done?: boolean;
  // Drives the header label + leading icon. During streaming we show a
  // phase-specific label ("Querying data tools", "Synthesizing answer")
  // with the rotating loader; once done we switch to "Reasoning" with
  // the sparkle icon.
  status?: TurnStatus;
  // Called as the closing button at the end of the body starts the collapse,
  // so the turn can bring its question back into view alongside it.
  onClose?: () => void;
  // The answer card rendered below the block: kept in view while the
  // reasoning streams open, and scrolled up to when the turn finishes.
  answerCardRef?: RefObject<HTMLElement | null>;
}

/** Share of the skeleton card kept in view below streaming reasoning. */
const SKELETON_PEEK = 1;

/**
 * Returns the header label for the turn status: the phase's label while
 * streaming, falling back to a generic one, and the done label afterwards.
 */
function getPhaseLabel(streaming: boolean, status?: TurnStatus): string {
  if (!streaming) return REASONING_DONE_LABEL;
  return (
    (status && REASONING_PHASE_LABELS[status]) ?? REASONING_DEFAULT_PHASE_LABEL
  );
}

/**
 * Matches a line the body renders with `ReasoningHeading`: a markdown heading
 * (`## Plan`, closing `#`s dropped) or a lone bold line (`**Plan**`). A line
 * with several bold runs, such as `**Note:** see **this**`, is body text.
 */
const HEADING_LINE = /^\s*(?:#{1,6}\s+(.+?)(?:\s+#+)?|\*\*([^*]+)\*\*)\s*$/;

/** Returns the most recent section heading across the thoughts, if any. */
function latestHeading(thoughts: ThoughtEvent[]): string | undefined {
  for (
    let thoughtIndex = thoughts.length - 1;
    thoughtIndex >= 0;
    thoughtIndex--
  ) {
    const lines = thoughts[thoughtIndex].text.split('\n');
    for (let lineIndex = lines.length - 1; lineIndex >= 0; lineIndex--) {
      const match = HEADING_LINE.exec(lines[lineIndex]);
      if (match) return (match[1] ?? match[2]).trim();
    }
  }
  return undefined;
}

/**
 * Returns the body text for a reasoning block that has no thoughts associated
 * with it. During classification the text indicates that the question is
 * being reviewed. In later phases it indicates that a search is in progress.
 * Once the turn is done, the text says that data was retrieved. In any other
 * state, such as an error before the stream opened, the function returns an
 * empty string and the block is not rendered.
 */
function placeholderText(
  streaming: boolean,
  done: boolean,
  status?: TurnStatus,
): string {
  if (streaming) {
    return status === 'classify'
      ? REASONING_PLACEHOLDER_CLASSIFY
      : REASONING_PLACEHOLDER_STREAMING;
  }
  return done ? REASONING_PLACEHOLDER_DONE : '';
}

/** Collapsible "Reasoning" block: sparkle header plus the streamed thinking text. */
export function ReasoningBlock({
  thoughts,
  defaultOpen = false,
  streaming = false,
  done = false,
  status,
  onClose,
  answerCardRef,
}: ReasoningBlockProps) {
  const [open, setOpen] = useState(defaultOpen);
  // While streaming, the header also names the section the model is on.
  const heading = streaming ? latestHeading(thoughts) : undefined;
  const phaseLabel = getPhaseLabel(streaming, status);

  // While the turn streams with the reasoning open, keep the latest thought
  // in view: whenever the list grows past the visible band, which it does on
  // every frame of a thought's expand animation, scroll by the overflow.
  // Scrolling up pauses this so the reader can re-read; bringing the latest
  // thought's end back into view resumes it.
  const rootRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  // Whether following is active; read when the turn finishes, so a reader
  // who scrolled away is not pulled down to the answer either.
  const isFollowingRef = useRef(true);
  useEffect(() => {
    const body = bodyRef.current;
    const scroller = getScrollContainer();
    if (!streaming || !open || !body || !scroller) return;
    // The edge kept in view: SKELETON_PEEK of the way into the answer card
    // (the skeleton while streaming), so the reader sees the answer is
    // coming; the thought list's end when there is no card.
    const followEdge = () => {
      const card = answerCardRef?.current?.getBoundingClientRect();
      return card
        ? card.top + card.height * SKELETON_PEEK
        : body.getBoundingClientRect().bottom;
    };
    isFollowingRef.current = true;
    let lastScrollTop = scroller.scrollTop;
    const onScroll = () => {
      const band = getVisibleBand(body);
      if (!band) return;
      // Following only ever scrolls down, so an upward scroll is the reader's.
      if (scroller.scrollTop < lastScrollTop) isFollowingRef.current = false;
      lastScrollTop = scroller.scrollTop;
      // 1px of slack for fractional layout.
      if (followEdge() <= band.bottom + 1) {
        isFollowingRef.current = true;
      }
    };
    const observer = new ResizeObserver(() => {
      const band = getVisibleBand(body);
      if (!isFollowingRef.current || !band) return;
      const overflow = followEdge() - band.bottom;
      if (overflow > 0) band.scroller.scrollBy(0, overflow);
    });
    scroller.addEventListener('scroll', onScroll, { passive: true });
    observer.observe(body);
    return () => {
      scroller.removeEventListener('scroll', onScroll);
      observer.disconnect();
    };
  }, [streaming, open, answerCardRef]);

  // When the turn finishes with the reasoning open and following, scroll the
  // answer card up under the header, just as a new question is pinned; the
  // block's own end stands in when there is no card.
  const wasStreaming = useRef(streaming);
  useEffect(() => {
    const finished = wasStreaming.current && !streaming;
    wasStreaming.current = streaming;
    const root = rootRef.current;
    if (!finished || !open || !isFollowingRef.current || !root) return;
    const band = getVisibleBand(root);
    if (!band) return;
    const answerTop =
      answerCardRef?.current?.getBoundingClientRect().top ??
      root.getBoundingClientRect().bottom;
    const reduceMotion = window.matchMedia(REDUCED_MOTION_QUERY).matches;
    band.scroller.scrollBy({
      top: answerTop - band.top - SCROLL_PIN_OFFSET_PX,
      behavior: reduceMotion ? 'auto' : 'smooth',
    });
  }, [streaming, open, answerCardRef]);

  // The thoughts render back to back as one continuous block, not grouped
  // per phase; the placeholder stands in only when there are none.
  const placeholder = placeholderText(streaming, done, status);

  // If we have nothing at all (e.g. error before stream started),
  // skip rendering entirely.
  if (thoughts.length === 0 && !placeholder) return null;

  return (
    <div ref={rootRef} className="self-start shrink-0 w-full max-w-4xl">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="inline-flex items-center gap-3 bg-transparent border-0 p-0 cursor-pointer"
        aria-expanded={open}
      >
        {streaming ? <LoaderSpinner /> : <SparkleIcon />}
        <span className="inline-flex items-center gap-1 text-label-large text-on-surface">
          {/* One text run, so the colon hugs the label inside the flex gap. */}
          {heading ? `${phaseLabel}:` : phaseLabel}
          {heading && (
            // Keyed by the text so each new heading remounts and replays.
            <StreamedText
              key={heading}
              text={heading}
              className="font-normal"
            />
          )}
          <ChevronDownIcon
            className={`text-on-surface-variant transition-transform duration-150 ${
              open ? 'rotate-180' : 'rotate-0'
            }`}
          />
        </span>
      </button>
      {/* The body stays mounted and its grid row runs 0fr <-> 1fr, which lets
          the height animate to and from `auto`. `inert` keeps the collapsed
          text away from the keyboard and screen readers. */}
      <div
        inert={!open}
        className={`grid motion-safe:transition-[grid-template-rows,opacity] ease-out ${
          open ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0'
        }`}
        // Shared with TurnView's scroll back to the question, which runs in
        // step with the collapse.
        style={{ transitionDuration: `${REASONING_COLLAPSE_MS}ms` }}
      >
        <div className="overflow-hidden min-h-0">
          {/* Indented so the reasoning reads as an aside to the answer; the
            paragraphs and lists add the muted italic. The bottom padding keeps
            the last dot's pulse inside the clipping wrapper above. */}
          <div ref={bodyRef} className="mt-2 ml-2.25 pb-1 reasoning-markdown">
            {thoughts.length > 0 ? (
              thoughts.map((thought, i) => (
                // Thoughts only ever append, so the index is a stable key.
                <Thought
                  key={i}
                  text={thought.text}
                  animate={streaming}
                  isLatest={i === thoughts.length - 1}
                />
              ))
            ) : (
              <Thought
                key="placeholder"
                text={placeholder}
                animate={streaming}
                isLatest
              />
            )}
          </div>
          {/* Offered once the turn finishes, for closing a long read from
              its end. */}
          {!streaming && (
            // The bottom padding keeps the button's touch target inside the
            // clipping wrapper, where it can still be hit.
            <div className="flex justify-end mt-2 pb-3 motion-safe:animate-stream-in">
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  onClose?.();
                }}
                // The pseudo-element pads the 20px-tall label out to a 44px
                // touch target without changing the layout.
                className="relative inline-flex items-center gap-1 bg-transparent border-0 p-0 cursor-pointer text-label-large text-on-surface-variant hover:text-on-surface after:absolute after:-inset-x-1 after:-inset-y-3"
              >
                {CLOSE_REASONING_LABEL}
                <ChevronDownIcon className="rotate-180" />
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Thought layout: a left bar ending in a dot. A one-row grid so a streamed
 * thought can grow its height from 0fr; the bar and dot live here, outside the
 * clipping inner wrapper, so the dot is not cut off.
 */
const THOUGHT_CLASS = [
  'relative grid grid-rows-[1fr] pt-2 pb-3 pl-5.5',
  'border-l-2 border-border',
  // Dot centered on the 2px bar at its bottom end.
  'after:absolute after:bottom-0 after:-left-px after:-translate-x-1/2',
  'after:size-2 after:rounded-full',
].join(' ');

interface ThoughtProps {
  text: string;
  animate: boolean;
  isLatest: boolean;
}

/**
 * One thought, revealed word by word like the answer when it arrives live.
 * Whether it animates is fixed at mount: a thought restored with its session,
 * or still on screen when the turn ends, does not replay or cut short. The
 * latest thought's end dot tracks `animate` live and pulses until the turn
 * stops streaming.
 */
function Thought({ text, animate, isLatest }: ThoughtProps) {
  const [streamMs] = useState(() =>
    animate ? calculateStreamDurationMs(text) : undefined,
  );
  const streamClass =
    streamMs === undefined
      ? ''
      : ' markdown-stream motion-safe:animate-thought-expand';
  // The latest thought's dot pulses in the theme tint while the turn streams.
  const dotClass =
    animate && isLatest
      ? ' after:bg-theme-container motion-safe:after:animate-dot-pulse'
      : ' after:bg-border';
  const className = `${THOUGHT_CLASS}${streamClass}${dotClass}`;
  return (
    <div className={className}>
      <div className="flex flex-col gap-1.5 min-h-0 overflow-clip">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={
            streamMs === undefined ? [] : [[rehypeStreamWords, streamMs]]
          }
          components={REASONING_COMPONENTS}
        >
          {text}
        </ReactMarkdown>
      </div>
    </div>
  );
}

interface StreamedTextProps {
  text: string;
  // Extra classes for the wrapper, such as a weight that differs from the
  // surrounding text.
  className?: string;
}

/**
 * Plain text revealed word by word with the same stagger and keyframes as a
 * streamed thought, for places outside the markdown body such as the header.
 */
function StreamedText({ text, className = '' }: StreamedTextProps) {
  const parts = text.split(/(\s+)/);
  const wordCount = parts.filter((part) => part.trim() !== '').length;
  const step = calculateStreamDurationMs(text) / Math.max(wordCount, 1);
  let words = 0;
  return (
    <span className={`markdown-stream whitespace-pre-wrap ${className}`}>
      {parts.map((part, i) =>
        part.trim() === '' ? (
          part
        ) : (
          <span
            // Parts are fixed for a given text, so the index is a stable key.
            key={i}
            className={STREAM_WORD_CLASS}
            style={{ animationDelay: `${Math.round(words++ * step)}ms` }}
          >
            {part}
          </span>
        ),
      )}
    </span>
  );
}

/** Rotating indicator shown while the turn is streaming. */
function LoaderSpinner() {
  const { thinkingIndicatorUrl } = getInstanceConfig();
  return (
    <img
      src={thinkingIndicatorUrl}
      alt=""
      aria-hidden="true"
      width={20}
      height={20}
      className="shrink-0 motion-safe:animate-spin"
    />
  );
}

/** Static indicator shown after the turn finishes streaming. */
function SparkleIcon() {
  const { doneIndicatorUrl } = getInstanceConfig();
  return (
    <img
      src={doneIndicatorUrl}
      alt=""
      aria-hidden="true"
      width={20}
      height={20}
      className="shrink-0"
    />
  );
}
