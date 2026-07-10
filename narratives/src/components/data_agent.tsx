/**
 * @fileoverview Data Agent chat surface: prompt input, streaming turns, stop control, and follow-up handling.
 */

import { useEffect, useRef, useState } from "react";
import { InitialView } from "./view_initial";
import { SkeletonCard } from "./card_skeleton";
import { ReasoningBlock } from "./reasoning_block";
import { AnswerPanel } from "./panel_answer";
import type { ChatTurn } from "../hooks/use_sse_chat";
import { useChatSession } from "../hooks/chat_session_context";

/**
 * The main chat surface: renders the empty-state view or the turn list, the
 * prompt input with send/stop controls, and auto-scrolls new turns into view.
 */
export function DataAgent() {
  const [query, setQuery] = useState("");
  // Pulled from the Context (ChatSessionProvider in App.tsx) so turns
  // survive when the user navigates to another SPA tab and back, and across
  // browser refreshes (persisted to localStorage).
  const { turns, isStreaming, error, send, stop } = useChatSession();
  const isExpanded = query.trim().length > 0;
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  // Track the turn count we last reacted to so we only scroll when a NEW
  // turn is added (e.g. follow-up question click) — not on every re-render
  // caused by streaming text chunks arriving.
  const prevTurnsLength = useRef(turns.length);

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

  useEffect(() => {
    if (!textareaRef.current) return;
    if (isExpanded) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    } else {
      textareaRef.current.style.height = "";
    }
  }, [query, isExpanded]);

  // When a new turn is appended (typed prompt OR follow-up question click),
  // pin the user's new question to the top of the chat surface so they can
  // immediately see the message and the reasoning that streams below it.
  // Otherwise the new content gets appended out of view and the user only
  // sees stale answer chrome from the previous turn until they scroll.
  useEffect(() => {
    if (turns.length > prevTurnsLength.current) {
      const container = scrollRef.current;
      const targetIndex = turns.length - 1;
      const scrollToLatest = () => {
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
        container.scrollTop = Math.max(0, top - 8);
      };
      // Pin once now, then again on every animation frame for ~600ms so late
      // layout shifts from the previous turn's AnswerPanel (e.g. Data Commons
      // chart hydration, FollowUpQuestions unmounting) don't leave the new
      // bubble stranded mid-scroller. Cancelled when the user scrolls away.
      const start = performance.now();
      let cancelled = false;
      const onUserScroll = () => {
        cancelled = true;
      };
      container?.addEventListener("wheel", onUserScroll, { passive: true });
      container?.addEventListener("touchmove", onUserScroll, { passive: true });
      const tick = () => {
        if (cancelled) return;
        scrollToLatest();
        if (performance.now() - start < 600) requestAnimationFrame(tick);
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
        textareaRef={textareaRef}
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
              isLast={i === turns.length - 1}
              isStreaming={isStreaming && i === turns.length - 1}
              onAsk={(q) => send(q)}
            />
          ))}
          {error && turns.length === 0 && (
            <div className="self-start px-4 py-3 rounded-2xl bg-red-50 text-red-700 text-body-large">
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
          gradient reads as a continuous merge rather than a separator. */}
      <div className="w-full flex flex-col items-center gap-3 bg-white pb-4 sm:pb-6">
        <div className="w-full max-w-[720px] min-h-[64px] bg-white border border-gray-200 rounded-[24px] p-4 flex flex-col justify-between shadow-[0_2px_12px_rgba(0,0,0,0.06)] hover:shadow-[0_4px_16px_rgba(0,0,0,0.1)] transition-all duration-300">
          <textarea
            ref={textareaRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={isStreaming ? "Streaming…" : "Ask a follow-up question"}
            disabled={isStreaming}
            className="bg-transparent w-full outline-none text-body-large text-on-surface placeholder:text-placeholder resize-none flex-1 pl-2 pt-1"
            rows={1}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
          />
          <button
            onClick={isStreaming ? stop : () => handleSend()}
            disabled={!isStreaming && !query.trim()}
            className="w-10 h-10 rounded-full flex items-center justify-center bg-surface-blue hover:bg-button-hover transition-colors self-end shrink-0 disabled:opacity-50"
          >
            {isStreaming ? (
              <div className="w-3 h-3 rounded-sm bg-brand-primary" />
            ) : (
              <img src="/send.svg" alt="Send" className="w-5 h-5" />
            )}
          </button>
        </div>
        <div className="text-center text-caption text-muted max-w-xl">
          Powered by Data Commons, an initiative from Google.
          <br />
          Data overviews are synthesized by Gemini; as with any AI-generated
          content please verify content against primary source data.
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
  isLast: boolean;
  isStreaming: boolean;
  onAsk?: (question: string) => void;
}

/** One conversation turn: the user's bubble plus the streamed agent response. */
function TurnView({ turn, index, isStreaming, onAsk }: TurnViewProps) {
  return (
    <>
      {/* User bubble — Figma uses Type scale Body L (16/28/400). The
          .text-body-large utility gives the right family + size + weight,
          but its line-height is 24px (GM3 body/large); override inline
          because the utility's rule sets line-height with a CSS variable
          and out-classes the Tailwind `leading-*` helper in source order. */}
      <div
        data-turn-index={index}
        className="self-end shrink-0 max-w-[85%] sm:max-w-[80%] px-4 sm:px-6 py-3 sm:py-4 rounded-[24px] text-body-large shadow-sm bg-user-msg text-on-surface break-words scroll-mt-4"
        style={{ lineHeight: "28px" }}
      >
        {turn.userMessage}
      </div>

      {/* Phase loader removed — ReasoningBlock below is the sole progress
          indicator. Showing both was redundant ("Querying data tools…"
          duplicated "Searching Data Commons for relevant indicators…"). */}

      {/* Tool-call chips hidden — loader + phase message convey progress
          on their own. The raw search_indicators(...) / get_observations(...)
          text was leaking into the answer area. */}

      {/* Reasoning block — sparkle + "Reasoning" header, expanded by default.
          Always renders above the response card per Figma 3427-16715;
          falls back to a status placeholder when the agent emits no thoughts. */}
      <ReasoningBlock
        thoughts={turn.thoughts}
        streaming={isStreaming && turn.status !== "done" && turn.status !== "error"}
        done={turn.status === "done"}
        status={turn.status}
      />

      {/* Skeleton while the turn is streaming but no synthesis text has
          arrived yet. Covers the full pre-text window: mcp (tools running),
          kb (knowledge base lookup), and synthesis (model thinking before
          first token). Previously this only checked `mcp`, leaving a ~3s
          blank gap between mcp_complete and the first text chunk. */}
      {!turn.text &&
        (turn.status === "mcp" ||
          turn.status === "kb" ||
          turn.status === "synthesis") && (
          <div className="self-start w-full max-w-4xl">
            <SkeletonCard query={turn.userMessage} />
          </div>
        )}

      {/* Streaming + final answer — full Figma AnswerPanel */}
      {turn.text && (
        <AnswerPanel turn={turn} isStreaming={isStreaming} onAsk={onAsk} />
      )}

      {/* Error */}
      {turn.status === "error" && turn.error && (
        <div className="self-start px-4 py-3 rounded-2xl bg-red-50 text-red-700 text-body-large max-w-4xl">
          {turn.error}
        </div>
      )}
    </>
  );
}
