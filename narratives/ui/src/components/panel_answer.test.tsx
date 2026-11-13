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
 * @fileoverview Tests for how the answer panel renders a turn's text and
 * chart blocks, waits for its charts to settle, and reveals its text.
 */

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ANSWER_SETTLE_MAX_MS,
  AnswerPanel,
} from '@/src/components/panel_answer';
import { DEBUG_PANEL_COPY } from '@/src/components/panel_debug/copy_debug';
import { EXIT_MS, VISIBLE_MS } from '@/src/components/toast';
import { resetDebugModeCacheForTests } from '@/src/hooks/use_debug_mode';
import type { ChartItem, ChatTurn } from '@/src/hooks/use_sse_chat';
import { parseServerDebugReport } from '@/src/types/debug_report';
import { calculateStreamDurationMs } from '@/src/utils/rehype_stream_words';

vi.mock('@/src/utils/download_pdf', () => ({
  downloadPdf: vi.fn().mockResolvedValue(undefined),
}));

const LINE_CHART: ChartItem = {
  vizType: 'line',
  title: 'Population, France',
  variableDcids: ['Count_Person'],
  placeDcids: ['country/FRA'],
};

const INCOME_CHART: ChartItem = {
  vizType: 'line',
  title: 'Median household income, France',
  variableDcids: ['Median_Income_Household'],
  placeDcids: ['country/FRA'],
};

/** A text block and the chart after it, for the pairing cases. */
interface ChartAnswerBlockInput {
  text: string;
  chart: ChartItem;
  standalone?: boolean;
}

/** How often the chart settle poll reads the component, in milliseconds. */
const CHART_POLL_MS = 300;

/**
 * Class that hides the body's non-text children, other than chart tiles and
 * paired stats rows, while the text reveals.
 */
const HIDE_NON_TEXT_CLASS =
  'motion-safe:[&>:not(.markdown-body,.dc-charts-container,.answer-pair)]:opacity-0';

/** Builds a finished turn whose answer arrived as the given blocks. */
const buildTurnWithBlocks = (
  blocks: ChatTurn['blocks'],
  overrides: Partial<ChatTurn> = {},
): ChatTurn => ({
  userMessage: 'What is the population of France?',
  status: 'done',
  toolCalls: [],
  thoughts: [],
  text: blocks
    .flatMap((block) => (block.type === 'text' ? [block.markdown] : []))
    .join('\n\n'),
  blocks,
  provenance: [],
  ...overrides,
});

/** A paragraph, a chart, and a second paragraph. */
const INTERLEAVED_BLOCKS: ChatTurn['blocks'] = [
  { index: 0, type: 'text', markdown: 'France has about 68 million people.' },
  { index: 1, type: 'chart', chart: LINE_CHART },
  { index: 2, type: 'text', markdown: 'The population grew 0.3% last year.' },
];

/** Reads the answer's text bodies and chart cards in document order. */
const readAnswerParts = (container: HTMLElement): string[] =>
  Array.from(container.querySelectorAll('.markdown-body, .dc-chart-card')).map(
    (node) =>
      node.classList.contains('dc-chart-card')
        ? `chart:${node.querySelector('[header]')?.getAttribute('header')}`
        : `text:${node.textContent?.trim()}`,
  );

/** Gives the mounted line chart a shadow root holding a drawn chart. */
const drawLineChart = (container: HTMLElement): void => {
  const element = container.querySelector('datacommons-line');
  if (!element) throw new Error('No datacommons-line element is mounted.');
  element.attachShadow({ mode: 'open' }).innerHTML =
    '<div class="chart-container"><svg></svg></div>';
};

/** Returns the panel body that holds the answer blocks. */
const getBody = (container: HTMLElement): HTMLElement => {
  const body = container.querySelector('.markdown-body')?.parentElement;
  if (!body) throw new Error('No answer body is rendered.');
  return body;
};

let originalUrl = '';

beforeEach(() => {
  originalUrl = window.location.href;
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ status: 'ok', debug_report: 'off' }),
    })),
  );
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  resetDebugModeCacheForTests();
  window.history.replaceState(null, '', originalUrl);
});

