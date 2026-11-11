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
 * @fileoverview Synchronous unit tests for `turn_timings.ts`: elapsed duration
 * rounding and clamping, write-once milestone recording, and stream event
 * milestone transitions.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  computeElapsedMs,
  recordStreamEventTiming,
  recordTimingMilestone,
} from '@/src/hooks/turn_timings';
import {
  applyEvent,
  type ChatStreamEvent,
  type ChatTurn,
} from '@/src/hooks/use_sse_chat';

const SUBMITTED_AT = '2026-04-11T15:30:00.000Z';

/** Builds a fresh baseline turn initialized with `clientTimings.submittedAt`. */
const makeTurn = (overrides: Partial<ChatTurn> = {}): ChatTurn => ({
  userMessage: 'What is the population of France?',
  status: 'idle',
  toolCalls: [],
  thoughts: [],
  text: '',
  blocks: [],
  provenance: [],
  clientTimings: { submittedAt: SUBMITTED_AT },
  ...overrides,
});

/** Applies `event` via `applyEvent` and records its stream timing milestone. */
const applyTimedEvent = (
  turn: ChatTurn,
  event: ChatStreamEvent,
  elapsedMs: number,
): ChatTurn => {
  const nextTurn = applyEvent(turn, event);
  return recordStreamEventTiming(turn, nextTurn, event, elapsedMs);
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe('computeElapsedMs', () => {
  it('rounds positive deltas to two decimal places, clamps negative deltas to +0, and defaults to performance.now()', () => {
    // Test: Monotonic delta calculation, rounding, and non-negative clamping.
    // Situation: `computeElapsedMs` is called with explicit fractional and
    //   negative deltas, and with `nowPerfMs` omitted while `performance.now`
    //   is stubbed.
    // Expectation: Fractional deltas round to 2 decimals, negative deltas clamp
    //   to `+0` (never `-0`), and the default argument reads `performance.now()`.
    expect(computeElapsedMs(1000, 1035.678)).toBe(35.68);
    expect(computeElapsedMs(1000, 1245.554)).toBe(245.55);
    expect(Object.is(computeElapsedMs(1000, 999.999), 0)).toBe(true);

    vi.spyOn(performance, 'now').mockReturnValue(1512.345);
    expect(computeElapsedMs(1000)).toBe(512.35);
  });
});

describe('recordTimingMilestone', () => {
  it('records each milestone once and leaves turns without clientTimings or with existing milestones unchanged', () => {
    // Test: Write-once milestone semantics and no-op reference preservation.
    // Situation: `headersReceivedMs` is recorded twice on a timed turn, and
    //   once on a turn without `clientTimings`.
    // Expectation: The first write sets `headersReceivedMs`, the second write
    //   returns the same turn reference with the original value intact, and an
    //   untimed turn is returned unchanged.
    const initial = makeTurn();
    const recorded = recordTimingMilestone(initial, 'headersReceivedMs', 28.4);
    expect(recorded.clientTimings).toEqual({
      submittedAt: SUBMITTED_AT,
      headersReceivedMs: 28.4,
    });

    const duplicate = recordTimingMilestone(recorded, 'headersReceivedMs', 99);
    expect(duplicate).toBe(recorded);
    expect(duplicate.clientTimings?.headersReceivedMs).toBe(28.4);

    const untimed = makeTurn({ clientTimings: undefined });
    expect(recordTimingMilestone(untimed, 'totalMs', 50)).toBe(untimed);
  });
});

describe('recordStreamEventTiming', () => {
  it('records write-once firstThoughtMs, terminalMs, and valid followUpsMs while ignoring status and malformed follow_ups', () => {
    // Test: Stream milestone capture for thoughts, terminal frames, and follow-ups.
    // Situation: A turn processes `status`, two `thought` frames, a `terminal`
    //   frame, a malformed non-array `follow_ups` frame, and two valid
    //   `follow_ups` frames.
    // Expectation: `status` and non-array `follow_ups` set no milestone, while
    //   `firstThoughtMs`, `terminalMs`, and `followUpsMs` record the first
    //   valid arrival of each event type.
    let turn = makeTurn();
    turn = applyTimedEvent(
      turn,
      { event: 'status', data: { phase: 'discovery' } },
      15,
    );
    expect(turn.clientTimings).toEqual({ submittedAt: SUBMITTED_AT });

    turn = applyTimedEvent(
      turn,
      { event: 'thought', data: { thought: 'Searching', phase: 'discovery' } },
      85.25,
    );
    turn = applyTimedEvent(
      turn,
      {
        event: 'thought',
        data: { thought: 'Synthesizing', phase: 'synthesis' },
      },
      140.5,
    );
    turn = applyTimedEvent(
      turn,
      {
        event: 'terminal',
        data: { state: 'complete', idempotency_key: 'k1', reason: 'ok' },
      },
      310,
    );
    turn = applyTimedEvent(
      turn,
      {
        event: 'follow_ups',
        data: { follow_up_questions: 'invalid' as unknown as string[] },
      },
      340,
    );
    expect(turn.clientTimings?.followUpsMs).toBeUndefined();

    turn = applyTimedEvent(
      turn,
      { event: 'follow_ups', data: { follow_up_questions: ['And Spain?'] } },
      365.75,
    );
    turn = applyTimedEvent(
      turn,
      { event: 'follow_ups', data: { follow_up_questions: ['And Italy?'] } },
      390,
    );

    expect(turn.clientTimings).toEqual({
      submittedAt: SUBMITTED_AT,
      firstThoughtMs: 85.25,
      terminalMs: 310,
      followUpsMs: 365.75,
    });
  });

  it('sets firstBlockMs only when applyEvent appends a valid text or chart block', () => {
    // Test: `firstBlockMs` requires `turn.blocks.length` to grow.
    // Situation: Non-block `content` payloads (`tool_call`, `sources`), an
    //   empty text block, and malformed chart blocks run through `applyEvent`
    //   before two valid blocks arrive.
    // Expectation: Ignored content leaves `firstBlockMs` undefined; the first
    //   valid block sets `firstBlockMs`, and the second valid block does not
    //   overwrite it.
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    let turn = makeTurn();

    turn = applyTimedEvent(
      turn,
      {
        event: 'content',
        data: { tool_call: { name: 'fetch_observations', arguments: {} } },
      },
      40,
    );
    turn = applyTimedEvent(
      turn,
      {
        event: 'content',
        data: { sources: [{ name: 'INSEE', url: 'https://www.insee.fr/' }] },
      },
      55,
    );
    turn = applyTimedEvent(
      turn,
      { event: 'content', data: { block: { type: 'text', markdown: '' } } },
      70,
    );
    turn = applyTimedEvent(
      turn,
      {
        event: 'content',
        data: {
          block: {
            type: 'chart',
            chart: { viz_type: 'line', variable_dcids: [] },
          },
        },
      },
      90,
    );
    expect(turn.blocks).toHaveLength(0);
    expect(turn.clientTimings?.firstBlockMs).toBeUndefined();

    turn = applyTimedEvent(
      turn,
      {
        event: 'content',
        data: { block: { type: 'text', markdown: 'About 68 million.' } },
      },
      195.4,
    );
    turn = applyTimedEvent(
      turn,
      {
        event: 'content',
        data: { block: { type: 'text', markdown: 'In 2023.' } },
      },
      240.8,
    );

    expect(turn.blocks).toHaveLength(2);
    expect(turn.clientTimings?.firstBlockMs).toBe(195.4);
  });
});
