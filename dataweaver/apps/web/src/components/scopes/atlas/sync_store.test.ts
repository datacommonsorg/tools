import { describe, expect, it, vi } from 'vitest';

import type { ComparisonResult, QueryResult } from '~/server/types';
import { useAtlasStore } from '~/store';
import { deriveChartContent, deriveContentForCard } from './sync_store';

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

const mockChildResult: QueryResult = {
  id: 'res_europe',
  title: 'Unemployment in Europe',
  placeDcid: 'europe',
  placeName: 'Europe',
  isChildQuery: true,
  parentPlaceDcid: 'europe',
  variables: [
    {
      dcid: 'UnemploymentRate',
      name: 'Unemployment Rate',
    },
  ],
  entities: [
    { dcid: 'country/FRA', name: 'France' },
    { dcid: 'country/DEU', name: 'Germany' },
  ],
  timeSeries: [
    {
      variableDcid: 'UnemploymentRate',
      entityDcid: 'country/FRA',
      facets: [
        {
          facetId: 'f1',
          source: 'Eurostat',
          sourceUrl: 'https://ec.europa.eu/eurostat',
          earliestDate: '2020',
          latestDate: '2021',
          observationCount: 2,
          unit: '%',
          observations: [
            { date: '2020', value: 8.0 },
            { date: '2021', value: 7.9 },
          ],
        },
      ],
    },
    {
      variableDcid: 'UnemploymentRate',
      entityDcid: 'country/DEU',
      facets: [
        {
          facetId: 'f2',
          source: 'Eurostat',
          sourceUrl: 'https://ec.europa.eu/eurostat',
          earliestDate: '2020',
          latestDate: '2021',
          observationCount: 2,
          unit: '%',
          observations: [
            { date: '2020', value: 3.8 },
            { date: '2021', value: 3.6 },
          ],
        },
      ],
    },
  ],
};

describe('sync_store child place chart derivation', () => {
  // Test: Multi-series chart derivation for child queries.
  // Situation: QueryResult contains multiple child entities, and entityDcid is omitted.
  // Expectation: Derives a multi-series chart with all entity series and parent place DCID.
  it('derives multi-series chart when entityDcid is omitted', () => {
    const content = deriveChartContent(mockChildResult, 'UnemploymentRate');
    expect(content).not.toBeNull();
    expect(content?.variant).toBe('chart');
    if (content?.variant === 'chart') {
      expect(content.series).toHaveLength(2);
      expect(content.series?.[0]?.key).toBe('country/FRA');
      expect(content.series?.[0]?.unit).toBe('%');
      expect(content.series?.[0]?.facets).toHaveLength(1);
      expect(content.series?.[1]?.key).toBe('country/DEU');
      expect(content.series?.[1]?.unit).toBe('%');
      expect(content.series?.[1]?.facets).toHaveLength(1);
      expect(content.parentPlaceDcid).toBe('europe');
    }
  });

  // Test: Single-entity chart derivation for spawned child place card.
  // Situation: QueryResult contains multiple child entities, and a specific childPlaceDcid is provided.
  // Expectation: Derives a single-entity chart scoped to that entity without parentPlaceDcid.
  it('derives single-entity line chart when specific childPlaceDcid is provided', () => {
    const content = deriveChartContent(
      mockChildResult,
      'UnemploymentRate',
      'country/FRA',
    );
    expect(content).not.toBeNull();
    expect(content?.variant).toBe('chart');
    if (content?.variant === 'chart') {
      expect(content.series).toHaveLength(1);
      expect(content.series?.[0]?.key).toBe('country/FRA');
      expect(content.series?.[0]?.label).toBe('France');
      expect(content.series?.[0]?.unit).toBe('%');
      expect(content.series?.[0]?.facets).toHaveLength(1);
      expect(content.series?.[0]?.data).toEqual([
        { date: '2020', value: 8.0 },
        { date: '2021', value: 7.9 },
      ]);
      expect(content.title).toBe('Unemployment Rate in France');
      expect(content.parentPlaceDcid).toBeUndefined();
    }
  });
});

