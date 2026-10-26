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

import { useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChevronDownIcon } from "./icons";
import { getInstanceConfig } from "@/src/config/instance_config";
import type { ThoughtEvent, TurnStatus } from "../hooks/use_sse_chat";
import {
  calculateStreamDurationMs,
  rehypeStreamWords,
} from "../utils/rehype_stream_words";

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
 * not a real heading. We style those as headings (models rarely emit `##`
 * here).
 */
function isBoldOnlyParagraph(node?: HastNode): boolean {
  const kids = (node?.children ?? []).filter(
    (child) => !(child.type === "text" && !(child.value ?? "").trim()),
  );
  return (
    kids.length === 1 &&
    kids[0].type === "element" &&
    kids[0].tagName === "strong"
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
      <p className="text-on-surface-variant italic text-sm leading-5.5">{children}</p>
    ),
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  ul: ({ children }) => (
    <ul className="list-disc space-y-0.5 pl-9.5">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="list-decimal space-y-0.5 pl-9.5">
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
  // phase-specific label ("Querying data tools…", "Synthesizing answer…")
  // with the rotating loader; once done we switch to "Reasoning" with
  // the sparkle icon.
  status?: TurnStatus;
}

const PLACEHOLDER_CLASSIFY = "Reviewing your question…";
const PLACEHOLDER_STREAMING =
  "Searching Data Commons for relevant indicators and observations…";
const PLACEHOLDER_DONE =
  "Analyzed the query and retrieved relevant data from Data Commons.";

/**
 * Header label is derived from the turn status. The server's `status` events
 * move the turn through the `classify`, `discovery`, and `synthesis` phases,
 * and its `terminal` event ends it; these strings are the UI-side copy for
 * each phase.
 */
function phaseLabel(streaming: boolean, status?: TurnStatus): string {
  if (!streaming) return "Reasoning details";
  switch (status) {
    case "classify":
      return "Understanding your question…";
    case "discovery":
      return "Querying data tools…";
    case "synthesis":
      return "Synthesizing answer…";
    default:
      return "Thinking…";
  }
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
    return status === "classify" ? PLACEHOLDER_CLASSIFY : PLACEHOLDER_STREAMING;
  }
  return done ? PLACEHOLDER_DONE : "";
}

/** Collapsible "Reasoning" block: sparkle header plus the streamed thinking text. */
export function ReasoningBlock({
  thoughts,
  defaultOpen = false,
  streaming = false,
  done = false,
  status,
}: ReasoningBlockProps) {
  const [open, setOpen] = useState(defaultOpen);
  const label = phaseLabel(streaming, status);

  // The thoughts render back to back as one continuous block, not grouped
  // per phase; the placeholder stands in only when there are none.
  const placeholder = placeholderText(streaming, done, status);

  // If we have nothing at all (e.g. error before stream started),
  // skip rendering entirely.
  if (thoughts.length === 0 && !placeholder) return null;

  return (
    <div className="self-start shrink-0 w-full max-w-4xl">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="inline-flex items-center gap-3 bg-transparent border-0 p-0 cursor-pointer"
        aria-expanded={open}
      >
        {streaming ? <LoaderSpinner /> : <SparkleIcon />}
        <span className="inline-flex items-center gap-1 text-label-large text-on-surface">
          {label}
          <ChevronDownIcon
            className={`text-on-surface-variant transition-transform duration-150 ${
              open ? "rotate-180" : "rotate-0"
            }`}
          />
        </span>
      </button>
      {/* The body stays mounted and its grid row runs 0fr <-> 1fr, which lets
          the height animate to and from `auto`. `inert` keeps the collapsed
          text away from the keyboard and screen readers. */}
      <div
        inert={!open}
        className={`grid motion-safe:transition-[grid-template-rows,opacity] duration-200 ease-out ${
          open ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
        }`}
      >
        <div className="overflow-hidden min-h-0">
        {/* Softer than the response body + italic + indented, so the
            reasoning reads as an aside distinct from the actual answer. */}
        <div className="mt-2 ml-2.25 reasoning-markdown">
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
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={REASONING_COMPONENTS}
            >
              {placeholder}
            </ReactMarkdown>
          )}
        </div>
        </div>
      </div>
    </div>
  );
}

/** Streamed thought: word reveal plus a left bar ending in a dot. */
const STREAMED_THOUGHT_CLASS = [
  "markdown-stream relative flex flex-col gap-1.5 pt-2 pb-3 pl-5.5",
  "border-l-2 border-border",
  // Dot centered on the 2px bar at its bottom end.
  "after:absolute after:bottom-0 after:-left-px after:-translate-x-1/2",
  "after:size-2 after:rounded-full after:bg-border",
].join(" ");

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
  const dotClass =
    animate && isLatest ? "motion-safe:after:animate-dot-pulse" : "";
  const className =
    streamMs === undefined ? undefined : `${STREAMED_THOUGHT_CLASS} ${dotClass}`;
  return (
    <div className={className}>
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

