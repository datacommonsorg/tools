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
 * @fileoverview Tests for ReasoningBlock splash indicator assets.
 */

import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { resetInstanceConfigForTests } from '@/src/config/instance_config';
import { ReasoningBlock } from './block_reasoning';

const writeSlot = (themeDocument: Record<string, unknown>): void => {
  const slot = document.createElement('script');
  slot.id = 'instance-config';
  slot.type = 'application/json';
  slot.textContent = JSON.stringify(themeDocument);
  document.head.appendChild(slot);
  resetInstanceConfigForTests();
};

const getIndicatorSrc = (container: HTMLElement): string | null =>
  container.querySelector('img')?.getAttribute('src') ?? null;

afterEach(() => {
  cleanup();
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
    expect(container.textContent).toContain('Understanding your question…');
    expect(container.textContent).toContain('Reviewing your question…');
    expect(container.textContent).not.toContain('Searching Data Commons');

    rerender(
      <ReasoningBlock thoughts={[]} defaultOpen streaming status="discovery" />,
    );
    expect(container.textContent).toContain('Querying data tools…');
    expect(container.textContent).toContain(
      'Searching Data Commons for relevant indicators and observations…',
    );

    rerender(
      <ReasoningBlock thoughts={[]} defaultOpen streaming status="synthesis" />,
    );
    expect(container.textContent).toContain('Synthesizing answer…');

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
  });

  it.each([
    ['discovery', 'Querying data tools…'],
    ['processing', 'Analyzing data…'],
  ] as const)('labels the header for the %s phase while streaming', (status, label) => {
    // Test: Phase copy for the discovery and processing statuses.
    // Situation: ReasoningBlock renders while the turn is streaming in the
    //            `discovery` or `processing` status.
    // Expectation: The header carries the copy for finding data or for
    //              analyzing it.
    const { getByRole } = render(
      <ReasoningBlock thoughts={[]} streaming status={status} />,
    );

    expect(getByRole('button').textContent).toContain(label);
  });
});
