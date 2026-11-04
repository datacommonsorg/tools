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
 * @fileoverview Unit tests for ConfigurationTab: renders build metadata,
 * role configs, and prompt SHA-256 hashes.
 */

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import {
  DEBUG_CONFIG_LABELS,
  DEBUG_EMPTY_STATE_MESSAGES,
  DEBUG_PANEL_COPY,
  DEBUG_SECTION_HEADINGS,
} from '@/src/components/panel_debug/copy_debug';
import { ConfigurationTab } from '@/src/components/panel_debug/tab_debug_configuration';
import {
  parseServerDebugReport,
  type ServerDebugReport,
} from '@/src/types/debug_report';

afterEach(() => {
  cleanup();
});

const makeServerReport = (
  overrides: Record<string, unknown> = {},
): ServerDebugReport => {
  const parsed = parseServerDebugReport({
    turn_id: 'test-turn-configuration',
    terminal_state: 'complete',
    duration_ms: 550,
    tokens: { total_token_count: 60 },
    ...overrides,
  });
  if (!parsed) {
    throw new Error('Failed to parse test server debug report');
  }
  return parsed;
};

describe('ConfigurationTab', () => {
  it('renders noServerReport empty state when serverReport is null', () => {
    // Test: Missing server report.
    // Situation: serverReport is null.
    // Expectation: Renders the no-server-report empty state message.
    render(<ConfigurationTab serverReport={null} />);

    expect(
      screen.getByText(DEBUG_EMPTY_STATE_MESSAGES.noServerReport),
    ).toBeDefined();
  });

  it('renders buildSha and falls back to None when buildSha is null', () => {
    // Test: Build SHA display and null fallback.
    // Situation: serverReport with null buildSha, then with a concrete SHA.
    // Expectation: None fallback displayed when null; exact SHA displayed when provided.
    const nullReport = makeServerReport({ build_sha: null });
    const { rerender } = render(<ConfigurationTab serverReport={nullReport} />);

    expect(screen.getByText(DEBUG_CONFIG_LABELS.buildSha)).toBeDefined();
    expect(screen.getByText(DEBUG_PANEL_COPY.noneFallback)).toBeDefined();

    const shaReport = makeServerReport({ build_sha: 'a1b2c3d4e5f6' });
    rerender(<ConfigurationTab serverReport={shaReport} />);

    expect(screen.getByText('a1b2c3d4e5f6')).toBeDefined();
  });

  it('renders role configurations and prompt hashes', () => {
    // Test: Role configurations and prompt hashes.
    // Situation: Concrete role configs and prompt hashes in serverReport.
    // Expectation: Role names, models, temperatures, thinking levels, and hashes are rendered.
    const report = makeServerReport({
      role_configs: [
        {
          role: 'discovery',
          model: 'gemini-2.5-flash',
          temperature: 0.2,
          thinking_level: 'high',
        },
      ],
      prompt_hashes: {
        'discovery.system': 'abcdef1234567890',
        'synthesis.user': '1234567890abcdef',
      },
    });

    render(<ConfigurationTab serverReport={report} />);

    expect(screen.getByText(DEBUG_SECTION_HEADINGS.roleConfigs)).toBeDefined();
    expect(screen.getByText('discovery')).toBeDefined();
    expect(screen.getByText('gemini-2.5-flash')).toBeDefined();
    expect(screen.getByText('0.2')).toBeDefined();
    expect(screen.getByText('high')).toBeDefined();

    expect(screen.getByText(DEBUG_SECTION_HEADINGS.promptHashes)).toBeDefined();
    expect(screen.getByText('discovery.system')).toBeDefined();
    expect(screen.getByText('abcdef1234567890')).toBeDefined();
    expect(screen.getByText('synthesis.user')).toBeDefined();
    expect(screen.getByText('1234567890abcdef')).toBeDefined();
  });

  it('renders empty fallback messages when role configs and prompt hashes are empty', () => {
    // Test: Empty role configs and prompt hashes.
    // Situation: serverReport has empty role_configs and empty prompt_hashes.
    // Expectation: Displays roleConfigs and promptHashes empty state messages.
    const report = makeServerReport({
      role_configs: [],
      prompt_hashes: {},
    });

    render(<ConfigurationTab serverReport={report} />);

    expect(
      screen.getByText(DEBUG_EMPTY_STATE_MESSAGES.roleConfigs),
    ).toBeDefined();
    expect(
      screen.getByText(DEBUG_EMPTY_STATE_MESSAGES.promptHashes),
    ).toBeDefined();
  });
});
