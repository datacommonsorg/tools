import { describe, expect, it } from 'vitest';

import type { ComparisonResult, QueryResult } from '~/server/types';
import { deriveContentForCard } from './sync_store';

describe('sync_store multi-series alphabetization', () => {
  const sampleObservations = [{ date: '2020', value: 100 }];

  // Test: deriveContentForCard multi-entity alphabetization
  // Situation: QueryResult contains multiple entities in non-alphabetical order (Texas, Alaska, California).
  // Expectation: Resulting chart series are sorted alphabetically by label (Alaska, California, Texas).
  it('alphabetizes series by entity name in multi-entity charts', () => {
    const result: QueryResult = {
      id: 'res-1',
      title: 'Population',
      variables: [{ dcid: 'Count_Person', name: 'Population' }],
      entities: [
        { dcid: 'geoId/48', name: 'Texas' },
        { dcid: 'geoId/02', name: 'Alaska' },
        { dcid: 'geoId/06', name: 'California' },
      ],
      timeSeries: [
        {
          variableDcid: 'Count_Person',
          entityDcid: 'geoId/48',
          facets: [
            {
              facetId: 'f1',
              source: 'Census',
              sourceUrl: '',
              unit: '',
              earliestDate: '2020',
              latestDate: '2020',
              observationCount: 1,
              observations: sampleObservations,
            },
          ],
        },
        {
          variableDcid: 'Count_Person',
          entityDcid: 'geoId/02',
          facets: [
            {
              facetId: 'f2',
              source: 'Census',
              sourceUrl: '',
              unit: '',
              earliestDate: '2020',
              latestDate: '2020',
              observationCount: 1,
              observations: sampleObservations,
            },
          ],
        },
        {
          variableDcid: 'Count_Person',
          entityDcid: 'geoId/06',
          facets: [
            {
              facetId: 'f3',
              source: 'Census',
              sourceUrl: '',
              unit: '',
              earliestDate: '2020',
              latestDate: '2020',
              observationCount: 1,
              observations: sampleObservations,
            },
          ],
        },
      ],
    };

    const content = deriveContentForCard('chart', result);
    expect(content).not.toBeNull();
    expect(content?.variant).toBe('chart');
    if (content && content.variant === 'chart') {
      const labels = content.series?.map((s) => s.label);
      expect(labels).toEqual(['Alaska', 'California', 'Texas']);
    }
  });

  // Test: deriveContentForCard for variable multi-entity alphabetization
  // Situation: QueryResult has multiple entities in reverse order for a specific variable.
  // Expectation: Resulting chart series are sorted alphabetically by entity name.
  it('alphabetizes series by entity name in variable-specific charts', () => {
    const result: QueryResult = {
      id: 'res-2',
      title: 'Income',
      variables: [{ dcid: 'Median_Income', name: 'Median Income' }],
      entities: [
        { dcid: 'geoId/48', name: 'Texas' },
        { dcid: 'geoId/06', name: 'California' },
      ],
      timeSeries: [
        {
          variableDcid: 'Median_Income',
          entityDcid: 'geoId/48',
          facets: [
            {
              facetId: 'f1',
              source: 'Census',
              sourceUrl: '',
              unit: '$',
              earliestDate: '2020',
              latestDate: '2020',
              observationCount: 1,
              observations: sampleObservations,
            },
          ],
        },
        {
          variableDcid: 'Median_Income',
          entityDcid: 'geoId/06',
          facets: [
            {
              facetId: 'f2',
              source: 'Census',
              sourceUrl: '',
              unit: '$',
              earliestDate: '2020',
              latestDate: '2020',
              observationCount: 1,
              observations: sampleObservations,
            },
          ],
        },
      ],
    };

    const content = deriveContentForCard(
      'chart',
      result,
      undefined,
      'Median_Income',
    );
    expect(content).not.toBeNull();
    if (content && content.variant === 'chart') {
      const labels = content.series?.map((s) => s.label);
      expect(labels).toEqual(['California', 'Texas']);
    }
  });

  // Test: deriveContentForCard cross-place alphabetization
  // Situation: Comparison across multiple places (Texas, Alaska, California) for a single variable.
  // Expectation: Series are sorted alphabetically by place name label.
  it('alphabetizes series by place name in cross-place comparison charts', () => {
    const comparison: ComparisonResult = {
      id: 'comp-1',
      title: 'State Comparison',
      charts: [
        {
          variableDcid: 'Count_Person',
          title: 'Population Comparison',
          description: 'Comparison across states',
        },
      ],
    };

    const allResults: Record<string, QueryResult> = {
      tx: {
        id: 'tx',
        title: 'Texas',
        placeDcid: 'geoId/48',
        placeName: 'Texas',
        variables: [{ dcid: 'Count_Person', name: 'Population' }],
        entities: [{ dcid: 'geoId/48', name: 'Texas' }],
        timeSeries: [
          {
            variableDcid: 'Count_Person',
            entityDcid: 'geoId/48',
            facets: [
              {
                facetId: 'f1',
                source: 'Census',
                sourceUrl: '',
                unit: '',
                earliestDate: '2020',
                latestDate: '2020',
                observationCount: 1,
                observations: sampleObservations,
              },
            ],
          },
        ],
      },
      ak: {
        id: 'ak',
        title: 'Alaska',
        placeDcid: 'geoId/02',
        placeName: 'Alaska',
        variables: [{ dcid: 'Count_Person', name: 'Population' }],
        entities: [{ dcid: 'geoId/02', name: 'Alaska' }],
        timeSeries: [
          {
            variableDcid: 'Count_Person',
            entityDcid: 'geoId/02',
            facets: [
              {
                facetId: 'f2',
                source: 'Census',
                sourceUrl: '',
                unit: '',
                earliestDate: '2020',
                latestDate: '2020',
                observationCount: 1,
                observations: sampleObservations,
              },
            ],
          },
        ],
      },
      ca: {
        id: 'ca',
        title: 'California',
        placeDcid: 'geoId/06',
        placeName: 'California',
        variables: [{ dcid: 'Count_Person', name: 'Population' }],
        entities: [{ dcid: 'geoId/06', name: 'California' }],
        timeSeries: [
          {
            variableDcid: 'Count_Person',
            entityDcid: 'geoId/06',
            facets: [
              {
                facetId: 'f3',
                source: 'Census',
                sourceUrl: '',
                unit: '',
                earliestDate: '2020',
                latestDate: '2020',
                observationCount: 1,
                observations: sampleObservations,
              },
            ],
          },
        ],
      },
    };

    const content = deriveContentForCard(
      'chart',
      undefined,
      undefined,
      'Count_Person',
      comparison,
      allResults,
    );
    expect(content).not.toBeNull();
    if (content && content.variant === 'chart') {
      const labels = content.series?.map((s) => s.label);
      expect(labels).toEqual(['Alaska', 'California', 'Texas']);
    }
  });

  // Test: deriveContentForCard same-place variable alphabetization
  // Situation: Same-place comparison overlaying multiple variables.
  // Expectation: Series are sorted alphabetically by variable name using deterministic English locale.
  it('alphabetizes series by variable name in same-place comparison charts', () => {
    const comparison: ComparisonResult = {
      id: 'comp-2',
      title: 'City Metrics',
      charts: [
        {
          variableDcid: 'Var_A',
          title: 'Metrics Comparison',
          description: 'Comparing variables in one city',
        },
      ],
    };

    const allResults: Record<string, QueryResult> = {
      sf: {
        id: 'sf',
        title: 'San Francisco',
        placeDcid: 'geoId/0667000',
        placeName: 'San Francisco',
        variables: [
          { dcid: 'Var_Z', name: 'Zebra Count' },
          { dcid: 'Var_A', name: 'Apple Yield' },
          { dcid: 'Var_M', name: 'Mango Output' },
        ],
        entities: [{ dcid: 'geoId/0667000', name: 'San Francisco' }],
        timeSeries: [
          {
            variableDcid: 'Var_Z',
            entityDcid: 'geoId/0667000',
            facets: [
              {
                facetId: 'fZ',
                source: 'USDA',
                sourceUrl: '',
                unit: '',
                earliestDate: '2020',
                latestDate: '2020',
                observationCount: 1,
                observations: sampleObservations,
              },
            ],
          },
          {
            variableDcid: 'Var_A',
            entityDcid: 'geoId/0667000',
            facets: [
              {
                facetId: 'fA',
                source: 'USDA',
                sourceUrl: '',
                unit: '',
                earliestDate: '2020',
                latestDate: '2020',
                observationCount: 1,
                observations: sampleObservations,
              },
            ],
          },
          {
            variableDcid: 'Var_M',
            entityDcid: 'geoId/0667000',
            facets: [
              {
                facetId: 'fM',
                source: 'USDA',
                sourceUrl: '',
                unit: '',
                earliestDate: '2020',
                latestDate: '2020',
                observationCount: 1,
                observations: sampleObservations,
              },
            ],
          },
        ],
      },
    };

    const content = deriveContentForCard(
      'chart',
      undefined,
      undefined,
      'Var_A',
      comparison,
      allResults,
    );
    expect(content).not.toBeNull();
    if (content && content.variant === 'chart') {
      const labels = content.series?.map((s) => s.label);
      expect(labels).toEqual(['Apple Yield', 'Mango Output', 'Zebra Count']);
    }
  });
});
