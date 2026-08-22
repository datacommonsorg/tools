import { describe, expect, it } from 'vitest';
import type { QueryResult } from '~/server/types';
import {
  formatChartCardTitle,
  formatNotesCardTitle,
  formatTableCardTitle,
  resolvePlaceName,
} from './format_card_title';

describe('format_card_title', () => {
  const baseResult: QueryResult = {
    id: 'test-1',
    title: 'Metrics across Africa',
    placeName: 'Africa',
    isChildQuery: true,
    variables: [{ dcid: 'Count_Person', name: 'Population' }],
    entities: [{ dcid: 'country/KEN', name: 'Kenya' }],
    timeSeries: [],
  };

  describe('resolvePlaceName', () => {
    it('uses explicit placeName when present', () => {
      expect(resolvePlaceName(baseResult)).toBe('Africa');
    });

    it('falls back to variables[0].placeName when placeName is absent', () => {
      const result: QueryResult = {
        ...baseResult,
        placeName: undefined,
        variables: [
          { dcid: 'Count_Person', name: 'Population', placeName: 'Kenya' },
        ],
      };
      expect(resolvePlaceName(result)).toBe('Kenya');
    });

    it('falls back to title for child queries when placeName is absent', () => {
      const result: QueryResult = {
        ...baseResult,
        placeName: undefined,
        title: 'Metrics across Europe',
        isChildQuery: true,
        variables: [{ dcid: 'Count_Person', name: 'Population' }],
        entities: [{ dcid: 'country/DEU', name: 'Germany' }],
      };
      expect(resolvePlaceName(result)).toBe('Europe');
    });

    it('falls back to entities[0].name for non-child queries when placeName is absent', () => {
      const result: QueryResult = {
        ...baseResult,
        placeName: undefined,
        title: 'Metrics for Uganda',
        isChildQuery: false,
        variables: [{ dcid: 'Count_Person', name: 'Population' }],
        entities: [{ dcid: 'country/UGA', name: 'Uganda' }],
      };
      expect(resolvePlaceName(result)).toBe('Uganda');
    });
  });

  describe('formatTableCardTitle', () => {
    it('formats child queries with "across"', () => {
      expect(formatTableCardTitle('Africa', true)).toBe(
        'Metrics across Africa',
      );
    });

    it('formats single place queries with "for"', () => {
      expect(formatTableCardTitle('Kenya', false)).toBe('Metrics for Kenya');
    });
  });

  describe('formatChartCardTitle', () => {
    it('formats child query chart title as varName across placeName', () => {
      expect(formatChartCardTitle('GDP', 'Africa', true)).toBe(
        'GDP across Africa',
      );
    });

    it('formats single entity chart title as varName in placeName', () => {
      expect(formatChartCardTitle('Population', 'Kenya', false)).toBe(
        'Population in Kenya',
      );
    });

    it('falls back to table title if variable name is missing', () => {
      expect(formatChartCardTitle(undefined, 'Kenya', false)).toBe(
        'Metrics for Kenya',
      );
    });
  });

  describe('formatNotesCardTitle', () => {
    it('formats notes card title consistently from place name', () => {
      expect(formatNotesCardTitle('Kenya')).toBe('Relevant insights on Kenya');
      expect(formatNotesCardTitle('Africa')).toBe(
        'Relevant insights on Africa',
      );
    });
  });
});
