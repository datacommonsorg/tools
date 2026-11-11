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
 * @fileoverview Unit tests for OverviewTab: user message, outcome classifications,
 * turn indexing, summary counts, and conversation context.
 */

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { TurnDebugReport } from '@/src/components/panel_debug/report_debug';
import { OverviewTab } from '@/src/components/panel_debug/tab_debug_overview';

/** Builds a fresh TurnDebugReport with default values and optional overrides. */
const makeReport = (
  overrides: Partial<TurnDebugReport> = {},
): TurnDebugReport => ({
  userMessage: 'What is the population of France?',
  idempotencyKey: null,
  turnIndex: null,
  outcome: { kind: 'done', reason: null, truncated: false },
  clientTimings: null,
  trajectory: { thoughts: [], toolCalls: [] },
  response: { text: '', blocks: [], provenance: [], followUps: [] },
  context: {
    signedInWindow: false,
    stateSlots: null,
    compactedSummary: null,
  },
  ...overrides,
});

afterEach(() => {
  cleanup();
});

describe('OverviewTab', () => {
  it('renders user query, turn identifiers, and fallback None for absent fields', () => {
    // Test: Query text and absent-field fallback rendering.
    // Situation: A report with null turnIndex, null idempotencyKey, and no context.
    // Expectation: The user query is rendered and None is shown for absent identifiers.
    render(
      <OverviewTab
        report={makeReport({
          userMessage: 'Compare health metrics in Ohio and Michigan',
          turnIndex: null,
          idempotencyKey: null,
        })}
      />,
    );

    expect(
      screen.getByText('Compare health metrics in Ohio and Michigan'),
    ).toBeDefined();
    expect(screen.getAllByText('None')).toHaveLength(5);

    const sections = document.querySelectorAll('section');
    expect(sections).toHaveLength(5);
    expect(sections[0]?.querySelector('h4')?.textContent).toBe('User query');
    expect(sections[1]?.querySelector('h4')?.textContent).toBe('Turn outcome');
    for (const section of Array.from(sections)) {
      expect([...section.classList]).toEqual(
        expect.arrayContaining([
          'p-3',
          'rounded-lg',
          '[&:nth-of-type(even)]:bg-surface-narrative',
        ]),
      );
    }
  });

  it('renders turn index and idempotency key when provided', () => {
    // Test: Turn identifiers when present.
    // Situation: A report with turnIndex=3 and an idempotency key.
    // Expectation: Both values are rendered in the identifiers section.
    render(
      <OverviewTab
        report={makeReport({
          turnIndex: 3,
          idempotencyKey: 'idem-key-12345',
        })}
      />,
    );

    expect(screen.getByText('3')).toBeDefined();
    expect(screen.getByText('idem-key-12345')).toBeDefined();
  });

  it('renders done outcome with truncation flag and terminal reason', () => {
    // Test: Done outcome details.
    // Situation: A report with done outcome, truncated=true, and a reason string.
    // Expectation: Kind done, reason, and truncation Yes are displayed.
    render(
      <OverviewTab
        report={makeReport({
          outcome: {
            kind: 'done',
            reason: 'complete',
            truncated: true,
          },
        })}
      />,
    );

    expect(screen.getByText('done')).toBeDefined();
    expect(screen.getByText('complete')).toBeDefined();
    expect(screen.getByText('Yes')).toBeDefined();
  });

  it('renders refused outcome with refusal message and reason', () => {
    // Test: Refused outcome details.
    // Situation: A report with refused outcome and a message.
    // Expectation: Kind refused and the refusal message are displayed.
    render(
      <OverviewTab
        report={makeReport({
          outcome: {
            kind: 'refused',
            message: 'Question out of scope.',
            reason: 'policy',
          },
        })}
      />,
    );

    expect(screen.getByText('refused')).toBeDefined();
    expect(screen.getByText('Question out of scope.')).toBeDefined();
    expect(screen.getByText('policy')).toBeDefined();
  });

  it('renders error outcome with error detail', () => {
    // Test: Error outcome details.
    // Situation: A report with error outcome and an error message.
    // Expectation: Kind error and the error message are displayed.
    render(
      <OverviewTab
        report={makeReport({
          outcome: {
            kind: 'error',
            error: 'Backend request failed.',
            reason: null,
          },
        })}
      />,
    );

    expect(screen.getByText('error')).toBeDefined();
    expect(screen.getByText('Backend request failed.')).toBeDefined();
  });

  it('renders stopped and in_progress outcomes', () => {
    // Test: Stopped and in_progress outcome display.
    // Situation: First a stopped report, then an in_progress report.
    // Expectation: The respective kinds and pipeline phase are rendered.
    const { rerender } = render(
      <OverviewTab report={makeReport({ outcome: { kind: 'stopped' } })} />,
    );
    expect(screen.getByText('stopped')).toBeDefined();

    rerender(
      <OverviewTab
        report={makeReport({
          outcome: { kind: 'in_progress', phase: 'discovery' },
        })}
      />,
    );
    expect(screen.getByText('in_progress')).toBeDefined();
    expect(screen.getByText('discovery')).toBeDefined();
  });

  it('renders summary counts for trajectory and response collections', () => {
    // Test: Summary count metrics.
    // Situation: A report with 2 tool calls, 1 thought, 3 blocks, and 2 citations.
    // Expectation: The summary counts section displays each count.
    render(
      <OverviewTab
        report={makeReport({
          trajectory: {
            toolCalls: [
              { name: 'fetch_observations', arguments: {} },
              { name: 'get_variable_metadata', arguments: {} },
            ],
            thoughts: [{ text: 'Searching...', phase: 'discovery' }],
          },
          response: {
            text: 'Result',
            blocks: [
              { index: 0, type: 'text', markdown: 'Intro' },
              { index: 1, type: 'text', markdown: 'Body' },
              { index: 2, type: 'text', markdown: 'Conclusion' },
            ],
            provenance: [
              { name: 'Source 1', url: 'https://example.com/1' },
              { name: 'Source 2', url: 'https://example.com/2' },
              { name: 'Source 3', url: 'https://example.com/3' },
              { name: 'Source 4', url: 'https://example.com/4' },
            ],
            followUps: [],
          },
        })}
      />,
    );

    expect(screen.getByText('2')).toBeDefined();
    expect(screen.getByText('1')).toBeDefined();
    expect(screen.getByText('3')).toBeDefined();
    expect(screen.getByText('4')).toBeDefined();
  });

  it('renders conversation context details when present', () => {
    // Test: Context rendering for signed window, state slots, and compacted summary.
    // Situation: A report with signedInWindow=true, slots, and summary text.
    // Expectation: Yes is shown for signed window, and slot keys/values appear.
    render(
      <OverviewTab
        report={makeReport({
          context: {
            signedInWindow: true,
            compactedSummary: 'Previous turns discussed population.',
            stateSlots: {
              scopes: [
                {
                  places: { 'country/USA': 'United States' },
                  parent_place: null,
                  child_place_type: null,
                  variables: {},
                  date_range: null,
                },
              ],
            },
          },
        })}
      />,
    );

    expect(screen.getByText('Yes')).toBeDefined();
    expect(
      screen.getByText('Previous turns discussed population.'),
    ).toBeDefined();
    expect(screen.getByText(/"country\/USA": "United States"/)).toBeDefined();
  });
});
