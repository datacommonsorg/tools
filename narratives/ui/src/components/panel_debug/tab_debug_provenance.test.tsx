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
 * @fileoverview Unit tests for ProvenanceTab: renders provenance sections or a
 * single empty-state paragraph when all collections are empty.
 */

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import {
  DEBUG_FACET_DETAIL_LABELS,
  RESOLVED_DURING_SEARCH_NOTE,
  UNNAMED_SOURCE_LABEL,
  VARIABLE_NAME_SEPARATOR,
} from '@/src/components/panel_debug/copy_debug';
import { ProvenanceTab } from '@/src/components/panel_debug/tab_debug_provenance';
import type { FacetInfo, TurnInspection } from '@/src/utils/inspect_turn';

/** Builds a fresh TurnInspection object with default empty arrays and overrides. */
const makeInspection = (
  overrides: Partial<TurnInspection> = {},
): TurnInspection => ({
  facets: [],
  variables: [],
  places: [],
  charts: [],
  sourceChosenExplicitly: false,
  ...overrides,
});

/** Builds a fresh FacetInfo object with default fields and overrides. */
const makeFacet = (overrides: Partial<FacetInfo> = {}): FacetInfo => ({
  facetId: 'facet_1',
  forVariables: ['Count_Person'],
  used: true,
  use: 'chosen',
  ...overrides,
});

afterEach(() => {
  cleanup();
});

