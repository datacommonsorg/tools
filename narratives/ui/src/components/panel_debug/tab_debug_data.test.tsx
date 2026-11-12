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
 * @fileoverview Unit tests for DataTab: verifies empty states, populated cached table cards,
 * scope summaries, usage statuses, detail label omissions, and link sanitization.
 */

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import {
  DEBUG_EMPTY_STATE_MESSAGES,
  DEBUG_FACET_DETAIL_LABELS,
  DEBUG_TABLE_USAGE_LABELS,
  UNNAMED_SOURCE_LABEL,
  VARIABLE_NAME_SEPARATOR,
} from '@/src/components/panel_debug/copy_debug';
import { DataTab } from '@/src/components/panel_debug/tab_debug_data';
import type {
  ServerDebugReport,
  ServerDebugTable,
} from '@/src/types/debug_report';

/** Builds a fresh ServerDebugTable with realistic defaults and overrides. */
const makeServerTable = (
  overrides: Partial<ServerDebugTable> = {},
): ServerDebugTable => ({
  tableId: 't0',
  usedInAnswer: true,
  variableDcid: 'Count_Person',
  variableName: 'Total Population',
  unit: 'people',
  scalingFactor: null,
  measurementMethod: 'CensusACS5yrSurvey',
  observationPeriod: 'P1Y',
  parentPlaceDcid: 'country/USA',
  childPlaceType: 'State',
  placesWithDataCount: 52,
  places: [{ dcid: 'geoId/06', name: 'California' }],
  facetId: 'facet_123',
  sourceSelection: 'chosen',
  source: {
    name: 'US Census Bureau',
    url: 'https://census.gov',
    license: 'Public Domain',
    dataset: 'Decennial Census',
    provider: 'Department of Commerce',
    dateRange: '2020..2024',
  },
  dateRange: ['2020', '2024'],
  rowCount: 520,
  ...overrides,
});

/** Builds a fresh ServerDebugReport containing the given tables. */
const makeServerReport = (
  tables: readonly ServerDebugTable[] = [],
  overrides: Partial<ServerDebugReport> = {},
): ServerDebugReport => ({
  turnId: 'turn-123',
  terminalState: 'complete',
  terminalReason: null,
  isClarification: false,
  pattern: 'direct',
  durationMs: 1200,
  phaseDurationsMs: { discovery: 1000, synthesis: 200 },
  nestedPhases: {},
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
  tables,
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
  buildSha: 'build-sha-123',
  ...overrides,
});

afterEach(() => {
  cleanup();
});

