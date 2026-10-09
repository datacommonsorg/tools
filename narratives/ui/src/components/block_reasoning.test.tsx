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
});
