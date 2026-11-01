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
 * @fileoverview Tests for the provenance inspector's chart listing, which
 * reads a turn's chart blocks.
 */

import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type {
  ChartItem,
  ChatTurn,
  ToolCallEvent,
} from '@/src/hooks/use_sse_chat';
import { ProvenanceInspector } from './panel_debug_provenance';

const FETCH_CALL: ToolCallEvent = {
  name: 'fetch_observations',
  arguments: { variable_dcid: 'Count_Person', place_dcids: ['country/FRA'] },
  status: 'success',
};

const LINE_CHART: ChartItem = {
  vizType: 'line',
  title: 'Population, France',
  variableDcids: ['Count_Person'],
  placeDcids: ['country/FRA'],
};

/** Builds a finished turn with one fetch call and the given overrides. */
const buildFinishedTurn = (overrides: Partial<ChatTurn> = {}): ChatTurn => ({
  userMessage: 'What is the population of France?',
  status: 'done',
  toolCalls: [FETCH_CALL],
  thoughts: [],
  text: 'France has about 68 million people.',
  blocks: [
    { index: 0, type: 'text', markdown: 'France has about 68 million people.' },
  ],
  provenance: [],
  ...overrides,
});

/** Renders the inspector for the turn and opens its slide-over. */
const openInspector = (turn: ChatTurn) => {
  render(<ProvenanceInspector turn={turn} />);
  fireEvent.click(
    screen.getByLabelText('Inspect data sources for this answer'),
  );
};

afterEach(() => {
  cleanup();
});

describe('ProvenanceInspector', () => {
  it('lists the charts from the turn chart blocks', () => {
    // Test: The chart listing of a turn streamed as blocks.
    // Situation: A finished turn holding a text block and a chart block.
    // Expectation: The "Charts requested" section lists the chart block's
    //   title.
    openInspector(
      buildFinishedTurn({
        blocks: [
          {
            index: 0,
            type: 'text',
            markdown: 'France has about 68 million people.',
          },
          { index: 1, type: 'chart', chart: LINE_CHART },
        ],
      }),
    );

    expect(screen.getByText('Charts requested')).toBeTruthy();
    expect(screen.getByText('Population, France')).toBeTruthy();
  });

  it('omits the chart section for a turn without charts', () => {
    // Test: The chart listing of a turn that rendered no chart.
    // Situation: A finished turn whose only block is text.
    // Expectation: No "Charts requested" section renders, while the tool
    //   calls section still does.
    openInspector(
      buildFinishedTurn({
        blocks: [
          {
            index: 0,
            type: 'text',
            markdown: 'France has about 68 million people.',
          },
        ],
      }),
    );

    expect(screen.queryByText('Charts requested')).toBeNull();
    expect(screen.getByText('Tool calls (1)')).toBeTruthy();
  });
});
