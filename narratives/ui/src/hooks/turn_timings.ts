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
 * @fileoverview Client-observed turn timing model and pure monotonic milestone
 * reducers consumed by `useSseChat`.
 */

import type { ChatStreamEvent, ChatTurn } from '@/src/hooks/use_sse_chat';

const ELAPSED_MS_PRECISION_FACTOR = 100;

/**
 * Client-observed wall-clock submission time and monotonic elapsed durations
 * (in milliseconds from submission) for one chat turn.
 */
export interface ClientTurnTimings {
  /** ISO-8601 UTC timestamp captured when the user submits the turn. */
  submittedAt: string;
  /** Elapsed milliseconds until `fetch` resolves with HTTP response headers. */
  headersReceivedMs?: number;
  /** Elapsed milliseconds until the first `thought` SSE frame arrives. */
  firstThoughtMs?: number;
  /** Elapsed milliseconds until the first valid answer block is appended. */
  firstBlockMs?: number;
  /** Elapsed milliseconds until the `terminal` SSE frame arrives. */
  terminalMs?: number;
  /** Elapsed milliseconds until a valid `follow_ups` SSE frame arrives. */
  followUpsMs?: number;
  /** Elapsed milliseconds until the turn settles or stream reading terminates. */
  totalMs?: number;
}

/** Numeric milestone keys recorded once per turn on {@link ClientTurnTimings}. */
export type TimingMilestone = Exclude<keyof ClientTurnTimings, 'submittedAt'>;

/**
 * Computes elapsed milliseconds since `submittedPerfMs`, clamping negative
 * deltas to `0` and rounding to two decimal places.
 */
export const computeElapsedMs = (
  submittedPerfMs: number,
  nowPerfMs: number = performance.now(),
): number => {
  const clampedMs = Math.max(0, nowPerfMs - submittedPerfMs);
  return (
    Math.round(clampedMs * ELAPSED_MS_PRECISION_FACTOR) /
    ELAPSED_MS_PRECISION_FACTOR
  );
};

/**
 * Records a write-once elapsed timing milestone on `turn` when
 * `turn.clientTimings` is present and `milestone` is not yet set.
 */
export const recordTimingMilestone = (
  turn: ChatTurn,
  milestone: TimingMilestone,
  elapsedMs: number,
): ChatTurn => {
  const timings = turn.clientTimings;
  if (!timings || timings[milestone] !== undefined) {
    return turn;
  }
  return {
    ...turn,
    clientTimings: {
      ...timings,
      [milestone]: elapsedMs,
    },
  };
};

/**
 * Records write-once client timing milestones for streamed SSE events after
 * `applyEvent` produces `nextTurn`.
 */
export const recordStreamEventTiming = (
  previousTurn: ChatTurn,
  nextTurn: ChatTurn,
  event: ChatStreamEvent,
  elapsedMs: number,
): ChatTurn => {
  if (event.event === 'thought') {
    return recordTimingMilestone(nextTurn, 'firstThoughtMs', elapsedMs);
  }
  if (
    event.event === 'content' &&
    nextTurn.blocks.length > previousTurn.blocks.length
  ) {
    return recordTimingMilestone(nextTurn, 'firstBlockMs', elapsedMs);
  }
  if (event.event === 'terminal') {
    return recordTimingMilestone(nextTurn, 'terminalMs', elapsedMs);
  }
  if (
    event.event === 'follow_ups' &&
    Array.isArray(event.data.follow_up_questions)
  ) {
    return recordTimingMilestone(nextTurn, 'followUpsMs', elapsedMs);
  }
  return nextTurn;
};
