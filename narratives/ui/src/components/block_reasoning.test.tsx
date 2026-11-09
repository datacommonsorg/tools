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
 * @fileoverview Tests for ReasoningBlock indicators, header, body, and scroll
 * behavior.
 */

import { cleanup, fireEvent, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ReasoningBlock } from '@/src/components/block_reasoning';
import { CLOSE_REASONING_LABEL } from '@/src/config/copy_chat';
import { resetInstanceConfigForTests } from '@/src/config/instance_config';

const writeSlot = (themeDocument: Record<string, unknown>): void => {
  const slot = document.createElement('script');
  slot.id = 'instance-config';
  slot.type = 'application/json';
  slot.textContent = JSON.stringify(themeDocument);
  document.head.appendChild(slot);
  resetInstanceConfigForTests();
};

// Each thought (or the placeholder standing in for them) is one timeline
// entry: a left bar ending in a dot.
const getThoughts = (container: HTMLElement): HTMLElement[] => [
  ...container.querySelectorAll<HTMLElement>('.border-l-2'),
];
const isPulsing = (thought: HTMLElement): boolean =>
  thought.classList.contains('motion-safe:after:animate-dot-pulse');
const isExpanding = (thought: HTMLElement): boolean =>
  thought.classList.contains('motion-safe:animate-thought-expand');

const getIndicatorSrc = (container: HTMLElement): string | null =>
  container.querySelector('img')?.getAttribute('src') ?? null;

// jsdom has no ResizeObserver. Records the latest callback so a test can
// report a resize.
let reportResize: () => void = vi.fn();
class FakeResizeObserver {
  constructor(callback: () => void) {
    reportResize = callback;
  }
  observe = vi.fn();
  disconnect = vi.fn();
}

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', FakeResizeObserver);
  reportResize = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  document.querySelector('main')?.remove();
  document.getElementById('instance-config')?.remove();
  resetInstanceConfigForTests();
});

