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

import {
  type RefObject,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { ExportPdfButton } from '@/src/components/button_export_pdf';
import { CardHeader } from '@/src/components/card_header';
import { ResponseCard } from '@/src/components/card_response';
import { CitationNumberingProvider } from '@/src/components/chip_citation';
import {
  isSectionHeading,
  SectionHeading,
} from '@/src/components/heading_section';
import { ExportIcon } from '@/src/components/icons';
import { Link } from '@/src/components/link';
import { CitationsList } from '@/src/components/list_citations';
import { DisclaimerNote } from '@/src/components/note_disclaimer';
import { DebugPanel } from '@/src/components/panel_debug/panel_debug';
import { isTurnSettled } from '@/src/components/panel_debug/report_debug';
import { FollowUpQuestions } from '@/src/components/questions_follow_up';
import { AnswerSection } from '@/src/components/section_answer';
import { ChartTile } from '@/src/components/tile_chart';
import { Toast } from '@/src/components/toast';
import { Tooltip } from '@/src/components/tooltip';
import {
  formatAnswerHeader,
  SUGGEST_DATASET_LINK_LABEL,
  SUGGEST_DATASET_PROMPT,
  SUGGEST_DATASET_URL,
} from '@/src/config/copy_chat';
import { IS_PDF_EXPORT_ENABLED } from '@/src/config/features';
import { REDUCED_MOTION_QUERY } from '@/src/config/motion';
import { useDebugMode } from '@/src/hooks/use_debug_mode';
import {
  type AnswerBlock,
  type ChartItem,
  type ChatTurn,
  getTurnCharts,
} from '@/src/hooks/use_sse_chat';
import { downloadPdf } from '@/src/utils/download_pdf';
import {
  calculateStreamDurationMs,
  countWords,
} from '@/src/utils/rehype_stream_words';

/**
 * Wraps the full answer in a "Side panel" card (Figma node 3427:16726):
 *   • Outer: 1px border (--color-border), 16px radius
 *   • Toolbar header (16/16/0/0 radius, #F9F9F9 fill, padding 12 12 12 20):
 *       left  = data label (`formatAnswerHeader`): Title S, 14/20 Medium
 *       right = "Export PDF" outline pill (#F0F4F9 fill), hidden while
 *               `IS_PDF_EXPORT_ENABLED` is false
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
  /** The follow-up prompt, which takes focus when the export toast closes. */
  promptTextareaRef?: RefObject<HTMLTextAreaElement | null>;
}

/**
 * How far the panel's reveal has progressed. `settling`: laid out but waiting for
 * its charts to finish loading. Charts that settle within
 * {@link ANSWER_SETTLE_MAX_MS} move nothing once the panel is shown; a chart
 * that draws or reports no data after the cap can still change its height.
 * `revealing`: the text is revealing word by word, charts show their skeleton,
 * and everything else is hidden. `revealed`: everything is shown.
 */
type RevealPhase = 'settling' | 'revealing' | 'revealed';

/**
 * Returns the phase a panel mounts in. It settles first only when a caller
 * waits on `onSettled`; otherwise it reveals at once when it should reveal
 * and is shown in full when it should not.
 */
function getInitialPhase(
  shouldReveal: boolean,
  isAwaited: boolean,
): RevealPhase {
  if (isAwaited) return 'settling';
  if (shouldReveal) return 'revealing';
  return 'revealed';
}

/**
 * Longest the panel waits for its charts to settle before revealing anyway,
 * in milliseconds, so a slow chart cannot hold back the answer.
 */
export const ANSWER_SETTLE_MAX_MS = 2000;

/**
 * Fade of the answer body's children other than text, chart tiles, section
 * headings, and sections, which hold their place while the text reveals.
 * Written out in full, here and in {@link HIDE_NON_TEXT_CLASS}, so Tailwind
 * finds the classes.
 */
const REVEAL_TRANSITION_CLASS =
  'motion-safe:[&>:not(.markdown-body,.dc-charts-container,.answer-heading,.answer-section)]:transition-opacity motion-safe:[&>:not(.markdown-body,.dc-charts-container,.answer-heading,.answer-section)]:duration-300';

/** Hides the children {@link REVEAL_TRANSITION_CLASS} fades, until revealed. */
export const HIDE_NON_TEXT_CLASS =
  'motion-safe:[&>:not(.markdown-body,.dc-charts-container,.answer-heading,.answer-section)]:opacity-0';

