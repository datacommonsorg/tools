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
 * @fileoverview Unit tests for `report_debug.ts`: `?debug` URL flag parsing,
 * settled-turn detection, discriminated turn outcome classification, and
 * read-only JSON-serializable turn debug report construction.
 */

import { describe, expect, it } from 'vitest';
import {
  buildTurnDebugReport,
  classifyTurnOutcome,
  isDebugUrlEnabled,
  isTurnSettled,
} from '@/src/components/panel_debug/report_debug';
import type { ChatTurn, TurnStatus } from '@/src/hooks/use_sse_chat';

/** Builds a fresh baseline `ChatTurn` with optional field overrides. */
const makeTurn = (overrides: Partial<ChatTurn> = {}): ChatTurn => ({
  userMessage: 'What is the population of France?',
  status: 'idle',
  toolCalls: [],
  thoughts: [],
  text: '',
  blocks: [],
  provenance: [],
  ...overrides,
});

describe('isDebugUrlEnabled', () => {
  it('returns true for bare, empty, true, and 1 debug query values', () => {
    // Test: Accepted truthy forms of the `?debug` query parameter.
    // Situation: Query strings carry bare `?debug`, `?debug=`, `debug=true`
    //   (mixed case and whitespace-padded), or `debug=1`, with or without a
    //   leading `?` and alongside other query parameters.
    // Expectation: Every accepted form returns `true`.
    expect(isDebugUrlEnabled('?debug')).toBe(true);
    expect(isDebugUrlEnabled('?debug=')).toBe(true);
    expect(isDebugUrlEnabled('debug=true')).toBe(true);
    expect(isDebugUrlEnabled('?debug=TRUE')).toBe(true);
    expect(isDebugUrlEnabled('?debug=  True  ')).toBe(true);
    expect(isDebugUrlEnabled('?debug=1')).toBe(true);
    expect(isDebugUrlEnabled('?q=france&debug=1&lang=en')).toBe(true);
  });

  it('returns false when debug is absent or set to provenance, false, 0, or other values', () => {
    // Test: Rejection of absent, legacy, and falsy or unrecognized values.
    // Situation: Query strings omit `debug` or set it to `provenance`, `false`,
    //   `0`, `yes`, control-byte-prefixed text, or arbitrary strings.
    // Expectation: Every case returns `false`.
    expect(isDebugUrlEnabled('')).toBe(false);
    expect(isDebugUrlEnabled('?q=france')).toBe(false);
    expect(isDebugUrlEnabled('?debug=provenance')).toBe(false);
    expect(isDebugUrlEnabled('?debug=false')).toBe(false);
    expect(isDebugUrlEnabled('?debug=0')).toBe(false);
    expect(isDebugUrlEnabled('?debug=yes')).toBe(false);
    expect(isDebugUrlEnabled('?debug=%00true')).toBe(false);
  });
});

describe('isTurnSettled', () => {
  it.each([
    'done',
    'refused',
    'error',
  ] as const)('returns true when turn status is %s', (status) => {
    // Test: Terminal statuses settle a turn.
    // Situation: A turn carries one of the terminal `TurnStatus` values.
    // Expectation: `isTurnSettled` returns `true`.
    expect(isTurnSettled(makeTurn({ status }))).toBe(true);
  });

  it.each([
    'idle',
    'classify',
    'discovery',
    'processing',
    'synthesis',
  ] as const)('returns false when turn status is %s and not stopped', (status) => {
    // Test: Non-terminal pipeline phases are not settled.
    // Situation: A turn is in an active pipeline phase with `stopped` unset.
    // Expectation: `isTurnSettled` returns `false`.
    expect(isTurnSettled(makeTurn({ status }))).toBe(false);
  });

  it('returns true when turn.stopped is true regardless of status', () => {
    // Test: User-aborted turns count as settled.
    // Situation: `stopped: true` is set on a turn with `done` or `synthesis`.
    // Expectation: `isTurnSettled` returns `true` in both cases.
    expect(isTurnSettled(makeTurn({ status: 'done', stopped: true }))).toBe(
      true,
    );
    expect(
      isTurnSettled(makeTurn({ status: 'synthesis', stopped: true })),
    ).toBe(true);
  });
});

