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
 * @fileoverview Tests that the chat is held in memory only, and that New chat empties it.
 */

import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatSessionProvider, useChatSession } from './chat_session_context';
import { INTERRUPTED_TURN_ERROR } from './use_sse_chat';

/** The keys earlier builds wrote the transcript to. */
const LEGACY_KEYS = ['cdc:chat:v1', 'cdc:chat:v2'];

/** Returns the envelope an older build saved one finished chat in. */
const savedChat = (): string =>
  JSON.stringify({
    version: 2,
    currentId: 's1',
    sessions: [
      {
        id: 's1',
        title: 'What is the population of France?',
        createdAt: 1,
        updatedAt: 1,
        turns: [
          {
            userMessage: 'What is the population of France?',
            status: 'done',
            toolCalls: [],
            thoughts: [],
            text: 'About 68 million.',
            provenance: [],
          },
        ],
      },
    ],
  });

/**
 * Returns an in-memory Storage. The test environment leaves `localStorage`
 * unset, so the tests install one to watch what the provider does, and does
 * not, write to it.
 */
const memoryStorage = (): Storage => {
  const entries = new Map<string, string>();
  return {
    get length(): number {
      return entries.size;
    },
    key: (index: number): string | null => [...entries.keys()][index] ?? null,
    getItem: (key: string): string | null => entries.get(key) ?? null,
    setItem: (key: string, value: string): void => {
      entries.set(key, value);
    },
    removeItem: (key: string): void => {
      entries.delete(key);
    },
    clear: (): void => {
      entries.clear();
    },
  };
};

const wrapper = ({ children }: { children: ReactNode }) => (
  <ChatSessionProvider>{children}</ChatSessionProvider>
);

/** A stream the test feeds and ends by hand, standing in for a live answer. */
const openStream = () => {
  let stream!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      stream = controller;
    },
  });
  const encoder = new TextEncoder();
  return {
    body,
    // One SSE frame, framed the way the agent writes them.
    push: (event: string, data: unknown): void => {
      stream.enqueue(
        encoder.encode(
          `event: ${event}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`,
        ),
      );
    },
    end: (): void => stream.close(),
    // Fails the body the way fetch does when its request is aborted.
    abort: (): void =>
      stream.error(
        new DOMException('The operation was aborted.', 'AbortError'),
      ),
  };
};

type TestStream = ReturnType<typeof openStream>;

/** A stream that ends straight away, with no terminal event. */
const closedStream = (): TestStream => {
  const stream = openStream();
  stream.end();
  return stream;
};

/** Answers each agent request with the next stream, failing it on abort. */
const stubFetch = (...streams: TestStream[]) => {
  let next = 0;
  const fetchMock = vi.fn(async (_url: string, init: RequestInit) => {
    const stream = streams[next++];
    init.signal?.addEventListener('abort', stream.abort);
    return { ok: true, status: 200, statusText: 'OK', body: stream.body };
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
};

/** Returns the abort signal the request at `index` was sent with. */
const signalOf = (
  fetchMock: ReturnType<typeof stubFetch>,
  index: number,
): AbortSignal | null | undefined => fetchMock.mock.calls[index][1].signal;

let storage: Storage;

beforeEach(() => {
  storage = memoryStorage();
  vi.stubGlobal('localStorage', storage);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ChatSessionProvider', () => {
  it('writes nothing to storage, even once the chat has turns', async () => {
    // Test: What a chat leaves on the device.
    // Situation: A provider is mounted and the user sends one message.
    // Expectation: The turn is on the surface, and storage is still empty, so
    //   closing the page leaves no transcript behind.
    stubFetch(closedStream());
    const { result } = renderHook(() => useChatSession(), { wrapper });

    await act(async () => {
      await result.current.send('What is the population of France?');
    });

    expect(result.current.turns).toHaveLength(1);
    expect(storage.length).toBe(0);
  });

  it('ignores a chat an older build saved and clears it from the device', () => {
    // Test: Upgrading a browser that still holds saved chats.
    // Situation: Both legacy keys hold a transcript when the provider mounts.
    // Expectation: The chat starts empty rather than restoring the transcript,
    //   and both keys are removed, so the old chats stop being carried around.
    for (const key of LEGACY_KEYS) {
      storage.setItem(key, savedChat());
    }

    const { result } = renderHook(() => useChatSession(), { wrapper });

    expect(result.current.turns).toEqual([]);
    for (const key of LEGACY_KEYS) {
      expect(storage.getItem(key)).toBeNull();
    }
  });

  it('clears a failed answer and its error on New chat', async () => {
    // Test: New chat after an answer failed.
    // Situation: The first answer's stream ends without a terminal event, so
    //   the chat holds an errored turn and the interrupted-connection error.
    // Expectation: New chat leaves no turns and no error, and the next
    //   question is answered in the new chat.
    const next = openStream();
    stubFetch(closedStream(), next);
    const { result } = renderHook(() => useChatSession(), { wrapper });
    await act(async () => {
      await result.current.send('What is the population of France?');
    });
    expect(result.current.error).toBe(INTERRUPTED_TURN_ERROR);

    act(() => {
      result.current.newChat();
    });
    expect(result.current.turns).toEqual([]);
    expect(result.current.error).toBeNull();

    await act(async () => {
      const answered = result.current.send('What is the population of Spain?');
      next.push('content', {
        block: { index: 0, type: 'text', markdown: 'About 48 million.' },
      });
      next.push('terminal', { state: 'complete', idempotency_key: 'key-2' });
      next.end();
      await answered;
    });

    expect(result.current.turns).toMatchObject([
      {
        userMessage: 'What is the population of Spain?',
        status: 'done',
        text: 'About 48 million.',
      },
    ]);
    expect(result.current.error).toBeNull();
  });

  it('ends a streaming answer on New chat and answers the next question', async () => {
    // Test: New chat while an answer is still streaming.
    // Situation: A question is in flight when the user starts a new chat, and
    //   then asks another question.
    // Expectation: New chat aborts the request and leaves an idle, empty chat
    //   at once; the next question gets its own answer and nothing else.
    const first = openStream();
    const second = openStream();
    const fetchMock = stubFetch(first, second);
    const { result } = renderHook(() => useChatSession(), { wrapper });
    await act(async () => {
      void result.current.send('What is the population of France?');
    });
    expect(result.current.isStreaming).toBe(true);

    act(() => {
      result.current.newChat();
    });
    expect(signalOf(fetchMock, 0)?.aborted).toBe(true);
    expect(result.current.turns).toEqual([]);
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.error).toBeNull();

    await act(async () => {
      const answered = result.current.send('What is the population of Spain?');
      second.push('content', {
        block: { index: 0, type: 'text', markdown: 'About 48 million.' },
      });
      second.push('terminal', { state: 'complete', idempotency_key: 'key-2' });
      second.end();
      await answered;
    });

    expect(result.current.turns).toMatchObject([
      {
        userMessage: 'What is the population of Spain?',
        status: 'done',
        text: 'About 48 million.',
      },
    ]);
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.error).toBeNull();
  });
});
