import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { FacetInfo } from '~/server/types';
import { FacetSelector } from './facet_selector';

const mockFacetA: FacetInfo = {
  facetId: 'facet_a',
  source: 'US Census Bureau',
  sourceUrl: 'https://census.gov',
  earliestDate: '2010',
  latestDate: '2020',
  observationCount: 11,
  unit: '$',
  observations: [],
};

const mockFacetB: FacetInfo = {
  facetId: 'facet_b',
  source: 'Bureau of Labor Statistics',
  sourceUrl: 'https://bls.gov',
  earliestDate: '2015',
  latestDate: '2022',
  observationCount: 8,
  unit: '$',
  observations: [],
};

describe('FacetSelector', () => {
  // Test: Render static badge when only 1 facet exists
  // Situation: facets array has length 1.
  // Expectation: Renders non-interactive badge with prefix and formatted facet label.
  it('renders static badge when facets length is 1', () => {
    const html = renderToStaticMarkup(
      <FacetSelector
        facets={[mockFacetA]}
        selectedFacetId="facet_a"
        onSelect={vi.fn()}
        label="Income"
      />,
    );

    expect(html).toContain('Income');
    expect(html).toContain('US Census Bureau');
  });

  // Test: Render interactive select when multiple facets exist and match
  // Situation: facets has 2 items and selectedFacetId matches facet_b.
  // Expectation: Renders select component container.
  it('renders select component when multiple facets exist and selection is valid', () => {
    const html = renderToStaticMarkup(
      <FacetSelector
        facets={[mockFacetA, mockFacetB]}
        selectedFacetId="facet_b"
        onSelect={vi.fn()}
        label="Income"
      />,
    );

    expect(html).toContain('Bureau of Labor Statistics');
  });

  // Test: Resilient fallback to facets[0] when selectedFacetId is stale/unmatched
  // Situation: selectedFacetId is "stale_unknown_id" absent from facets.
  // Expectation: Does not return null; falls back to facets[0].
  it('falls back to facets[0] when selectedFacetId is stale or unmatched', () => {
    const html = renderToStaticMarkup(
      <FacetSelector
        facets={[mockFacetA, mockFacetB]}
        selectedFacetId="stale_unknown_id"
        onSelect={vi.fn()}
        label="Income"
      />,
    );

    expect(html).not.toBe('');
    expect(html).toContain('US Census Bureau');
  });

  // Test: Null render when facets array is empty
  // Situation: facets array has length 0.
  // Expectation: Returns empty markup.
  it('returns empty markup when facets array is empty', () => {
    const html = renderToStaticMarkup(
      <FacetSelector
        facets={[]}
        selectedFacetId="facet_a"
        onSelect={vi.fn()}
        label="Income"
      />,
    );

    expect(html).toBe('');
  });
});
