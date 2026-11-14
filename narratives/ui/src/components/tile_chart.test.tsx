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
 * hands its Data Commons web component, the tile's rendering of a one-item
 * configuration, and the rows the tile splits its charts into.
 */

import { act, cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  ChartTile,
  getDcComponentAttributes,
  getDcComponentTag,
  splitChartRows,
} from '@/src/components/tile_chart';
import type { ChartItem } from '@/src/hooks/use_sse_chat';
import type { DataCommonsComponentTagName } from '@/src/utils/datacommons_component';

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

/** A bar chart over one place. */
const BAR_CHART: ChartItem = {
  vizType: 'bar',
  title: 'GDP, Germany',
  variableDcids: [GDP],
  placeDcids: ['country/DEU'],
};

/** A ranking chart over the US states. */
const RANKING_CHART: ChartItem = {
  vizType: 'ranking',
  title: 'GDP by state',
  variableDcids: [GDP],
  parentPlace: 'country/USA',
  childPlaceType: 'State',
};

/** A scatter chart of two variables over the US states. */
const SCATTER_CHART: ChartItem = {
  vizType: 'scatter',
  title: 'GDP against population by state',
  variableDcids: [GDP, 'Count_Person'],
  parentPlace: 'country/USA',
  childPlaceType: 'State',
};

/** A second scatter chart, over the US counties. */
const SECOND_SCATTER_CHART: ChartItem = {
  ...SCATTER_CHART,
  title: 'GDP against population by county',
  childPlaceType: 'County',
};

/** Returns the tile's row elements in document order. */
const getRows = (container: HTMLElement): HTMLElement[] =>
  Array.from(container.querySelectorAll<HTMLElement>('.dc-charts-row'));

/** Returns how many chart cards each row of the tile holds. */
const countCardsPerRow = (container: HTMLElement): number[] =>
  getRows(container).map(
    (row) => row.querySelectorAll('.dc-chart-card').length,
  );

/** Returns the chart card that mounts the `tag` element. */
const getCard = (
  container: HTMLElement,
  tag: DataCommonsComponentTagName,
): Element | null | undefined =>
  container.querySelector(tag)?.closest('.dc-chart-card');

/** Class fragment of a row that lays its charts out side by side. */
const SIDE_BY_SIDE_FRAGMENT = 'grid-cols-[repeat(auto-fit,';

