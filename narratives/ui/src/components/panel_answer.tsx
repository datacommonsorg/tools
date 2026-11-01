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
 * @fileoverview Renders a completed answer as a side-panel card: markdown body, sources, charts, disclaimer, export, and follow-ups.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  type AnswerBlock,
  type ChatTurn,
  getTurnCharts,
} from "@/src/hooks/use_sse_chat";
import { ChartTile } from "./tile_chart";
import { DisclaimerNote } from "./note_disclaimer";
import {
  ProvenanceInspector,
  isProvenanceDebugEnabled,
} from "./panel_debug_provenance";
import { ExportIcon } from "./icons";
import { ExportPdfButton } from "./button_export_pdf";
import { FollowUpQuestions } from "./questions_follow_up";
import { ResponseCard } from "./card_response";
import { Tooltip } from "./tooltip";
import { CitationNumberingProvider } from "./chip_citation";
import { CitationsList } from "./list_citations";
import { downloadPdf } from "@/src/utils/download_pdf";
import {
  calculateStreamDurationMs,
  countWords,
} from "@/src/utils/rehype_stream_words";
import { Toast } from "./toast";
import { CardHeader } from "./card_header";

/**
 * Wraps the full answer in a "Side panel" card (Figma node 3427:16726):
 *   • Outer: 1px border (--color-border), 16px radius
 *   • Toolbar header (16/16/0/0 radius, #F9F9F9 fill, padding 12 12 12 20):
 *       left  = title text (user's question) — Title S, 14/20 Medium
 *       right = "Export PDF" outline pill (#F0F4F9 fill)
 *   • Content body (#FFFFFF) hosts the existing sections.
 */

interface AnswerPanelProps {
  turn: ChatTurn;
  isStreaming: boolean;
  onAsk?: (question: string) => void;
  /**
   * Display label for each of this turn's provenance rows, as
   * `assignCitationNumbers` worked them out across the whole thread. Left
   * undefined the panel falls back to numbering itself from 1.
   */
  citationNumbers?: number[];
  /** Which turn this is, so its anchors cannot collide with another's. */
  turnIndex?: number;
  /**
   * Called once every chart has settled or {@link ANSWER_SETTLE_MAX_MS} has
   * passed. Passing it makes the panel wait for its charts before it reports
   * settled, so the caller can keep it hidden until its layout is final.
   */
  onSettled?: () => void;
}

/**
 * How far the panel's reveal has progressed. `settling`: laid out but waiting for
 * its charts to finish loading. Charts that settle within
 * {@link ANSWER_SETTLE_MAX_MS} move nothing once the panel is shown; a chart
 * that draws or reports no data after the cap can still change its height.
 * `revealing`: the text is revealing word by word and everything else is
 * hidden. `revealed`: everything is shown.
 */
type RevealPhase = "settling" | "revealing" | "revealed";

/**
 * Returns the phase a panel mounts in. It settles first only when a caller
 * waits on `onSettled`; otherwise it reveals at once when it should reveal
 * and is shown in full when it should not.
 */
function getInitialPhase(
  shouldReveal: boolean,
  isAwaited: boolean,
): RevealPhase {
  if (isAwaited) return "settling";
  if (shouldReveal) return "revealing";
  return "revealed";
}

/** Media query for the user's reduced-motion preference. */
const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

/**
 * Longest the panel waits for its charts to settle before revealing anyway,
 * in milliseconds, so a slow chart cannot hold back the answer.
 */
export const ANSWER_SETTLE_MAX_MS = 2000;

const COLOR_BORDER = "var(--color-border)";
/**
 * Per Figma 3427-16728 the content body fills the narrative surface — light gray in the
 * neutral theme, tinted blue (#F5FAFF) in the Base DC one.
 *
 * The body takes --color-surface-narrative rather than --color-surface-soft:
 * the narrative token exists so an instance can tint the answer tile without
 * moving every other soft surface, and SkeletonCard already paints with it. On
 * --color-surface-soft the card rendered blue while streaming and then flipped
 * to gray the moment the content replaced the skeleton.
 */
