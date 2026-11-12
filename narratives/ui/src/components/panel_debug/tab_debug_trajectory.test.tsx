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
 * @fileoverview Unit tests for TrajectoryTab: renders model thoughts and tool
 * invocations or an empty state when neither was recorded.
 */

import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { TOOL_CALL_ERROR_MARKER } from '@/src/components/panel_debug/copy_debug';
import { TrajectoryTab } from '@/src/components/panel_debug/tab_debug_trajectory';
import type { ThoughtEvent, ToolCallEvent } from '@/src/hooks/use_sse_chat';
import { parseServerDebugReport } from '@/src/types/debug_report';

afterEach(() => {
  cleanup();
});

describe('TrajectoryTab', () => {
  it('renders an empty-state paragraph when both thoughts and tool calls are empty', () => {
    // Test: Empty state rendering.
    // Situation: Both thoughts and toolCalls are empty.
    // Expectation: A single empty-state message is rendered.
    render(<TrajectoryTab thoughts={[]} toolCalls={[]} />);

    expect(
      screen.getByText(
        'No thoughts or tool calls were recorded for this turn.',
      ),
    ).toBeDefined();
  });

  it('renders ordered thoughts with phase labels and pre-wrapped text', () => {
    // Test: Thoughts rendering.
    // Situation: Two thoughts in discovery and synthesis phases.
    // Expectation: Both phase labels and thought contents are displayed.
    const thoughts: readonly ThoughtEvent[] = [
      { phase: 'discovery', text: 'Searching for demographics data...' },
      { phase: 'synthesis', text: 'Drafting summary of observations...' },
    ];

    render(<TrajectoryTab thoughts={thoughts} toolCalls={[]} />);

    expect(screen.getByText('Thoughts (2)')).toBeDefined();
    expect(screen.getByText('discovery')).toBeDefined();
    expect(
      screen.getByText('Searching for demographics data...'),
    ).toBeDefined();
    expect(screen.getByText('synthesis')).toBeDefined();
    expect(
      screen.getByText('Drafting summary of observations...'),
    ).toBeDefined();
    const preElements = document.querySelectorAll('pre');
    expect(preElements[0]?.textContent).toBe(
      'Searching for demographics data...',
    );
    expect(preElements[1]?.textContent).toBe(
      'Drafting summary of observations...',
    );
  });

  it('renders tool calls when tool calls are provided', () => {
    // Test: Tool calls rendering.
    // Situation: One tool call is executed.
    // Expectation: The tool calls section heading and call details render.
    const toolCalls: readonly ToolCallEvent[] = [
      {
        name: 'fetch_observations',
        arguments: { variable_dcid: 'Count_Person' },
        status: 'success',
      },
    ];

    render(<TrajectoryTab thoughts={[]} toolCalls={toolCalls} />);

    expect(screen.getByText('Tool calls (1)')).toBeDefined();
    expect(screen.getByText('fetch_observations')).toBeDefined();
  });

  it('hides raw tool response behind toggle, updates toggle label, and tracks aria-expanded', () => {
    // Test: Raw response disclosure toggle.
    // Situation: A tool call with a raw response string.
    // Expectation: Raw response is hidden initially with aria-expanded="false"; clicking the toggle
    // reveals the raw response, updates aria-expanded="true", and flips label from Show to Hide.
    const rawResult = '{"observations":[{"date":"2020","value":100}]}';
    const toolCalls: readonly ToolCallEvent[] = [
      {
        name: 'fetch_observations',
        arguments: { variable_dcid: 'Count_Person' },
        status: 'success',
        result: rawResult,
      },
    ];

    render(<TrajectoryTab thoughts={[]} toolCalls={toolCalls} />);

    const toggleButton = screen.getByRole('button', {
      name: `Show raw response (${rawResult.length} chars)`,
    });
    expect(toggleButton.getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByText(rawResult)).toBeNull();

    fireEvent.click(toggleButton);

    expect(toggleButton.getAttribute('aria-expanded')).toBe('true');
    expect(
      screen.getByRole('button', {
        name: `Hide raw response (${rawResult.length} chars)`,
      }),
    ).toBeDefined();
    expect(screen.getByText(rawResult)).toBeDefined();

    fireEvent.click(toggleButton);

    expect(toggleButton.getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByText(rawResult)).toBeNull();
  });

  it('ensures at most one raw response is open by closing the first when opening a second', () => {
    // Test: Single active disclosure in tool call list.
    // Situation: Two tool calls each carrying a raw response.
    // Expectation: Opening the second call's raw response closes the first.
    const result1 = '{"first": 1}';
    const result2 = '{"second_call": 2}';
    const toolCalls: readonly ToolCallEvent[] = [
      {
        name: 'fetch_observations',
        arguments: { id: 1 },
        status: 'success',
        result: result1,
      },
      {
        name: 'fetch_observations',
        arguments: { id: 2 },
        status: 'success',
        result: result2,
      },
    ];

    render(<TrajectoryTab thoughts={[]} toolCalls={toolCalls} />);

    const toggle1 = screen.getByRole('button', {
      name: `Show raw response (${result1.length} chars)`,
    });
    const toggle2 = screen.getByRole('button', {
      name: `Show raw response (${result2.length} chars)`,
    });

    fireEvent.click(toggle1);
    expect(screen.getByText(result1)).toBeDefined();
    expect(screen.queryByText(result2)).toBeNull();
    expect(toggle1.getAttribute('aria-expanded')).toBe('true');
    expect(toggle2.getAttribute('aria-expanded')).toBe('false');

    fireEvent.click(toggle2);
    expect(screen.queryByText(result1)).toBeNull();
    expect(screen.getByText(result2)).toBeDefined();
    expect(toggle1.getAttribute('aria-expanded')).toBe('false');
    expect(toggle2.getAttribute('aria-expanded')).toBe('true');
  });

  it('renders error marker when a tool call fails with error status', () => {
    // Test: Errored tool call indicator.
    // Situation: A tool call finishes with status 'error'.
    // Expectation: Renders the error marker next to the tool name.
    const toolCalls: readonly ToolCallEvent[] = [
      {
        name: 'fetch_observations',
        arguments: { variable_dcid: 'Count_Person' },
        status: 'error',
      },
    ];

    render(<TrajectoryTab thoughts={[]} toolCalls={toolCalls} />);

    expect(screen.getByText('fetch_observations')).toBeDefined();
    expect(screen.getByText(TOOL_CALL_ERROR_MARKER.trim())).toBeDefined();
  });

  it('interleaves discovery thoughts and tool calls by round with duration and maintains single disclosure across rounds', () => {
    // Test: Per-round grouping and cross-round single-open disclosure.
    // Situation: Thoughts and tool calls spanning round 1 and round 2, plus synthesis thoughts.
    // Expectation: Groups round 1 and round 2 with formatted durations, puts synthesis thoughts
    // in their own section, and opening round 2 toggle closes round 1 toggle.
    const thoughts: readonly ThoughtEvent[] = [
      { phase: 'discovery', text: 'Searching demographics data...', round: 1 },
      { phase: 'discovery', text: 'Refining place filters...', round: 2 },
      { phase: 'synthesis', text: 'Drafting summary answer...' },
    ];
    const rawResult1 = '{"data": "r1"}';
    const rawResult2 = '{"data": "longer-round-2-result"}';
    const toolCalls: readonly ToolCallEvent[] = [
      {
        name: 'fetch_observations',
        arguments: { id: 1 },
        status: 'success',
        result: rawResult1,
        round: 1,
        duration_ms: 120,
      },
      {
        name: 'run_script',
        arguments: { id: 2 },
        status: 'success',
        result: rawResult2,
        round: 2,
        duration_ms: 250,
      },
    ];

    render(<TrajectoryTab thoughts={thoughts} toolCalls={toolCalls} />);

    expect(screen.getByText('Discovery round 1')).toBeDefined();
    expect(screen.getByText('Discovery round 2')).toBeDefined();
    expect(screen.getByText('Searching demographics data...')).toBeDefined();
    expect(screen.getByText('Refining place filters...')).toBeDefined();
    expect(screen.getByText('Synthesis thoughts')).toBeDefined();
    expect(screen.getByText('Drafting summary answer...')).toBeDefined();
    expect(screen.getByText('(120 ms)')).toBeDefined();
    expect(screen.getByText('(250 ms)')).toBeDefined();

    const toggle1 = screen.getByRole('button', {
      name: `Show raw response (${rawResult1.length} chars)`,
    });
    const toggle2 = screen.getByRole('button', {
      name: `Show raw response (${rawResult2.length} chars)`,
    });

    fireEvent.click(toggle1);
    expect(toggle1.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByText(rawResult1)).toBeDefined();
    expect(screen.queryByText(rawResult2)).toBeNull();

    fireEvent.click(toggle2);
    expect(toggle1.getAttribute('aria-expanded')).toBe('false');
    expect(toggle2.getAttribute('aria-expanded')).toBe('true');
    expect(screen.queryByText(rawResult1)).toBeNull();
    expect(screen.getByText(rawResult2)).toBeDefined();
  });

  it('falls back to serverReport toolCalls and thoughts on aborted discovery turns', () => {
    // Test: Aborted discovery fallback.
    // Situation: turn.toolCalls and turn.thoughts are empty, but serverReport has partial trajectory.
    // Expectation: Effective thoughts and tool calls are populated from serverReport with mapped durations.
    const serverReport = parseServerDebugReport({
      turn_id: 'turn-aborted-1',
      terminal_state: 'error',
      terminal_reason: 'Discovery failed',
      duration_ms: 320,
      tokens: { total_token_count: 0 },
      thoughts: [
        {
          phase: 'discovery',
          text: 'Partial reasoning before abort',
          round: 1,
        },
      ],
      tool_calls: [
        {
          name: 'fetch_observations',
          arguments: { variable_dcid: 'Count_Person' },
          status: 'error',
          round: 1,
          duration_ms: 85,
        },
      ],
    });

    render(
      <TrajectoryTab
        thoughts={[]}
        toolCalls={[]}
        serverReport={serverReport}
      />,
    );

    expect(screen.getByText('Discovery round 1')).toBeDefined();
    expect(screen.getByText('Partial reasoning before abort')).toBeDefined();
    expect(screen.getByText('fetch_observations')).toBeDefined();
    expect(screen.getByText('(85 ms)')).toBeDefined();
  });
});