/** Class of a row that lays its charts out in one column. */
const SINGLE_COLUMN_CLASS = 'grid-cols-1';

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

  it('sets the date bounds only on a line chart', () => {
    // Test: Date bound wiring.
    // Situation: A line chart with both bounds, a line chart with only an
    //   end bound, a line chart with none, and a bar chart whose item
    //   carries bounds that only a line component reads.
    // Expectation: The first line receives `startDate` and `endDate`, the
    //   second only `endDate`, and the unbounded line and the bar receive
    //   neither.
    const bounded = getDcComponentAttributes({
      ...LINE_CHART,
      startDate: '2005',
      endDate: '2020-06',
    });
    const endOnly = getDcComponentAttributes({
      ...LINE_CHART,
      endDate: '2020-01-31',
    });
    const unbounded = getDcComponentAttributes(LINE_CHART);
    const bar = getDcComponentAttributes({
      vizType: 'bar',
      title: 'GDP',
      variableDcids: [GDP],
      placeDcids: ['country/FRA'],
      startDate: '2005',
      endDate: '2020',
    });

    expect(bounded).toMatchObject({ startDate: '2005', endDate: '2020-06' });
    expect(endOnly.endDate).toBe('2020-01-31');
    expect(endOnly).not.toHaveProperty('startDate');
    for (const attrs of [unbounded, bar]) {
      expect(attrs).not.toHaveProperty('startDate');
      expect(attrs).not.toHaveProperty('endDate');
    }
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

  it('sets the date bounds on the mounted line component', () => {
    // Test: Rendering a line chart clamped to date bounds.
    // Situation: A configuration holding one line chart with `startDate`
    //   and `endDate`.
    // Expectation: The mounted `datacommons-line` element carries the
    //   `startDate` and `endDate` attributes.
    const { container } = render(
      <ChartTile
        config={{
          shouldRender: true,
          charts: [{ ...LINE_CHART, startDate: '2005', endDate: '2020' }],
        }}
      />,
    );

    const element = container.querySelector('datacommons-line');
    expect(element?.getAttribute('startDate')).toBe('2005');
    expect(element?.getAttribute('endDate')).toBe('2020');
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

  it('holds the card busy behind a skeleton until its chart draws', () => {
    // Test: The card's loading state.
    // Situation: A one-item line chart that draws after one poll.
    // Expectation: The card is busy and announces loading before the chart
    //   draws, and does neither once it does.
    vi.useFakeTimers();
    const { container } = render(
      <ChartTile config={{ shouldRender: true, charts: [LINE_CHART] }} />,
    );
    const card = container.querySelector('.dc-chart-card');
    expect(card?.querySelector('[aria-busy]')?.getAttribute('aria-busy')).toBe(
      'true',
    );
    expect(card?.querySelector('[role="status"]')?.textContent).toBe(
      'Loading chart',
    );
    expect(card?.querySelector('[aria-busy] [role="status"]')).toBeNull();

    drawChart(container, 'datacommons-line');
    act(() => {
      vi.advanceTimersByTime(CHART_POLL_MS);
    });
    expect(card?.querySelector('[aria-busy]')?.getAttribute('aria-busy')).toBe(
      'false',
    );
    expect(card?.querySelector('[role="status"]')).toBeNull();
  });

  it('keeps a drawn chart behind its skeleton while held', () => {
    // Test: Holding the skeleton.
    // Situation: A one-item line chart that draws while `shouldHoldSkeleton`
    //   is set, then the hold is released.
    // Expectation: Once drawn, the chart is no longer busy and the status is
    //   gone, but the skeleton overlay stays visible and sweeping while held;
    //   once released, the overlay hides and stops sweeping.
    vi.useFakeTimers();
    const config = { shouldRender: true, charts: [LINE_CHART] };
    const { container, rerender } = render(
      <ChartTile config={config} shouldHoldSkeleton />,
    );
    const card = container.querySelector('.dc-chart-card');
    const overlay = card?.querySelector('[aria-hidden="true"]');

    drawChart(container, 'datacommons-line');
    act(() => {
      vi.advanceTimersByTime(CHART_POLL_MS);
    });
    expect(card?.querySelector('[aria-busy]')?.getAttribute('aria-busy')).toBe(
      'false',
    );
    expect(card?.querySelector('[role="status"]')).toBeNull();
    expect(overlay?.className).not.toContain('invisible');
    expect(overlay?.querySelector('[class*="animate-shimmer"]')).not.toBeNull();

    rerender(<ChartTile config={config} />);
    expect(overlay?.className).toContain('invisible');
    expect(overlay?.querySelector('[class*="animate-shimmer"]')).toBeNull();
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

describe('splitChartRows', () => {
  it.each([
    { run: 'A', charts: [LINE_CHART], rows: [[0]] },
    {
      run: 'A, B, C',
      charts: [LINE_CHART, BAR_CHART, RANKING_CHART],
      rows: [[0, 1, 2]],
    },
    { run: 'A, S', charts: [LINE_CHART, SCATTER_CHART], rows: [[0], [1]] },
    { run: 'S, A', charts: [SCATTER_CHART, LINE_CHART], rows: [[0], [1]] },
    {
      run: 'A, S, B',
      charts: [LINE_CHART, SCATTER_CHART, BAR_CHART],
      rows: [[0], [1], [2]],
    },
    {
      run: 'A, B, S',
      charts: [LINE_CHART, BAR_CHART, SCATTER_CHART],
      rows: [[0, 1], [2]],
    },
    {
      run: 'S, A, B',
      charts: [SCATTER_CHART, LINE_CHART, BAR_CHART],
      rows: [[0], [1, 2]],
    },
    {
      run: 'S1, S2',
      charts: [SCATTER_CHART, SECOND_SCATTER_CHART],
      rows: [[0], [1]],
    },
    { run: 'empty', charts: [], rows: [] },
  ])('splits the run $run into rows $rows', ({ charts, rows }) => {
    // Test: The row rule.
    // Situation: A run of charts in emission order, where S is a scatter
    //   chart and A, B, and C are other kinds.
    // Expectation: Each scatter is a row of its own, each stretch of other
    //   charts between scatters is one row, and an empty run has no rows.
    expect(splitChartRows(charts)).toEqual(rows);
  });
});

describe('ChartTile rows', () => {
  it('stacks a scatter below the charts before it in one tile', () => {
    // Test: Rows of a run that ends in a scatter.
    // Situation: A tile with a line chart, a bar chart, and a scatter chart.
    // Expectation: One charts container holds two rows: the line and bar
    //   charts, then the scatter chart.
    const { container } = render(
      <ChartTile
        config={{
          shouldRender: true,
          charts: [LINE_CHART, BAR_CHART, SCATTER_CHART],
        }}
      />,
    );

    expect(container.querySelectorAll('.dc-charts-container')).toHaveLength(1);
    expect(countCardsPerRow(container)).toEqual([2, 1]);
    expect(getRows(container)[1].querySelector('datacommons-scatter')).not.toBe(
      null,
    );
  });

  it('lays a multi-chart row out side by side and a one-chart row in one column', () => {
    // Test: Per-row column layout.
    // Situation: A tile with a line chart, a bar chart, and a scatter chart,
    //   all of which have data.
    // Expectation: The two-chart row uses the auto-fit columns and the
    //   scatter row uses one column.
    const { container } = render(
      <ChartTile
        config={{
          shouldRender: true,
          charts: [LINE_CHART, BAR_CHART, SCATTER_CHART],
        }}
      />,
    );

    const [sharedRow, scatterRow] = getRows(container);
    expect(sharedRow.className).toContain(SIDE_BY_SIDE_FRAGMENT);
    expect(scatterRow.className).toContain(SINGLE_COLUMN_CLASS);
    expect(scatterRow.className).not.toContain(SIDE_BY_SIDE_FRAGMENT);
  });

  it('keeps a run without a scatter in one side-by-side row', () => {
    // Test: A run with no scatter chart.
    // Situation: A tile with a line chart, a bar chart, and a ranking chart.
    // Expectation: All three cards share one row that uses the auto-fit
    //   columns.
    const { container } = render(
      <ChartTile
        config={{
          shouldRender: true,
          charts: [LINE_CHART, BAR_CHART, RANKING_CHART],
        }}
      />,
    );

    expect(countCardsPerRow(container)).toEqual([3]);
    expect(getRows(container)[0].className).toContain(SIDE_BY_SIDE_FRAGMENT);
  });

  it('lays a row out in one column once only one of its charts has data', () => {
    // Test: Per-row column layout after an empty chart.
    // Situation: A tile with a line chart, a bar chart, and a scatter chart;
    //   the bar chart reports no data.
    // Expectation: The first row switches to one column, because only the
    //   line chart in it is visible.
    vi.useFakeTimers();
    const { container } = render(
      <ChartTile
        config={{
          shouldRender: true,
          charts: [LINE_CHART, BAR_CHART, SCATTER_CHART],
        }}
      />,
    );

    showNoData(container, 'datacommons-bar');
    act(() => {
      vi.advanceTimersByTime(CHART_POLL_MS);
    });

    const [sharedRow] = getRows(container);
    expect(sharedRow.className).toContain(SINGLE_COLUMN_CLASS);
    expect(sharedRow.className).not.toContain(SIDE_BY_SIDE_FRAGMENT);
  });

  it('hides a row whose charts are all empty and keeps the other rows', () => {
    // Test: A row with no visible chart.
    // Situation: A tile with a line chart, a bar chart, and a scatter chart;
    //   the line and bar charts both report no data.
    // Expectation: The first row is hidden, the scatter row stays visible,
    //   and the scatter card is the same element as before.
    vi.useFakeTimers();
    const { container } = render(
      <ChartTile
        config={{
          shouldRender: true,
          charts: [LINE_CHART, BAR_CHART, SCATTER_CHART],
        }}
      />,
    );
    const scatterCard = getCard(container, 'datacommons-scatter');

    showNoData(container, 'datacommons-line');
    showNoData(container, 'datacommons-bar');
    act(() => {
      vi.advanceTimersByTime(CHART_POLL_MS);
    });

    const [sharedRow, scatterRow] = getRows(container);
    expect(sharedRow.classList.contains('hidden')).toBe(true);
    expect(scatterRow.classList.contains('hidden')).toBe(false);
    expect(getCard(container, 'datacommons-scatter')).toBe(scatterCard);
  });

  it('keeps its rows when the scatter between two charts is empty', () => {
    // Test: Rows ignore the empty state.
    // Situation: A tile with a line chart, a scatter chart, and a bar chart;
    //   the scatter chart reports no data.
    // Expectation: The tile keeps three rows, with the scatter row hidden
    //   and the line and bar charts on rows of their own, and neither of
    //   their cards is remounted.
    vi.useFakeTimers();
    const { container } = render(
      <ChartTile
        config={{
          shouldRender: true,
          charts: [LINE_CHART, SCATTER_CHART, BAR_CHART],
        }}
      />,
    );
    const lineCard = getCard(container, 'datacommons-line');
    const barCard = getCard(container, 'datacommons-bar');

    showNoData(container, 'datacommons-scatter');
    act(() => {
      vi.advanceTimersByTime(CHART_POLL_MS);
    });

    expect(countCardsPerRow(container)).toEqual([1, 1, 1]);
    expect(getRows(container)[1].classList.contains('hidden')).toBe(true);
    expect(getCard(container, 'datacommons-line')).toBe(lineCard);
    expect(getCard(container, 'datacommons-bar')).toBe(barCard);
  });

  it('keeps every card and row element as charts stream in', () => {
    // Test: Streaming stability.
    // Situation: A tile rerendered with its charts appended one at a time:
    //   a line chart, then a scatter chart, then a bar chart.
    // Expectation: After each rerender, the cards and rows already mounted
    //   are the same elements as before.
    const { container, rerender } = render(
      <ChartTile config={{ shouldRender: true, charts: [LINE_CHART] }} />,
    );
    const lineCard = getCard(container, 'datacommons-line');
    const [lineRow] = getRows(container);

    rerender(
      <ChartTile
        config={{ shouldRender: true, charts: [LINE_CHART, SCATTER_CHART] }}
      />,
    );
    const scatterCard = getCard(container, 'datacommons-scatter');
    const scatterRow = getRows(container)[1];
    expect(getCard(container, 'datacommons-line')).toBe(lineCard);
    expect(getRows(container)[0]).toBe(lineRow);

    rerender(
      <ChartTile
        config={{
          shouldRender: true,
          charts: [LINE_CHART, SCATTER_CHART, BAR_CHART],
        }}
      />,
    );
    expect(getCard(container, 'datacommons-line')).toBe(lineCard);
    expect(getCard(container, 'datacommons-scatter')).toBe(scatterCard);
    expect(getRows(container)[0]).toBe(lineRow);
    expect(getRows(container)[1]).toBe(scatterRow);
    expect(countCardsPerRow(container)).toEqual([1, 1, 1]);
  });

  it('keeps a row and its cards as the row gains a chart', () => {
    // Test: Streaming stability of a growing row.
    // Situation: A tile rerendered with its charts appended one at a time:
    //   a line chart, then a bar chart, then a scatter chart.
    // Expectation: The first row holds one card, then two, then sits above
    //   the scatter row, and it stays the same element with the same line
    //   card throughout.
    const { container, rerender } = render(
      <ChartTile config={{ shouldRender: true, charts: [LINE_CHART] }} />,
    );
    const lineCard = getCard(container, 'datacommons-line');
    const [firstRow] = getRows(container);

    rerender(
      <ChartTile
        config={{ shouldRender: true, charts: [LINE_CHART, BAR_CHART] }}
      />,
    );
    expect(countCardsPerRow(container)).toEqual([2]);
    expect(getRows(container)[0]).toBe(firstRow);
    expect(getCard(container, 'datacommons-line')).toBe(lineCard);

    rerender(
      <ChartTile
        config={{
          shouldRender: true,
          charts: [LINE_CHART, BAR_CHART, SCATTER_CHART],
        }}
      />,
    );
    expect(countCardsPerRow(container)).toEqual([2, 1]);
    expect(getRows(container)[0]).toBe(firstRow);
    expect(getCard(container, 'datacommons-line')).toBe(lineCard);
  });
});
