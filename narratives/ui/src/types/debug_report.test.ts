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
 * @fileoverview Unit tests for the server debug report wire parser:
 * envelope validation, full payload decoding, and field narrowing.
 */

import { describe, expect, it } from 'vitest';
import {
  parseServerDebugReport,
  type ServerDebugReport,
} from '@/src/types/debug_report';

/** Builds a full valid raw server debug report wire payload. */
const makeValidRawPayload = (
  overrides: Record<string, unknown> = {},
): Record<string, unknown> => ({
  turn_id: 'turn_test_123',
  terminal_state: 'complete',
  terminal_reason: 'complete',
  is_clarification: false,
  pattern: 'comparison',
  duration_ms: 1250.5,
  phase_durations_ms: { classify: 120, discovery: 800, synthesis: 330.5 },
  nested_phases: { processing: 'discovery' },
  mcp_iterations: 2,
  scripts: ['ranking', 'timeseries'],
  processing_retries: 1,
  charts_emitted: 2,
  charts_rejected: 0,
  tokens: {
    prompt_token_count: 500,
    candidates_token_count: 150,
    thoughts_token_count: 50,
    total_token_count: 700,
    calls: [
      {
        phase: 'discovery',
        model: 'gemini-2.5-flash',
        round: 1,
        prompt_token_count: 300,
        candidates_token_count: 50,
        thoughts_token_count: 20,
        total_token_count: 370,
      },
      {
        phase: 'synthesis',
        model: 'gemini-2.5-pro',
        round: null,
        prompt_token_count: 200,
        candidates_token_count: 100,
        thoughts_token_count: 30,
        total_token_count: 330,
      },
    ],
  },
  tables: [
    {
      table_id: 't0',
      used_in_answer: true,
      variable_dcid: 'Count_Person',
      variable_name: 'Total Population',
      unit: 'person',
      scaling_factor: 1,
      measurement_method: 'Census',
      observation_period: 'P1Y',
      parent_place_dcid: 'country/FRA',
      child_place_type: null,
      places_with_data_count: 1,
      places: [{ dcid: 'country/FRA', name: 'France' }],
      facet_id: '12345',
      source_selection: 'chosen',
      source: {
        name: 'INSEE',
        url: 'https://insee.fr',
        license: 'Open License',
        dataset: 'Demographics',
        provider: 'National Statistical Institute',
        date_range: '2010-2023',
      },
      date_range: ['2010', '2023'],
      row_count: 14,
    },
  ],
  thoughts: [
    { phase: 'discovery', text: 'Searching for demographics', round: 1 },
    { phase: 'synthesis', text: 'Composing narrative', round: null },
  ],
  tool_calls: [
    {
      name: 'fetch_observations',
      arguments: { variable_dcid: 'Count_Person' },
      status: 'success',
      result: '{"ok": true}',
      round: 1,
      duration_ms: 150.2,
    },
  ],
  rejected_specifications: [
    {
      round: 1,
      reason: 'schema_validation_error',
      errors: ['Missing required step'],
      specification: { steps: [] },
    },
  ],
  diagnostics: [
    {
      kind: 'step_refusal',
      round: 1,
      step_id: 's0',
      script: 'ranking',
      refusal_reason: 'insufficient_coverage',
      message: 'Not enough data points.',
      input_table_ids: ['t0'],
      coverage: {
        contributing_places: 3,
        requested_places: 10,
        coverage_ratio: 0.3,
        reference_date: '2020',
        missing_places: ['geoId/06'],
        mixed_vintages: false,
      },
      alternative_source_count: 2,
    },
    {
      kind: 'timeout',
      round: 2,
      timeout_seconds: 5,
      message: 'Processing budget exceeded.',
    },
  ],
  specification: { steps: [{ script: 'ranking' }] },
  specification_origin: 'model',
  unavailable: null,
  digest: { summary: 'Completed 1 step' },
  synthesis_prompt: {
    text: 'Synthesize demographic data.',
    truncated: false,
    total_chars: 29,
  },
  synthesis_raw_output: {
    text: 'France has 68M residents.',
    truncated: false,
    total_chars: 25,
  },
  role_configs: [
    {
      role: 'planner',
      model: 'gemini-2.5-flash',
      temperature: 0.2,
      thinking_level: 'low',
    },
  ],
  prompt_hashes: { system: 'hash123' },
  build_sha: 'commit_sha_xyz',
  ...overrides,
});