const COLOR_BODY_BG = "var(--color-surface-narrative)";
const COLOR_TONAL_CONTAINER = "var(--color-theme-container)";
const COLOR_TONAL_CONTENT = "var(--color-on-theme-container)";
const FONT_LABEL =
  '"Google Sans Text", "Google Sans", Inter, system-ui, sans-serif';

/** The full answer card: toolbar with export action, markdown body, charts, sources, and follow-ups. */
export function AnswerPanel({
  turn,
  isStreaming,
  onAsk,
  citationNumbers,
  turnIndex,
  onSettled,
}: AnswerPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const hasCharts = getTurnCharts(turn).length > 0;
  // A panel that mounts mid-stream, or whose caller waits on `onSettled`, is
  // taking over from the skeleton, so it reveals its text in reading order.
  // The caller check covers a stream that closed in the same render as the
  // terminal event. A panel with a waiting caller settles its charts first,
  // so charts that settle within the cap load while hidden. Under reduced
  // motion there is no word reveal, so the whole card, export controls
  // included, shows as soon as it settles.
  const [shouldReveal] = useState(
    () =>
      (isStreaming || onSettled !== undefined) &&
      !window.matchMedia(REDUCED_MOTION_QUERY).matches,
  );
  const [phase, setPhase] = useState<RevealPhase>(() =>
    getInitialPhase(shouldReveal, onSettled !== undefined),
  );
  const streamMs = shouldReveal
    ? calculateStreamDurationMs(turn.text)
    : undefined;
  const [settledChartIndices, setSettledChartIndices] = useState<
    ReadonlySet<number>
  >(() => new Set());
  const markChartSettled = useCallback((index: number) => {
    setSettledChartIndices((prev) => {
      if (prev.has(index)) return prev;
      const next = new Set(prev);
      next.add(index);
      return next;
    });
  }, []);
  // True at once for a turn with no chart blocks.
  const areChartsSettled = turn.blocks.every(
    (block) => block.type !== "chart" || settledChartIndices.has(block.index),
  );
  useEffect(() => {
    if (phase !== "settling") return;
    const nextPhase: RevealPhase = shouldReveal ? "revealing" : "revealed";
    if (areChartsSettled) {
      setPhase(nextPhase);
      return;
    }
    const timer = window.setTimeout(
      () => setPhase(nextPhase),
      ANSWER_SETTLE_MAX_MS,
    );
    return () => window.clearTimeout(timer);
  }, [phase, areChartsSettled, shouldReveal]);
  useEffect(() => {
    if (phase !== "revealing" || streamMs === undefined) return;
    const timer = window.setTimeout(() => setPhase("revealed"), streamMs);
    return () => window.clearTimeout(timer);
  }, [phase, streamMs]);
  // Held in a ref so an inline arrow from the caller does not re-fire the
  // effect; `isSettling` changes at most once, so the call happens once.
  const onSettledRef = useRef(onSettled);
  onSettledRef.current = onSettled;
  const isSettling = phase === "settling";
  useEffect(() => {
    if (!isSettling) onSettledRef.current?.();
  }, [isSettling]);
  const isRevealed = phase === "revealed";
  /**
   * `turn.provenance` is the sources that actually supplied the answer's
   * numbers. The backend decides membership from which facet each observation
   * call served, so a source the agent only looked at on the way there is not
   * in here. Position n is `[n]`, in the prose and in the list below, because
   * the synthesis prompt was handed this same list already numbered.
   *
   * Nothing is filtered or dropped here, on purpose. Either would make what
   * the reader sees depend on the agent having cited exactly right, and it does
   * not: it under-cites, and a source dropped for want of a marker leaves its
   * figures with no attribution at all. Selection belongs where the evidence
   * is -- the tool results -- not in the renderer. Relabelling is a different
   * thing: `citationNumbers` changes only which numeral a position wears.
   */
  const hasCitations = turn.provenance.length > 0;
  // One export state for the card: the toolbar pill and the in-content button
  // are the same action in two placements, so they share a busy flag and a
  // single confirmation rather than each raising their own.
  const [exporting, setExporting] = useState(false);
  const [exported, setExported] = useState(false);
  // Memoized: a fresh object re-renders every chip on any state change here,
  // including the export flags above.
  const numbering = useMemo(
    () => ({ numbers: citationNumbers, turnIndex }),
    [citationNumbers, turnIndex],
  );

  const onExport = async () => {
    if (exporting) return;
    setExporting(true);
    try {
      await downloadPdf(panelRef.current, turn.userMessage);
      setExported(true);
    } finally {
      setExporting(false);
    }
  };

  return (
    <CitationNumberingProvider value={numbering}>
    <div
      ref={panelRef}
      className="self-start shrink-0 w-full max-w-4xl flex flex-col overflow-hidden"
      style={{
        border: `1px solid ${COLOR_BORDER}`,
        borderRadius: 16,
        // Outer takes the body color so the rounded corners of the
        // body section match the card. Toolbar paints white on top.
        background: COLOR_BODY_BG,
      }}
    >
      {/* Toolbar header, shared with SkeletonCard. Only expose the toolbar
          pill once the turn is fully streamed — otherwise clicking it while
          the ChartTile's DataCommons web component is still hydrating
          produces a PDF missing the chart. This matches the filled "Export
          PDF" button below, which also waits for status === "done". */}
      <CardHeader title={turn.userMessage}>
        {turn.status === "done" && isRevealed && (
          <>
            {/* Opens the provenance slide-over. Only under ?debug=provenance,
                so end users never see it. */}
            {isProvenanceDebugEnabled() && <ProvenanceInspector turn={turn} />}
            <ToolbarExportPdfPill onExport={onExport} busy={exporting} />
          </>
        )}
      </CardHeader>

      {/* Content body: everything after and between the text blocks stays
          hidden until the text has finished revealing. */}
      <div
        className={`flex flex-col p-4 sm:p-6 motion-safe:[&>:not(.markdown-body)]:transition-opacity motion-safe:[&>:not(.markdown-body)]:duration-300${
          isRevealed ? "" : " motion-safe:[&>:not(.markdown-body)]:opacity-0"
        }`}
        style={{
          gap: 16,
          background: COLOR_BODY_BG,
        }}
      >
        {/* 1. The answer: text and chart blocks in emission order. */}
        <AnswerBlocks
          turn={turn}
          phase={phase}
          streamMs={streamMs}
          onChartSettled={markChartSettled}
        />

        {/* 2. Truncation notice: the agent ran out of research steps, so
            this answer rests on less data than it meant to gather. Not styled
            as an error: the answer is usable, just less complete. */}
        {turn.truncated && (
          <p
            className="m-0 text-body-medium text-on-surface-variant"
            role="status"
          >
            This answer may be incomplete — the agent reached its limit on
            research steps before it finished gathering data.
          </p>
        )}

        {/* 3. Citations: at the end of the document, above the disclaimer,
            where a reader who has finished the answer looks for them. */}
        {hasCitations && (
          <CitationsList
            sources={turn.provenance}
            numbers={citationNumbers}
            turnIndex={turnIndex}
          />
        )}

        {/* 4. Disclaimer */}
        {(hasCharts || hasCitations) && <DisclaimerNote />}

        {/* 5. Export PDF (filled, in-content) */}
        {turn.status === "done" && isRevealed && (
          <ExportPdfButton onExport={onExport} busy={exporting} />
        )}

        {/* 6. Follow-up questions: agent-generated, self-contained. Hidden
            when the agent returned none (no static fallback).

            Marked non-print: they are buttons that ask a NEW question, so they
            are an invitation to keep browsing rather than part of the answer
            being exported. In a saved PDF they read as unanswered questions
            belonging to the document, which is the opposite of their meaning. */}
        {turn.status === "done" && (turn.followUps?.length ?? 0) > 0 && (
          <div data-non-print="true">
            <FollowUpQuestions questions={turn.followUps ?? []} onAsk={onAsk} />
          </div>
        )}
      </div>
      {exported && (
        <Toast message="PDF downloaded" onDismiss={() => setExported(false)} />
      )}
    </div>
    </CitationNumberingProvider>
  );
}