/** The full answer card: toolbar with export action, markdown body, charts, sources, and follow-ups. */
export function AnswerPanel({
  turn,
  isStreaming,
  onAsk,
  citationNumbers,
  turnIndex,
  onSettled,
  promptTextareaRef,
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
    (block) => block.type !== 'chart' || settledChartIndices.has(block.index),
  );
  useEffect(() => {
    if (phase !== 'settling') return;
    const nextPhase: RevealPhase = shouldReveal ? 'revealing' : 'revealed';
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
    if (phase !== 'revealing' || streamMs === undefined) return;
    const timer = window.setTimeout(() => setPhase('revealed'), streamMs);
    return () => window.clearTimeout(timer);
  }, [phase, streamMs]);
  // Held in a ref so an inline arrow from the caller does not re-fire the
  // effect; `isSettling` changes at most once, so the call happens once.
  const onSettledRef = useRef(onSettled);
  onSettledRef.current = onSettled;
  const isSettling = phase === 'settling';
  useEffect(() => {
    if (!isSettling) onSettledRef.current?.();
  }, [isSettling]);
  const isRevealed = phase === 'revealed';
  const isDebugEnabled = useDebugMode(isRevealed && isTurnSettled(turn));
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
  // An answer that reports no data has nothing worth exporting, so it offers
  // no PDF. `hasData` is undefined on turns that never report it, which keep
  // the export.
  const shouldOfferExport = turn.hasData !== false;
  // The question already shows in the user's bubble, so the header labels the
  // answer instead.
  const headerTitle = formatAnswerHeader({
    hasData: turn.hasData,
    isTruncated: turn.truncated === true,
    citationCount: turn.provenance.length,
  });
  // A search that finished without matching data ends with the link for
  // proposing a dataset. A search that ended early does not, because the
  // data may exist.
  const shouldSuggestDataset =
    turn.status === 'done' && turn.hasData === false && turn.truncated !== true;
  // One export state for the card: the toolbar pill and the in-content button
  // are the same action in two placements, so they share a busy flag and a
  // single confirmation rather than each raising their own.
  const [exporting, setExporting] = useState(false);
  // When the last export finished; keys the toast so a repeat export remounts
  // it with a fresh dismiss timer.
  const [exportedAt, setExportedAt] = useState<number | null>(null);
  // Memoized: a fresh object re-renders every chip on any state change here,
  // including the export flags above.
  const numbering = useMemo(
    () => ({ numbers: citationNumbers, turnIndex }),
    [citationNumbers, turnIndex],
  );

  const isExportVisible =
    IS_PDF_EXPORT_ENABLED &&
    shouldOfferExport &&
    turn.status === 'done' &&
    isRevealed &&
    areChartsSettled;

  const onExport = async () => {
    if (exporting) return;
    setExporting(true);
    try {
      await downloadPdf(panelRef.current, turn.title ?? turn.userMessage);
      setExportedAt(Date.now());
    } finally {
      setExporting(false);
    }
  };

  return (
    <CitationNumberingProvider value={numbering}>
      {/* Per Figma 3427-16728 the body fills the narrative surface: light gray
        in the neutral theme, tinted blue (#F5FAFF) in the Base DC one. It is
        bg-surface-narrative rather than bg-surface-soft so an instance can
        tint the answer tile without moving every other soft surface, and so
        it matches SkeletonCard: on surface-soft the card rendered blue while
        streaming, then flipped to gray when the content replaced the
        skeleton. The outer card takes the body color too, so the body's
        rounded corners match the card; the toolbar paints white on top. */}
      <div
        ref={panelRef}
        className="self-start shrink-0 w-full max-w-4xl flex flex-col overflow-hidden border border-border rounded-card bg-surface-narrative"
      >
        {/* Toolbar header, shared with SkeletonCard. Only expose the toolbar
          pill once the turn is fully streamed — otherwise clicking it while
          the ChartTile's DataCommons web component is still hydrating
          produces a PDF missing the chart. It also waits for every chart to
          settle, since the reveal can end before a slow chart draws. This
          matches the filled "Export PDF" button below. */}
        <CardHeader title={headerTitle}>
          {isRevealed &&
            isTurnSettled(turn) &&
            (isDebugEnabled || turn.serverReport !== undefined) && (
              <DebugPanel turn={turn} />
            )}
          {isExportVisible && (
            <ToolbarExportPdfPill onExport={onExport} busy={exporting} />
          )}
        </CardHeader>

        {/* Intro block: the agent's title for the answer, a short label for
          the data it presents. Outside the content body so the body's reveal
          does not hide it. An answer without data has no title, and so no
          intro block. The PDF writes the title into the header row as its
          heading, so the export leaves this block out. */}
        {turn.title && (
          <div
            className="px-4 pt-4 sm:px-6 sm:pt-6 bg-surface-narrative"
            data-non-print="true"
          >
            <h1 className="text-title-large-emphasized text-on-surface wrap-break-word">
              {turn.title}
            </h1>
          </div>
        )}

        {/* Content body: everything after and between the text blocks stays
          hidden until the text has finished revealing, except chart tiles,
          section headings, and sections, which hold their space so no gap
          shows. */}
        <div
          className={`@container flex flex-col gap-4 px-4 sm:px-6 pt-3 pb-6 bg-surface-narrative ${REVEAL_TRANSITION_CLASS}${
            isRevealed ? '' : ` ${HIDE_NON_TEXT_CLASS}`
          }`}
        >
          {/* 1. The answer: text and chart blocks in emission order. */}
          <AnswerBlocks
            turn={turn}
            phase={phase}
            streamMs={streamMs}
            onChartSettled={markChartSettled}
          />

          {/* 2. Dataset suggestion: the app's own closing for an answer
            without data, so its wording and link do not depend on the
            model. */}
          {shouldSuggestDataset && (
            <p className="text-body-regular text-on-surface">
              {SUGGEST_DATASET_PROMPT}{' '}
              <Link
                href={SUGGEST_DATASET_URL}
                className="text-theme-primary hover:underline"
              >
                {SUGGEST_DATASET_LINK_LABEL}
              </Link>
            </p>
          )}

          {/* 3. Truncation notice: the agent ran out of research steps, so
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

          {/* 4. Citations: at the end of the document, above the disclaimer,
            where a reader who has finished the answer looks for them. */}
          {hasCitations && (
            <CitationsList
              sources={turn.provenance}
              numbers={citationNumbers}
              turnIndex={turnIndex}
            />
          )}

          {/* 5. Disclaimer */}
          {(hasCharts || hasCitations) && <DisclaimerNote />}

          {/* 6. Export PDF (filled, in-content) */}
          {isExportVisible && (
            <ExportPdfButton onExport={onExport} busy={exporting} />
          )}
        </div>
        {exportedAt !== null && (
          <Toast
            key={exportedAt}
            message="PDF downloaded"
            onDismiss={() => setExportedAt(null)}
            returnFocusRef={promptTextareaRef}
          />
        )}
      </div>
      {/* The agent generates the follow-up questions with each answer. They are
        hidden when the agent returns none, since there is no static fallback,
        and they wait until the text has finished revealing, as the body's
        other non-text children do.

        They sit outside the card because the PDF export clones the card, and
        each question asks something new rather than being part of this
        answer. */}
      {turn.status === 'done' &&
        isRevealed &&
        (turn.followUps?.length ?? 0) > 0 && (
          <div className="px-4 sm:px-6 mb-6">
            <FollowUpQuestions
              questions={turn.followUps ?? []}
              onAsk={onAsk}
              hasData={turn.hasData !== false}
            />
          </div>
        )}
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
 * panel body: each text block through the Markdown renderer, a heading line
 * as a section heading, and each run of consecutive chart blocks through one
 * chart tile, which sets two or three charts side by side when there is room
 * and gives each scatter chart a row of its own, except that a bullet list or
 * table directly followed by a chart renders beside it, stats first, in a
 * section headed by its heading line (see `groupAnswerBlocks`). A tile
 * reports every chart in its run as settled once all of them have. The text
 * blocks share one reveal in reading order, and the word animations start
 * only once `phase` is `revealing`.
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
  const renderText = (block: TextAnswerBlock) => {
    const revealWindow = schedule?.get(block.index);
    return (
      <ResponseCard
        key={block.index}
        title={turn.userMessage}
        body={block.markdown}
        streamMs={revealWindow?.durationMs}
        streamStartMs={revealWindow?.startMs}
        revealing={phase === 'revealing'}
        sources={turn.provenance}
        bare
      />
    );
  };
  return (
    <>
      {groupAnswerBlocks(blocks).map((group) => {
        if (group.type === 'charts') {
          return (
            <ChartTile
              key={group.indices[0]}
              config={{ shouldRender: true, charts: group.charts }}
              onSettled={() => {
                for (const index of group.indices) onChartSettled(index);
              }}
              shouldHoldSkeleton={phase !== 'revealed'}
            />
          );
        }
        const block = group.block;
        if (group.type === 'text') {
          // A heading line reads as a heading whether or not its section
          // has formed yet, so it does not change shape when its chart
          // arrives while the answer streams.
          return isSectionHeading(block.markdown) ? (
            <SectionHeading key={block.index} markdown={block.markdown} />
          ) : (
            renderText(block)
          );
        }
        const { chartIndex, heading } = group;
        return (
          <AnswerSection
            key={heading?.index ?? block.index}
            heading={heading?.markdown}
            stats={renderText(block)}
            isTable={TABLE_BLOCK_START.test(block.markdown)}
            chart={
              <ChartTile
                config={{ shouldRender: true, charts: [group.chart] }}
                onSettled={() => onChartSettled(chartIndex)}
                shouldHoldSkeleton={phase !== 'revealed'}
              />
            }
          />
        );
      })}
    </>
  );
}

type TextAnswerBlock = Extract<AnswerBlock, { type: 'text' }>;
type ChartAnswerBlock = Extract<AnswerBlock, { type: 'chart' }>;

/**
 * One rendered unit of an answer: a text block, a run of chart blocks, or a
 * stats block paired with the one chart that illustrates it.
 */
type AnswerBlockGroup =
  | { type: 'text'; block: TextAnswerBlock }
  | { type: 'charts'; charts: ChartItem[]; indices: number[] }
  | {
      type: 'pair';
      block: TextAnswerBlock;
      chart: ChartItem;
      chartIndex: number;
      /** The heading line above the stats, heading their section. */
      heading?: TextAnswerBlock;
    };

/** Chart kinds that need the full width and are never paired with text. */
const FULL_WIDTH_CHART_TYPES: ReadonlySet<ChartItem['vizType']> = new Set([
  'map',
  'scatter',
]);

/** Matches Markdown that opens with a list item or a table row. */
const STATS_BLOCK_START = /^\s*(?:[-*+]\s|\d+[.)]\s|\|)/;