describe('AnswerPanel', () => {
  it('renders text and chart blocks in the order they arrived', () => {
    // Test: Interleaved block rendering.
    // Situation: A finished turn whose blocks are a paragraph, a chart, and
    //   a second paragraph.
    // Expectation: The answer body holds a Markdown body for each paragraph
    //   and a chart card for the chart, in that order, as direct children of
    //   the body, and the chart card mounts the chart's web component.
    const { container } = render(
      <AnswerPanel
        turn={buildTurnWithBlocks(INTERLEAVED_BLOCKS)}
        isStreaming={false}
      />,
    );

    expect(readAnswerParts(container)).toEqual([
      'text:France has about 68 million people.',
      'chart:Population, France',
      'text:The population grew 0.3% last year.',
    ]);
    const body = getBody(container);
    for (const markdown of container.querySelectorAll('.markdown-body')) {
      expect(markdown.parentElement).toBe(body);
    }
    expect(container.querySelector('datacommons-line')).not.toBeNull();
  });

  it('holds the reveal while a chart is settling', () => {
    // Test: The settling phase.
    // Situation: A panel mounts mid-stream with a chart block that has not
    //   drawn yet.
    // Expectation: `onSettled` has not fired and no text block carries the
    //   reveal animation class.
    vi.useFakeTimers();
    const onSettled = vi.fn();
    const { container } = render(
      <AnswerPanel
        turn={buildTurnWithBlocks(INTERLEAVED_BLOCKS)}
        isStreaming
        onSettled={onSettled}
      />,
    );

    expect(onSettled).not.toHaveBeenCalled();
    expect(container.querySelectorAll('.markdown-body')).toHaveLength(2);
    expect(container.querySelector('.markdown-stream')).toBeNull();
  });

  it('settles at once when the answer has no charts', () => {
    // Test: A text-only answer.
    // Situation: A panel mounts mid-stream with two text blocks and no
    //   chart blocks.
    // Expectation: `onSettled` fires once and the text starts revealing.
    const onSettled = vi.fn();
    const { container } = render(
      <AnswerPanel
        turn={buildTurnWithBlocks([
          { index: 0, type: 'text', markdown: 'First paragraph.' },
          { index: 1, type: 'text', markdown: 'Second paragraph.' },
        ])}
        isStreaming
        onSettled={onSettled}
      />,
    );

    expect(onSettled).toHaveBeenCalledTimes(1);
    expect(container.querySelectorAll('.markdown-stream')).toHaveLength(2);
  });

  it('ends settling when its chart reports settled', () => {
    // Test: A chart that draws before the cap.
    // Situation: A panel mounts mid-stream with one chart block, and the
    //   chart draws before the next settle poll.
    // Expectation: `onSettled` fires once after that poll, well before the
    //   cap, and the text starts revealing.
    vi.useFakeTimers();
    const onSettled = vi.fn();
    const { container } = render(
      <AnswerPanel
        turn={buildTurnWithBlocks(INTERLEAVED_BLOCKS)}
        isStreaming
        onSettled={onSettled}
      />,
    );

    drawLineChart(container);
    act(() => {
      vi.advanceTimersByTime(CHART_POLL_MS);
    });

    expect(onSettled).toHaveBeenCalledTimes(1);
    expect(container.querySelectorAll('.markdown-stream')).toHaveLength(2);
  });

  it('ends settling at the cap when a chart never settles', () => {
    // Test: The settle cap.
    // Situation: A panel mounts mid-stream with a chart that never draws.
    // Expectation: `onSettled` has not fired just before
    //   ANSWER_SETTLE_MAX_MS and fires once when it passes.
    vi.useFakeTimers();
    const onSettled = vi.fn();
    render(
      <AnswerPanel
        turn={buildTurnWithBlocks(INTERLEAVED_BLOCKS)}
        isStreaming
        onSettled={onSettled}
      />,
    );

    act(() => {
      vi.advanceTimersByTime(ANSWER_SETTLE_MAX_MS - 1);
    });
    expect(onSettled).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(onSettled).toHaveBeenCalledTimes(1);
  });

  it('waits for its charts when the stream has already closed', () => {
    // Test: A handoff from the skeleton after the stream closed.
    // Situation: The panel mounts with `isStreaming` false but with an
    //   `onSettled` caller, and its chart has not drawn yet.
    // Expectation: `onSettled` waits for the chart to draw, and the text
    //   then reveals word by word as in any other handoff.
    vi.useFakeTimers();
    const onSettled = vi.fn();
    const { container } = render(
      <AnswerPanel
        turn={buildTurnWithBlocks(INTERLEAVED_BLOCKS)}
        isStreaming={false}
        onSettled={onSettled}
      />,
    );
    expect(onSettled).not.toHaveBeenCalled();

    drawLineChart(container);
    act(() => {
      vi.advanceTimersByTime(CHART_POLL_MS);
    });

    expect(onSettled).toHaveBeenCalledTimes(1);
    expect(container.querySelectorAll('.markdown-stream')).toHaveLength(2);
  });

  it('reveals at once when no caller waits on it', () => {
    // Test: A mid-stream panel with no `onSettled` caller.
    // Situation: The panel mounts with `isStreaming` true, no `onSettled`,
    //   and a chart block that has not drawn.
    // Expectation: The text carries the reveal animation class immediately,
    //   without any timer advancing.
    vi.useFakeTimers();
    const { container } = render(
      <AnswerPanel
        turn={buildTurnWithBlocks(INTERLEAVED_BLOCKS)}
        isStreaming
      />,
    );

    expect(container.querySelector('.markdown-stream')).not.toBeNull();
  });

  it('starts each text block where the previous one ended', () => {
    // Test: One reveal across text blocks.
    // Situation: A text-only panel mounts mid-stream with a three-word block
    //   and a two-word block, five words revealed over 100ms.
    // Expectation: The first block's words start at 0ms, 20ms, and 40ms, and
    //   the second block's first word starts at 60ms.
    const { container } = render(
      <AnswerPanel
        turn={buildTurnWithBlocks([
          { index: 0, type: 'text', markdown: 'one two three' },
          { index: 1, type: 'text', markdown: 'four five' },
        ])}
        isStreaming
      />,
    );

    const [first, second] = Array.from(
      container.querySelectorAll('.markdown-body'),
    );
    const readDelays = (body: Element): string[] =>
      Array.from(body.querySelectorAll<HTMLElement>('.stream-word')).map(
        (word) => word.style.animationDelay,
      );
    expect(readDelays(first)).toEqual(['0ms', '20ms', '40ms']);
    expect(readDelays(second)[0]).toBe('60ms');
  });

  it('shows everything at once when it neither reveals nor is awaited', () => {
    // Test: A panel that mounts after the stream closed, with no caller
    //   waiting on it.
    // Situation: `isStreaming` is false and no `onSettled` is given.
    // Expectation: Without advancing any timer, no text block carries the
    //   reveal animation, the body does not hide its non-text children, and
    //   the Export PDF control renders.
    vi.useFakeTimers();
    const { container } = render(
      <AnswerPanel
        turn={buildTurnWithBlocks([
          { index: 0, type: 'text', markdown: 'France has about 68 million.' },
        ])}
        isStreaming={false}
      />,
    );

    expect(container.querySelector('.markdown-stream')).toBeNull();
    expect(getBody(container).className).not.toContain(HIDE_NON_TEXT_CLASS);
    expect(
      screen.queryAllByRole('button', { name: 'Export PDF' }).length,
    ).toBeGreaterThan(0);
  });

  it('restarts the export toast when the user exports again', async () => {
    // Test: A second PDF export while the confirmation is still showing.
    // Situation: The user exports, then exports again shortly before the
    //   first toast's VISIBLE_MS runs out.
    // Expectation: The toast is still showing once the first toast's window
    //   has passed, because the second export started a fresh one.
    vi.useFakeTimers();
    render(
      <AnswerPanel
        turn={buildTurnWithBlocks([
          { index: 0, type: 'text', markdown: 'France has about 68 million.' },
        ])}
        isStreaming={false}
      />,
    );
    const exportPdf = async () => {
      await act(async () => {
        fireEvent.click(
          screen.getAllByRole('button', { name: 'Export PDF' })[0],
        );
      });
    };

    await exportPdf();
    expect(screen.getByText('PDF downloaded')).toBeTruthy();
    act(() => vi.advanceTimersByTime(VISIBLE_MS - 1000));
    await exportPdf();
    // Two steps: the exit timer is only scheduled once React commits the
    // leaving state, after the first advance returns.
    act(() => vi.advanceTimersByTime(2000));
    act(() => vi.advanceTimersByTime(EXIT_MS));

    expect(screen.queryByText('PDF downloaded')).not.toBeNull();
  });

  it('shows the whole card at once under reduced motion', () => {
    // Test: The reveal under `prefers-reduced-motion: reduce`.
    // Situation: The user prefers reduced motion, and a text-only panel
    //   mounts mid-stream on a finished turn.
    // Expectation: Without advancing any timer, no text block carries the
    //   reveal animation, the body does not hide its non-text children, and
    //   the Export PDF control renders.
    vi.useFakeTimers();
    vi.stubGlobal(
      'matchMedia',
      (query: string): Pick<MediaQueryList, 'matches' | 'media'> => ({
        matches: query === '(prefers-reduced-motion: reduce)',
        media: query,
      }),
    );
    const { container } = render(
      <AnswerPanel
        turn={buildTurnWithBlocks([
          { index: 0, type: 'text', markdown: 'France has about 68 million.' },
        ])}
        isStreaming
      />,
    );

    expect(container.querySelector('.markdown-stream')).toBeNull();
    expect(getBody(container).className).not.toContain(HIDE_NON_TEXT_CLASS);
    expect(
      screen.queryAllByRole('button', { name: 'Export PDF' }).length,
    ).toBeGreaterThan(0);
  });

  it('holds a drawn chart behind its skeleton until the reveal ends', () => {
    // Test: The chart skeleton during the reveal.
    // Situation: A panel mounts mid-stream with a long paragraph and a chart
    //   block whose chart draws before the text has finished revealing.
    // Expectation: The chart card's skeleton overlay stays visible while the
    //   text reveals, and hides once the reveal duration passes.
    vi.useFakeTimers();
    const turn = buildTurnWithBlocks([
      { index: 0, type: 'text', markdown: 'France grew. '.repeat(100) },
      { index: 1, type: 'chart', chart: LINE_CHART },
    ]);
    const { container } = render(<AnswerPanel turn={turn} isStreaming />);
    const overlay = container.querySelector(
      '.dc-chart-card > [aria-hidden="true"]',
    );

    drawLineChart(container);
    act(() => {
      vi.advanceTimersByTime(CHART_POLL_MS);
    });
    expect(overlay?.className).not.toContain('invisible');

    act(() => {
      vi.advanceTimersByTime(calculateStreamDurationMs(turn.text));
    });
    expect(overlay?.className).toContain('invisible');
  });

  it('withholds the export controls until its charts settle', () => {
    // Test: Export gating on charts.
    // Situation: A panel mounts mid-stream with a chart that has not drawn;
    //   the settle cap passes and the text reveal ends before it draws.
    // Expectation: No Export PDF control renders until the chart draws.
    vi.useFakeTimers();
    const turn = buildTurnWithBlocks(INTERLEAVED_BLOCKS);
    const { container } = render(
      <AnswerPanel turn={turn} isStreaming onSettled={vi.fn()} />,
    );

    act(() => {
      vi.advanceTimersByTime(ANSWER_SETTLE_MAX_MS);
    });
    act(() => {
      vi.advanceTimersByTime(calculateStreamDurationMs(turn.text));
    });
    expect(
      screen.queryAllByRole('button', { name: 'Export PDF' }),
    ).toHaveLength(0);

    drawLineChart(container);
    act(() => {
      vi.advanceTimersByTime(CHART_POLL_MS);
    });
    expect(
      screen.queryAllByRole('button', { name: 'Export PDF' }).length,
    ).toBeGreaterThan(0);
  });

  it('hides non-text children and the export controls until the reveal ends', () => {
    // Test: Hiding during the reveal.
    // Situation: A text-only panel mounts mid-stream on a finished turn, so
    //   it reveals at once.
    // Expectation: While the text reveals, the body hides its non-text
    //   children and no Export PDF control renders; once the reveal duration
    //   passes, the hiding class is gone and the export controls render.
    vi.useFakeTimers();
    const turn = buildTurnWithBlocks([
      { index: 0, type: 'text', markdown: 'France has about 68 million.' },
    ]);
    const { container } = render(<AnswerPanel turn={turn} isStreaming />);

    expect(getBody(container).className).toContain(HIDE_NON_TEXT_CLASS);
    expect(
      screen.queryAllByRole('button', { name: 'Export PDF' }),
    ).toHaveLength(0);

    act(() => {
      vi.advanceTimersByTime(calculateStreamDurationMs(turn.text));
    });

    expect(getBody(container).className).not.toContain(HIDE_NON_TEXT_CLASS);
    expect(
      screen.queryAllByRole('button', { name: 'Export PDF' }).length,
    ).toBeGreaterThan(0);
  });

  it('hides the follow-up questions until the reveal ends', () => {
    // Test: Follow-ups during the reveal.
    // Situation: A finished text-only turn with one follow-up question mounts
    //   mid-stream, so its text reveals at once.
    // Expectation: The follow-up question does not render while the text
    //   reveals, and renders once the reveal duration passes.
    vi.useFakeTimers();
    const turn = buildTurnWithBlocks(
      [{ index: 0, type: 'text', markdown: 'France has about 68 million.' }],
      { followUps: ['How has it changed since 2000?'] },
    );
    render(<AnswerPanel turn={turn} isStreaming />);
    const followUp = { name: 'How has it changed since 2000?' };

    expect(screen.queryByRole('button', followUp)).toBeNull();

    act(() => {
      vi.advanceTimersByTime(calculateStreamDurationMs(turn.text));
    });

    expect(screen.getByRole('button', followUp)).not.toBeNull();
  });

  it('opens with the question as its h1, visible during the reveal', () => {
    // Test: Intro block.
    // Situation: A streaming answer that has not finished revealing.
    // Expectation: The question is the panel's level-one heading and is not
    //   inside the content body the reveal hides.
    const turn = buildTurnWithBlocks([
      { index: 0, type: 'text', markdown: 'France has about 68 million.' },
    ]);
    render(<AnswerPanel turn={turn} isStreaming />);
    const heading = screen.getByRole('heading', { level: 1 });

    expect(heading.textContent).toBe(turn.userMessage);
    expect(heading.closest('[class*="opacity-0"]')).toBeNull();
  });

  describe('stats and chart pairing', () => {
    const BULLETS =
      '- **Long-term trend:** Life expectancy rose 24.14% since 1960.\n' +
      '- **Historical peak:** It peaked at 84.56 years in 2020.';
    const TABLE =
      '| Country | Infant mortality rate (2024) |\n' +
      '| --- | --- |\n| Japan | 1.8 |\n| Italy | 2.3 |';
    const SCATTER_CHART: ChartItem = {
      vizType: 'scatter',
      title: 'Income and rent',
      variableDcids: ['Median_Income_Household', 'Median_GrossRent'],
      parentPlace: 'country/USA',
      childPlaceType: 'State',
    };
    const MAP_CHART: ChartItem = {
      vizType: 'map',
      title: 'Unemployment rate across states',
      variableDcids: ['UnemploymentRate_Person'],
      parentPlace: 'country/USA',
      childPlaceType: 'State',
    };
    const renderBlocks = (blocks: ChatTurn['blocks']) =>
      render(
        <AnswerPanel turn={buildTurnWithBlocks(blocks)} isStreaming={false} />,
      ).container;

    it.each([
      ['a bullet list', BULLETS],
      ['a table', TABLE],
    ])('sets %s beside the chart that follows it', (_, markdown) => {
      // Test: Pairing of a stats block with its chart.
      // Situation: A headline paragraph, then a bullet list or a table
      //   directly followed by one line chart.
      // Expectation: The stats block and the chart render in one paired row,
      //   stats first; the headline stays outside it, full width.
      const container = renderBlocks([
        { index: 0, type: 'text', markdown: 'Life expectancy reached 84.' },
        { index: 1, type: 'text', markdown },
        { index: 2, type: 'chart', chart: LINE_CHART },
      ]);

      const pairs = container.querySelectorAll('.answer-pair');
      expect(pairs).toHaveLength(1);
      expect(
        Array.from(pairs[0].children).map((child) =>
          child.classList.contains('markdown-body') ? 'text' : 'chart',
        ),
      ).toEqual(['text', 'chart']);
      expect(pairs[0].textContent).not.toContain('Life expectancy reached 84.');
      // The paired stats drop their bullet markers, and only bullet stats,
      // not a table, sit lower than the chart's top edge.
      expect(pairs[0].className).toContain('[&_ul]:list-none');
      expect(pairs[0].className.includes('[&>:first-child]:pt-1')).toBe(
        markdown === BULLETS,
      );
    });

    it('opens the stats column of a bullet list with its lead-in line', () => {
      // Test: A lead-in line joins its bullets in the paired row.
      // Situation: A headline paragraph, a one-line lead-in ending with a
      //   colon, then a bullet list directly followed by its chart.
      // Expectation: The lead-in and the bullets share the row's first
      //   column, lead-in first, and the column sits 4px below the chart's
      //   top edge side by side; the headline stays outside the row.
      const container = renderBlocks([
        { index: 0, type: 'text', markdown: 'Life expectancy reached 84.' },
        {
          index: 1,
          type: 'text',
          markdown: 'Female life expectancy in Japan and France:',
        },
        { index: 2, type: 'text', markdown: BULLETS },
        { index: 3, type: 'chart', chart: LINE_CHART },
      ]);

      const pairs = container.querySelectorAll('.answer-pair');
      expect(pairs).toHaveLength(1);
      const [column, chart] = Array.from(pairs[0].children);
      expect(chart.classList.contains('dc-charts-container')).toBe(true);
      expect(column.children[0].textContent).toBe(
        'Female life expectancy in Japan and France:',
      );
      expect(column.children).toHaveLength(2);
      expect(pairs[0].textContent).not.toContain('Life expectancy reached 84.');
      expect(pairs[0].className).toContain('[&>:first-child]:pt-1');
    });

    it("keeps a table's lead-in line full width above the row", () => {
      // Test: A table's card stays level with its chart's.
      // Situation: A one-line lead-in ending with a colon, then a table
      //   directly followed by its chart.
      // Expectation: The lead-in renders outside the paired row, whose first
      //   child is the table itself, with no top space.
      const container = renderBlocks([
        {
          index: 0,
          type: 'text',
          markdown: 'The ten highest are Puerto Rico and nine states:',
        },
        { index: 1, type: 'text', markdown: TABLE },
        { index: 2, type: 'chart', chart: LINE_CHART },
      ]);

      const pair = container.querySelector('.answer-pair');
      expect(pair?.textContent).not.toContain('The ten highest are');
      expect(pair?.children[0].classList.contains('markdown-body')).toBe(true);
      expect(pair?.className).not.toContain('[&>:first-child]:pt-1');
    });

    it('leaves a paragraph that is not a lead-in line outside the row', () => {
      // Test: Only a one-line lead-in ending with a colon joins the row.
      // Situation: A sentence that ends with a full stop sits directly above
      //   a bullet list and its chart.
      // Expectation: The sentence renders full width, outside the paired row.
      const container = renderBlocks([
        { index: 0, type: 'text', markdown: 'Japan leads on both measures.' },
        { index: 1, type: 'text', markdown: BULLETS },
        { index: 2, type: 'chart', chart: LINE_CHART },
      ]);

      const pair = container.querySelector('.answer-pair');
      expect(pair?.textContent).not.toContain('Japan leads on both measures.');
      expect(pair?.children[0].classList.contains('markdown-body')).toBe(true);
    });

    it.each<[string, ChartAnswerBlockInput]>([
      [
        'prose rather than a list or table',
        { text: 'France has about 68 million.', chart: LINE_CHART },
      ],
      ['a scatter chart', { text: BULLETS, chart: SCATTER_CHART }],
      ['a map', { text: BULLETS, chart: MAP_CHART }],
      [
        'a chart the server supplied',
        { text: BULLETS, chart: LINE_CHART, standalone: true },
      ],
    ])('keeps the chart full width after %s', (_, input) => {
      // Test: Charts that are never paired.
      // Situation: A chart follows prose, is a scatter or a map, or is a
      //   default chart the server appended.
      // Expectation: No paired row renders; the chart stands alone.
      const container = renderBlocks([
        { index: 0, type: 'text', markdown: input.text },
        {
          index: 1,
          type: 'chart',
          chart: input.chart,
          ...(input.standalone ? { standalone: true } : {}),
        },
      ]);

      expect(container.querySelector('.answer-pair')).toBeNull();
      expect(container.querySelectorAll('.dc-charts-container')).toHaveLength(
        1,
      );
    });

    it('does not pair a stats block followed by two charts', () => {
      // Test: A stats block followed by charts back to back.
      // Situation: A table directly followed by two line charts.
      // Expectation: No paired row renders, and both charts share one tile.
      const container = renderBlocks([
        { index: 0, type: 'text', markdown: TABLE },
        { index: 1, type: 'chart', chart: LINE_CHART },
        { index: 2, type: 'chart', chart: INCOME_CHART },
      ]);

      expect(container.querySelector('.answer-pair')).toBeNull();
      expect(container.querySelectorAll('.dc-charts-container')).toHaveLength(
        1,
      );
    });

    it('pairs each stats block with its own chart down the answer', () => {
      // Test: Several stats and chart pairs in one answer.
      // Situation: Two tables, each directly followed by its line chart.
      // Expectation: Two paired rows render, in order, each with its stats
      //   before its chart.
      const container = renderBlocks([
        { index: 0, type: 'text', markdown: TABLE },
        { index: 1, type: 'chart', chart: LINE_CHART },
        { index: 2, type: 'text', markdown: BULLETS },
        { index: 3, type: 'chart', chart: INCOME_CHART },
      ]);

      expect(container.querySelectorAll('.answer-pair')).toHaveLength(2);
      expect(
        readAnswerParts(container).map((part) => part.split(':')[0]),
      ).toEqual(['text', 'chart', 'text', 'chart']);
    });
  });

  it('places back-to-back charts in one shared tile', () => {
    // Test: Grouping of consecutive chart blocks.
    // Situation: A finished turn whose blocks are a paragraph followed by
    //   two chart blocks in a row.
    // Expectation: Both chart cards render inside a single charts container,
    //   whose grid sets them side by side.
    const { container } = render(
      <AnswerPanel
        turn={buildTurnWithBlocks([
          { index: 0, type: 'text', markdown: 'Rents rise with incomes.' },
          { index: 1, type: 'chart', chart: LINE_CHART },
          { index: 2, type: 'chart', chart: INCOME_CHART },
        ])}
        isStreaming={false}
      />,
    );

    const tiles = container.querySelectorAll('.dc-charts-container');
    expect(tiles).toHaveLength(1);
    expect(tiles[0].querySelectorAll('.dc-chart-card')).toHaveLength(2);
  });

  it('keeps charts separated by text in their own tiles', () => {
    // Test: Charts that are not consecutive.
    // Situation: A finished turn whose blocks are a chart, a paragraph, and
    //   a second chart.
    // Expectation: Each chart renders in its own charts container, in the
    //   order the blocks arrived.
    const { container } = render(
      <AnswerPanel
        turn={buildTurnWithBlocks([
          { index: 0, type: 'chart', chart: LINE_CHART },
          { index: 1, type: 'text', markdown: 'Incomes rose too.' },
          { index: 2, type: 'chart', chart: INCOME_CHART },
        ])}
        isStreaming={false}
      />,
    );

    expect(container.querySelectorAll('.dc-charts-container')).toHaveLength(2);
    expect(readAnswerParts(container)).toEqual([
      'chart:Population, France',
      'text:Incomes rose too.',
      'chart:Median household income, France',
    ]);
  });

  it('renders DebugPanel on a settled error turn with answer text under ?debug', () => {
    // Test: Debug panel rendering on settled error turn with partial answer.
    // Situation: ?debug=1 is enabled and an error turn has partial text and mounts revealed.
    // Expectation: DebugPanel renders in CardHeader while Export PDF is omitted.
    window.history.replaceState(null, '', '/?debug=1');
    const turn = buildTurnWithBlocks(
      [{ index: 0, type: 'text', markdown: 'Partial answer before error.' }],
      { status: 'error', error: 'Stream disconnected' },
    );
    render(<AnswerPanel turn={turn} isStreaming={false} />);

    expect(
      screen.getByLabelText(DEBUG_PANEL_COPY.openButtonLabel),
    ).toBeDefined();
    expect(screen.queryByRole('button', { name: 'Export PDF' })).toBeNull();
  });

  it('omits DebugPanel when ?debug is not enabled', () => {
    // Test: Debug panel gating on ?debug query flag.
    // Situation: Page URL has no ?debug parameter.
    // Expectation: DebugPanel trigger button is not rendered.
    window.history.replaceState(null, '', '/');
    const turn = buildTurnWithBlocks([
      { index: 0, type: 'text', markdown: 'France has about 68 million.' },
    ]);
    render(<AnswerPanel turn={turn} isStreaming={false} />);

    expect(
      screen.queryByLabelText(DEBUG_PANEL_COPY.openButtonLabel),
    ).toBeNull();
  });

  it('omits DebugPanel while answer text is still revealing and renders it once revealed', () => {
    // Test: Debug panel visibility during progressive reveal.
    // Situation: An active stream (isStreaming={true}) under ?debug=1.
    // Expectation: DebugPanel is omitted before the reveal timer settles, and appears once revealed.
    vi.useFakeTimers();
    window.history.replaceState(null, '', '/?debug=1');
    const turn = buildTurnWithBlocks(
      [{ index: 0, type: 'text', markdown: 'Progressive reveal in motion.' }],
      { status: 'done' },
    );
    render(<AnswerPanel turn={turn} isStreaming />);

    expect(
      screen.queryByLabelText(DEBUG_PANEL_COPY.openButtonLabel),
    ).toBeNull();

    act(() => {
      vi.advanceTimersByTime(calculateStreamDurationMs(turn.text) + 10);
    });

    expect(
      screen.getByLabelText(DEBUG_PANEL_COPY.openButtonLabel),
    ).toBeDefined();
  });

  it('renders DebugPanel without ?debug when /agent/health reports debug_report on', async () => {
    // Test: Debug panel display gated on debug report mode on in AnswerPanel without ?debug.
    // Situation: URL debug is absent, /agent/health reports debug_report: 'on', turn is revealed and settled.
    // Expectation: DebugPanel trigger button renders in CardHeader.
    window.history.replaceState(null, '', '/');
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.endsWith('/agent/health')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ status: 'ok', debug_report: 'on' }),
          };
        }
        throw new Error(`Unexpected url: ${url}`);
      }),
    );

    const turn = buildTurnWithBlocks([
      { index: 0, type: 'text', markdown: 'France has about 68 million.' },
    ]);
    render(<AnswerPanel turn={turn} isStreaming={false} />);

    await waitFor(() => {
      expect(
        screen.getByLabelText(DEBUG_PANEL_COPY.openButtonLabel),
      ).toBeDefined();
    });
  });

  it('renders DebugPanel without ?debug when turn.serverReport is present', () => {
    // Test: Debug panel display when turn has serverReport attached.
    // Situation: URL debug is absent, turn has serverReport.
    // Expectation: DebugPanel trigger button renders in CardHeader.
    window.history.replaceState(null, '', '/');
    const serverReport = parseServerDebugReport({
      turn_id: 't1',
      terminal_state: 'complete',
      terminal_reason: 'ok',
      duration_ms: 50,
      tokens: {},
    });
    expect(serverReport).not.toBeNull();
    if (!serverReport) {
      throw new Error('Expected serverReport to parse');
    }

    const turn = buildTurnWithBlocks(
      [{ index: 0, type: 'text', markdown: 'France has about 68 million.' }],
      { serverReport },
    );
    render(<AnswerPanel turn={turn} isStreaming={false} />);

    expect(
      screen.getByLabelText(DEBUG_PANEL_COPY.openButtonLabel),
    ).toBeDefined();
  });

  it.each([
    'flag',
    'off',
  ])('omits DebugPanel without ?debug when /agent/health returns %s', async (mode) => {
    // Test: Debug panel suppressed when server mode is flag or off.
    // Situation: URL debug is absent, /agent/health reports mode flag or off.
    // Expectation: DebugPanel is not rendered.
    window.history.replaceState(null, '', '/');
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ status: 'ok', debug_report: mode }),
    }));
    vi.stubGlobal('fetch', fetchMock);

    const turn = buildTurnWithBlocks([
      { index: 0, type: 'text', markdown: 'France has about 68 million.' },
    ]);
    render(<AnswerPanel turn={turn} isStreaming={false} />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    expect(
      screen.queryByLabelText(DEBUG_PANEL_COPY.openButtonLabel),
    ).toBeNull();
  });
});
