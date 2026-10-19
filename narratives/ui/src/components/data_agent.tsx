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
 * @fileoverview Data Agent chat surface: prompt input, streaming turns, stop control, and follow-up handling.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { InitialView } from "./view_initial";
import { SkeletonCard } from "./card_skeleton";
import { ReasoningBlock } from "./block_reasoning";
import { AnswerPanel } from "./panel_answer";
import { DISCLAIMER_TEXT } from "./note_disclaimer";
import { PromptInput } from "./input_prompt";
import { assignCitationNumbers, type ChatTurn } from "../hooks/use_sse_chat";
import { useChatSession } from "../hooks/chat_session_context";

/** How long the scroll to a new question glides. */
const PIN_GLIDE_MS = 400;
/** How long the new question is held at the top while late layout settles. */
const PIN_HOLD_MS = 600;
/** Gap between the sticky header and the pinned question. */
const PIN_TOP_OFFSET_PX = 8;
/** Must match the duration in `--animate-stream-in` (ui/src/index.css). */
export const HANDOFF_MS = 400;
/** Centered content column; the page scrolls at full width. */
const COLUMN = "w-full max-w-4xl mx-auto px-3 sm:px-4 lg:px-8";

/**
 * The main chat surface: renders the empty-state view or the turn list, the
 * prompt input with send/stop controls, and pins each new question to the top.
 */
