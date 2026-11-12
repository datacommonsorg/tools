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
 * @fileoverview Unit tests for TokensTab: verifies empty states, aggregate token
 * counts, and per-call token breakdowns.
 */

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import {
  DEBUG_EMPTY_STATE_MESSAGES,
  DEBUG_SECTION_HEADINGS,
} from '@/src/components/panel_debug/copy_debug';
import { TokensTab } from '@/src/components/panel_debug/tab_debug_tokens';
import type {
  ServerDebugReport,
  ServerDebugTokenCall,
} from '@/src/types/debug_report';

/** Builds a fresh ServerDebugTokenCall with sensible defaults and overrides. */
const makeTokenCall = (
  overrides: Partial<ServerDebugTokenCall> = {},
): ServerDebugTokenCall => ({
  phase: 'discovery',
  model: 'gemini-2.5-flash',
  round: 1,
  promptTokenCount: 1200,
  candidatesTokenCount: 300,
  thoughtsTokenCount: 150,
  totalTokenCount: 1650,
  ...overrides,
});

/** Builds a fresh ServerDebugReport with minimal fields and overrides. */
const makeServerReport = (
  overrides: Partial<ServerDebugReport> = {},
): ServerDebugReport => ({
  turnId: 'turn-123',
  terminalState: 'complete',
  terminalReason: null,
  isClarification: false,
  pattern: 'direct',
  durationMs: 1500,
  phaseDurationsMs: { discovery: 1200, synthesis: 300 },
  nestedPhases: {},
  mcpIterations: 1,
  scripts: [],
  processingRetries: 0,
  chartsEmitted: 1,
  chartsRejected: 0,
  tokens: {
    promptTokenCount: 2000,
    candidatesTokenCount: 500,
    thoughtsTokenCount: 250,
    totalTokenCount: 2750,
    calls: [makeTokenCall()],
  },
  tables: [],
  thoughts: [],
  toolCalls: [],
  rejectedSpecifications: [],
  diagnostics: [],
  specification: null,
  specificationOrigin: null,
  unavailable: null,
  digest: null,
  synthesisPrompt: null,
  synthesisRawOutput: null,
  roleConfigs: [],
  promptHashes: {},
  buildSha: 'abc1234',
  ...overrides,
});

afterEach(() => {
  cleanup();
});

describe('TokensTab', () => {
  it('renders noServerReport empty state when serverReport is null', () => {
    // Test: Missing server report empty state.
    // Situation: serverReport prop is null.
    // Expectation: Renders the standard noServerReport message.
    render(<TokensTab serverReport={null} />);

    expect(
      screen.getByText(DEBUG_EMPTY_STATE_MESSAGES.noServerReport),
    ).toBeDefined();
  });

  it('renders aggregate counts and tokenCalls empty state when calls is empty', () => {
    // Test: Aggregate tokens with no individual calls.
    // Situation: serverReport has non-zero token totals but calls array is empty.
    // Expectation: Renders Token totals section and the tokenCalls empty state message.
    const report = makeServerReport({
      tokens: {
        promptTokenCount: 1500,
        candidatesTokenCount: 350,
        thoughtsTokenCount: 100,
        totalTokenCount: 1950,
        calls: [],
      },
    });

    render(<TokensTab serverReport={report} />);

    expect(screen.getByText(DEBUG_SECTION_HEADINGS.tokenTotals)).toBeDefined();
    expect(screen.getByText('1,500')).toBeDefined();
    expect(screen.getByText('350')).toBeDefined();
    expect(screen.getByText('100')).toBeDefined();
    expect(screen.getByText('1,950')).toBeDefined();
    expect(
      screen.getByText(DEBUG_EMPTY_STATE_MESSAGES.tokenCalls),
    ).toBeDefined();
  });

  it('renders per-call breakdown with phase, model, round, and token counts', () => {
    // Test: Populated token calls breakdown.
    // Situation: serverReport has multiple calls, one with a round and one without.
    // Expectation: Both calls render phase, model, token values, and round label only when present.
    const callWithRound = makeTokenCall({
      phase: 'discovery',
      model: 'gemini-2.5-flash',
      round: 1,
      promptTokenCount: 1111,
      candidatesTokenCount: 222,
      thoughtsTokenCount: 55,
      totalTokenCount: 1388,
    });
    const callWithoutRound = makeTokenCall({
      phase: 'synthesis',
      model: 'gemini-2.5-pro',
      round: null,
      promptTokenCount: 3333,
      candidatesTokenCount: 888,
      thoughtsTokenCount: 111,
      totalTokenCount: 4332,
    });
    const report = makeServerReport({
      tokens: {
        promptTokenCount: 4444,
        candidatesTokenCount: 1110,
        thoughtsTokenCount: 166,
        totalTokenCount: 5720,
        calls: [callWithRound, callWithoutRound],
      },
    });

    render(<TokensTab serverReport={report} />);

    expect(
      screen.queryByText(DEBUG_EMPTY_STATE_MESSAGES.tokenCalls),
    ).toBeNull();
    expect(screen.getByText('discovery')).toBeDefined();
    expect(screen.getByText('(round 1)')).toBeDefined();
    expect(screen.getByText('gemini-2.5-flash')).toBeDefined();
    expect(screen.getByText('1,111')).toBeDefined();

    expect(screen.getByText('synthesis')).toBeDefined();
    expect(screen.getByText('gemini-2.5-pro')).toBeDefined();
    expect(screen.getByText('3,333')).toBeDefined();
    expect(screen.getByText('888')).toBeDefined();
    expect(screen.getByText('4,332')).toBeDefined();
    expect(screen.queryByText('(round null)')).toBeNull();
  });
});