/** Matches Markdown that opens with a table row. */
const TABLE_BLOCK_START = /^\s*\|/;

/**
 * Whether `text` and the chart after it render side by side: the text is a
 * bullet list or a table, the chart was placed by the model rather than
 * supplied by the server, and it is not a kind that needs the full width.
 * The decision reads no later block, so a pair formed while the answer
 * streams is never regrouped, and its chart tile is never remounted, when
 * more blocks arrive.
 */
function isStatsChartPair(
  text: TextAnswerBlock,
  chart: ChartAnswerBlock,
): boolean {
  return (
    STATS_BLOCK_START.test(text.markdown) &&
    !chart.standalone &&
    !FULL_WIDTH_CHART_TYPES.has(chart.chart.vizType)
  );
}

/**
 * Groups a turn's blocks in order. A bullet list or table directly followed
 * by a chart becomes a pair with that chart, rendered side by side in one
 * section, and a Markdown heading line directly above the list or table
 * joins the pair as its section's heading. Any other run of
 * consecutive chart blocks, including the charts after a pair's chart,
 * becomes one group that renders in a single chart tile. As blocks stream
 * in, the last group may still grow, and a trailing stats block (with its
 * heading) becomes a pair when its chart arrives; a pair, once formed, is
 * never regrouped.
 */
