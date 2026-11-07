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
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  COMPOSER_DISCLAIMER_TEXT,
  DataAgent,
  HANDOFF_MS,
  TurnView,
} from '@/src/components/data_agent';
import { DISCLAIMER_TEXT } from '@/src/components/note_disclaimer';
import { ANSWER_SETTLE_MAX_MS } from '@/src/components/panel_answer';
import { RETRY_LABEL } from '@/src/config/copy_chat';
import {
  ChatSessionContext,
  type ChatSessionContextValue,
} from '@/src/hooks/chat_session_context';
import type { ChatTurn } from '@/src/hooks/use_sse_chat';

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
  vi.useRealTimers();
});

/** Returns the surface over a settled chat state holding `turns`. */
const chatSurface = (turns: ChatTurn[], send = vi.fn()) => {
  const chat: ChatSessionContextValue = {
    turns,
    isStreaming: false,
    error: null,
    send,
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
const renderTurns = (turns: ChatTurn[], send = vi.fn()) =>
  render(chatSurface(turns, send));

/** Returns a turn that ended in `error` with `error` as its message. */
const buildErrorTurn = (error: string, isRetryable: boolean): ChatTurn => ({
  userMessage: 'What is the population of France?',
  status: 'error',
  error,
  isRetryable,
  toolCalls: [],
  thoughts: [],
  text: '',
  blocks: [],
  provenance: [],
});

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
        blocks: [],
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
    // Situation: A turn completes with a clarification question as its only
    //            text block, while `thoughts`, `toolCalls`, and `provenance`
    //            are all empty.
    // Expectation: The clarification text is rendered and the completed
    //              ReasoningBlock placeholder is omitted.
    const clarification =
      'Are you referring to the state of Georgia in the United States or the country of Georgia?';
    renderTurns([
      {
        userMessage: 'What is the population of Georgia?',
        status: 'done',
        toolCalls: [],
        thoughts: [],
        text: clarification,
        blocks: [{ index: 0, type: 'text', markdown: clarification }],
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

  it('shows the error and no answer panel for an error turn with only chart blocks', () => {
    // Test: A failed turn that streamed charts but no prose.
    // Situation: A turn ends in `error` holding a single chart block and no
    //   answer text.
    // Expectation: The error message renders and no answer panel, chart, or
    //   Markdown body does.
    const { container } = render(
      <TurnView
        turn={{
          userMessage: 'What is the population of France?',
          status: 'error',
          error: 'The agent failed to finish the answer.',
          toolCalls: [],
          thoughts: [],
          text: '',
          blocks: [
            {
              index: 0,
              type: 'chart',
              chart: {
                vizType: 'line',
                title: 'Population, France',
                variableDcids: ['Count_Person'],
                placeDcids: ['country/FRA'],
              },
            },
          ],
          provenance: [],
        }}
        index={0}
        isLast
        isStreaming={false}
      />,
    );

    expect(
      screen.getByText('The agent failed to finish the answer.'),
    ).toBeDefined();
    expect(container.querySelector('.max-w-4xl.grid')).toBeNull();
    expect(container.querySelector('.dc-chart-card')).toBeNull();
    expect(container.querySelector('.markdown-body')).toBeNull();
  });
});

describe('DataAgent error turns', () => {
  it('follows a retryable error with an inline button that resubmits the query', () => {
    // Test: Retrying a transient failed turn.
    // Situation: The chat holds a retryable error turn with the high-traffic
    //            message.
    // Expectation: The notice renders the message followed inline by the
    //              "Try again" button, and clicking the button sends the
    //              turn's question again.
    const send = vi.fn();
    const message = 'We are experiencing unusually high traffic.';
    renderTurns([buildErrorTurn(message, true)], send);

    expect(screen.getByTestId('turn-error-notice').textContent).toBe(
      `${message} ${RETRY_LABEL}`,
    );
    const retry = screen.getByRole('button', { name: RETRY_LABEL });
    fireEvent.click(retry);
    expect(send).toHaveBeenCalledWith('What is the population of France?');
  });

  it.each([
    'The response could not be generated.',
    'Chat is temporarily unavailable. Please try again later.',
    'HTTP 422 Unprocessable Entity',
  ])('shows non-retryable error %j without a retry button', (message) => {
    // Test: Rendering a failed turn that is not retryable.
    // Situation: The turn carries `isRetryable: false`, including when its prose
    //            mentions trying again later (chat disabled).
    // Expectation: The message is rendered verbatim and no retry button is
    //              shown.
    renderTurns([buildErrorTurn(message, false)]);

    screen.getByText(message);
    expect(screen.queryByRole('button', { name: RETRY_LABEL })).toBeNull();
  });

  it('omits the retry button when the turn view has no ask handler', () => {
    // Test: Rendering a retryable turn without a way to resend it.
    // Situation: `TurnView` renders a retryable error turn with no `onAsk`.
    // Expectation: The message is rendered and no retry button is shown, so
    //              no control renders that does nothing.
    const message = 'We are experiencing unusually high traffic.';
    render(
      <TurnView
        turn={buildErrorTurn(message, true)}
        index={0}
        isLast
        isStreaming={false}
      />,
    );

    expect(screen.getByTestId('turn-error-notice').textContent).toBe(message);
    expect(screen.queryByRole('button', { name: RETRY_LABEL })).toBeNull();
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
        blocks: [{ index: 0, type: 'text', markdown: 'About 68 million.' }],
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

describe('DataAgent prompt box disclaimer', () => {
  it('shows the short wording under the prompt box, not the answer note', () => {
    // Test: The disclaimer under the follow-up prompt box.
    // Situation: The chat holds an answered turn, so the sticky prompt box
    //            renders with its disclaimer.
    // Expectation: The prompt box disclaimer holds exactly the short wording,
    //              and the long answer wording is neither under the prompt
    //              box nor merged into the short one.
    renderTurns([
      {
        userMessage: 'What is the population of France?',
        status: 'done',
        toolCalls: [],
        thoughts: [],
        text: 'About 68 million.',
        blocks: [{ index: 0, type: 'text', markdown: 'About 68 million.' }],
        provenance: [],
      },
    ]);

    const composerNote = screen.getByText(COMPOSER_DISCLAIMER_TEXT);
    expect(composerNote.textContent).toBe(COMPOSER_DISCLAIMER_TEXT);
    expect(COMPOSER_DISCLAIMER_TEXT).not.toContain(DISCLAIMER_TEXT);
    expect(DISCLAIMER_TEXT).not.toContain(COMPOSER_DISCLAIMER_TEXT);
    const promptBox = composerNote.parentElement;
    expect(promptBox?.textContent).not.toContain(DISCLAIMER_TEXT);
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
      blocks: [{ index: 0, type: 'text', markdown: 'About 68 million.' }],
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

  it('holds the answer invisible behind the skeleton until it settles', () => {
    // Test: The skeleton handoff after synthesis.
    // Situation: A streaming turn in the synthesis phase already holds a
    //   text block and a chart block, then finishes, and its chart never
    //   draws.
    // Expectation: During synthesis only the skeleton renders. Once the turn
    //   is done the answer mounts invisible and aria-hidden behind a fully
    //   visible skeleton; when the settle cap passes, the answer shows and
    //   the skeleton fades.
    vi.useFakeTimers();
    const synthesizing: ChatTurn = {
      userMessage: 'What is the population of France?',
      status: 'synthesis',
      toolCalls: [],
      thoughts: [],
      text: 'France has about 68 million people.',
      blocks: [
        {
          index: 0,
          type: 'text',
          markdown: 'France has about 68 million people.',
        },
        {
          index: 1,
          type: 'chart',
          chart: {
            vizType: 'line',
            title: 'Population, France',
            variableDcids: ['Count_Person'],
            placeDcids: ['country/FRA'],
          },
        },
      ],
      provenance: [],
    };
    const { container, rerender } = render(
      <TurnView turn={synthesizing} index={0} isLast isStreaming />,
    );

    expect(container.querySelector('.bg-skeleton-bar')).not.toBeNull();
    expect(container.querySelector('.markdown-body')).toBeNull();

    rerender(
      <TurnView
        turn={{ ...synthesizing, status: 'done' }}
        index={0}
        isLast
        isStreaming
      />,
    );
    const cell = container.querySelector('.max-w-4xl.grid');
    const [skeleton, answer] = Array.from(cell?.children ?? []);
    expect(skeleton.querySelector('.bg-skeleton-bar')).not.toBeNull();
    expect(skeleton.classList.contains('opacity-0')).toBe(false);
    expect(answer.querySelector('.markdown-body')).not.toBeNull();
    expect(answer.classList.contains('invisible')).toBe(true);
    expect(answer.getAttribute('aria-hidden')).toBe('true');

    act(() => {
      vi.advanceTimersByTime(ANSWER_SETTLE_MAX_MS);
    });

    expect(answer.classList.contains('invisible')).toBe(false);
    expect(answer.getAttribute('aria-hidden')).toBeNull();
    expect(skeleton.classList.contains('opacity-0')).toBe(true);
  });
});