describe('ProvenanceTab', () => {
  it('renders a single empty-state paragraph when all four sections are empty', () => {
    // Test: Empty state rendering.
    // Situation: An inspection where facets, variables, places, and charts are all empty.
    // Expectation: A single empty-state message is rendered.
    render(<ProvenanceTab inspection={makeInspection()} />);

    expect(
      screen.getByText(
        'No provenances, variables, places, or charts were recorded for this turn.',
      ),
    ).toBeDefined();
  });

  it('renders populated sections when inspection collections contain items', () => {
    // Test: Populated sections rendering.
    // Situation: An inspection with facets, variables, places, and charts.
    // Expectation: The respective section headers and content render.
    render(
      <ProvenanceTab
        inspection={makeInspection({
          facets: [
            makeFacet({
              facetId: 'facet_1',
              provenance: 'Census Bureau',
              url: 'https://census.gov',
              unit: 'people',
              forVariables: ['Count_Person'],
              used: true,
              use: 'chosen',
            }),
          ],
          variables: [
            {
              dcid: 'Count_Person',
              referencedBy: ['fetch_observations'],
              fetched: true,
            },
          ],
          places: ['geoId/06'],
          charts: [
            {
              title: 'Population Bar Chart',
              variables: ['Count_Person'],
              places: ['geoId/06'],
            },
          ],
        })}
      />,
    );

    expect(screen.getByText('Provenances used')).toBeDefined();
    expect(screen.getByText('Census Bureau')).toBeDefined();
    expect(screen.getByText(DEBUG_FACET_DETAIL_LABELS.unit)).toBeDefined();
    expect(screen.getByText('people')).toBeDefined();
    expect(screen.getByText('Variables')).toBeDefined();
    expect(screen.getByText('Count_Person')).toBeDefined();
    expect(screen.getByText('Places (1)')).toBeDefined();
    expect(screen.getByText('geoId/06')).toBeDefined();
    expect(screen.getByText('Charts requested')).toBeDefined();
    expect(screen.getByText('Population Bar Chart')).toBeDefined();
  });

  it('lists only used facets and omits unused candidate facets', () => {
    // Test: Facet filtering by usage.
    // Situation: An inspection with one used facet and one unused candidate facet.
    // Expectation: Only the used facet is rendered.
    render(
      <ProvenanceTab
        inspection={makeInspection({
          facets: [
            makeFacet({
              facetId: 'used_facet',
              provenance: 'Used Provenance',
              forVariables: ['Count_Person'],
              used: true,
              use: 'chosen',
            }),
            makeFacet({
              facetId: 'unused_facet',
              provenance: 'Unused Provenance',
              forVariables: ['Count_Person'],
              used: false,
              use: 'unused',
            }),
          ],
        })}
      />,
    );

    expect(screen.getByText('Used Provenance')).toBeDefined();
    expect(screen.queryByText('Unused Provenance')).toBeNull();
  });

  it('falls back to unnamed source label and omits empty detail fields', () => {
    // Test: Fallback label and empty field omission for facets.
    // Situation: A used facet with no provenance name and no unit specified.
    // Expectation: Renders UNNAMED_SOURCE_LABEL and coverage date, but omits the Unit label.
    render(
      <ProvenanceTab
        inspection={makeInspection({
          facets: [
            makeFacet({
              facetId: 'facet_111',
              forVariables: ['Count_Person'],
              used: true,
              use: 'chosen',
              dateRange: '2020-2024',
            }),
          ],
        })}
      />,
    );

    expect(screen.getByText(UNNAMED_SOURCE_LABEL)).toBeDefined();
    expect(screen.getByText('2020-2024')).toBeDefined();
    expect(screen.queryByText(DEBUG_FACET_DETAIL_LABELS.unit)).toBeNull();
  });

  it('renders safe https facet URLs as external links and unsafe javascript URLs as plain text', () => {
    // Test: Safe vs unsafe URL rendering in facets.
    // Situation: One facet with https: URL and one facet with javascript: URL.
    // Expectation: Safe URL renders an external link with target="_blank" and rel="noopener noreferrer",
    // while unsafe URL renders as a span without an anchor tag.
    const safeUrl = 'https://example.org/dataset';
    const unsafeUrl = 'javascript:alert(1)';
    render(
      <ProvenanceTab
        inspection={makeInspection({
          facets: [
            makeFacet({
              facetId: 'safe_facet',
              provenance: 'Safe Source',
              url: safeUrl,
              forVariables: ['Count_Person'],
              used: true,
              use: 'chosen',
            }),
            makeFacet({
              facetId: 'unsafe_facet',
              provenance: 'Unsafe Source',
              url: unsafeUrl,
              forVariables: ['Count_Person'],
              used: true,
              use: 'chosen',
            }),
          ],
        })}
      />,
    );

    const safeLink = screen.getByRole('link', { name: safeUrl });
    expect(safeLink.getAttribute('href')).toBe(safeUrl);
    expect(safeLink.getAttribute('target')).toBe('_blank');
    expect(safeLink.getAttribute('rel')).toBe('noopener noreferrer');

    const unsafeSpan = screen.getByText(unsafeUrl);
    expect(unsafeSpan.tagName).toBe('SPAN');
    expect(screen.queryByRole('link', { name: unsafeUrl })).toBeNull();
  });

  it('shows variable name after separator and appends resolved-during-search only to unfetched variables', () => {
    // Test: Variable formatting and search resolution note.
    // Situation: One fetched variable and one unfetched variable, both with names.
    // Expectation: Variable names are displayed, and only the unfetched variable carries RESOLVED_DURING_SEARCH_NOTE.
    render(
      <ProvenanceTab
        inspection={makeInspection({
          variables: [
            {
              dcid: 'Count_Person',
              name: 'Total Population',
              referencedBy: ['fetch_observations'],
              fetched: true,
            },
            {
              dcid: 'Median_Age_Person',
              name: 'Median Age',
              referencedBy: ['find_variables'],
              fetched: false,
            },
          ],
        })}
      />,
    );

    expect(screen.getByText('Count_Person')).toBeDefined();
    expect(
      screen.getByText(`${VARIABLE_NAME_SEPARATOR}Total Population`.trim()),
    ).toBeDefined();
    expect(screen.getByText('Median_Age_Person')).toBeDefined();
    expect(
      screen.getByText(`${VARIABLE_NAME_SEPARATOR}Median Age`.trim()),
    ).toBeDefined();
    expect(screen.getByText(RESOLVED_DURING_SEARCH_NOTE.trim())).toBeDefined();
  });

  it('omits charts section when charts array is empty while rendering other populated sections', () => {
    // Test: Omission of empty charts section.
    // Situation: Inspection with facets and places, but an empty charts array.
    // Expectation: Renders provenances and places, but omits the Charts requested heading.
    render(
      <ProvenanceTab
        inspection={makeInspection({
          facets: [
            makeFacet({
              facetId: 'f1',
              provenance: 'Census Bureau',
              forVariables: ['Count_Person'],
              used: true,
              use: 'chosen',
            }),
          ],
          places: ['country/USA'],
          charts: [],
        })}
      />,
    );

    expect(screen.getByText('Provenances used')).toBeDefined();
    expect(screen.getByText('Places (1)')).toBeDefined();
    expect(screen.queryByText('Charts requested')).toBeNull();
  });
});