export function DataAgent() {
  const [query, setQuery] = useState("");
  // Pulled from the Context (ChatSessionProvider in app.tsx) so turns
  // survive when the user navigates to another SPA tab and back, and across
  // browser refreshes (persisted to localStorage).
  const { turns, isStreaming, error, send, stop, currentSessionId } = useChatSession();
  // Citation labels belong to the thread, not to one answer, so they are
  // worked out here, where every turn is in view.
  const citationNumbers = useMemo(() => assignCitationNumbers(turns), [turns]);
  const promptRef = useRef<HTMLDivElement>(null);
  const showConversation = turns.length > 0 || isStreaming;
  // Track the turn count we last reacted to so we only scroll when a NEW
  // turn is added (e.g. follow-up question click) — not on every re-render
  // caused by streaming text chunks arriving.
  const prevTurnsLength = useRef(turns.length);
  // Turns already here when the surface mounts (a restored session, or coming
  // back from another tab) are not news, so they do not animate in.
  const restoredTurns = useRef(turns.length);
  // The surface stays mounted across session switches and "New chat", so a
  // different session counts as a fresh mount: its turns are not news either.
  const prevSessionId = useRef(currentSessionId);
  if (prevSessionId.current !== currentSessionId) {
    prevSessionId.current = currentSessionId;
    prevTurnsLength.current = turns.length;
    restoredTurns.current = turns.length;
  }

  // `override` lets a caller (e.g. a suggestion chip in InitialView) submit
  // a message directly without first round-tripping through the `query`
  // state — setState is async, so chaining setQuery → handleSend in one tick
  // would otherwise send an empty string.
  const handleSend = async (override?: string) => {
    const message = (override ?? query).trim();
    if (!message || isStreaming) return;
    setQuery("");
    await send(message);
  };

  // When a new turn is appended (typed prompt OR follow-up question click),
  // pin the user's new question to the top of the chat surface so they can
  // immediately see the message and the reasoning that streams below it.
  // Otherwise the new content gets appended out of view and the user only
  // sees stale answer chrome from the previous turn until they scroll.
  //
  // That is the only scroll the surface makes. The answer then streams in
  // below the question, top to bottom, and the viewport stays where it is;
  // the last turn's min-height (see TurnView) reserves the room for it.
  useEffect(() => {
    if (turns.length > prevTurnsLength.current) {
      const targetIndex = turns.length - 1;
      // Glides rather than jumps, unless the reader asked for reduced motion.
      const from = window.scrollY;
      const glideMs = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : PIN_GLIDE_MS;
      const scrollToLatest = (elapsed: number) => {
        const target = document.querySelector<HTMLElement>(
          `[data-turn-index="${targetIndex}"]`,
        );
        if (!target) return;
        // offsetTop ignores the enter animation's translate.
        let top = 0;
        let node: HTMLElement | null = target;
        while (node) {
          top += node.offsetTop;
          node = node.offsetParent as HTMLElement | null;
        }
        top -= document.querySelector<HTMLElement>("main > header")?.offsetHeight ?? 0;
        // Ease-out cubic. The target is re-read every frame, so the glide
        // lands on the bubble even if the layout above it is still settling.
        const progress = 1 - (1 - Math.min(1, elapsed / (glideMs || 1))) ** 3;
        window.scrollTo(0, from + (Math.max(0, top - PIN_TOP_OFFSET_PX) - from) * progress);
      };
      // Glide there, then hold on every animation frame for PIN_HOLD_MS so late
      // layout shifts from the previous turn's AnswerPanel (e.g. Data Commons
      // chart hydration, FollowUpQuestions unmounting) don't leave the new
      // bubble stranded mid-scroller. Canceled when the user scrolls away.
      const start = performance.now();
      let canceled = false;
      const onUserScroll = () => {
        canceled = true;
      };
      window.addEventListener("wheel", onUserScroll, { passive: true });
      window.addEventListener("touchmove", onUserScroll, { passive: true });
      const tick = () => {
        if (canceled) return;
        const elapsed = performance.now() - start;
        scrollToLatest(elapsed);
        if (elapsed < PIN_HOLD_MS) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
      // Tidy listeners after the pin window closes.
      window.setTimeout(() => {
        window.removeEventListener("wheel", onUserScroll);
        window.removeEventListener("touchmove", onUserScroll);
      }, PIN_HOLD_MS + 100);
    }
    prevTurnsLength.current = turns.length;
  }, [turns.length]);

  // Exposes the sticky header + prompt height as --chrome-h for TurnView.
  useEffect(() => {
    const prompt = promptRef.current;
    const header = document.querySelector<HTMLElement>("main > header");
    if (!prompt) return;
    const observer = new ResizeObserver(() =>
      prompt.parentElement?.style.setProperty(
        "--chrome-h",
        `${prompt.offsetHeight + (header?.offsetHeight ?? 0)}px`,
      ),
    );
    observer.observe(prompt);
    if (header) observer.observe(header);
    return () => observer.disconnect();
  }, [showConversation]);

  if (!showConversation) {
    return (
      <InitialView
        query={query}
        setQuery={setQuery}
        onSend={handleSend}
      />
    );
  }

  return (
    <div className="flex-1 flex flex-col w-full min-w-0">
      <div className="flex-1 flex flex-col gap-6 pt-8 sm:pt-10 pb-6">
        {turns.map((t, i) => (
          <TurnView
            // Keyed by turn identity so a new turn or session at the same
            // index gets fresh state; older saved turns fall back to index.
            key={t.idempotencyKey ?? i}
            turn={t}
            index={i}
            citationNumbers={citationNumbers[i]}
            isLast={i === turns.length - 1}
            animate={i >= restoredTurns.current}
            isStreaming={isStreaming && i === turns.length - 1}
            onAsk={(question) => send(question)}
          />
        ))}
        {error && turns.length === 0 && (
          <div className={COLUMN}>
            <div className="w-fit px-4 py-3 rounded-2xl bg-error-surface text-error-strong text-body-large">
              {error}
            </div>
          </div>
        )}
      </div>

      {/* Sticky follow-up input; full-width background hides content behind it. */}
      <div ref={promptRef} className="sticky bottom-0 z-[5] w-full bg-surface">
        {/* Fade above the bar so content softens into it. */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute left-0 right-0 bottom-full h-4"
          style={{
            background:
              "linear-gradient(to top, #FFFFFF 0%, rgba(255,255,255,0) 100%)",
          }}
        />
        {/* Relative so the prompt's shadow paints over the fade. */}
        <div className={`${COLUMN} relative flex flex-col items-center gap-3 pb-4 sm:pb-6`}>
          <PromptInput
            value={query}
            placeholder="Ask a follow-up question"
            onValueChange={setQuery}
            onSubmit={() => handleSend()}
            isStreaming={isStreaming}
            onStop={stop}
          />
          <div className="text-center text-caption text-muted max-w-xl">
            {DISCLAIMER_TEXT}
          </div>
        </div>
      </div>
    </div>
  );
}

interface TurnViewProps {
  turn: ChatTurn;
  // Index in the turn list — emitted as data-turn-index on the user bubble so
  // the auto-scroll effect in DataAgent can find the new turn's anchor.
  index: number;
  /** Thread-wide label for each of this turn's provenance rows. */
  citationNumbers?: number[];
  isLast: boolean;
  /** Whether the pieces of the turn fade up into place as they arrive. */
  animate: boolean;
  isStreaming: boolean;
  onAsk?: (question: string) => void;
}

/** One conversation turn: the user's bubble plus the streamed agent response. */
function TurnView({
  turn,
  index,
  citationNumbers,
  isLast,
  animate,
  isStreaming,
  onAsk,
}: TurnViewProps) {
  // The answer stays behind the skeleton until its text has arrived in full.
  const textReady =
    turn.textComplete || turn.status === "done" || turn.status === "error";
  const showAnswer = Boolean(turn.text) && !turn.stopped && textReady;
  const showSkeleton =
    !showAnswer &&
    !turn.stopped &&
    (turn.status === "mcp" || turn.status === "synthesis");
  // Keep a shown skeleton under the answer until the crossfade ends.
  // Restored turns never had one, so they skip it.
  const [hadSkeleton, setHadSkeleton] = useState(false);
  if (showSkeleton && !hadSkeleton) setHadSkeleton(true);
  const [handedOff, setHandedOff] = useState(false);
  useEffect(() => {
    if (!showAnswer || !hadSkeleton) return;
    const timer = window.setTimeout(() => setHandedOff(true), HANDOFF_MS);
    return () => window.clearTimeout(timer);
  }, [showAnswer, hadSkeleton]);
  const crossfading = showAnswer && hadSkeleton && !handedOff;
  const className = [
    "shrink-0 flex flex-col gap-6",
    COLUMN,
    animate && "motion-safe:*:animate-enter",
    // Viewport minus sticky chrome and the list's pb-6.
    isLast && "min-h-[calc(100dvh-var(--chrome-h,0px)-1.5rem)]",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    // The last turn fills the viewport between header and prompt, so its
    // question can be pinned to the top while the answer streams in below.
    <div className={className}>
      {/* User bubble — Figma uses Type scale Body L (16/28/400). The
          .text-body-large utility gives the right family + size + weight,
          but its line-height is 24px (GM3 body/large); override inline
          because the utility's rule sets line-height with a CSS variable
          and out-classes the Tailwind `leading-*` helper in source order. */}
      <div
        data-turn-index={index}
        className={`self-end shrink-0 max-w-[85%] sm:max-w-[80%] px-4 sm:px-6 py-3 sm:py-4 rounded-card text-body-large shadow-sm bg-user-msg text-on-surface break-words${
          index > 0 ? " mt-3" : ""
        }`}
        style={{ lineHeight: "28px" }}
      >
        {turn.userMessage}
      </div>

      {/* Tool-call chips hidden — loader + phase message convey progress
          on their own. The raw search_indicators(...) / get_observations(...)
          text was leaking into the answer area. */}

      {/* Reasoning block — sparkle + "Reasoning" header, expanded by default.
          Always renders above the response card per Figma 3427-16715;
          falls back to a status placeholder when the agent emits no thoughts.
          Suppressed when the turn was stopped or refused, and `done` is gated
          on evidence of a data call so clarification turns do not render the
          completed data-retrieval placeholder. */}
      {!turn.stopped && turn.status !== "refused" && (
        <ReasoningBlock
          thoughts={turn.thoughts}
          streaming={isStreaming && turn.status !== "done" && turn.status !== "error"}
          done={
            turn.status === "done" &&
            (turn.thoughts.length > 0 ||
              turn.toolCalls.length > 0 ||
              turn.provenance.length > 0)
          }
          status={turn.status}
        />
      )}

      {/* Narrative card — one wrapper for both of its states, so it enters
          once and the skeleton hands over to the answer in place rather than
          the card leaving and coming back.

          Loading: `mcp` through `synthesis`; not during `classify`, which
          may still refuse.

          Answer: AnswerPanel once the text is whole, crossfading over the
          skeleton in a shared grid cell. Hidden when stopped. */}
      {(showSkeleton || showAnswer) && (
        <div className="self-start shrink-0 w-full max-w-4xl grid *:col-start-1 *:row-start-1">
          {(showSkeleton || crossfading) && (
            <div
              aria-hidden={showAnswer}
              className={`motion-safe:transition-opacity ease-out${
                showAnswer ? " opacity-0" : ""
              }`}
              style={{ transitionDuration: `${HANDOFF_MS}ms` }}
            >
              <SkeletonCard query={turn.userMessage} />
            </div>
          )}
          {showAnswer && (
            <div
              className={
                hadSkeleton
                  ? "motion-safe:animate-stream-in"
                  : undefined
              }
            >
              <AnswerPanel
                turn={turn}
                isStreaming={isStreaming}
                onAsk={onAsk}
                citationNumbers={citationNumbers}
                turnIndex={index}
              />
            </div>
          )}
        </div>
      )}

      {/* Stopped note — shown in place of the reasoning/answer when the user
          aborts the turn via the Stop button. */}
      {turn.stopped && (
        <div className="self-start shrink-0 w-full max-w-4xl text-body-large text-on-surface-variant">
          Stopped per your request
        </div>
      )}

      {/* Refusal notice for unserviceable or safety-blocked requests. */}
      {turn.status === "refused" && turn.refusalMessage && (
        <div
          role="note"
          data-testid="turn-refusal-notice"
          className="self-start px-4 py-3 rounded-2xl bg-surface-soft text-on-surface-variant text-body-large max-w-4xl"
        >
          {turn.refusalMessage}
        </div>
      )}

      {/* Error */}
      {turn.status === "error" && turn.error && (
        <div className="self-start px-4 py-3 rounded-2xl bg-error-surface text-error-strong text-body-large max-w-4xl">
          {turn.error}
        </div>
      )}
    </div>
  );
}