export function groupAnswerBlocks(blocks: AnswerBlock[]): AnswerBlockGroup[] {
  const groups: AnswerBlockGroup[] = [];
  for (const block of blocks) {
    if (block.type === 'text') {
      groups.push({ type: 'text', block });
      continue;
    }
    const last = groups.at(-1);
    if (last?.type === 'text' && isStatsChartPair(last.block, block)) {
      const beforeStats = groups.at(-2);
      const heading =
        beforeStats?.type === 'text' &&
        isSectionHeading(beforeStats.block.markdown)
          ? beforeStats.block
          : undefined;
      groups.splice(heading ? -2 : -1, heading ? 2 : 1, {
        type: 'pair',
        block: last.block,
        chart: block.chart,
        chartIndex: block.index,
        heading,
      });
      continue;
    }
    if (last?.type === 'charts') {
      last.charts.push(block.chart);
      last.indices.push(block.index);
    } else {
      groups.push({
        type: 'charts',
        charts: [block.chart],
        indices: [block.index],
      });
    }
  }
  return groups;
}

/**
 * Splits one reveal of `totalMs` across the text blocks in reading order, in
 * proportion to their word counts, so each block starts where the previous
 * one ends. A heading line renders as a heading, which shows at once, so it
 * takes no share. Returns each revealed text block's window keyed by its
 * block index.
 */
function scheduleTextReveal(
  blocks: AnswerBlock[],
  totalMs: number,
): Map<number, TextRevealWindow> {
  const wordCounts = blocks.map((block) =>
    block.type === 'text' && !isSectionHeading(block.markdown)
      ? countWords(block.markdown)
      : 0,
  );
  const totalWords = wordCounts.reduce((sum, count) => sum + count, 0);
  const msPerWord = totalMs / Math.max(totalWords, 1);
  const schedule = new Map<number, TextRevealWindow>();
  let wordsBefore = 0;
  blocks.forEach((block, position) => {
    if (block.type !== 'text') return;
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
        className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-theme-container text-on-theme-container text-label-large enabled:hover:opacity-90 disabled:opacity-60"
        aria-label="Export PDF"
      >
        <ExportIcon size="xs" />
        <span>Export PDF</span>
      </button>
    </Tooltip>
  );
}
