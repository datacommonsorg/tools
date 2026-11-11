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
 * @fileoverview Unit tests for ResponseTab: answer blocks, citations with Link
 * sanitization, follow-up suggestions, and outcome notes.
 */

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { TurnDebugResponse } from '@/src/components/panel_debug/report_debug';
import { ResponseTab } from '@/src/components/panel_debug/tab_debug_response';

/** Builds a fresh TurnDebugResponse object with default empty collections. */
const makeResponse = (
  overrides: Partial<TurnDebugResponse> = {},
): TurnDebugResponse => ({
  text: '',
  blocks: [],
  provenance: [],
  followUps: [],
  ...overrides,
});

afterEach(() => {
  cleanup();
});

describe('ResponseTab', () => {
  it('renders clear empty states when blocks, citations, and follow-ups are empty', () => {
    // Test: Empty state messages for response collections.
    // Situation: Done outcome with no blocks, citations, or follow-ups.
    // Expectation: Explanatory empty-state paragraphs render for each section.
    render(
      <ResponseTab
        outcome={{ kind: 'done', reason: null, truncated: false }}
        response={makeResponse()}
      />,
    );

    expect(
      screen.getByText('No answer blocks were recorded for this turn.'),
    ).toBeDefined();
    expect(
      screen.getByText('No citations were recorded for this turn.'),
    ).toBeDefined();
    expect(
      screen.getByText('No follow-up suggestions were recorded for this turn.'),
    ).toBeDefined();
  });

  it('renders an advisory note for an unanswered or refused turn', () => {
    // Test: Outcome note for non-done turn.
    // Situation: A refused turn outcome.
    // Expectation: A note region displays the refusal reason.
    render(
      <ResponseTab
        outcome={{
          kind: 'refused',
          message: 'Unsupported topic.',
          reason: 'policy',
        }}
        response={makeResponse()}
      />,
    );

    expect(screen.getByRole('note')).toBeDefined();
    expect(
      screen.getByText('This turn was refused: Unsupported topic.'),
    ).toBeDefined();

    const sections = document.querySelectorAll('section');
    expect(sections).toHaveLength(3);
    for (const section of Array.from(sections)) {
      expect(
        section.classList.contains(
          '[&:nth-of-type(even)]:bg-surface-narrative',
        ),
      ).toBe(true);
      expect(section.classList.contains('even:bg-surface-narrative')).toBe(
        false,
      );
    }
  });

  it('renders text markdown in pre elements and chart fields', () => {
    // Test: Block rendering for text and charts.
    // Situation: A response with one text block and one chart block.
    // Expectation: Preformatted text and chart metadata are rendered.
    render(
      <ResponseTab
        outcome={{ kind: 'done', reason: null, truncated: false }}
        response={makeResponse({
          blocks: [
            {
              index: 0,
              type: 'text',
              markdown: 'Population grew 5% in 2024.',
            },
            {
              index: 1,
              type: 'chart',
              chart: {
                vizType: 'line',
                title: 'Population Trend',
                placeDcids: ['country/USA'],
                variableDcids: ['Count_Person'],
              },
            },
          ],
        })}
      />,
    );

    expect(screen.getByText('Population grew 5% in 2024.')).toBeDefined();
    expect(screen.getByText('Population Trend')).toBeDefined();
    expect(screen.getByText('country/USA')).toBeDefined();
    expect(screen.getByText('Count_Person')).toBeDefined();
  });

  it('renders numbered citations and sanitizes unsafe javascript: URLs with an inert span', () => {
    // Test: Citation links and XSS URL sanitization via Link component.
    // Situation: A citation list containing a safe HTTPS URL and an unsafe javascript: URL.
    // Expectation: The safe URL renders an anchor tag, while the unsafe javascript:
    //              URL renders an inert span rather than a clickable link.
    render(
      <ResponseTab
        outcome={{ kind: 'done', reason: null, truncated: false }}
        response={makeResponse({
          provenance: [
            {
              name: 'Safe Source',
              url: 'https://example.org/dataset',
              license: 'CC-BY',
            },
            {
              name: 'Suspicious Source',
              url: 'javascript:alert(1)',
            },
          ],
        })}
      />,
    );

    expect(screen.getByText('[1]')).toBeDefined();
    expect(screen.getByText('Safe Source')).toBeDefined();
    const safeLink = screen.getByRole('link', {
      name: 'https://example.org/dataset',
    });
    expect(safeLink.getAttribute('href')).toBe('https://example.org/dataset');
    expect(screen.getByText('License: CC-BY')).toBeDefined();

    expect(screen.getByText('[2]')).toBeDefined();
    expect(screen.getByText('Suspicious Source')).toBeDefined();
    expect(document.querySelector('a[href="javascript:alert(1)"]')).toBeNull();
    expect(screen.getByText('javascript:alert(1)').tagName.toLowerCase()).toBe(
      'span',
    );
  });

  it('renders follow-up suggestions in a list', () => {
    // Test: Follow-up questions list.
    // Situation: Two follow-up questions in response.
    // Expectation: Both questions are rendered as list items.
    render(
      <ResponseTab
        outcome={{ kind: 'done', reason: null, truncated: false }}
        response={makeResponse({
          followUps: ['What about 2025?', 'Compare with Canada?'],
        })}
      />,
    );

    expect(screen.getByText('What about 2025?')).toBeDefined();
    expect(screen.getByText('Compare with Canada?')).toBeDefined();
  });
});
