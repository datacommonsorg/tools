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
 * @fileoverview Tests for the desktop rail's new-chat control.
 */

import {
  act,
  cleanup,
  fireEvent,
  renderHook,
  screen,
} from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  ChatSessionProvider,
  useChatSession,
} from '@/src/hooks/chat_session_context';
import { Sidebar } from './sidebar';

/** Renders the rail inside the same chat session as the hook under test. */
const wrapper = ({ children }: { children: ReactNode }) => (
  <ChatSessionProvider>
    <Sidebar />
    {children}
  </ChatSessionProvider>
);

/** Answers the agent request with a stream that ends straight away. */
const stubFetch = (): void => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: 'OK',
      body: new ReadableStream<Uint8Array>({
        start(controller) {
          controller.close();
        },
      }),
    }),
  );
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('Sidebar', () => {
  it('clears the conversation when New chat is clicked', async () => {
    // Test: The new-chat control on the desktop rail.
    // Situation: One question has been asked, so the chat holds a turn.
    // Expectation: Clicking the control leaves no turns, and the rail offers
    //   no list of saved chats to bring the old one back from.
    stubFetch();
    const { result } = renderHook(() => useChatSession(), { wrapper });
    await act(async () => {
      await result.current.send('What is the population of France?');
    });
    expect(result.current.turns).toHaveLength(1);

    fireEvent.click(screen.getByRole('button', { name: 'New chat' }));

    expect(result.current.turns).toEqual([]);
    expect(
      screen.queryByRole('button', { name: 'Toggle chats list' }),
    ).toBeNull();
  });
});
