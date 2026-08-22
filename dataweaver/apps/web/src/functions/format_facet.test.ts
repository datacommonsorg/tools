import { describe, expect, it } from 'vitest';
import { formatFacetBlock, formatFacetLabel } from '~/functions/format_facet';
import type { FacetInfo } from '~/server/types';

describe('formatFacetLabel', () => {
  it('formats all fields when present', () => {
    const facet: Partial<FacetInfo> = {
      facetId: '1',
      source: 'Census Bureau',
      earliestDate: '2010',
      latestDate: '2020',
      unit: 'USD',
    };
    expect(formatFacetLabel(facet)).toBe('Census Bureau, 2010 – 2020, USD');
  });

  it('omits missing fields without leaving trailing or consecutive commas', () => {
    const facet: Partial<FacetInfo> = {
      facetId: '2',
      source: 'BLS',
      earliestDate: '2020',
      latestDate: '2020',
    };
    expect(formatFacetLabel(facet)).toBe('BLS, 2020');
  });

  it('returns an empty string when all formatting fields are absent', () => {
    const facet: Partial<FacetInfo> = { facetId: '3' };
    expect(formatFacetLabel(facet)).toBe('');
  });
});

describe('formatFacetBlock', () => {
  it('formats all 4 fields separated by <br>', () => {
    const facet: Partial<FacetInfo> = {
      facetId: '1',
      source: 'Eurostat',
      earliestDate: '2015',
      latestDate: '2022',
      measurementMethod: 'Survey',
      unit: 'EUR',
    };
    expect(formatFacetBlock(facet)).toBe(
      'Eurostat<br>2015 – 2022<br>Survey<br>EUR',
    );
  });

  it('omits empty fields without emitting consecutive or trailing <br> tags', () => {
    const facet: Partial<FacetInfo> = {
      facetId: '2',
      source: 'World Bank',
      unit: '%',
    };
    expect(formatFacetBlock(facet)).toBe('World Bank<br>%');
  });

  it('returns an empty string when all formatting fields are absent', () => {
    const facet: Partial<FacetInfo> = { facetId: '3' };
    expect(formatFacetBlock(facet)).toBe('');
  });
});
