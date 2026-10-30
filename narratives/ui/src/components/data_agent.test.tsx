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
 * @fileoverview Tests for DataAgent turn rendering, new-turn scrolling, and its
 * skeleton handoff timing.
 */

import { readFileSync } from 'node:fs';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ChatSessionContext,
  type ChatSessionContextValue,
} from '@/src/hooks/chat_session_context';
import type { ChatTurn } from '@/src/hooks/use_sse_chat';
import { DataAgent, HANDOFF_MS } from './data_agent';

class NoopResizeObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', NoopResizeObserver);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** Returns the surface over a settled chat state holding `turns`. */
const chatSurface = (turns: ChatTurn[]) => {
  const chat: ChatSessionContextValue = {
    turns,
    isStreaming: false,
    error: null,
    send: vi.fn(),
    stop: vi.fn(),
    newChat: vi.fn(),
    isDrawerOpen: false,
    toggleDrawer: vi.fn(),
    closeDrawer: vi.fn(),
  };
  return (
    <ChatSessionContext.Provider value={chat}>
      <DataAgent />
    </ChatSessionContext.Provider>
  );
};

/** Renders the surface over a settled chat state holding `turns`. */
const renderTurns = (turns: ChatTurn[]) => render(chatSurface(turns));

describe('DataAgent refused and clarification turns', () => {
  it('renders a refused turn as a neutral notice card, not an error card', () => {
    // Test: Rendering a refused turn in DataAgent.
    // Situation: The chat holds a refused turn with a refusal notice message.
    // Expectation: The notice message is rendered in a note region using the
    //              theme surface token, without error styling and without a
    //              ReasoningBlock.
    const { container } = renderTurns([
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
    renderTurns([
      {
        userMessage: 'What is the population of Georgia?',
        status: 'done',
        toolCalls: [],
        thoughts: [],
        text: 'Are you referring to the state of Georgia in the United States or the country of Georgia?',
        provenance: [],
      },
    ]);

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

describe('DataAgent New chat', () => {
  it('drops an unsent follow-up when the chat is emptied', () => {
    // Test: New chat with a follow-up typed but not sent.
    // Situation: The chat holds an answered turn, the user types a follow-up
    //            into the prompt, and New chat then empties the chat.
    // Expectation: The landing view's prompt is empty, so the draft does not
    //              carry over into the new chat.
    const { rerender } = renderTurns([
      {
        userMessage: 'What is the population of France?',
        status: 'done',
        toolCalls: [],
        thoughts: [],
        text: 'About 68 million.',
        provenance: [],
      },
    ]);
    fireEvent.change(
      screen.getByRole('textbox', { name: 'Ask a follow-up question' }),
      { target: { value: 'And Germany?' } },
    );

    rerender(chatSurface([]));

    const prompt = screen.getByRole('textbox', {
      name: 'Ask a question to explore relevant statistical data',
    });
    expect((prompt as HTMLTextAreaElement).value).toBe('');
  });
});

describe('DataAgent new-turn scroll', () => {
  it('scrolls <main>, not the window, to a newly added question', () => {
    // Test: A follow-up question is added to the chat.
    // Situation: The surface renders inside <main>, the app's scroll
    //            container, and a second turn is appended.
    // Expectation: The glide scrolls <main>; the window does not move.
    const frames: FrameRequestCallback[] = [];
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      frames.push(callback);
      return frames.length;
    });
    const windowScrollTo = vi.fn();
    vi.stubGlobal('scrollTo', windowScrollTo);
    const turn: ChatTurn = {
      userMessage: 'What is the population of France?',
      status: 'done',
      toolCalls: [],
      thoughts: [],
      text: 'About 68 million.',
      provenance: [],
    };
    const { rerender } = render(<main>{chatSurface([turn])}</main>);
    const mainScrollTo = vi.fn();
    screen.getByRole('main').scrollTo = mainScrollTo;

    rerender(
      <main>
        {chatSurface([turn, { ...turn, userMessage: 'And Germany?' }])}
      </main>,
    );
    frames.shift()?.(performance.now());

    expect(mainScrollTo).toHaveBeenCalled();
    expect(windowScrollTo).not.toHaveBeenCalled();
  });
});

describe('DataAgent skeleton handoff', () => {
  it('keeps HANDOFF_MS equal to the --animate-stream-in duration', () => {
    // Test: The skeleton unmount timer against the answer's fade-in.
    // Situation: HANDOFF_MS unmounts the skeleton; --animate-stream-in in
    //            index.css fades the answer in over it.
    // Expectation: Both durations are equal, so the skeleton is not removed
    //              before or long after the answer has fully appeared.
    // Vitest runs from the ui/ package root.
    const css = readFileSync('src/index.css', 'utf8');
    const duration = css.match(/--animate-stream-in:\s*stream-in\s+(\d+)ms/);
    expect(duration).not.toBeNull();
    expect(Number(duration?.[1])).toBe(HANDOFF_MS);
  });
});