describe('classifyTurnOutcome', () => {
  it('classifies a stopped turn as stopped before checking status === done', () => {
    // Test: Precedence of `stopped` over `status: 'done'`.
    // Situation: `stop()` marks an aborted turn with both `status: 'done'` and
    //   `stopped: true`.
    // Expectation: `classifyTurnOutcome` returns `{ kind: 'stopped' }`.
    expect(
      classifyTurnOutcome(
        makeTurn({
          status: 'done',
          stopped: true,
          terminalReason: 'ok',
          truncated: true,
        }),
      ),
    ).toEqual({ kind: 'stopped' });
  });

  it('classifies completed, refused, and error turns with normalized reasons', () => {
    // Test: Terminal outcome shapes and empty-reason normalization.
    // Situation: Completed, refused, and error turns carry non-empty, empty, or
    //   omitted `terminalReason` values.
    // Expectation: Each classifies into its discriminated `kind` with `reason`
    //   normalized to a non-empty string or `null`.
    expect(
      classifyTurnOutcome(
        makeTurn({
          status: 'done',
          terminalReason: 'ok',
          truncated: true,
        }),
      ),
    ).toEqual({ kind: 'done', reason: 'ok', truncated: true });

    expect(
      classifyTurnOutcome(makeTurn({ status: 'done', terminalReason: '' })),
    ).toEqual({ kind: 'done', reason: null, truncated: false });

    expect(
      classifyTurnOutcome(
        makeTurn({
          status: 'refused',
          refusalMessage: 'Outside statistical scope.',
          terminalReason: 'off_domain',
        }),
      ),
    ).toEqual({
      kind: 'refused',
      message: 'Outside statistical scope.',
      reason: 'off_domain',
    });

    expect(
      classifyTurnOutcome(
        makeTurn({
          status: 'error',
          error: 'MCP request timed out.',
          terminalReason: 'mcp_timeout',
        }),
      ),
    ).toEqual({
      kind: 'error',
      error: 'MCP request timed out.',
      reason: 'mcp_timeout',
    });

    expect(
      classifyTurnOutcome(
        makeTurn({ status: 'error', error: 'HTTP 500 Internal Server Error' }),
      ),
    ).toEqual({
      kind: 'error',
      error: 'HTTP 500 Internal Server Error',
      reason: null,
    });

    expect(classifyTurnOutcome(makeTurn({ status: 'refused' }))).toEqual({
      kind: 'refused',
      message: '',
      reason: null,
    });

    expect(classifyTurnOutcome(makeTurn({ status: 'error' }))).toEqual({
      kind: 'error',
      error: '',
      reason: null,
    });
  });

  it.each([
    'idle',
    'classify',
    'discovery',
    'processing',
    'synthesis',
  ] as const)('classifies active status %s as in_progress with matching phase', (phase: Exclude<
    TurnStatus,
    'done' | 'refused' | 'error'
  >) => {
    // Test: Outcome shape for in-flight pipeline phases.
    // Situation: A turn is in active phase `phase` and not stopped.
    // Expectation: `classifyTurnOutcome` returns `{ kind: 'in_progress', phase }`.
    expect(classifyTurnOutcome(makeTurn({ status: phase }))).toEqual({
      kind: 'in_progress',
      phase,
    });
  });
});

describe('buildTurnDebugReport', () => {
  it('maps absent optional fields to explicit null and serializes cleanly to JSON', () => {
    // Test: Null normalization and JSON round-trip on a minimal turn.
    // Situation: A turn omits `idempotencyKey`, `turnIndex`, `clientTimings`,
    //   `followUps`, `hmac`, `stateSlots`, and `compactedSummary`.
    // Expectation: Top-level optional fields are `null` (or `[]` for
    //   `followUps`), `signedInWindow` is `false`, and `JSON.parse(JSON.stringify(report))`
    //   equals `report` with no dropped keys.
    const report = buildTurnDebugReport(
      makeTurn({
        status: 'done',
        text: 'About 68 million.',
        blocks: [{ index: 0, type: 'text', markdown: 'About 68 million.' }],
      }),
    );

    expect(report).toEqual({
      userMessage: 'What is the population of France?',
      idempotencyKey: null,
      turnIndex: null,
      outcome: { kind: 'done', reason: null, truncated: false },
      clientTimings: null,
      trajectory: {
        thoughts: [],
        toolCalls: [],
      },
      response: {
        text: 'About 68 million.',
        blocks: [{ index: 0, type: 'text', markdown: 'About 68 million.' }],
        provenance: [],
        followUps: [],
      },
      context: {
        signedInWindow: false,
        stateSlots: null,
        compactedSummary: null,
      },
    });
    expect(JSON.parse(JSON.stringify(report))).toEqual(report);
  });

  it('projects populated turn state while redacting raw hmac into signedInWindow', () => {
    // Test: Full turn report projection and HMAC redaction.
    // Situation: A signed turn carries `hmac`, `clientTimings`, `thoughts`,
    //   `toolCalls`, `blocks`, `provenance`, `followUps`, `stateSlots`, and
    //   `compactedSummary`.
    // Expectation: `report` exposes all read-only fields cleanly for JSON
    //   serialization, sets `context.signedInWindow` to `true`, and excludes
    //   both the `hmac` property and its secret digest string.
    const secretHmac = 'deadbeef'.repeat(8);
    const turn = makeTurn({
      status: 'done',
      idempotencyKey: 'key-7',
      turnIndex: 3,
      hmac: secretHmac,
      terminalReason: 'ok',
      clientTimings: {
        submittedAt: '2026-04-11T16:00:00.000Z',
        headersReceivedMs: 22.5,
        totalMs: 365,
      },
      thoughts: [{ text: 'Checking population', phase: 'discovery' }],
      toolCalls: [
        {
          name: 'fetch_observations',
          arguments: { variable_dcid: 'Count_Person' },
          status: 'success',
        },
      ],
      text: 'France has 68 million residents.',
      blocks: [
        {
          index: 0,
          type: 'text',
          markdown: 'France has 68 million residents.',
        },
      ],
      provenance: [{ name: 'INSEE', url: 'https://www.insee.fr/' }],
      followUps: ['How does Germany compare?'],
      stateSlots: {
        scopes: [
          {
            places: { 'country/FRA': 'France' },
            parent_place: null,
            child_place_type: null,
            variables: { Count_Person: 'Total Population' },
            date_range: ['2020', '2023'],
          },
        ],
      },
      compactedSummary: 'Earlier demographic turns.',
    });

    const report = buildTurnDebugReport(turn);
    const serialized = JSON.stringify(report);

    expect(report.context.signedInWindow).toBe(true);
    expect(report).not.toHaveProperty('hmac');
    expect(report.context).not.toHaveProperty('hmac');
    expect(serialized).not.toContain(secretHmac);
    expect(JSON.parse(serialized)).toEqual(report);
  });
});