interface AnswerBlocksProps {
  turn: ChatTurn;
  phase: RevealPhase;
  /** Duration of the whole text reveal; undefined when the panel does not reveal. */
  streamMs?: number;
  onChartSettled: (index: number) => void;
}

/** One text block's share of the reveal, in milliseconds. */
interface TextRevealWindow {
  startMs: number;
  durationMs: number;
}

/**
 * Renders a turn's blocks in emission order, as direct children of the
 * panel body: each text block through the Markdown renderer and each chart
 * block through a one-item chart tile that reports when it has settled. The
 * text blocks share one reveal in reading order, and the word animations
 * start only once `phase` is `revealing`.
 */
function AnswerBlocks({
  turn,
  phase,
  streamMs,
  onChartSettled,
}: AnswerBlocksProps) {
  const blocks = turn.blocks;
  const schedule =
    streamMs === undefined ? undefined : scheduleTextReveal(blocks, streamMs);
  return (
    <>
      {blocks.map((block) => {
        if (block.type === "chart") {
          return (
            <ChartTile
              key={block.index}
              config={{ shouldRender: true, charts: [block.chart] }}
              onSettled={() => onChartSettled(block.index)}
            />
          );
        }
        const revealWindow = schedule?.get(block.index);
        return (
          <ResponseCard
            key={block.index}
            title={turn.userMessage}
            body={block.markdown}
            streamMs={revealWindow?.durationMs}
            streamStartMs={revealWindow?.startMs}
            revealing={phase === "revealing"}
            sources={turn.provenance}
            bare
          />
        );
      })}
    </>
  );
}

