import { describe, expect, it } from 'vitest';
import type { FacetInfo } from '~/server/types';
import { resolveActiveFacet } from './facet_resolution';

const buildFacet = (
  facetId: string,
  observations: FacetInfo['observations'],
): FacetInfo => ({
  facetId,
  source: `Source ${facetId}`,
  sourceUrl: '',
  unit: '%',
  earliestDate: '2020',
  latestDate: '2021',
  observationCount: observations.length,
  observations,
});

const emptyFacet = buildFacet('f_empty', []);
const populatedFacet = buildFacet('f_full', [{ date: '2020', value: 1 }]);

describe('resolveActiveFacet', () => {
  // Test: An explicit selection wins.
  // Situation: The selected id matches a facet, even one without observations.
  // Expectation: That facet is returned so the user's choice is honoured.
  it('returns the selected facet when it matches', () => {
    expect(
      resolveActiveFacet([populatedFacet, emptyFacet], 'f_empty'),
    ).toStrictEqual(emptyFacet);
  });

  // Test: Stale or absent selection.
  // Situation: No selection has been made yet, and facets[0] carries no observations.
  // Expectation: The first facet with observations is used instead of an empty chart.
  it('falls back to the first facet with observations', () => {
    expect(
      resolveActiveFacet([emptyFacet, populatedFacet], undefined),
    ).toStrictEqual(populatedFacet);
    expect(
      resolveActiveFacet([emptyFacet, populatedFacet], 'stale_id'),
    ).toStrictEqual(populatedFacet);
  });

  // Test: Nothing has observations.
  // Situation: Every facet is empty.
  // Expectation: The first facet is returned so the selector still renders.
  it('falls back to the first facet when none have observations', () => {
    expect(resolveActiveFacet([emptyFacet], 'stale_id')).toStrictEqual(
      emptyFacet,
    );
  });

  // Test: No facets at all.
  // Situation: The series carries no facet list, or an empty one.
  // Expectation: Undefined, so callers keep the series data untouched.
  it('returns undefined when there are no facets', () => {
    expect(resolveActiveFacet(undefined, 'f_full')).toBeUndefined();
    expect(resolveActiveFacet([], 'f_full')).toBeUndefined();
  });
});
