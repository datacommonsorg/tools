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
});
