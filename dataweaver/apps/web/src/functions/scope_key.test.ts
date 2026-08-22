import { describe, expect, it } from 'vitest';
import type { QueryResult } from '~/server/types';
import { getResultScopeKey, resolveResultForPlace } from './scope_key';

describe('scope_key', () => {
  describe('getResultScopeKey', () => {
    it('derives scope key from root isChildQuery and parentPlaceDcid', () => {
      const result: QueryResult = {
        id: 'test-root-child',
        title: 'Metrics across Africa',
        isChildQuery: true,
        parentPlaceDcid: 'africa',
        childPlaceType: 'Country',
        variables: [],
        entities: [
          { dcid: 'country/KEN', name: 'Kenya' },
          { dcid: 'country/NGA', name: 'Nigeria' },
        ],
        timeSeries: [],
      };

      expect(getResultScopeKey(result)).toBe('africa:Country');
    });

    it('derives scope key for sub-region / child queries via variable flags', () => {
      const result: QueryResult = {
        id: 'test-1',
        title: 'Metrics across Africa',
        variables: [
          {
            dcid: 'Count_Person',
            name: 'Population',
            isChildQuery: true,
            parentPlaceDcid: 'africa',
            childPlaceType: 'countries',
          },
        ],
        entities: [
          { dcid: 'country/KEN', name: 'Kenya' },
          { dcid: 'country/NGA', name: 'Nigeria' },
        ],
        timeSeries: [],
      };

      expect(getResultScopeKey(result)).toBe('africa:Country');
    });

    it('derives scope key for single-entity queries', () => {
      const result: QueryResult = {
        id: 'test-2',
        title: 'Metrics for Kenya',
        variables: [{ dcid: 'Count_Person', name: 'Population' }],
        entities: [{ dcid: 'country/KEN', name: 'Kenya' }],
        timeSeries: [],
      };

      expect(getResultScopeKey(result)).toBe('country/KEN');
    });

    it('derives sorted concatenated scope key for multi-entity comparison queries', () => {
      const result: QueryResult = {
        id: 'test-3',
        title: 'Comparison between Uganda and Kenya',
        variables: [
          {
            dcid: 'Count_Person',
            name: 'Population',
            placeDcid: 'country/KEN',
          },
        ],
        entities: [
          { dcid: 'country/UGA', name: 'Uganda' },
          { dcid: 'country/KEN', name: 'Kenya' },
        ],
        timeSeries: [],
      };

      expect(getResultScopeKey(result)).toBe('country/KEN+country/UGA');
    });

    it('falls back to variable placeDcid when entities array is empty', () => {
      const result: QueryResult = {
        id: 'test-4',
        title: 'Metrics',
        variables: [
          {
            dcid: 'Count_Person',
            name: 'Population',
            placeDcid: 'country/KEN',
          },
        ],
        entities: [],
        timeSeries: [],
      };

      expect(getResultScopeKey(result)).toBe('country/KEN');
    });

    it('falls back to fallbackPlace or unknown when nothing is available', () => {
      const result: QueryResult = {
        id: 'test-5',
        title: 'Empty result',
        variables: [],
        entities: [],
        timeSeries: [],
      };

      expect(getResultScopeKey(result, 'fallback/place')).toBe(
        'fallback/place',
      );
      expect(getResultScopeKey(result)).toBe('unknown');
    });
  });

  describe('resolveResultForPlace', () => {
    const kenyaResult: QueryResult = {
      id: 'res-kenya',
      title: 'Metrics for Kenya',
      placeDcid: 'country/KEN',
      variables: [{ dcid: 'Count_Person', name: 'Population' }],
      entities: [{ dcid: 'country/KEN', name: 'Kenya' }],
      timeSeries: [],
    };

    const africaResult: QueryResult = {
      id: 'res-africa',
      title: 'Metrics across Africa',
      isChildQuery: true,
      placeDcid: 'africa',
      parentPlaceDcid: 'africa',
      childPlaceType: 'Country',
      variables: [{ dcid: 'Count_Person', name: 'Population' }],
      entities: [{ dcid: 'country/KEN', name: 'Kenya' }],
      timeSeries: [],
    };

    it('returns undefined when results map is undefined or for comparison cards', () => {
      expect(resolveResultForPlace(undefined, 'country/KEN')).toBeUndefined();
      expect(
        resolveResultForPlace({ 'country/KEN': kenyaResult }, '__comparison'),
      ).toBeUndefined();
      expect(
        resolveResultForPlace({ 'country/KEN': kenyaResult }, ''),
      ).toBeUndefined();
    });

    it('matches directly by exact key', () => {
      const results = {
        'country/KEN': kenyaResult,
        'africa:Country': africaResult,
      };
      expect(resolveResultForPlace(results, 'country/KEN')).toBe(kenyaResult);
      expect(resolveResultForPlace(results, 'africa:Country')).toBe(
        africaResult,
      );
    });

    it('matches composite placeDcid with colon to raw key in results', () => {
      const results = {
        africa: africaResult,
      };
      expect(resolveResultForPlace(results, 'africa:Country')).toBe(
        africaResult,
      );
    });

    it('matches raw placeDcid without colon to composite key with colon in results', () => {
      const results = {
        'africa:Country': africaResult,
      };
      expect(resolveResultForPlace(results, 'africa')).toBe(africaResult);
    });

    it('falls back to matching result.placeDcid or result.parentPlaceDcid', () => {
      const results = {
        'custom-key': africaResult,
      };
      expect(resolveResultForPlace(results, 'africa')).toBe(africaResult);
    });

    it('returns undefined when no matching result exists', () => {
      const results = {
        'country/KEN': kenyaResult,
      };
      expect(resolveResultForPlace(results, 'country/UGA')).toBeUndefined();
    });
  });
});
