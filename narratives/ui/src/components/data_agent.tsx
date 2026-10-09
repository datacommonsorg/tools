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

/**
 * The main chat surface: renders the empty-state view or the turn list, the
 * prompt input with send/stop controls, and pins each new question to the top.
 */
export function DataAgent() {
  const [query, setQuery] = useState("");
  // Pulled from the Context (ChatSessionProvider in app.tsx) so turns
  // survive when the user navigates to another SPA tab and back, and across
  // browser refreshes (persisted to localStorage).
  const { turns, isStreaming, error, send, stop } = useChatSession();
  // Citation labels belong to the thread, not to one answer, so they are
  // worked out here, where every turn is in view.
  const citationNumbers = useMemo(() => assignCitationNumbers(turns), [turns]);
  const scrollRef = useRef<HTMLDivElement>(null);
  // Track the turn count we last reacted to so we only scroll when a NEW
  // turn is added (e.g. follow-up question click) — not on every re-render
  // caused by streaming text chunks arriving.
  const prevTurnsLength = useRef(turns.length);
  // Turns already here when the surface mounts (a restored session, or coming
  // back from another tab) are not news, so they do not animate in.
  const restoredTurns = useRef(turns.length);

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
      const container = scrollRef.current;
      const targetIndex = turns.length - 1;
      // Glides rather than jumps, unless the reader asked for reduced motion.
      const from = container?.scrollTop ?? 0;
      const glideMs = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 400;
      const scrollToLatest = (elapsed: number) => {
        if (!container) return;
        const target = container.querySelector<HTMLElement>(
          `[data-turn-index="${targetIndex}"]`,
        );
        if (!target) return;
        let top = 0;
        let node: HTMLElement | null = target;
        while (node && node !== container) {
          top += node.offsetTop;
          node = node.offsetParent as HTMLElement | null;
        }
        // Ease-out cubic. The target is re-read every frame, so the glide
        // lands on the bubble even if the layout above it is still settling.
        const progress = 1 - (1 - Math.min(1, elapsed / (glideMs || 1))) ** 3;
        container.scrollTop = from + (Math.max(0, top - 8) - from) * progress;
      };
      // Glide there, then hold on every animation frame up to ~600ms so late
      // layout shifts from the previous turn's AnswerPanel (e.g. Data Commons
      // chart hydration, FollowUpQuestions unmounting) don't leave the new
      // bubble stranded mid-scroller. Canceled when the user scrolls away.
      const start = performance.now();
      let canceled = false;
      const onUserScroll = () => {
        canceled = true;
      };
      container?.addEventListener("wheel", onUserScroll, { passive: true });
      container?.addEventListener("touchmove", onUserScroll, { passive: true });
      const tick = () => {
        if (canceled) return;
        const elapsed = performance.now() - start;
        scrollToLatest(elapsed);
        if (elapsed < 600) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
      // Tidy listeners after the pin window closes.
      window.setTimeout(() => {
        container?.removeEventListener("wheel", onUserScroll);
        container?.removeEventListener("touchmove", onUserScroll);
      }, 700);
    }
    prevTurnsLength.current = turns.length;
  }, [turns.length]);

  if (turns.length === 0 && !isStreaming) {
    return (
      <InitialView
        query={query}
        setQuery={setQuery}
        onSend={handleSend}
      />
    );
  }

  return (
    <div className="flex-1 flex flex-col h-full w-full max-w-4xl mx-auto px-3 sm:px-4 lg:px-8 pt-4 sm:pt-6 relative overflow-hidden min-w-0">
      <div className="flex-1 min-h-0 relative">
        <div
          ref={scrollRef}
          className="absolute inset-0 overflow-y-auto no-scrollbar flex flex-col gap-6 pt-4 pb-6"
        >
          {turns.map((t, i) => (
            <TurnView
              key={i}
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
            <div className="self-start px-4 py-3 rounded-2xl bg-error-surface text-error-strong text-body-large">
              {error}
            </div>
          )}
        </div>

        {/* 16px transparent-to-white gradient overlaying the bottom of the
            scroll area — chat content scrolling up "behind" the input box
            visibly fades into the chrome rather than terminating in a hard
            edge. Positioned absolutely so it sits ON TOP of the scrollable
            content (not as a sibling in the white gap). */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute left-0 right-0 bottom-0 h-4"
          style={{
            background:
              "linear-gradient(to top, #FFFFFF 0%, rgba(255,255,255,0) 100%)",
          }}
        />
      </div>

      {/* Follow-up input — flush against the fade (no top margin) so the
          gradient reads as a continuous merge rather than a separator.
          Positioned so it paints over the fade, which would otherwise clip
          the top of the prompt's shadow. */}
      <div className="relative w-full flex flex-col items-center gap-3 bg-surface pb-4 sm:pb-6">
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
  const showAnswer = Boolean(turn.text) && !turn.stopped;
  const showSkeleton = !turn.text && turn.status === "synthesis";
  const className = [
    "shrink-0 flex flex-col gap-6",
    animate && "motion-safe:*:animate-enter",
    isLast && "min-h-full",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    // The last turn is at least as tall as the scroll area, so its question
    // can be pinned to the top before any of the answer exists and the answer
    // can fill in beneath it without the view moving.
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
          Suppressed when the turn was stopped — we replace the half-finished
          reasoning with the "Stopped per your request" note below. */}
      {!turn.stopped && (
        <ReasoningBlock
          thoughts={turn.thoughts}
          streaming={isStreaming && turn.status !== "done" && turn.status !== "error"}
          done={turn.status === "done"}
          status={turn.status}
        />
      )}

      {/* Narrative card — one wrapper for both of its states, so it enters
          once and the skeleton hands over to the answer in place rather than
          the card leaving and coming back.

          Loading: only once the agent starts constructing the narrative (the
          `synthesis` phase), not during mcp (tools running). Through that
          earlier phase the user sees just the reasoning.

          Answer: the full Figma AnswerPanel, streaming then final. Hidden
          when the turn was stopped so we don't show a truncated partial
          answer. */}
      {(showSkeleton || showAnswer) && (
        <div className="self-start shrink-0 w-full max-w-4xl">
          {showAnswer ? (
            <AnswerPanel
              turn={turn}
              isStreaming={isStreaming}
              onAsk={onAsk}
              citationNumbers={citationNumbers}
              turnIndex={index}
            />
          ) : (
            <SkeletonCard query={turn.userMessage} />
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

      {/* Error */}
      {turn.status === "error" && turn.error && (
        <div className="self-start px-4 py-3 rounded-2xl bg-error-surface text-error-strong text-body-large max-w-4xl">
          {turn.error}
        </div>
      )}
    </div>
  );
}