describe('DataTab', () => {
  it('renders noServerReport empty state when serverReport is null', () => {
    // Test: Missing server report empty state.
    // Situation: serverReport prop is null.
    // Expectation: Renders noServerReport message.
    render(<DataTab serverReport={null} />);

    expect(
      screen.getByText(DEBUG_EMPTY_STATE_MESSAGES.noServerReport),
    ).toBeDefined();
  });

  it('renders dataTables empty state when serverReport tables list is empty', () => {
    // Test: Empty cached tables list.
    // Situation: serverReport is provided but tables is empty [].
    // Expectation: Renders dataTables empty state message.
    render(<DataTab serverReport={makeServerReport([])} />);

    expect(
      screen.getByText(DEBUG_EMPTY_STATE_MESSAGES.dataTables),
    ).toBeDefined();
  });

  it('renders populated table rows with all metadata fields', () => {
    // Test: Populated table card rendering.
    // Situation: serverReport contains a fully populated ServerDebugTable.
    // Expectation: Table ID, used status, selection mode, variable DCID and name,
    // scope, places, observations, coverage, unit, facet, and license are rendered.
    const table = makeServerTable();
    render(<DataTab serverReport={makeServerReport([table])} />);

    expect(screen.getByText('Cached tables (1)')).toBeDefined();
    expect(screen.getByText('t0')).toBeDefined();
    expect(screen.getByText('Used in answer')).toBeDefined();
    expect(screen.getByText('chosen')).toBeDefined();
    expect(screen.getByText('Count_Person')).toBeDefined();
    expect(
      screen.getByText(`${VARIABLE_NAME_SEPARATOR}Total Population`.trim()),
    ).toBeDefined();
    expect(screen.getByText(/State in country\/USA/)).toBeDefined();
    expect(screen.getByText(/52 with data/)).toBeDefined();
    expect(screen.getByText('California (geoId/06)')).toBeDefined();
    expect(
      screen.getByText(DEBUG_FACET_DETAIL_LABELS.observations),
    ).toBeDefined();
    expect(screen.getByText('520')).toBeDefined();
    expect(screen.getByText(DEBUG_FACET_DETAIL_LABELS.coverage)).toBeDefined();
    expect(screen.getByText('2020..2024')).toBeDefined();
    expect(screen.getByText(DEBUG_FACET_DETAIL_LABELS.unit)).toBeDefined();
    expect(screen.getByText('people')).toBeDefined();
    expect(screen.getByText(DEBUG_FACET_DETAIL_LABELS.facet)).toBeDefined();
    expect(screen.getByText('facet_123')).toBeDefined();
    expect(screen.getByText(DEBUG_FACET_DETAIL_LABELS.license)).toBeDefined();
    expect(screen.getByText('Public Domain')).toBeDefined();
    expect(screen.getByText('US Census Bureau')).toBeDefined();
    expect(screen.getByText(/Decennial Census/)).toBeDefined();
  });

  it('renders Unused status and not Used in answer when table usedInAnswer is false', () => {
    // Test: Unused table status rendering and zero places with data.
    // Situation: Table with usedInAnswer: false, sourceSelection: 'derived', and placesWithDataCount: 0.
    // Expectation: Renders Unused, does not render Used in answer, and renders "(0 with data)".
    const table = makeServerTable({
      tableId: 's1',
      usedInAnswer: false,
      sourceSelection: 'derived',
      placesWithDataCount: 0,
    });
    render(<DataTab serverReport={makeServerReport([table])} />);

    expect(screen.getByText(DEBUG_TABLE_USAGE_LABELS.unused)).toBeDefined();
    expect(screen.getByText('derived')).toBeDefined();
    expect(screen.getByText(/State in country\/USA/)).toBeDefined();
    expect(screen.getByText(/0 with data/)).toBeDefined();
    expect(screen.queryByText(DEBUG_TABLE_USAGE_LABELS.used)).toBeNull();
  });

  it('falls back to UNNAMED_SOURCE_LABEL and omits empty detail fields', () => {
    // Test: Fallback source name and null detail field omission.
    // Situation: Table with source: null, unit: null, facetId: null, and single-year dateRange.
    // Expectation: UNNAMED_SOURCE_LABEL is rendered, single-year dateRange is displayed,
    // and unit/facet labels are omitted.
    const table = makeServerTable({
      tableId: 't1',
      source: null,
      unit: null,
      facetId: null,
      dateRange: ['2023', '2023'],
      places: [],
      parentPlaceDcid: null,
      childPlaceType: null,
      variableName: '',
    });
    render(<DataTab serverReport={makeServerReport([table])} />);

    expect(screen.getByText(UNNAMED_SOURCE_LABEL)).toBeDefined();
    expect(screen.getByText('2023')).toBeDefined();
    expect(screen.queryByText(DEBUG_FACET_DETAIL_LABELS.unit)).toBeNull();
    expect(screen.queryByText(DEBUG_FACET_DETAIL_LABELS.facet)).toBeNull();
  });

  it('renders safe https source URLs as external links and unsafe javascript URLs as inert text', () => {
    // Test: Link sanitization for source URLs.
    // Situation: One table with https: URL and one table with javascript: URL.
    // Expectation: Safe URL renders an anchor with target="_blank" and rel="noopener noreferrer",
    // while unsafe URL renders as a span without an anchor tag.
    const safeUrl = 'https://example.org/dataset';
    const unsafeUrl = 'javascript:alert(1)';
    const tableSafe = makeServerTable({
      tableId: 't_safe',
      source: {
        name: 'Safe Source',
        url: safeUrl,
        license: null,
        dataset: null,
        provider: null,
        dateRange: null,
      },
    });
    const tableUnsafe = makeServerTable({
      tableId: 't_unsafe',
      source: {
        name: 'Unsafe Source',
        url: unsafeUrl,
        license: null,
        dataset: null,
        provider: null,
        dateRange: null,
      },
    });

    render(
      <DataTab serverReport={makeServerReport([tableSafe, tableUnsafe])} />,
    );

    const safeLink = screen.getByRole('link', { name: safeUrl });
    expect(safeLink.getAttribute('href')).toBe(safeUrl);
    expect(safeLink.getAttribute('target')).toBe('_blank');
    expect(safeLink.getAttribute('rel')).toBe('noopener noreferrer');

    const unsafeSpan = screen.getByText(unsafeUrl);
    expect(unsafeSpan.tagName).toBe('SPAN');
    expect(screen.queryByRole('link', { name: unsafeUrl })).toBeNull();
  });
});
