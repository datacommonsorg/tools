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
 * @fileoverview Tests for refused, clarification, and error turn rendering in DataAgent.
 */

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatSessionProvider } from '@/src/hooks/chat_session_context';
import type { ChatTurn } from '@/src/hooks/use_sse_chat';
import { DataAgent } from './data_agent';

class NoopResizeObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', NoopResizeObserver);
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

const seedTurns = (turns: ChatTurn[]): void => {
  window.localStorage.setItem(
    'cdc:chat:v2',
    JSON.stringify({
      version: 2,
      currentId: 's1',
      sessions: [
        {
          id: 's1',
          title: 'Test',
          createdAt: 1,
          updatedAt: 1,
          turns,
        },
      ],
    }),
  );
};

describe('DataAgent refused and clarification turns', () => {
  it('renders a refused turn as a neutral notice card, not an error card', () => {
    // Test: Rendering a refused turn in DataAgent.
    // Situation: The active session contains a refused turn with a refusal
    //            notice message.
    // Expectation: The notice message is rendered in a note region using the
    //              theme surface token, without error styling and without a
    //              ReasoningBlock.
    seedTurns([
      {
        userMessage: 'How much does a latte cost in Seattle?',
        status: 'refused',
        refusalMessage:
          'That request is outside the public statistical data this service covers (retail coffee prices). Ask about a demographic, economic, health, climate, or social indicator for a place.',
        toolCalls: [],
        thoughts: [],
        text: '',
        provenance: [],
      },
    ]);

    const { container } = render(
      <ChatSessionProvider>
        <DataAgent />
      </ChatSessionProvider>,
    );

    const notice = screen.getByRole('note');
    expect(notice.textContent).toContain('retail coffee prices');
    expect(notice.className).toContain('bg-surface-soft');
    expect(notice.className).not.toContain('bg-error-surface');
    expect(container.querySelector('.bg-error-surface')).toBeNull();
    expect(screen.queryByText('Reasoning details')).toBeNull();
  });

  it('omits the completed reasoning placeholder on a clarification turn with no data calls', () => {
    // Test: Rendering a completed clarification turn in DataAgent.
    // Situation: A turn completes with a clarification question in `text`,
    //            while `thoughts`, `toolCalls`, and `provenance` are all empty.
    // Expectation: The clarification text is rendered and the completed
    //              ReasoningBlock placeholder is omitted.
    seedTurns([
      {
        userMessage: 'What is the population of Georgia?',
        status: 'done',
        toolCalls: [],
        thoughts: [],
        text: 'Are you referring to the state of Georgia in the United States or the country of Georgia?',
        provenance: [],
      },
    ]);

    render(
      <ChatSessionProvider>
        <DataAgent />
      </ChatSessionProvider>,
    );

    expect(
      screen.getByText(
        'Are you referring to the state of Georgia in the United States or the country of Georgia?',
      ),
    ).toBeDefined();
    expect(screen.queryByText('Reasoning details')).toBeNull();
    expect(
      screen.queryByText(
        'Analyzed the query and retrieved relevant data from Data Commons.',
      ),
    ).toBeNull();
  });
});
