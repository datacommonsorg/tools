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

import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ChartItem, ChatTurn } from '@/src/hooks/use_sse_chat';
import { calculateStreamDurationMs } from '@/src/utils/rehype_stream_words';
import { ANSWER_SETTLE_MAX_MS, AnswerPanel } from './panel_answer';

const LINE_CHART: ChartItem = {
  vizType: 'line',
  title: 'Population, France',
  variableDcids: ['Count_Person'],
  placeDcids: ['country/FRA'],
};

/** How often the chart settle poll reads the component, in milliseconds. */
const CHART_POLL_MS = 300;

/** Class that hides the body's non-text children while the text reveals. */
const HIDE_NON_TEXT_CLASS = 'motion-safe:[&>:not(.markdown-body)]:opacity-0';

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

afterEach(() => {
  cleanup();
  vi.useRealTimers();
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
});