/**
 * Splits one reveal of `totalMs` across the text blocks in reading order, in
 * proportion to their word counts, so each block starts where the previous
 * one ends. Returns each text block's window keyed by its block index.
 */
function scheduleTextReveal(
  blocks: AnswerBlock[],
  totalMs: number,
): Map<number, TextRevealWindow> {
  const wordCounts = blocks.map((block) =>
    block.type === "text" ? countWords(block.markdown) : 0,
  );
  const totalWords = wordCounts.reduce((sum, count) => sum + count, 0);
  const msPerWord = totalMs / Math.max(totalWords, 1);
  const schedule = new Map<number, TextRevealWindow>();
  let wordsBefore = 0;
  blocks.forEach((block, position) => {
    if (block.type !== "text") return;
    const words = wordCounts[position];
    schedule.set(block.index, {
      startMs: wordsBefore * msPerWord,
      durationMs: words * msPerWord,
    });
    wordsBefore += words;
  });
  return schedule;
}

/**
 * Tonal "Export PDF" pill in the card's toolbar header, with the `output`
 * leading icon. Shares the tonal container/content tokens and the icon with
 * the <ExportPdfButton /> inside the card body, so the two read as one control
 * in two placements rather than two different buttons.
 */
function ToolbarExportPdfPill({
  onExport,
  busy,
}: {
  onExport: () => void;
  busy: boolean;
}) {
  return (
    <Tooltip label="Download this answer as a PDF">
    <button
      type="button"
      onClick={onExport}
      disabled={busy}
      data-non-print="true"
      className="inline-flex items-center cursor-pointer hover:opacity-90"
      style={{
        background: COLOR_TONAL_CONTAINER,
        color: COLOR_TONAL_CONTENT,
        border: 0,
        borderRadius: 999,
        padding: "6px 16px",
        gap: 8,
        fontFamily: FONT_LABEL,
        fontSize: 14,
        lineHeight: "20px",
        fontWeight: 500,
      }}
      aria-label="Export PDF"
    >
      <ExportIcon size="xs" />
      <span>Export PDF</span>
    </button>
    </Tooltip>
  );
}
