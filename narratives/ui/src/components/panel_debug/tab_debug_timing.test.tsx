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
 * @fileoverview Unit tests for TimingTab: submission timestamp, formatted milestone
 * durations, unrecorded milestone labels, and server phase durations with nested labeling.
 */

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import {
  DEBUG_EMPTY_STATE_MESSAGES,
  DEBUG_SECTION_HEADINGS,
} from '@/src/components/panel_debug/copy_debug';
import { TimingTab } from '@/src/components/panel_debug/tab_debug_timing';
import type { ClientTurnTimings } from '@/src/hooks/turn_timings';
import type { ServerDebugReport } from '@/src/types/debug_report';

/** Builds a fresh ClientTurnTimings object with sample milestones. */
const makeTimings = (
  overrides: Partial<ClientTurnTimings> = {},
): ClientTurnTimings => ({
  submittedAt: '2026-11-04T12:00:00.000Z',
  headersReceivedMs: 120,
  firstThoughtMs: 300,
  firstBlockMs: 650,
  terminalMs: 1200,
  followUpsMs: 1450,
  totalMs: 1500,
  ...overrides,
});

/** Builds a fresh ServerDebugReport for timing tests. */
const makeServerReport = (
  overrides: Partial<ServerDebugReport> = {},
): ServerDebugReport => ({
  turnId: 'turn-time-1',
  terminalState: 'complete',
  terminalReason: null,
  isClarification: false,
  pattern: 'direct',
  durationMs: 2500,
  phaseDurationsMs: {
    admission: 10,
    discovery: 1800,
    processing: 600,
    synthesis: 650,
  },
  nestedPhases: {
    processing: 'discovery',
  },
  mcpIterations: 1,
  scripts: [],
  processingRetries: 0,
  chartsEmitted: 1,
  chartsRejected: 0,
  tokens: {
    promptTokenCount: 1000,
    candidatesTokenCount: 200,
    thoughtsTokenCount: 100,
    totalTokenCount: 1300,
    calls: [],
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
  buildSha: 'build-sha',
  ...overrides,
});

afterEach(() => {
  cleanup();
});

describe('TimingTab', () => {
  it('renders an empty-state paragraph when both client timings and server report are absent', () => {
    // Test: Absent timings empty state.
    // Situation: clientTimings is null and serverReport is null.
    // Expectation: A single empty-state message is rendered.
    render(<TimingTab clientTimings={null} serverReport={null} />);

    expect(screen.getByText(DEBUG_EMPTY_STATE_MESSAGES.timing)).toBeDefined();
  });

  it('renders submission time and formatted milestones when client timings are present', () => {
    // Test: Formatted milestone values.
    // Situation: Timings with recorded milestones and no serverReport.
    // Expectation: Submission timestamp and millisecond durations are displayed.
    render(<TimingTab clientTimings={makeTimings()} />);

    expect(screen.getByText('2026-11-04T12:00:00.000Z')).toBeDefined();
    expect(screen.getByText('120 ms')).toBeDefined();
    expect(screen.getByText('300 ms')).toBeDefined();
    expect(screen.getByText('650 ms')).toBeDefined();
    expect(screen.getByText('1,200 ms')).toBeDefined();
    expect(screen.getByText('1,450 ms')).toBeDefined();
    expect(screen.getByText('1,500 ms')).toBeDefined();
    expect(screen.queryByText(DEBUG_SECTION_HEADINGS.serverTimings)).toBeNull();
  });

  it('labels unrecorded optional milestones with Not recorded', () => {
    // Test: Unrecorded milestone label.
    // Situation: Timings with headersReceivedMs and totalMs but undefined optional intermediate milestones.
    // Expectation: Missing milestones show "Not recorded".
    render(
      <TimingTab
        clientTimings={makeTimings({
          firstThoughtMs: undefined,
          followUpsMs: undefined,
        })}
      />,
    );

    expect(screen.getAllByText('Not recorded').length).toBe(2);
  });

  it('renders server timings and labels nested processing phase explicitly when serverReport is present', () => {
    // Test: Server timing display with nested phase labeling.
    // Situation: clientTimings is null but serverReport is provided with nestedPhases: { processing: 'discovery' }.
    // Expectation: Server turn duration renders, admission and synthesis render directly, and processing is labeled "processing (nested in discovery)".
    const serverReport = makeServerReport();
    render(<TimingTab clientTimings={null} serverReport={serverReport} />);

    expect(screen.queryByText(DEBUG_EMPTY_STATE_MESSAGES.timing)).toBeNull();
    expect(
      screen.getByText(DEBUG_SECTION_HEADINGS.serverTimings),
    ).toBeDefined();
    expect(screen.getByText('Server turn duration')).toBeDefined();
    expect(screen.getByText('2,500 ms')).toBeDefined();
    expect(screen.getByText('admission')).toBeDefined();
    expect(screen.getByText('10 ms')).toBeDefined();
    expect(screen.getByText('discovery')).toBeDefined();
    expect(screen.getByText('1,800 ms')).toBeDefined();
    expect(screen.getByText('processing (nested in discovery)')).toBeDefined();
    expect(screen.getByText('600 ms')).toBeDefined();
    expect(screen.getByText('synthesis')).toBeDefined();
    expect(screen.getByText('650 ms')).toBeDefined();
  });

  it('renders both client milestones and server timings when both are provided', () => {
    // Test: Combined client and server timings.
    // Situation: Both clientTimings and serverReport are non-null.
    // Expectation: Both Submission time/milestones and Server timings sections render together.
    render(
      <TimingTab
        clientTimings={makeTimings()}
        serverReport={makeServerReport()}
      />,
    );

    expect(
      screen.getByText(DEBUG_SECTION_HEADINGS.submissionTime),
    ).toBeDefined();
    expect(screen.getByText(DEBUG_SECTION_HEADINGS.milestones)).toBeDefined();
    expect(
      screen.getByText(DEBUG_SECTION_HEADINGS.serverTimings),
    ).toBeDefined();
  });
});
