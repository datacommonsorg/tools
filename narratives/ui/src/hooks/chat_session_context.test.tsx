/**
 * @fileoverview Tests that the chat is held in memory only, and that New chat empties it.
 */

import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatSessionProvider, useChatSession } from './chat_session_context';

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

/** Answers the agent request with `body`. */
const stubFetch = (body: ReadableStream<Uint8Array>): void => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: 'OK',
      body,
    }),
  );
};

/** A stream that ends straight away, with no terminal event. */
const closedStream = (): ReadableStream<Uint8Array> =>
  new ReadableStream<Uint8Array>({
    start(controller) {
      controller.close();
    },
  });

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
  };
};

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

  it('empties the chat on New chat', async () => {
    // Test: The New chat control.
    // Situation: One message has been sent, so the surface holds a turn.
    // Expectation: New chat leaves no turns behind, because there is no saved
    //   thread to come back to.
    stubFetch(closedStream());
    const { result } = renderHook(() => useChatSession(), { wrapper });

    await act(async () => {
      await result.current.send('What is the population of France?');
    });
    act(() => {
      result.current.newChat();
    });

    expect(result.current.turns).toEqual([]);
  });

  it('keeps a discarded answer out of the chat that replaces it', async () => {
    // Test: New chat while an answer is still streaming.
    // Situation: A question is in flight when the user starts a new chat, and
    //   the agent goes on to send the rest of that answer.
    //   `stop()` aborts the request, so the late text only reaches the reducer
    //   at all because this stub keeps delivering it.
    // Expectation: The chat is empty from the moment New chat is pressed, and
    //   the abandoned answer never lands in it.
    const stream = openStream();
    stubFetch(stream.body);
    const { result } = renderHook(() => useChatSession(), { wrapper });

    let answered!: Promise<void>;
    await act(async () => {
      answered = result.current.send('What is the population of France?');
    });
    expect(result.current.turns).toHaveLength(1);

    act(() => {
      result.current.newChat();
    });
    expect(result.current.turns).toEqual([]);

    await act(async () => {
      stream.push('content', { text: 'About 68 million.' });
      stream.end();
      await answered;
    });

    expect(result.current.turns).toEqual([]);
  });
});
