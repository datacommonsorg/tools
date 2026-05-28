'use client';

import { useCallback, useRef, useState } from 'react';
import type { QueryStreamRequest, StreamEvent } from '~/server/types';

export interface StreamingQueryState {
  status: string;
  isComplete: boolean;
  error: string | null;
}

export type StreamEventHandler = (event: StreamEvent) => void;

/**
 * Parses an SSE text stream into individual events.
 * SSE format: "event: {type}\ndata: {json}\n\n"
 */
const parseSSEChunk = (
  buffer: string,
): {
  events: StreamEvent[];
  remainder: string;
} => {
  const events: StreamEvent[] = [];
  const blocks = buffer.split('\n\n');
  // Last block may be incomplete
  const remainder = blocks.pop() || '';

  for (const block of blocks) {
    if (!block.trim()) continue;

    let dataLine = '';
    for (const line of block.split('\n')) {
      if (line.startsWith('data: ')) {
        dataLine = line.slice(6);
      }
    }

    if (dataLine) {
      try {
        const event: StreamEvent = JSON.parse(dataLine);
        events.push(event);
      } catch {
        // Skip malformed events
      }
    }
  }

  return { events, remainder };
};

export const useStreamingQuery = (onEvent?: StreamEventHandler) => {
  const [state, setState] = useState<StreamingQueryState>({
    status: '',
    isComplete: false,
    error: null,
  });
  const abortRef = useRef<AbortController | null>(null);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  const start = useCallback(async (params: QueryStreamRequest) => {
    setState({
      status: 'Connecting...',
      isComplete: false,
      error: null,
    });

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch('/api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
        signal: controller.signal,
      });

      if (!res.ok) {
        const errBody = await res.text();
        setState((prev) => ({
          ...prev,
          error: `API error: ${res.status} ${errBody}`,
          isComplete: true,
        }));
        return;
      }

      const reader = res.body?.getReader();
      if (!reader) {
        setState((prev) => ({
          ...prev,
          error: 'No response body',
          isComplete: true,
        }));
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';

      const handleEvent = (event: StreamEvent) => {
        switch (event.type) {
          case 'status':
            setState((prev) => ({ ...prev, status: event.message }));
            break;
          case 'complete':
            console.log(event);
            setState((prev) => ({
              ...prev,
              status: 'Complete',
              isComplete: true,
            }));
            break;
          case 'error':
            setState((prev) => ({
              ...prev,
              error: event.message,
              isComplete: true,
            }));
            break;
        }
        // Forward every event to the caller
        onEventRef.current?.(event);
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const { events, remainder } = parseSSEChunk(buffer);
        buffer = remainder;

        for (const event of events) {
          handleEvent(event);
        }
      }

      // Process any remaining buffer
      if (buffer.trim()) {
        const { events } = parseSSEChunk(`${buffer}\n\n`);
        for (const event of events) {
          handleEvent(event);
        }
      }

      setState((prev) =>
        prev.isComplete ? prev : { ...prev, isComplete: true },
      );
    } catch (err: unknown) {
      const error =
        err instanceof Error
          ? {
              name: err.name,
              message: err.message,
            }
          : null;

      if (error && error.name !== 'AbortError') {
        setState((prev) => ({
          ...prev,
          error: error.message,
          isComplete: true,
        }));
      }
    }
  }, []);

  const abort = useCallback(() => {
    abortRef.current?.abort();
    setState((prev) => ({ ...prev, status: 'Stopped', isComplete: true }));
  }, []);

  return { ...state, start, abort };
};
