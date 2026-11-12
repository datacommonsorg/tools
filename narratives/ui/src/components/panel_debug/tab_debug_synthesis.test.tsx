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
 * @fileoverview Unit tests for SynthesisTab: renders synthesis prompts and raw
 * model outputs with preview truncation, full-text toggles, server-cap notices,
 * and clipboard copy actions.
 */

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  DEBUG_EMPTY_STATE_MESSAGES,
  DEBUG_PANEL_COPY,
  DEBUG_SECTION_HEADINGS,
} from '@/src/components/panel_debug/copy_debug';
import {
  SYNTHESIS_PREVIEW_CHAR_LIMIT,
  SynthesisTab,
} from '@/src/components/panel_debug/tab_debug_synthesis';
import {
  parseServerDebugReport,
  type ServerDebugReport,
} from '@/src/types/debug_report';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const makeServerReport = (
  overrides: Record<string, unknown> = {},
): ServerDebugReport => {
  const parsed = parseServerDebugReport({
    turn_id: 'test-turn-synthesis',
    terminal_state: 'complete',
    duration_ms: 700,
    tokens: { total_token_count: 80 },
    ...overrides,
  });
  if (!parsed) {
    throw new Error('Failed to parse test server debug report');
  }
  return parsed;
};

describe('SynthesisTab', () => {
  it('renders noServerReport empty state when serverReport is null', () => {
    // Test: Missing server report.
    // Situation: serverReport is null.
    // Expectation: Renders the no-server-report empty state message.
    render(<SynthesisTab serverReport={null} />);

    expect(
      screen.getByText(DEBUG_EMPTY_STATE_MESSAGES.noServerReport),
    ).toBeDefined();
  });

  it('renders synthesis empty state when both synthesis fields are null', () => {
    // Test: Empty synthesis data.
    // Situation: serverReport has null synthesisPrompt and null synthesisRawOutput.
    // Expectation: Renders the synthesis empty state message.
    const report = makeServerReport();

    render(<SynthesisTab serverReport={report} />);

    expect(
      screen.getByText(DEBUG_EMPTY_STATE_MESSAGES.synthesis),
    ).toBeDefined();
  });

  it('truncates text exceeding preview limit and toggles full text', () => {
    // Test: Preview truncation and toggle.
    // Situation: synthesisPrompt text exceeds SYNTHESIS_PREVIEW_CHAR_LIMIT.
    // Expectation: Text is sliced to limit with aria-expanded="false"; clicking toggle expands text.
    const longText = 'A'.repeat(SYNTHESIS_PREVIEW_CHAR_LIMIT + 200);
    const report = makeServerReport({
      synthesis_prompt: {
        text: longText,
        truncated: false,
        total_chars: longText.length,
      },
    });

    render(<SynthesisTab serverReport={report} />);

    expect(
      screen.getByText(DEBUG_SECTION_HEADINGS.synthesisPrompt),
    ).toBeDefined();
    const toggleButton = screen.getByRole('button', {
      name: 'Show full prompt',
    });
    expect(toggleButton.getAttribute('aria-expanded')).toBe('false');

    const pre = screen.getByText('A'.repeat(SYNTHESIS_PREVIEW_CHAR_LIMIT));
    expect(pre.textContent).toBe('A'.repeat(SYNTHESIS_PREVIEW_CHAR_LIMIT));

    fireEvent.click(toggleButton);
    expect(toggleButton.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByRole('button', { name: 'Show preview' })).toBeDefined();
    expect(screen.getByText(longText).textContent).toBe(longText);

    fireEvent.click(screen.getByRole('button', { name: 'Show preview' }));
    expect(toggleButton.getAttribute('aria-expanded')).toBe('false');
  });

  it('surfaces explicit server truncation notice when truncated is true', () => {
    // Test: Server cap notice.
    // Situation: synthesisRawOutput has truncated: true and total_chars greater than text length.
    // Expectation: Displays the server capped character count notice.
    const report = makeServerReport({
      synthesis_raw_output: {
        text: 'Partial output',
        truncated: true,
        total_chars: 5_000,
      },
    });

    render(<SynthesisTab serverReport={report} />);

    expect(
      screen.getByText(DEBUG_SECTION_HEADINGS.synthesisRawOutput),
    ).toBeDefined();
    expect(
      screen.getByText(
        `Server capped: showing ${'Partial output'.length.toLocaleString()} of 5,000 characters`,
      ),
    ).toBeDefined();
  });

  it('copies full text via navigator.clipboard and displays Copied status', async () => {
    // Test: Successful clipboard copy.
    // Situation: navigator.clipboard.writeText resolves successfully.
    // Expectation: Copied status feedback is displayed.
    const writeTextSpy = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', {
      ...navigator,
      clipboard: { writeText: writeTextSpy },
    });

    const report = makeServerReport({
      synthesis_prompt: {
        text: 'System instructions for synthesis',
        truncated: false,
        total_chars: 33,
      },
    });

    render(<SynthesisTab serverReport={report} />);

    const copyButton = screen.getByRole('button', {
      name: 'Copy full prompt',
    });
    fireEvent.click(copyButton);

    expect(writeTextSpy).toHaveBeenCalledWith(
      'System instructions for synthesis',
    );
    await waitFor(() => {
      expect(screen.getByText(DEBUG_PANEL_COPY.copiedStatus)).toBeDefined();
    });
  });

  it('handles clipboard write rejection with Copy failed status', async () => {
    // Test: Clipboard rejection handling.
    // Situation: navigator.clipboard.writeText rejects.
    // Expectation: Copy failed status feedback is displayed.
    const writeTextSpy = vi
      .fn()
      .mockRejectedValue(new Error('Clipboard blocked'));
    vi.stubGlobal('navigator', {
      ...navigator,
      clipboard: { writeText: writeTextSpy },
    });

    const report = makeServerReport({
      synthesis_prompt: {
        text: 'Prompt text',
        truncated: false,
        total_chars: 11,
      },
    });

    render(<SynthesisTab serverReport={report} />);

    const copyButton = screen.getByRole('button', {
      name: 'Copy full prompt',
    });
    fireEvent.click(copyButton);

    await waitFor(() => {
      expect(screen.getByText(DEBUG_PANEL_COPY.copyFailedStatus)).toBeDefined();
    });
  });

  it('handles missing navigator.clipboard gracefully with Copy failed status', async () => {
    // Test: Missing clipboard API.
    // Situation: navigator.clipboard is undefined.
    // Expectation: Copy failed status feedback is displayed.
    vi.stubGlobal('navigator', {
      ...navigator,
      clipboard: undefined,
    });

    const report = makeServerReport({
      synthesis_prompt: {
        text: 'Prompt text',
        truncated: false,
        total_chars: 11,
      },
    });

    render(<SynthesisTab serverReport={report} />);

    const copyButton = screen.getByRole('button', {
      name: 'Copy full prompt',
    });
    fireEvent.click(copyButton);

    await waitFor(() => {
      expect(screen.getByText(DEBUG_PANEL_COPY.copyFailedStatus)).toBeDefined();
    });
  });
});