describe('ReasoningBlock', () => {
  it('renders the built-in thinking and done indicators by default', () => {
    // Test: Default indicator assets in ReasoningBlock.
    // Situation: The instance-config element is absent, and ReasoningBlock renders
    //            first in the streaming state and then in the done state.
    // Expectation: The indicator image uses `/agent-thinking.svg` while streaming
    //              and `/agent-done-thinking.svg` once done.
    const { container, rerender } = render(
      <ReasoningBlock thoughts={[]} streaming />,
    );
    expect(getIndicatorSrc(container)).toBe('/agent-thinking.svg');

    rerender(<ReasoningBlock thoughts={[]} done />);
    expect(getIndicatorSrc(container)).toBe('/agent-done-thinking.svg');
  });

  it('renders custom thinking and done indicators from #instance-config', () => {
    // Test: Custom splash indicator assets in ReasoningBlock.
    // Situation: The theme document configures custom `thinking_indicator` and
    //            `done_indicator` URLs under `splash_assets`.
    // Expectation: ReasoningBlock renders the configured indicator URL for each
    //              turn state.
    writeSlot({
      splash_assets: {
        thinking_indicator: '/theme/custom-thinking.svg',
        done_indicator: '/theme/custom-done.svg',
      },
    });
    const { container, rerender } = render(
      <ReasoningBlock thoughts={[]} streaming />,
    );
    expect(getIndicatorSrc(container)).toBe('/theme/custom-thinking.svg');

    rerender(<ReasoningBlock thoughts={[]} done />);
    expect(getIndicatorSrc(container)).toBe('/theme/custom-done.svg');
  });

  it('shows the phase label and placeholder body for classify, discovery, synthesis, and done', () => {
    // Test: Phase-specific header copy and placeholder body in ReasoningBlock.
    // Situation: ReasoningBlock renders expanded while streaming in each
    //            pipeline phase with no thoughts and then after completion.
    // Expectation: Each phase renders its label, classify renders its
    //              non-data placeholder body, discovery renders the data-search
    //              placeholder body, and the completed turn renders
    //              `Reasoning details`.
    const { container, rerender } = render(
      <ReasoningBlock thoughts={[]} defaultOpen streaming status="classify" />,
    );
    expect(container.textContent).toContain('Understanding your question');
    expect(container.textContent).toContain('Reviewing your question…');
    expect(container.textContent).not.toContain('Searching Data Commons');

    rerender(
      <ReasoningBlock thoughts={[]} defaultOpen streaming status="discovery" />,
    );
    expect(container.textContent).toContain('Querying data tools');
    expect(container.textContent).toContain(
      'Searching Data Commons for relevant indicators and observations…',
    );

    rerender(
      <ReasoningBlock thoughts={[]} defaultOpen streaming status="synthesis" />,
    );
    expect(container.textContent).toContain('Synthesizing answer');

    rerender(<ReasoningBlock thoughts={[]} defaultOpen done status="done" />);
    expect(container.textContent).toContain('Reasoning details');
  });

  it('streams new thoughts in without replaying earlier ones', () => {
    // Test: Live thoughts reveal word by word, once.
    // Situation: A streaming block gets one thought, then a second.
    // Expectation: The first thought's words are the same DOM nodes after the
    //              second arrives, and both are wrapped for the reveal.
    const first = { text: 'Looking up data.', phase: 'discovery' as const };
    const { container, rerender } = render(
      <ReasoningBlock thoughts={[first]} streaming />,
    );
    const before = container.querySelector('.stream-word');
    rerender(
      <ReasoningBlock
        thoughts={[first, { text: 'Found it.', phase: 'discovery' }]}
        streaming
      />,
    );

    expect(before).not.toBeNull();
    expect(container.querySelector('.stream-word')).toBe(before);
    expect(container.querySelectorAll('.markdown-stream')).toHaveLength(2);
    const thoughts = getThoughts(container);
    expect(thoughts).toHaveLength(2);
    expect(thoughts.every(isExpanding)).toBe(true);
    expect(thoughts.map(isPulsing)).toEqual([false, true]);
  });

  it('stops pulsing the latest dot once the turn stops streaming', () => {
    // Test: The active dot tracks the turn's streaming state live.
    // Situation: A streaming block with one thought, then the turn ends.
    // Expectation: The dot pulses while streaming and rests afterwards; the
    //              thought keeps its bar and is not re-mounted.
    const thought = { text: 'Looking up data.', phase: 'discovery' as const };
    const { container, rerender } = render(
      <ReasoningBlock thoughts={[thought]} streaming />,
    );
    const [entry] = getThoughts(container);
    expect(isPulsing(entry)).toBe(true);

    rerender(<ReasoningBlock thoughts={[thought]} done />);

    expect(getThoughts(container)).toEqual([entry]);
    expect(isPulsing(entry)).toBe(false);
    expect(entry.classList.contains('after:bg-border')).toBe(true);
  });

  it('lays the placeholder out as a timeline entry', () => {
    // Test: The placeholder matches the thoughts' bar-and-dot layout.
    // Situation: The block streams with no thoughts yet, then the turn ends
    //            without any.
    // Expectation: The placeholder sits in one timeline entry whose dot pulses
    //              while streaming and rests once done.
    const { container, rerender } = render(
      <ReasoningBlock thoughts={[]} streaming status="discovery" />,
    );
    let entries = getThoughts(container);
    expect(entries).toHaveLength(1);
    expect(entries[0].textContent).toContain('Searching Data Commons');
    expect(isPulsing(entries[0])).toBe(true);

    rerender(<ReasoningBlock thoughts={[]} done />);
    entries = getThoughts(container);
    expect(entries).toHaveLength(1);
    expect(entries[0].textContent).toContain('Analyzed the query');
    expect(isPulsing(entries[0])).toBe(false);
  });

  it('gives tight list items the muted italic body type', () => {
    // Test: Tight lists match paragraph typography.
    // Situation: A thought holds a tight list, whose items have no inner <p>.
    // Expectation: The list carries the muted italic classes the items inherit.
    const { container } = render(
      <ReasoningBlock
        thoughts={[{ text: '- one\n- two', phase: 'discovery' }]}
        done
      />,
    );
    const list = container.querySelector('ul');
    expect(list?.querySelector('p')).toBeNull();
    expect(list?.classList).toContain('italic');
    expect(list?.classList).toContain('text-on-surface-variant');
  });

  it('shows thoughts restored with a finished turn without a reveal', () => {
    // Test: Restored thoughts are simply there.
    // Situation: The block mounts for a turn that is already done.
    // Expectation: No word spans or reveal class are rendered.
    const { container } = render(
      <ReasoningBlock
        thoughts={[{ text: 'Done.', phase: 'discovery' }]}
        done
      />,
    );

    expect(container.querySelector('.markdown-stream')).toBeNull();
    expect(container.querySelector('.stream-word')).toBeNull();
    const [entry] = getThoughts(container);
    expect(isExpanding(entry)).toBe(false);
    expect(isPulsing(entry)).toBe(false);
  });

  it.each([
    ['discovery', 'Querying data tools'],
    ['processing', 'Analyzing data'],
  ] as const)('labels the header for the %s phase while streaming', (status, label) => {
    // Test: Phase copy for the discovery and processing statuses.
    // Situation: ReasoningBlock renders while the turn is streaming in the
    //            `discovery` or `processing` status.
    // Expectation: The header carries the copy for finding data or for
    //              analyzing it.
    const { getByRole } = render(
      <ReasoningBlock thoughts={[]} streaming status={status} />,
    );

    expect(getByRole('button', { expanded: false }).textContent).toContain(
      label,
    );
  });

  it('appends the latest reasoning heading to the header only while streaming', () => {
    // Test: Header names the section the model is reasoning about.
    // Situation: Thoughts carry a `##` heading and a later lone-bold heading;
    //            the block renders streaming, then done.
    // Expectation: Streaming shows the phase label, a colon, and the latest
    //              heading, revealed word by word; done falls back to `Reasoning details`.
    const thoughts = [
      { text: '## Plan\nFind the data.', phase: 'discovery' as const },
      {
        text: '**Checking sources**\n\nLooking up.',
        phase: 'discovery' as const,
      },
    ];
    const { getByRole, rerender } = render(
      <ReasoningBlock thoughts={thoughts} streaming status="discovery" />,
    );
    expect(getByRole('button', { expanded: false }).textContent).toBe(
      'Querying data tools:Checking sources',
    );
    expect(
      [
        ...getByRole('button', { expanded: false }).querySelectorAll(
          '.stream-word',
        ),
      ].map((word) => word.textContent),
    ).toEqual(['Checking', 'sources']);

    rerender(<ReasoningBlock thoughts={thoughts} done />);
    expect(getByRole('button', { expanded: false }).textContent).toBe(
      'Reasoning details',
    );
  });

  it.each([
    ['**Note:** see **this**', 'Querying data tools'],
    ['# Plan #', 'Querying data tools:Plan'],
  ])('reads only real headings into the header (%s)', (line, label) => {
    // Test: Heading detection matches what the body renders as a heading.
    // Situation: The latest thought line has several bold runs, or is an ATX
    //            heading with closing `#`s.
    // Expectation: The bold-run line adds no heading; the closing `#`s are
    //              dropped.
    const { getByRole } = render(
      <ReasoningBlock
        thoughts={[{ text: line, phase: 'discovery' }]}
        streaming
        status="discovery"
      />,
    );

    expect(getByRole('button', { expanded: false }).textContent).toBe(label);
  });

  it.each([
    [true, [{ top: 292, behavior: 'smooth' }]],
    [false, undefined],
  ])('scrolls the answer to the top when the turn finishes (open=%s)', (open, scrolled) => {
    // Test: Finishing the turn brings the answer up under an open block.
    // Situation: The block streams inside <main>, open or collapsed, with the
    //            answer card 300px down, and the turn then finishes.
    // Expectation: Open, <main> scrolls the card to 8px below the band's top;
    //              collapsed, it does not scroll.
    vi.stubGlobal('matchMedia', () => ({ matches: false }));
    const main = document.createElement('main');
    const scrollBy = vi.fn();
    main.scrollBy = scrollBy;
    document.body.appendChild(main);
    const thoughts = [{ text: 'Thinking.', phase: 'discovery' as const }];
    const card = document.createElement('div');
    card.getBoundingClientRect = () => ({ top: 300 }) as DOMRect;
    const answerCardRef = { current: card };
    const { rerender } = render(
      <ReasoningBlock
        thoughts={thoughts}
        defaultOpen={open}
        streaming
        status="synthesis"
        answerCardRef={answerCardRef}
      />,
      { container: main },
    );
    expect(scrollBy).not.toHaveBeenCalled();

    rerender(
      <ReasoningBlock
        thoughts={thoughts}
        defaultOpen={open}
        done
        answerCardRef={answerCardRef}
      />,
    );
    expect(scrollBy.mock.calls[0]).toEqual(scrolled);
  });

  it('leaves a reader who scrolled away in place when the turn finishes', () => {
    // Test: The finish scroll respects a paused follow.
    // Situation: The block streams open inside <main>; the reader scrolls up
    //            while the latest thought ends below the band, then the turn
    //            finishes.
    // Expectation: <main> does not scroll to the answer.
    vi.stubGlobal('matchMedia', () => ({ matches: false }));
    const main = document.createElement('main');
    const scrollBy = vi.fn();
    main.scrollBy = scrollBy;
    let scrollTop = 500;
    Object.defineProperty(main, 'scrollTop', { get: () => scrollTop });
    document.body.appendChild(main);
    const thoughts = [{ text: 'Thinking.', phase: 'discovery' as const }];
    const { container, rerender } = render(
      <ReasoningBlock
        thoughts={thoughts}
        defaultOpen
        streaming
        status="synthesis"
      />,
      { container: main },
    );
    const body = container.querySelector<HTMLElement>('.reasoning-markdown');
    if (body) body.getBoundingClientRect = () => ({ bottom: 300 }) as DOMRect;
    scrollTop = 400;
    main.dispatchEvent(new Event('scroll'));

    rerender(<ReasoningBlock thoughts={thoughts} defaultOpen done />);
    expect(scrollBy).not.toHaveBeenCalled();
  });

  it('offers the close button once the turn finishes and reports the close', () => {
    // Test: Closing the reasoning from below its text.
    // Situation: The block renders expanded while streaming, then finishes,
    //            and the reader clicks `Close reasoning details`.
    // Expectation: No close button while streaming; afterwards the click
    //              collapses the block and calls `onClose`.
    const thoughts = [{ text: 'Done.', phase: 'discovery' as const }];
    const onClose = vi.fn();
    const { getByRole, queryByRole, rerender } = render(
      <ReasoningBlock
        thoughts={thoughts}
        defaultOpen
        streaming
        status="synthesis"
        onClose={onClose}
      />,
    );
    expect(queryByRole('button', { name: CLOSE_REASONING_LABEL })).toBeNull();

    rerender(
      <ReasoningBlock thoughts={thoughts} defaultOpen done onClose={onClose} />,
    );
    const header = getByRole('button', { name: /^Reasoning details/ });
    fireEvent.click(getByRole('button', { name: CLOSE_REASONING_LABEL }));
    expect(header.getAttribute('aria-expanded')).toBe('false');
    expect(onClose).toHaveBeenCalledOnce();
  });

  it.each([
    [true, [0, 100]],
    [false, undefined],
  ])('follows the latest thought while streaming (open=%s)', (open, scrolled) => {
    // Test: Streaming reasoning keeps its latest thought in view.
    // Situation: The block streams inside a 200px <main>, open or collapsed,
    //            and its thought list grows to end 300px down.
    // Expectation: Open, <main> scrolls by the 100px overflow; collapsed, it
    //              does not scroll.
    vi.stubGlobal('matchMedia', () => ({ matches: false }));
    const main = document.createElement('main');
    const scrollBy = vi.fn();
    main.scrollBy = scrollBy;
    Object.defineProperty(main, 'clientHeight', { value: 200 });
    document.body.appendChild(main);
    const { container } = render(
      <ReasoningBlock
        thoughts={[{ text: 'Thinking.', phase: 'discovery' }]}
        defaultOpen={open}
        streaming
        status="discovery"
      />,
      { container: main },
    );
    const body = container.querySelector<HTMLElement>('.reasoning-markdown');
    if (body) {
      body.getBoundingClientRect = () => ({ bottom: 300 }) as DOMRect;
    }

    reportResize();
    expect(scrollBy.mock.calls[0]).toEqual(scrolled);
  });

  it('pauses following while the reader scrolls up and resumes at the end', () => {
    // Test: Following yields to a reader who scrolls back.
    // Situation: The block streams open inside a 200px <main>. The reader
    //            scrolls up while the latest thought ends below the band,
    //            then scrolls until it ends inside the band.
    // Expectation: A resize while scrolled up does not scroll; after the
    //              thought's end is back in view, the next resize does.
    vi.stubGlobal('matchMedia', () => ({ matches: false }));
    const main = document.createElement('main');
    const scrollBy = vi.fn();
    main.scrollBy = scrollBy;
    Object.defineProperty(main, 'clientHeight', { value: 200 });
    let scrollTop = 500;
    Object.defineProperty(main, 'scrollTop', { get: () => scrollTop });
    document.body.appendChild(main);
    const { container } = render(
      <ReasoningBlock
        thoughts={[{ text: 'Thinking.', phase: 'discovery' }]}
        defaultOpen
        streaming
        status="discovery"
      />,
      { container: main },
    );
    const body = container.querySelector<HTMLElement>('.reasoning-markdown');
    let bottom = 300;
    if (body) body.getBoundingClientRect = () => ({ bottom }) as DOMRect;

    scrollTop = 400;
    main.dispatchEvent(new Event('scroll'));
    reportResize();
    expect(scrollBy).not.toHaveBeenCalled();

    scrollTop = 600;
    bottom = 150;
    main.dispatchEvent(new Event('scroll'));
    bottom = 300;
    reportResize();
    expect(scrollBy).toHaveBeenCalledWith(0, 100);
  });

  it('keeps the following card in view while streaming', () => {
    // Test: Following keeps the skeleton in view below the reasoning.
    // Situation: The block streams open inside a 200px <main>, with an answer
    //            card whose 200px starts 250px down.
    // Expectation: <main> scrolls so the whole card (SKELETON_PEEK is 1)
    //              ends at the band's bottom: by 250px.
    vi.stubGlobal('matchMedia', () => ({ matches: false }));
    const main = document.createElement('main');
    const scrollBy = vi.fn();
    main.scrollBy = scrollBy;
    Object.defineProperty(main, 'clientHeight', { value: 200 });
    document.body.appendChild(main);
    const card = document.createElement('div');
    card.getBoundingClientRect = () => ({ top: 250, height: 200 }) as DOMRect;
    render(
      <ReasoningBlock
        thoughts={[{ text: 'Thinking.', phase: 'discovery' }]}
        defaultOpen
        streaming
        status="discovery"
        answerCardRef={{ current: card }}
      />,
      { container: main },
    );

    reportResize();
    expect(scrollBy).toHaveBeenCalledWith(0, 250);
  });
});
