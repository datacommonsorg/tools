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
 * @fileoverview Unit tests for AnalysisTab: renders server-side analysis
 * specifications, rejected specifications, step refusal and timeout
 * diagnostics, and analysis digests.
 */

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import {
  DEBUG_EMPTY_STATE_MESSAGES,
  DEBUG_PANEL_COPY,
  DEBUG_SECTION_HEADINGS,
} from '@/src/components/panel_debug/copy_debug';
import { AnalysisTab } from '@/src/components/panel_debug/tab_debug_analysis';
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
    turn_id: 'test-turn-analysis',
    terminal_state: 'complete',
    duration_ms: 600,
    tokens: { total_token_count: 50 },
    ...overrides,
  });
  if (!parsed) {
    throw new Error('Failed to parse test server debug report');
  }
  return parsed;
};

describe('AnalysisTab', () => {
  it('renders noServerReport empty state when serverReport is null', () => {
    // Test: Missing server report.
    // Situation: serverReport is null.
    // Expectation: Renders the no-server-report empty state message.
    render(<AnalysisTab serverReport={null} />);

    expect(
      screen.getByText(DEBUG_EMPTY_STATE_MESSAGES.noServerReport),
    ).toBeDefined();
  });

  it('renders analysis empty state when serverReport has no analysis data', () => {
    // Test: Empty analysis report.
    // Situation: serverReport is present but all analysis fields are empty/null.
    // Expectation: Renders the analysis empty state message.
    const report = makeServerReport();

    render(<AnalysisTab serverReport={report} />);

    expect(screen.getByText(DEBUG_EMPTY_STATE_MESSAGES.analysis)).toBeDefined();
  });

  it('renders analysis summary, accepted specification, and digest', () => {
    // Test: Successful analysis rendering.
    // Situation: An accepted specification, scripts list, and digest are present.
    // Expectation: Summary fields, specification JSON, and digest JSON are rendered.
    const report = makeServerReport({
      specification_origin: 'model',
      scripts: ['ranking', 'timeseries'],
      processing_retries: 1,
      specification: {
        steps: [{ script: 'ranking', input_tables: ['t0'] }],
      },
      digest: {
        summary: 'Ranking executed successfully',
      },
    });

    render(<AnalysisTab serverReport={report} />);

    expect(
      screen.getByText(DEBUG_SECTION_HEADINGS.analysisSummary),
    ).toBeDefined();
    expect(screen.getByText('model')).toBeDefined();
    expect(screen.getByText('ranking, timeseries')).toBeDefined();
    expect(screen.getByText('1')).toBeDefined();
    expect(
      screen.getByText(DEBUG_SECTION_HEADINGS.acceptedSpecification),
    ).toBeDefined();
    expect(
      screen.getByText(DEBUG_SECTION_HEADINGS.analysisDigest),
    ).toBeDefined();
    expect(screen.getByText(/Ranking executed successfully/)).toBeDefined();
  });

  it('renders unavailable report when serverReport records an unavailable query', () => {
    // Test: Unavailable report rendering.
    // Situation: serverReport.unavailable is non-null.
    // Expectation: The unavailable report section and formatted JSON are rendered.
    const report = makeServerReport({
      unavailable: {
        reason: 'no_data_for_variable',
        variable: 'Count_Farm',
      },
    });

    render(<AnalysisTab serverReport={report} />);

    expect(
      screen.getByText(DEBUG_SECTION_HEADINGS.unavailableReport),
    ).toBeDefined();
    expect(screen.getByText(/no_data_for_variable/)).toBeDefined();
  });

  it('renders rejected specifications with validation errors and specification JSON', () => {
    // Test: Rejected specification rendering.
    // Situation: One rejected specification with validation errors and spec payload.
    // Expectation: Section heading with count, round, reason, error list, and spec JSON render.
    const report = makeServerReport({
      rejected_specifications: [
        {
          round: 1,
          reason: 'invalid_table_reference',
          errors: ['Table t99 does not exist in cache'],
          specification: { step: 'invalid' },
        },
      ],
    });

    render(<AnalysisTab serverReport={report} />);

    expect(screen.getByText('Rejected specifications (1)')).toBeDefined();
    expect(screen.getByText('invalid_table_reference')).toBeDefined();
    expect(screen.getByText('Table t99 does not exist in cache')).toBeDefined();
    expect(screen.getByText(/"step": "invalid"/)).toBeDefined();
  });

  it('renders step refusal diagnostic with full coverage details', () => {
    // Test: Step refusal diagnostic rendering.
    // Situation: A step_refusal diagnostic carrying place coverage metadata.
    // Expectation: Renders step refusal fields, coverage ratio, places, and reference date.
    const report = makeServerReport({
      diagnostics: [
        {
          kind: 'step_refusal',
          round: 2,
          step_id: 'step_rank_1',
          script: 'ranking',
          refusal_reason: 'insufficient_coverage',
          message: 'Coverage of places was below threshold',
          input_table_ids: ['t0', 't1'],
          alternative_source_count: 2,
          coverage: {
            contributing_places: 40,
            requested_places: 50,
            coverage_ratio: 0.8,
            reference_date: '2023',
            missing_places: ['geoId/02', 'geoId/15'],
            mixed_vintages: false,
          },
        },
      ],
    });

    render(<AnalysisTab serverReport={report} />);

    expect(screen.getByText('Processing diagnostics (1)')).toBeDefined();
    expect(screen.getByText('step_rank_1')).toBeDefined();
    expect(screen.getByText('ranking')).toBeDefined();
    expect(screen.getByText('insufficient_coverage')).toBeDefined();
    expect(
      screen.getByText('Coverage of places was below threshold'),
    ).toBeDefined();
    expect(screen.getByText('t0, t1')).toBeDefined();
    expect(screen.getByText('40 / 50')).toBeDefined();
    expect(screen.getByText('0.8')).toBeDefined();
    expect(screen.getByText('2023')).toBeDefined();
    expect(screen.getByText('geoId/02, geoId/15')).toBeDefined();
    expect(screen.getByText('No')).toBeDefined();
  });

  it('renders timeout diagnostic', () => {
    // Test: Timeout diagnostic rendering.
    // Situation: A timeout diagnostic is recorded.
    // Expectation: Renders timeout duration and message.
    const report = makeServerReport({
      diagnostics: [
        {
          kind: 'timeout',
          round: 1,
          timeout_seconds: 15,
          message: 'Script timed out after 15 seconds',
        },
      ],
    });

    render(<AnalysisTab serverReport={report} />);

    expect(screen.getByText('Processing diagnostics (1)')).toBeDefined();
    expect(screen.getByText('15s')).toBeDefined();
    expect(screen.getByText('Script timed out after 15 seconds')).toBeDefined();
  });

  it('falls back to None for empty optional values in summary and diagnostics', () => {
    // Test: Empty fallback values.
    // Situation: Null specificationOrigin, empty scripts, diagnostic with empty inputTableIds.
    // Expectation: Displays None fallback labels.
    const report = makeServerReport({
      specification_origin: null,
      scripts: [],
      processing_retries: 0,
      diagnostics: [
        {
          kind: 'step_refusal',
          step_id: 'step_empty_inputs',
          script: 'distribution',
          refusal_reason: 'no_inputs',
          message: 'No inputs provided',
          input_table_ids: [],
          alternative_source_count: 0,
        },
      ],
    });

    render(<AnalysisTab serverReport={report} />);

    const noneElements = screen.getAllByText(DEBUG_PANEL_COPY.noneFallback);
    expect(noneElements.length).toBeGreaterThanOrEqual(2);
  });
});
