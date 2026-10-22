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
 * @fileoverview Tests for the chart tile: the attributes each chart item
 * hands its Data Commons web component, and the tile's rendering of a
 * one-item configuration.
 */

import { act, cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ChartItem } from '@/src/hooks/use_sse_chat';
import type { DataCommonsComponentTagName } from '@/src/utils/datacommons_component';
import {
  ChartTile,
  getDcComponentAttributes,
  getDcComponentTag,
} from './tile_chart';

const GDP = 'Amount_EconomicActivity_GrossDomesticProduct_Nominal';

/** How often the chart settle poll reads the component, in milliseconds. */
const CHART_POLL_MS = 300;

/**
 * How long the settle poll watches a pending component before giving up, in
 * milliseconds; mirrors `SETTLE_BUDGET_MS` in `datacommons_component.tsx`.
 */
const SETTLE_BUDGET_MS = 20_000;

/** Gives the mounted `tag` element a shadow root holding a drawn chart. */
const drawChart = (
  container: HTMLElement,
  tag: DataCommonsComponentTagName,
): void => {
  const element = container.querySelector(tag);
  if (!element) throw new Error(`No ${tag} element is mounted.`);
  element.attachShadow({ mode: 'open' }).innerHTML =
    '<div class="chart-container"><svg></svg></div>';
};

/** Gives the mounted `tag` element a shadow root holding the no-data notice. */
const showNoData = (
  container: HTMLElement,
  tag: DataCommonsComponentTagName,
): void => {
  const element = container.querySelector(tag);
  if (!element) throw new Error(`No ${tag} element is mounted.`);
  element.attachShadow({ mode: 'open' }).innerHTML =
    '<div class="chart-container">No data available.</div>';
};

/** A line chart over one place, which the tile renders as one card. */
const LINE_CHART: ChartItem = {
  vizType: 'line',
  title: 'GDP, France',
  variableDcids: [GDP],
  placeDcids: ['country/FRA'],
};

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('getDcComponentAttributes', () => {
  it('sets the per-capita variable list under the name each component reads', () => {
    // Test: Per-capita wiring.
    // Situation: A per-capita bar chart, a per-capita scatter chart, and a
    //   per-capita slider, each over one or two variables.
    // Expectation: The bar chart carries `perCapita`, the scatter chart
    //   carries `usePerCapita` instead, and the slider carries neither.
    const bar = getDcComponentAttributes({
      vizType: 'bar',
      title: 'GDP per person',
      variableDcids: [GDP],
      placeDcids: ['country/FRA', 'country/DEU'],
      perCapita: true,
    });
    const scatter = getDcComponentAttributes({
      vizType: 'scatter',
      title: 'GDP against population',
      variableDcids: [GDP, 'Count_Person'],
      parentPlace: 'country/USA',
      childPlaceType: 'State',
      perCapita: true,
    });
    const slider = getDcComponentAttributes({
      vizType: 'slider',
      title: 'Slider',
      variableDcids: [GDP],
      placeDcids: ['country/FRA'],
      perCapita: true,
    });

    expect(bar.perCapita).toBe(GDP);
    expect(bar.usePerCapita).toBeUndefined();
    expect(scatter.usePerCapita).toBe(`${GDP} Count_Person`);
    expect(scatter.perCapita).toBeUndefined();
    expect(slider.perCapita).toBeUndefined();
    expect(slider.usePerCapita).toBeUndefined();
  });

  it('pins each variable to its served facet under the attribute the component reads', () => {
    // Test: Facet-pinning wiring.
    // Situation: A highlight tile with one facet, a two-variable bar chart
    //   where both variables carry facets, and a two-variable line chart
    //   where only one variable carries a facet.
    // Expectation: The highlight tile receives `facetId`, the fully mapped
    //   bar chart receives `facetIds` in variable order, and the partially
    //   mapped line chart receives `facetMapping` as JSON.
    const highlight = getDcComponentAttributes({
      vizType: 'highlight',
      title: 'GDP',
      variableDcids: [GDP],
      placeDcids: ['country/FRA'],
      facetIds: { [GDP]: 'f1' },
    });
    const bar = getDcComponentAttributes({
      vizType: 'bar',
      title: 'Composition',
      variableDcids: [GDP, 'Count_Person'],
      placeDcids: ['country/FRA'],
      facetIds: { Count_Person: 'f2', [GDP]: 'f1' },
    });
    const line = getDcComponentAttributes({
      vizType: 'line',
      title: 'Partial facet map',
      variableDcids: [GDP, 'Count_Person'],
      placeDcids: ['country/FRA'],
      facetIds: { [GDP]: 'f1' },
    });

    expect(highlight.facetId).toBe('f1');
    expect(highlight.facetIds).toBeUndefined();
    expect(highlight.facetMapping).toBeUndefined();
    expect(bar.facetIds).toBe('f1 f2');
    expect(bar.facetId).toBeUndefined();
    expect(bar.facetMapping).toBeUndefined();
    expect(line.facetMapping).toBe(JSON.stringify({ [GDP]: 'f1' }));
    expect(line.facetIds).toBeUndefined();
  });

  it('passes the ranking and sort options through', () => {
    // Test: Optional ranking and bar-sort display attributes.
    // Situation: A ranking chart showing both ends of five places, a ranking
    //   chart showing only the lowest places, and a sorted bar chart.
    // Expectation: Each option maps to the attribute of the same name, with
    //   true booleans set as bare attributes, false booleans omitted, and
    //   numbers kept as numbers.
    const ranking = getDcComponentAttributes({
      vizType: 'ranking',
      title: 'GDP by state',
      variableDcids: [GDP],
      parentPlace: 'country/USA',
      childPlaceType: 'State',
      rankingCount: 5,
      showHighestLowest: true,
      showLowest: false,
    });
    const bottomRanking = getDcComponentAttributes({
      vizType: 'ranking',
      title: 'Lowest GDP by state',
      variableDcids: [GDP],
      parentPlace: 'country/USA',
      childPlaceType: 'State',
      rankingCount: 3,
      showLowest: true,
    });
    const bar = getDcComponentAttributes({
      vizType: 'bar',
      title: 'GDP',
      variableDcids: [GDP],
      placeDcids: ['country/FRA'],
      sort: 'descending',
    });

    expect(ranking).toMatchObject({
      parentPlace: 'country/USA',
      childPlaceType: 'State',
      variable: GDP,
      rankingCount: 5,
      showHighestLowest: true,
    });
    expect(ranking.showLowest).toBeUndefined();
    expect(bottomRanking.showLowest).toBe(true);
    expect(bottomRanking.showHighestLowest).toBeUndefined();
    expect(bar.sort).toBe('descending');
  });

  it('keeps the place, date, and unit attributes of a plain chart', () => {
    // Test: The attributes every chart carries.
    // Situation: A line chart over two places with a date and a unit, and
    //   no optional display settings.
    // Expectation: The header, variables, places, singular place and
    //   variable, date, and unit are set, and no per-capita, facet, ranking,
    //   or sort attribute appears.
    const attrs = getDcComponentAttributes({
      vizType: 'line',
      title: 'GDP, France and Germany',
      variableDcids: [GDP],
      placeDcids: ['country/FRA', 'country/DEU'],
      date: '2023',
      unit: 'USD',
    });

    expect(attrs).toEqual({
      header: 'GDP, France and Germany',
      variables: GDP,
      places: 'country/FRA country/DEU',
      place: 'country/FRA',
      variable: GDP,
      date: '2023',
      unit: 'USD',
    });
  });
});

