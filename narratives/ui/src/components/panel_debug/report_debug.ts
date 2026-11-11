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
 * @fileoverview Pure client-side turn debug report model, turn outcome
 * classifier, settled-turn predicate, and `?debug` URL flag helper.
 */

import type {
  AnswerBlock,
  ChatTurn,
  ClientTurnTimings,
  ConversationStateSlots,
  ProvenanceItem,
  ThoughtEvent,
  ToolCallEvent,
  TurnStatus,
} from '@/src/hooks/use_sse_chat';

const DEBUG_QUERY_PARAM = 'debug';

const ENABLED_DEBUG_VALUES: ReadonlySet<string> = new Set(['', 'true', '1']);

const SETTLED_TURN_STATUSES: ReadonlySet<TurnStatus> = new Set([
  'done',
  'refused',
  'error',
]);

const EMPTY_FOLLOW_UPS: readonly string[] = [];

/** Normalizes an optional terminal reason to a non-empty string or `null`. */
const normalizeTerminalReason = (reason: string | undefined): string | null => {
  if (reason === undefined || reason.length === 0) {
    return null;
  }
  return reason;
};

/** Pipeline phases in which a chat turn has not yet reached a terminal state. */
export type InProgressTurnPhase = Exclude<
  TurnStatus,
  'done' | 'refused' | 'error'
>;

/**
 * Mutually exclusive outcome classification of a {@link ChatTurn}, matching the
 * rendering precedence in `TurnView` (`stopped` overrides `status === 'done'`).
 */
export type TurnDebugOutcome =
  | { readonly kind: 'stopped' }
  | {
      readonly kind: 'done';
      readonly reason: string | null;
      readonly truncated: boolean;
    }
  | {
      readonly kind: 'refused';
      readonly message: string;
      readonly reason: string | null;
    }
  | {
      readonly kind: 'error';
      readonly error: string;
      readonly reason: string | null;
    }
  | { readonly kind: 'in_progress'; readonly phase: InProgressTurnPhase };

/** Streamed model thoughts and MCP/server tool-call records for one turn. */
export interface TurnDebugTrajectory {
  readonly thoughts: readonly ThoughtEvent[];
  readonly toolCalls: readonly ToolCallEvent[];
}

/** Assembled prose, ordered blocks, citations, and follow-up suggestions for one turn. */
export interface TurnDebugResponse {
  readonly text: string;
  readonly blocks: readonly AnswerBlock[];
  readonly provenance: readonly ProvenanceItem[];
  readonly followUps: readonly string[];
}

/** Multi-turn conversation window metadata for one turn, omitting raw HMAC material. */
export interface TurnDebugContext {
  readonly signedInWindow: boolean;
  readonly stateSlots: Readonly<ConversationStateSlots> | null;
  readonly compactedSummary: string | null;
}

/**
 * Read-only, JSON-serializable client debug snapshot for one chat turn, using
 * explicit `null` rather than `undefined` for absent top-level and outcome
 * fields.
 */
export interface TurnDebugReport {
  readonly userMessage: string;
  readonly idempotencyKey: string | null;
  readonly turnIndex: number | null;
  readonly outcome: TurnDebugOutcome;
  readonly clientTimings: Readonly<ClientTurnTimings> | null;
  readonly trajectory: TurnDebugTrajectory;
  readonly response: TurnDebugResponse;
  readonly context: TurnDebugContext;
}

/**
 * Reports whether the URL query string `search` enables debug mode (`?debug`,
 * `?debug=`, `?debug=true`, or `?debug=1`, case-insensitively after trimming).
 *
 * Rejects absent parameters and legacy or falsy values such as `'provenance'`,
 * `'false'`, or `'0'`.
 */
export const isDebugUrlEnabled = (search: string): boolean => {
  const rawValue = new URLSearchParams(search).get(DEBUG_QUERY_PARAM);
  if (rawValue === null) {
    return false;
  }
  return ENABLED_DEBUG_VALUES.has(rawValue.trim().toLowerCase());
};

/**
 * Reports whether `turn` has reached a settled state (`done`, `refused`,
 * `error`, or user-aborted `stopped`) rather than streaming or awaiting start.
 */
export const isTurnSettled = (turn: ChatTurn): boolean =>
  Boolean(turn.stopped) || SETTLED_TURN_STATUSES.has(turn.status);

/**
 * Classifies `turn` into a discriminated {@link TurnDebugOutcome}. Checks
 * `turn.stopped` before `turn.status === 'done'` because `stop()` sets both
 * `status: 'done'` and `stopped: true`.
 */
export const classifyTurnOutcome = (turn: ChatTurn): TurnDebugOutcome => {
  if (turn.stopped) {
    return { kind: 'stopped' };
  }
  const reason = normalizeTerminalReason(turn.terminalReason);
  if (turn.status === 'done') {
    return {
      kind: 'done',
      reason,
      truncated: Boolean(turn.truncated),
    };
  }
  if (turn.status === 'refused') {
    return {
      kind: 'refused',
      message: turn.refusalMessage ?? '',
      reason,
    };
  }
  if (turn.status === 'error') {
    return {
      kind: 'error',
      error: turn.error ?? '',
      reason,
    };
  }
  return {
    kind: 'in_progress',
    phase: turn.status,
  };
};

/**
 * Builds a read-only, JSON-serializable {@link TurnDebugReport} from `turn`.
 * Raw `turn.hmac` values are excluded; `context.signedInWindow` records only
 * whether the turn currently holds a window signature.
 */
export const buildTurnDebugReport = (turn: ChatTurn): TurnDebugReport => ({
  userMessage: turn.userMessage,
  idempotencyKey: turn.idempotencyKey ?? null,
  turnIndex: turn.turnIndex ?? null,
  outcome: classifyTurnOutcome(turn),
  clientTimings: turn.clientTimings ?? null,
  trajectory: {
    thoughts: turn.thoughts,
    toolCalls: turn.toolCalls,
  },
  response: {
    text: turn.text,
    blocks: turn.blocks,
    provenance: turn.provenance,
    followUps: turn.followUps ?? EMPTY_FOLLOW_UPS,
  },
  context: {
    signedInWindow: Boolean(turn.hmac),
    stateSlots: turn.stateSlots ?? null,
    compactedSummary: turn.compactedSummary ?? null,
  },
});
