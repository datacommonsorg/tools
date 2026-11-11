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
 * durations, and unrecorded milestone labels.
 */

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { TimingTab } from '@/src/components/panel_debug/tab_debug_timing';
import type { ClientTurnTimings } from '@/src/hooks/turn_timings';

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

afterEach(() => {
  cleanup();
});

describe('TimingTab', () => {
  it('renders an empty-state paragraph when client timings are absent', () => {
    // Test: Absent timings empty state.
    // Situation: clientTimings is null.
    // Expectation: A single empty-state message is rendered.
    render(<TimingTab clientTimings={null} />);

    expect(
      screen.getByText('No client timings were recorded for this turn.'),
    ).toBeDefined();
  });

  it('renders submission time and formatted milestones', () => {
    // Test: Formatted milestone values.
    // Situation: Timings with recorded milestones.
    // Expectation: Submission timestamp and millisecond durations are displayed.
    render(<TimingTab clientTimings={makeTimings()} />);

    expect(screen.getByText('2026-11-04T12:00:00.000Z')).toBeDefined();
    expect(screen.getByText('120 ms')).toBeDefined();
    expect(screen.getByText('300 ms')).toBeDefined();
    expect(screen.getByText('650 ms')).toBeDefined();
    expect(screen.getByText('1,200 ms')).toBeDefined();
    expect(screen.getByText('1,450 ms')).toBeDefined();
    expect(screen.getByText('1,500 ms')).toBeDefined();
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
});