describe('getDcComponentTag', () => {
  it('maps every chart kind to its component and unknown kinds to line', () => {
    // Test: The tag mapping.
    // Situation: Each chart kind the agent emits, plus `slider`, which has
    //   no mapping of its own.
    // Expectation: Each kind maps to its `datacommons-*` element and the
    //   unmapped kind falls back to the line component.
    const kinds: ChartItem['vizType'][] = [
      'line',
      'bar',
      'map',
      'ranking',
      'highlight',
      'scatter',
    ];

    expect(kinds.map(getDcComponentTag)).toEqual([
      'datacommons-line',
      'datacommons-bar',
      'datacommons-map',
      'datacommons-ranking',
      'datacommons-highlight',
      'datacommons-scatter',
    ]);
    expect(getDcComponentTag('slider')).toBe('datacommons-line');
  });
});

describe('ChartTile', () => {
  it('mounts one web component for a one-item configuration', () => {
    // Test: Rendering a chart block's one-item configuration.
    // Situation: A configuration holding one per-capita ranking chart over a
    //   cohort with a pinned facet.
    // Expectation: One `datacommons-ranking` element is mounted inside a
    //   chart card, carrying the cohort, per-capita, and facet attributes.
    const { container } = render(
      <ChartTile
        config={{
          shouldRender: true,
          charts: [
            {
              vizType: 'ranking',
              title: 'GDP per person by state',
              variableDcids: [GDP],
              parentPlace: 'country/USA',
              childPlaceType: 'State',
              perCapita: true,
              facetIds: { [GDP]: 'f1' },
            },
          ],
        }}
      />,
    );

    const cards = container.querySelectorAll('.dc-chart-card');
    expect(cards).toHaveLength(1);
    const element = cards[0].querySelector('datacommons-ranking');
    expect(element).not.toBeNull();
    expect(element?.getAttribute('parentPlace')).toBe('country/USA');
    expect(element?.getAttribute('childPlaceType')).toBe('State');
    expect(element?.getAttribute('perCapita')).toBe(GDP);
    expect(element?.getAttribute('facetIds')).toBe('f1');
    expect(element?.getAttribute('header')).toBe('GDP per person by state');
  });

  it('renders nothing for a chart without a place anchor', () => {
    // Test: The under-specified chart guard.
    // Situation: A configuration whose only chart names a variable but no
    //   places and no cohort.
    // Expectation: The tile renders nothing rather than mounting a component
    //   that cannot fetch.
    const { container } = render(
      <ChartTile
        config={{
          shouldRender: true,
          charts: [{ vizType: 'line', title: 'GDP', variableDcids: [GDP] }],
        }}
      />,
    );

    expect(container.querySelector('.dc-charts-container')).toBeNull();
  });

  it('reports settled once, after every card has settled', () => {
    // Test: The tile's settle report.
    // Situation: A tile with a line chart and a bar chart; the line chart
    //   draws first and the bar chart draws one poll later.
    // Expectation: `onSettled` has not fired while the bar chart is pending,
    //   fires once after it draws, and does not fire again.
    vi.useFakeTimers();
    const onSettled = vi.fn();
    const { container } = render(
      <ChartTile
        config={{
          shouldRender: true,
          charts: [
            {
              vizType: 'line',
              title: 'GDP, France',
              variableDcids: [GDP],
              placeDcids: ['country/FRA'],
            },
            {
              vizType: 'bar',
              title: 'GDP, Germany',
              variableDcids: [GDP],
              placeDcids: ['country/DEU'],
            },
          ],
        }}
        onSettled={onSettled}
      />,
    );

    drawChart(container, 'datacommons-line');
    act(() => {
      vi.advanceTimersByTime(CHART_POLL_MS);
    });
    expect(onSettled).not.toHaveBeenCalled();

    drawChart(container, 'datacommons-bar');
    act(() => {
      vi.advanceTimersByTime(CHART_POLL_MS * 3);
    });
    expect(onSettled).toHaveBeenCalledTimes(1);
  });

  it('reports settled at once when it renders nothing', () => {
    // Test: The settle report of an empty tile.
    // Situation: A configuration whose only chart has no place anchor, so
    //   the tile renders nothing.
    // Expectation: `onSettled` fires once right after mount.
    const onSettled = vi.fn();
    render(
      <ChartTile
        config={{
          shouldRender: true,
          charts: [{ vizType: 'line', title: 'GDP', variableDcids: [GDP] }],
        }}
        onSettled={onSettled}
      />,
    );

    expect(onSettled).toHaveBeenCalledTimes(1);
  });

  it('hides a chart that reports no data and reports settled once', () => {
    // Test: The settle report of a chart with no data.
    // Situation: A tile with one line chart whose shadow root holds the
    //   component's "No data available." notice.
    // Expectation: After the next poll `onSettled` fires once, the card is
    //   hidden, and later polls do not fire it again.
    vi.useFakeTimers();
    const onSettled = vi.fn();
    const { container } = render(
      <ChartTile
        config={{ shouldRender: true, charts: [LINE_CHART] }}
        onSettled={onSettled}
      />,
    );

    showNoData(container, 'datacommons-line');
    act(() => {
      vi.advanceTimersByTime(CHART_POLL_MS);
    });
    expect(onSettled).toHaveBeenCalledTimes(1);
    expect(container.querySelector('.dc-chart-card')).toBeNull();

    act(() => {
      vi.advanceTimersByTime(CHART_POLL_MS * 3);
    });
    expect(onSettled).toHaveBeenCalledTimes(1);
  });

  it('reports settled once when a chart stays pending past the settle budget', () => {
    // Test: The settle report of a chart that never settles.
    // Situation: A tile with one line chart whose component never attaches
    //   a shadow root, so it reads as pending on every poll.
    // Expectation: `onSettled` has not fired before the settle budget runs
    //   out, fires once on the first poll after it, and does not fire again.
    vi.useFakeTimers();
    const onSettled = vi.fn();
    render(
      <ChartTile
        config={{ shouldRender: true, charts: [LINE_CHART] }}
        onSettled={onSettled}
      />,
    );

    act(() => {
      vi.advanceTimersByTime(SETTLE_BUDGET_MS - 1);
    });
    expect(onSettled).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(CHART_POLL_MS);
    });
    expect(onSettled).toHaveBeenCalledTimes(1);

    act(() => {
      vi.advanceTimersByTime(CHART_POLL_MS * 3);
    });
    expect(onSettled).toHaveBeenCalledTimes(1);
  });
});