describe('parseServerDebugReport', () => {
  it('parses a complete valid server payload into ServerDebugReport', () => {
    // Test: Full wire payload parsing.
    // Situation: A valid report payload with all fields populated.
    // Expectation: Every field is decoded into the typed ServerDebugReport structure.
    const raw = makeValidRawPayload();
    const parsed = parseServerDebugReport(raw);

    expect(parsed).not.toBeNull();
    const report = parsed as ServerDebugReport;

    expect(report.turnId).toBe('turn_test_123');
    expect(report.terminalState).toBe('complete');
    expect(report.terminalReason).toBe('complete');
    expect(report.isClarification).toBe(false);
    expect(report.pattern).toBe('comparison');
    expect(report.durationMs).toBe(1250.5);
    expect(report.phaseDurationsMs).toEqual({
      classify: 120,
      discovery: 800,
      synthesis: 330.5,
    });
    expect(report.nestedPhases).toEqual({ processing: 'discovery' });
    expect(report.mcpIterations).toBe(2);
    expect(report.scripts).toEqual(['ranking', 'timeseries']);
    expect(report.processingRetries).toBe(1);
    expect(report.chartsEmitted).toBe(2);
    expect(report.chartsRejected).toBe(0);

    expect(report.tokens.promptTokenCount).toBe(500);
    expect(report.tokens.candidatesTokenCount).toBe(150);
    expect(report.tokens.thoughtsTokenCount).toBe(50);
    expect(report.tokens.totalTokenCount).toBe(700);
    expect(report.tokens.calls).toHaveLength(2);
    expect(report.tokens.calls[0]).toEqual({
      phase: 'discovery',
      model: 'gemini-2.5-flash',
      round: 1,
      promptTokenCount: 300,
      candidatesTokenCount: 50,
      thoughtsTokenCount: 20,
      totalTokenCount: 370,
    });
    expect(report.tokens.calls[1].round).toBeNull();

    expect(report.tables).toHaveLength(1);
    const table = report.tables[0];
    expect(table.tableId).toBe('t0');
    expect(table.usedInAnswer).toBe(true);
    expect(table.variableDcid).toBe('Count_Person');
    expect(table.variableName).toBe('Total Population');
    expect(table.unit).toBe('person');
    expect(table.scalingFactor).toBe(1);
    expect(table.places).toEqual([{ dcid: 'country/FRA', name: 'France' }]);
    expect(table.sourceSelection).toBe('chosen');
    expect(table.source).toEqual({
      name: 'INSEE',
      url: 'https://insee.fr',
      license: 'Open License',
      dataset: 'Demographics',
      provider: 'National Statistical Institute',
      dateRange: '2010-2023',
    });
    expect(table.dateRange).toEqual(['2010', '2023']);
    expect(table.rowCount).toBe(14);

    expect(report.thoughts).toEqual([
      { phase: 'discovery', text: 'Searching for demographics', round: 1 },
      { phase: 'synthesis', text: 'Composing narrative', round: null },
    ]);

    expect(report.toolCalls).toHaveLength(1);
    expect(report.toolCalls[0]).toEqual({
      name: 'fetch_observations',
      arguments: { variable_dcid: 'Count_Person' },
      status: 'success',
      result: '{"ok": true}',
      round: 1,
      durationMs: 150.2,
    });

    expect(report.rejectedSpecifications).toHaveLength(1);
    expect(report.rejectedSpecifications[0]).toEqual({
      round: 1,
      reason: 'schema_validation_error',
      errors: ['Missing required step'],
      specification: { steps: [] },
    });

    expect(report.diagnostics).toHaveLength(2);
    expect(report.diagnostics[0]).toEqual({
      kind: 'step_refusal',
      round: 1,
      stepId: 's0',
      script: 'ranking',
      refusalReason: 'insufficient_coverage',
      message: 'Not enough data points.',
      inputTableIds: ['t0'],
      coverage: {
        contributingPlaces: 3,
        requestedPlaces: 10,
        coverageRatio: 0.3,
        referenceDate: '2020',
        missingPlaces: ['geoId/06'],
        mixedVintages: false,
      },
      alternativeSourceCount: 2,
    });
    expect(report.diagnostics[1]).toEqual({
      kind: 'timeout',
      round: 2,
      timeoutSeconds: 5,
      message: 'Processing budget exceeded.',
    });

    expect(report.specification).toEqual({ steps: [{ script: 'ranking' }] });
    expect(report.specificationOrigin).toBe('model');
    expect(report.unavailable).toBeNull();
    expect(report.digest).toEqual({ summary: 'Completed 1 step' });
    expect(report.synthesisPrompt).toEqual({
      text: 'Synthesize demographic data.',
      truncated: false,
      totalChars: 29,
    });
    expect(report.synthesisRawOutput).toEqual({
      text: 'France has 68M residents.',
      truncated: false,
      totalChars: 25,
    });
    expect(report.roleConfigs).toEqual([
      {
        role: 'planner',
        model: 'gemini-2.5-flash',
        temperature: 0.2,
        thinkingLevel: 'low',
      },
    ]);
    expect(report.promptHashes).toEqual({ system: 'hash123' });
    expect(report.buildSha).toBe('commit_sha_xyz');
  });

  it('rejects invalid or malformed envelopes by returning null', () => {
    // Test: Envelope validation.
    // Situation: Inputs that are not objects, have empty turn_id, invalid terminal_state,
    //   non-finite duration, or missing tokens object.
    // Expectation: parseServerDebugReport returns null for every invalid case.
    expect(parseServerDebugReport(null)).toBeNull();
    expect(parseServerDebugReport(undefined)).toBeNull();
    expect(parseServerDebugReport('not an object')).toBeNull();
    expect(parseServerDebugReport([])).toBeNull();

    // Empty or non-string turn_id
    expect(
      parseServerDebugReport(makeValidRawPayload({ turn_id: '' })),
    ).toBeNull();
    expect(
      parseServerDebugReport(makeValidRawPayload({ turn_id: 123 })),
    ).toBeNull();
    expect(
      parseServerDebugReport(makeValidRawPayload({ turn_id: undefined })),
    ).toBeNull();

    // Invalid terminal_state
    expect(
      parseServerDebugReport(
        makeValidRawPayload({ terminal_state: 'cancelled' }),
      ),
    ).toBeNull();
    expect(
      parseServerDebugReport(makeValidRawPayload({ terminal_state: '' })),
    ).toBeNull();

    // Non-finite duration_ms
    expect(
      parseServerDebugReport(makeValidRawPayload({ duration_ms: Number.NaN })),
    ).toBeNull();
    expect(
      parseServerDebugReport(
        makeValidRawPayload({ duration_ms: Number.POSITIVE_INFINITY }),
      ),
    ).toBeNull();
    expect(
      parseServerDebugReport(makeValidRawPayload({ duration_ms: '100' })),
    ).toBeNull();

    // Invalid tokens
    expect(
      parseServerDebugReport(makeValidRawPayload({ tokens: null })),
    ).toBeNull();
    expect(
      parseServerDebugReport(makeValidRawPayload({ tokens: 'none' })),
    ).toBeNull();
  });
});
