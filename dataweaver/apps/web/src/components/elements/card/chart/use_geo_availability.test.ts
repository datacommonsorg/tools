import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { clearGeoCache } from './geo_service';
import { useGeoAvailability } from './use_geo_availability';

describe('useGeoAvailability', () => {
  beforeEach(() => {
    clearGeoCache();
  });

  afterEach(() => {
    clearGeoCache();
  });

  const TestHookConsumer = ({
    parentDcid,
    keys,
  }: {
    parentDcid?: string;
    keys?: string[];
  }) => {
    const [isGeoAvailable] = useGeoAvailability(parentDcid, keys);
    return createElement('div', {
      'data-testid': 'status',
      'data-available': String(isGeoAvailable),
    });
  };

  // Test: Single or zero entity count.
  // Situation: 0 or 1 entity keys provided.
  // Expectation: isGeoAvailable initializes to false immediately.
  it('initializes to false when fewer than 2 entities are provided', () => {
    const markupSingle = renderToStaticMarkup(
      createElement(TestHookConsumer, { keys: ['country/USA'] }),
    );
    expect(markupSingle).toContain('data-available="false"');

    const markupEmpty = renderToStaticMarkup(
      createElement(TestHookConsumer, { keys: [] }),
    );
    expect(markupEmpty).toContain('data-available="false"');
  });

  // Test: Un-cached multi-entity request.
  // Situation: 2+ entities with no cache entry.
  // Expectation: isGeoAvailable initializes to null (loading state).
  it('initializes to null when cache is cold for multi-entity query', () => {
    const markup = renderToStaticMarkup(
      createElement(TestHookConsumer, {
        keys: ['geoId/06', 'geoId/48'],
      }),
    );
    expect(markup).toContain('data-available="null"');
  });
});
