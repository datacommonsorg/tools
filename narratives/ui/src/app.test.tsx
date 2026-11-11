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
 * @fileoverview Tests that moving between the app's tabs drops the chat and
 * returns the scroll container to its top, and that the Data Agent route
 * renders the unavailable view while chat is disabled.
 */

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '@/src/app';
import {
  DEFAULT_INSTANCE_CONFIG,
  resetInstanceConfigForTests,
} from '@/src/config/instance_config';
import { resetRuntimeConfigForTests } from '@/src/config/runtime_config';

/** The landing prompt's accessible name. */
const LANDING_PROMPT = 'Ask a question to explore relevant statistical data';

/** A custom message for the chat-disabled cases. */
const UNAVAILABLE_MESSAGE = 'Chat is paused for maintenance.';

class NoopResizeObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}

/** Moves to `hash`, as a click on a section link does. */
const goTo = (hash: string): void => {
  act(() => {
    window.location.hash = hash;
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  });
};

/**
 * Replaces `#runtime-config` with one that disables chat with a custom
 * message, and clears the cached runtime configuration.
 */
const writeChatDisabledSlot = (): void => {
  document.getElementById('runtime-config')?.remove();
  const slot = document.createElement('script');
  slot.id = 'runtime-config';
  slot.type = 'application/json';
  slot.textContent = JSON.stringify({
    enable_chat: false,
    unavailable_message: UNAVAILABLE_MESSAGE,
  });
  document.head.appendChild(slot);
  resetRuntimeConfigForTests();
};

beforeEach(() => {
  window.location.hash = '';
  vi.stubGlobal('ResizeObserver', NoopResizeObserver);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.location.hash = '';
  document.getElementById('runtime-config')?.remove();
  document.getElementById('instance-config')?.remove();
  resetRuntimeConfigForTests();
  resetInstanceConfigForTests();
});

describe('App', () => {
  it('drops an answer still streaming when the user leaves the Data Agent tab', async () => {
    // Test: Leaving the Data Agent tab mid-answer.
    // Situation: A question is streaming when the user opens Key Metrics and
    //   then comes back.
    // Expectation: The request is aborted on the way out, and the Data Agent
    //   tab shows the empty landing view again.
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) => ({
      ok: true,
      status: 200,
      statusText: 'OK',
      // An answer that never finishes, and fails on abort as fetch does.
      body: new ReadableStream<Uint8Array>({
        start(controller) {
          init.signal?.addEventListener('abort', () =>
            controller.error(
              new DOMException('The operation was aborted.', 'AbortError'),
            ),
          );
        },
      }),
    }));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    fireEvent.change(screen.getByRole('textbox', { name: LANDING_PROMPT }), {
      target: { value: 'What is the population of France?' },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Submit' }));
    });
    expect(screen.getByText('What is the population of France?')).toBeTruthy();

    goTo('#/metrics');
    expect(fetchMock.mock.calls[0][1].signal?.aborted).toBe(true);

    goTo('#/');
    expect(screen.getByRole('textbox', { name: LANDING_PROMPT })).toBeTruthy();
    expect(screen.queryByText('What is the population of France?')).toBeNull();
  });

  it('keeps a streaming answer when the route changes but the view does not', async () => {
    // Test: A route change that stays on the Data Agent.
    // Situation: A question is streaming at '#/' when the hash becomes
    //   '#/agent', which shows the same Data Agent view.
    // Expectation: The request is not aborted and the question stays on
    //   screen.
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) => ({
      ok: true,
      status: 200,
      statusText: 'OK',
      body: new ReadableStream<Uint8Array>({
        start(controller) {
          init.signal?.addEventListener('abort', () =>
            controller.error(
              new DOMException('The operation was aborted.', 'AbortError'),
            ),
          );
        },
      }),
    }));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    fireEvent.change(screen.getByRole('textbox', { name: LANDING_PROMPT }), {
      target: { value: 'What is the population of France?' },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Submit' }));
    });

    goTo('#/agent');
    expect(fetchMock.mock.calls[0][1].signal?.aborted).toBe(false);
    expect(screen.getByText('What is the population of France?')).toBeTruthy();
  });

  it('scrolls <main> back to its top when the user switches tabs', () => {
    // Test: Switching from the Data Agent tab to Key Metrics.
    // Situation: <main> is the app's scroll container; the page itself does
    //   not scroll.
    // Expectation: <main> is scrolled to its top and the window is not.
    const mainScrollTo = vi.fn();
    const windowScrollTo = vi.fn();
    vi.stubGlobal('scrollTo', windowScrollTo);
    render(<App />);
    const main = screen.getByRole('main');
    main.scrollTo = mainScrollTo;

    goTo('#/metrics');

    expect(mainScrollTo).toHaveBeenCalledWith(0, 0);
    expect(windowScrollTo).not.toHaveBeenCalled();
  });
});

describe('App with chat disabled', () => {
  it.each([
    '',
    '#/agent',
  ])('renders the unavailable message instead of the chat at %j', (hash) => {
    // Test: The Data Agent route while chat is disabled.
    // Situation: #runtime-config disables chat with a custom message, and the
    //   route is the root or `#/agent`.
    // Expectation: The message renders, and neither the landing prompt nor a
    //   suggestion chip mounts.
    writeChatDisabledSlot();
    window.location.hash = hash;
    render(<App />);
    expect(screen.getByRole('note').textContent).toBe(UNAVAILABLE_MESSAGE);
    expect(screen.queryByRole('textbox', { name: LANDING_PROMPT })).toBeNull();
    expect(
      screen.queryByText(DEFAULT_INSTANCE_CONFIG.suggestions[0]),
    ).toBeNull();
  });

  it('keeps Key Metrics reachable and returns to the unavailable view', () => {
    // Test: Moving between tabs while chat is disabled.
    // Situation: #runtime-config disables chat; the user opens Key Metrics and
    //   then returns to the Data Agent tab.
    // Expectation: Key Metrics renders its heading, and the Data Agent tab
    //   renders the unavailable message again with <main> scrolled to its top.
    writeChatDisabledSlot();
    render(<App />);
    const mainScrollTo = vi.fn();
    screen.getByRole('main').scrollTo = mainScrollTo;

    goTo('#/metrics');
    expect(screen.getByRole('heading', { name: 'Key Metrics' })).toBeTruthy();
    expect(screen.queryByRole('note')).toBeNull();

    mainScrollTo.mockClear();
    goTo('#/agent');
    expect(screen.getByRole('note').textContent).toBe(UNAVAILABLE_MESSAGE);
    expect(mainScrollTo).toHaveBeenCalledWith(0, 0);
  });
});