describe('useAtlasStore child place card selection & combining', () => {
  // Test: Child place card registration.
  // Situation: cardRegisterChart called with parent shape ID and child place DCID.
  // Expectation: Card is registered in store with placeDcid and parentPlaceDcid, and focusTarget is set.
  it('registers a new child place chart card and focuses it', () => {
    const store = useAtlasStore.getState();

    // Set up a mock history node and parent card
    useAtlasStore.setState({
      nodes: {
        node_test: {
          id: 'node_test',
          parentId: null,
          query: 'Unemployment in Europe',
          parsedQuery: null,
          results: { europe: mockChildResult },
          cardIds: ['shape:node_test__europe__chart'],
          timestamp: Date.now(),
          status: 'complete',
        },
      },
      cards: {
        'shape:node_test__europe__chart': {
          shapeId: 'shape:node_test__europe__chart',
          historyNodeId: 'node_test',
          type: 'chart',
          placeDcid: 'europe',
          variableDcid: 'UnemploymentRate',
        },
      },
      focusTarget: null,
    });

    store.cardRegisterChart(
      'shape:node_test__europe__chart',
      'country/FRA',
      'UnemploymentRate',
    );

    const updatedState = useAtlasStore.getState();
    const expectedChildShapeId =
      'shape:node_test__country/FRA__chart__UnemploymentRate';

    expect(updatedState.cards[expectedChildShapeId]).toBeDefined();
    expect(updatedState.cards[expectedChildShapeId]?.placeDcid).toBe(
      'country/FRA',
    );
    expect(updatedState.cards[expectedChildShapeId]?.parentPlaceDcid).toBe(
      'europe',
    );
    expect(updatedState.focusTarget).toEqual({
      shapeId: expectedChildShapeId,
      sourceShapeId: 'shape:node_test__europe__chart',
    });
  });

  // Test: Child place card registration from a notes card.
  // Situation: cardRegisterChart called from a notes card for an enclosing region.
  // Expectation: Card is registered with placeDcid and inferred parentPlaceDcid.
  it('registers a child place chart card from a notes card and infers parentPlaceDcid', () => {
    const store = useAtlasStore.getState();

    useAtlasStore.setState({
      nodes: {
        node_test: {
          id: 'node_test',
          parentId: null,
          query: 'Unemployment in Europe',
          parsedQuery: null,
          results: { europe: mockChildResult },
          cardIds: ['shape:node_test__europe__notes'],
          timestamp: Date.now(),
          status: 'complete',
        },
      },
      cards: {
        'shape:node_test__europe__notes': {
          shapeId: 'shape:node_test__europe__notes',
          historyNodeId: 'node_test',
          type: 'notes',
          placeDcid: 'europe',
        },
      },
      focusTarget: null,
    });

    store.cardRegisterChart(
      'shape:node_test__europe__notes',
      'country/DEU',
      'UnemploymentRate',
    );

    const updatedState = useAtlasStore.getState();
    const expectedChildShapeId =
      'shape:node_test__country/DEU__chart__UnemploymentRate';

    expect(updatedState.cards[expectedChildShapeId]).toBeDefined();
    expect(updatedState.cards[expectedChildShapeId]?.placeDcid).toBe(
      'country/DEU',
    );
    expect(updatedState.cards[expectedChildShapeId]?.parentPlaceDcid).toBe(
      'europe',
    );
  });

  // Test: Single-place card registration does not set parentPlaceDcid (preventing self-parenting).
  // Situation: cardRegisterChart called from a single-entity notes card for the same place.
  // Expectation: Card is registered with placeDcid but parentPlaceDcid remains undefined.
  it('does not set parentPlaceDcid when spawning a chart for the same single-place entity', () => {
    const store = useAtlasStore.getState();

    const mockSingleResult: QueryResult = {
      id: 'res_france',
      title: 'Economy of France',
      placeDcid: 'country/FRA',
      placeName: 'France',
      variables: [
        { dcid: 'UnemploymentRate', name: 'Unemployment Rate' },
        { dcid: 'InflationRate', name: 'Inflation Rate' },
      ],
      entities: [{ dcid: 'country/FRA', name: 'France' }],
      timeSeries: [
        {
          variableDcid: 'InflationRate',
          entityDcid: 'country/FRA',
          facets: [
            {
              facetId: 'f1',
              source: 'INSEE',
              sourceUrl: '',
              earliestDate: '2020',
              latestDate: '2021',
              observationCount: 1,
              unit: '%',
              observations: [{ date: '2020', value: 1.5 }],
            },
          ],
        },
      ],
    };

    useAtlasStore.setState({
      nodes: {
        node_single: {
          id: 'node_single',
          parentId: null,
          query: 'Economy of France',
          parsedQuery: null,
          results: { 'country/FRA': mockSingleResult },
          cardIds: ['shape:node_single__country/FRA__notes'],
          timestamp: Date.now(),
          status: 'complete',
        },
      },
      cards: {
        'shape:node_single__country/FRA__notes': {
          shapeId: 'shape:node_single__country/FRA__notes',
          historyNodeId: 'node_single',
          type: 'notes',
          placeDcid: 'country/FRA',
        },
      },
      focusTarget: null,
    });

    store.cardRegisterChart(
      'shape:node_single__country/FRA__notes',
      'country/FRA',
      'InflationRate',
    );

    const updatedState = useAtlasStore.getState();
    const expectedShapeId =
      'shape:node_single__country/FRA__chart__InflationRate';

    expect(updatedState.cards[expectedShapeId]).toBeDefined();
    expect(updatedState.cards[expectedShapeId]?.placeDcid).toBe('country/FRA');
    expect(
      updatedState.cards[expectedShapeId]?.parentPlaceDcid,
    ).toBeUndefined();
  });

  // Test: Duplicate chart card focus.
  // Situation: cardRegisterChart called when target chart card already exists in the store.
  // Expectation: focusTarget is updated to the existing card and cardRegister is not called again.
  it('focuses existing card without calling cardRegister when target card already exists', () => {
    const store = useAtlasStore.getState();

    const existingShapeId =
      'shape:node_test__country/FRA__chart__UnemploymentRate';

    useAtlasStore.setState({
      nodes: {
        node_test: {
          id: 'node_test',
          parentId: null,
          query: 'Unemployment in Europe',
          parsedQuery: null,
          results: { europe: mockChildResult },
          cardIds: ['shape:node_test__europe__chart', existingShapeId],
          timestamp: Date.now(),
          status: 'complete',
        },
      },
      cards: {
        'shape:node_test__europe__chart': {
          shapeId: 'shape:node_test__europe__chart',
          historyNodeId: 'node_test',
          type: 'chart',
          placeDcid: 'europe',
          variableDcid: 'UnemploymentRate',
        },
        [existingShapeId]: {
          shapeId: existingShapeId,
          historyNodeId: 'node_test',
          type: 'chart',
          placeDcid: 'country/FRA',
          parentPlaceDcid: 'europe',
          variableDcid: 'UnemploymentRate',
        },
      },
      focusTarget: null,
    });

    const cardRegisterSpy = vi.spyOn(useAtlasStore.getState(), 'cardRegister');

    store.cardRegisterChart(
      'shape:node_test__europe__chart',
      'country/FRA',
      'UnemploymentRate',
    );

    const updatedState = useAtlasStore.getState();

    expect(cardRegisterSpy).not.toHaveBeenCalled();
    expect(updatedState.focusTarget).toEqual({
      shapeId: existingShapeId,
      sourceShapeId: 'shape:node_test__europe__chart',
    });

    cardRegisterSpy.mockRestore();
  });

  // Test: Child-of-child parentPlaceDcid inheritance.
  // Situation: cardRegisterChart called from an already spawned child card for the same place.
  // Expectation: Newly registered chart preserves the top-level enclosing parentPlaceDcid.
  it('preserves top-level enclosing parentPlaceDcid when registering a chart from an already spawned child card', () => {
    const store = useAtlasStore.getState();

    const spawnedChildShapeId =
      'shape:node_test__country/FRA__chart__UnemploymentRate';

    useAtlasStore.setState({
      nodes: {
        node_test: {
          id: 'node_test',
          parentId: null,
          query: 'Unemployment in Europe',
          parsedQuery: null,
          results: { europe: mockChildResult },
          cardIds: [spawnedChildShapeId],
          timestamp: Date.now(),
          status: 'complete',
        },
      },
      cards: {
        [spawnedChildShapeId]: {
          shapeId: spawnedChildShapeId,
          historyNodeId: 'node_test',
          type: 'chart',
          placeDcid: 'country/FRA',
          parentPlaceDcid: 'europe',
          variableDcid: 'UnemploymentRate',
        },
      },
      focusTarget: null,
    });

    store.cardRegisterChart(
      spawnedChildShapeId,
      'country/FRA',
      'YouthUnemploymentRate',
    );

    const updatedState = useAtlasStore.getState();
    const expectedNewShapeId =
      'shape:node_test__country/FRA__chart__YouthUnemploymentRate';

    expect(updatedState.cards[expectedNewShapeId]).toBeDefined();
    expect(updatedState.cards[expectedNewShapeId]?.placeDcid).toBe(
      'country/FRA',
    );
    expect(updatedState.cards[expectedNewShapeId]?.parentPlaceDcid).toBe(
      'europe',
    );
    expect(updatedState.focusTarget).toEqual({
      shapeId: expectedNewShapeId,
      sourceShapeId: spawnedChildShapeId,
    });
  });

  // Test: Multi-selection entity DCID isolation and QueryResult synthesizing.
  // Situation: Two child place cards are selected.
  // Expectation: getSelectedEntityDcids returns only the two child DCIDs, and getResultsForSelectedCards synthesizes two isolated QueryResults.
  it('correctly isolates single-entity QueryResults when selecting multiple child cards', () => {
    const store = useAtlasStore.getState();

    const shapeIdFra = 'shape:node_test__country/FRA__chart__UnemploymentRate';
    const shapeIdDeu = 'shape:node_test__country/DEU__chart__UnemploymentRate';

    useAtlasStore.setState({
      nodes: {
        node_test: {
          id: 'node_test',
          parentId: null,
          query: 'Unemployment in Europe',
          parsedQuery: null,
          results: { europe: mockChildResult },
          cardIds: [shapeIdFra, shapeIdDeu],
          timestamp: Date.now(),
          status: 'complete',
        },
      },
      cards: {
        [shapeIdFra]: {
          shapeId: shapeIdFra,
          historyNodeId: 'node_test',
          type: 'chart',
          placeDcid: 'country/FRA',
          parentPlaceDcid: 'europe',
          variableDcid: 'UnemploymentRate',
        },
        [shapeIdDeu]: {
          shapeId: shapeIdDeu,
          historyNodeId: 'node_test',
          type: 'chart',
          placeDcid: 'country/DEU',
          parentPlaceDcid: 'europe',
          variableDcid: 'UnemploymentRate',
        },
      },
    });

    const selectedEntities = store.getSelectedEntityDcids([
      shapeIdFra,
      shapeIdDeu,
    ]);
    expect(selectedEntities).toEqual(['country/FRA', 'country/DEU']);

    const selectedResults = store.getResultsForSelectedCards([
      shapeIdFra,
      shapeIdDeu,
    ]);
    expect(selectedResults).toHaveLength(2);

    const resFra = selectedResults[0];
    const resDeu = selectedResults[1];

    expect(resFra?.placeDcid).toBe('country/FRA');
    expect(resFra?.placeName).toBe('France');
    expect(resFra?.isChildQuery).toBe(false);
    expect(resFra?.parentPlaceDcid).toBeUndefined();
    expect(resFra?.entities).toEqual([{ dcid: 'country/FRA', name: 'France' }]);
    expect(resFra?.timeSeries).toHaveLength(1);
    expect(resFra?.timeSeries[0]?.entityDcid).toBe('country/FRA');

    expect(resDeu?.placeDcid).toBe('country/DEU');
    expect(resDeu?.placeName).toBe('Germany');
    expect(resDeu?.isChildQuery).toBe(false);
    expect(resDeu?.parentPlaceDcid).toBeUndefined();
    expect(resDeu?.entities).toEqual([
      { dcid: 'country/DEU', name: 'Germany' },
    ]);
    expect(resDeu?.timeSeries).toHaveLength(1);
    expect(resDeu?.timeSeries[0]?.entityDcid).toBe('country/DEU');
  });
});
