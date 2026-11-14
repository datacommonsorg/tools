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
 * @fileoverview Renders a Data Commons web-component chart (line/bar/map/ranking/…) from an agent chart config.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import type { ChartConfig, ChartItem } from '@/src/hooks/use_sse_chat';
import {
  API_ROOT,
  DataCommonsComponent,
  type DataCommonsComponentAttributes,
  type DataCommonsComponentTagName,
  useDcChartEmptyNotice,
} from '@/src/utils/datacommons_component';

/**
 * Chart renderer for chat answers.
 *
 * Charts are rendered via Data Commons web components (datacommons-line /
 * -bar / -ranking / -map / -highlight). Each component owns its own
 * data fetch, source attribution, "Source: X • About this data • API
 * code" footer, and metadata modal — wired to the actual DCIDs the agent
 * returned, so the modal that pops up over an India chart shows India
 * metadata (not USA, which was the bug in the previous Recharts impl
 * that defaulted missing placeDcids to country/USA).
 *
 * The surrounding card chrome from Figma is kept (rounded border, max charts
 * cap, charts side by side in a row grid, with each scatter chart on a row of
 * its own), but the chart interior is no longer custom.
 * This matches the Key Metrics dashboard's approach to chart rendering.
 */
interface ChartTileProps {
  config: ChartConfig;
  /**
   * Called once every rendered chart has settled (drawn, reported no data, or
   * reached the watch budget of `useDcChartEmptyNotice`), and right after
   * mount when the tile renders nothing.
   */
  onSettled?: () => void;
  /**
   * Keeps every card behind its skeleton even once its chart has drawn, for
   * while the surrounding answer is still revealing.
   */
  shouldHoldSkeleton?: boolean;
}

const MAX_CHARTS = 3;

/**
 * Space a card holds while its chart loads, so the layout does not jump when
 * the chart draws. Highlight is a single number; every other kind is a plot.
 * Approximations of the drawn heights: a chart that draws taller or shorter
 * still shifts the layout by the difference.
 */
const PENDING_HEIGHT_CLASS: Partial<
  Record<DataCommonsComponentTagName, string>
> = { 'datacommons-highlight': 'min-h-30' };
const DEFAULT_PENDING_HEIGHT_CLASS = 'min-h-90';

/**
 * Chart kinds that take a row of their own. A scatter plots one variable
 * against another, so its two axes need the tile's full width to stay legible.
 */
const FULL_ROW_CHART_KINDS: ReadonlySet<ChartItem['vizType']> = new Set([
  'scatter',
]);

/** Fewest visible charts that a row lays out side by side. */
const MIN_CHARTS_SIDE_BY_SIDE = 2;

/** The tile: its rows stacked `gap-6` (24px at the default root size) apart. */
const CHARTS_CONTAINER_CLASS = 'dc-charts-container flex flex-col gap-6';
/**
 * A row whose visible charts sit side by side, `gap-6` apart, in as many
 * columns of at least 20rem (320px at the default root size) as fit.
 */
const CHARTS_ROW_SIDE_BY_SIDE_CLASS =
  'dc-charts-row grid gap-6 grid-cols-[repeat(auto-fit,minmax(min(100%,20rem),1fr))]';
/** A row with one visible chart, which spans the tile's full width. */
const CHARTS_ROW_SINGLE_CLASS = 'dc-charts-row grid gap-6 grid-cols-1';
/** A row whose charts are all empty, taken out of the layout. */
const CHARTS_ROW_HIDDEN_CLASS = 'dc-charts-row hidden';

/**
 * Renders the agent's chart directive as rows of DC charts. Each scatter chart
 * has a row of its own, and the charts between scatters share a row, side by
 * side when there is room (see `splitChartRows`).
 */
export function ChartTile({
  config,
  onSettled,
  shouldHoldSkeleton = false,
}: ChartTileProps) {
  // Charts that reported no data of their own after mounting. The agent
  // already withholds chart configs when its tool calls returned no
  // observations, but each DC component runs its own fetch against the place
  // and date it was handed, and that can come back empty even when the answer
  // has numbers -- leaving a card whose whole content is "No data available."
  // over a gray placeholder. Those cards drop out of the layout below, and if
  // every card drops out the container goes with them rather than leaving an
  // empty grid behind. Declared before the early returns: hooks cannot be
  // called conditionally.
  const [emptyIndices, setEmptyIndices] = useState<ReadonlySet<number>>(
    () => new Set(),
  );
  const markEmpty = useCallback((index: number) => {
    setEmptyIndices((prev) => {
      if (prev.has(index)) return prev;
      const next = new Set(prev);
      next.add(index);
      return next;
    });
  }, []);
  const [settledIndices, setSettledIndices] = useState<ReadonlySet<number>>(
    () => new Set(),
  );
  const markSettled = useCallback((index: number) => {
    setSettledIndices((prev) => {
      if (prev.has(index)) return prev;
      const next = new Set(prev);
      next.add(index);
      return next;
    });
  }, []);

  const toRender = selectRenderableCharts(config);
  // True at once for a tile with nothing to render.
  const isSettled = toRender.every((_, index) => settledIndices.has(index));
  // Held in a ref so an inline arrow from the caller does not re-fire the
  // effect on every parent re-render.
  const onSettledRef = useRef(onSettled);
  onSettledRef.current = onSettled;
  useEffect(() => {
    if (isSettled) onSettledRef.current?.();
  }, [isSettled]);

  if (toRender.length === 0) return null;

  const visibleCount = toRender.filter(
    (_, index) => !emptyIndices.has(index),
  ).length;
  if (visibleCount === 0) return null;

  return (
    <div
      /* No top margin: the answer card's own flex gap already spaces this. */
      className={CHARTS_CONTAINER_CLASS}
    >
      {splitChartRows(toRender).map((row) => {
        const rowVisibleCount = row.filter(
          (index) => !emptyIndices.has(index),
        ).length;
        return (
          <div
            // The first index is stable as charts stream in, so a row keeps
            // its element and its cards are not remounted.
            key={row[0]}
            className={getChartRowClass(rowVisibleCount)}
          >
            {row.map((index) => (
              <ChartCard
                key={index}
                chart={toRender[index]}
                hidden={emptyIndices.has(index)}
                shouldHoldSkeleton={shouldHoldSkeleton}
                onEmpty={() => markEmpty(index)}
                onSettled={() => markSettled(index)}
              />
            ))}
          </div>
        );
      })}
    </div>
  );
}

/**
 * Splits a tile's charts into rows of indices into `charts`, in order. Each
 * chart of a kind in `FULL_ROW_CHART_KINDS` is a row of its own, and each
 * maximal stretch of other charts between them is one row. Rows depend on
 * chart kinds and order only, never on which charts reported no data, so a
 * card never moves to another row element, which would remount it and replay
 * its fetch.
 */
export function splitChartRows(charts: readonly ChartItem[]): number[][] {
  const rows: number[][] = [];
  for (const [index, chart] of charts.entries()) {
    const lastRow = rows.at(-1);
    const shouldJoinLastRow =
      lastRow !== undefined &&
      !isFullRowChart(chart) &&
      !isFullRowChart(charts[lastRow[0]]);
    if (shouldJoinLastRow) {
      lastRow.push(index);
    } else {
      rows.push([index]);
    }
  }
  return rows;
}

/** Returns whether `chart` takes a row of its own. */
function isFullRowChart(chart: ChartItem): boolean {
  return FULL_ROW_CHART_KINDS.has(chart.vizType);
}

/** Returns the class of a row that shows `visibleCount` charts. */
function getChartRowClass(visibleCount: number): string {
  if (visibleCount === 0) return CHARTS_ROW_HIDDEN_CLASS;
  if (visibleCount >= MIN_CHARTS_SIDE_BY_SIDE) {
    return CHARTS_ROW_SIDE_BY_SIDE_CLASS;
  }
  return CHARTS_ROW_SINGLE_CLASS;
}

/** Returns the charts of `config` the tile can render; empty when none. */
function selectRenderableCharts(config: ChartConfig): ChartItem[] {
  if (!config || !config.shouldRender || config.hideCharts) return [];

  // The directive lists its charts in `charts`; an empty list means there is
  // nothing to render.
  const charts: ChartItem[] | undefined = config.charts;
  if (!charts || !Array.isArray(charts) || charts.length === 0) {
    return [];
  }

  return (
    charts
      .slice(0, MAX_CHARTS)
      .filter((chart) => chart.variableDcids && chart.variableDcids.length > 0)
      // Each DC component needs SOME place anchor: either explicit places
      // or a parent + child type. Drop entries the agent under-specified
      // rather than letting the component crash.
      .filter(
        (chart) =>
          (chart.placeDcids && chart.placeDcids.length > 0) ||
          (chart.parentPlace && chart.childPlaceType),
      )
  );
}

interface ChartCardProps {
  chart: ChartItem;
  hidden: boolean;
  shouldHoldSkeleton: boolean;
  onEmpty: () => void;
  onSettled: () => void;
}

/**
 * Renders one chart as a Data Commons web component inside the card wrapper.
 *
 * Stays in the tree once `hidden`, taken out of the layout with
 * `display: none` rather than unmounted: a `display: none` grid item claims no
 * track, and keeping the element means the fetch it already made is not
 * replayed if React remounts the card.
 */
function ChartCard({
  chart,
  hidden,
  shouldHoldSkeleton,
  onEmpty,
  onSettled,
}: ChartCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [isLoading, setIsLoading] = useState(true);
  const tag = getDcComponentTag(chart.vizType);
  const attrs = getDcComponentAttributes(chart);
  useDcChartEmptyNotice(cardRef, tag, onEmpty, () => {
    setIsLoading(false);
    onSettled();
  });
  const pendingHeightClass =
    PENDING_HEIGHT_CLASS[tag] ?? DEFAULT_PENDING_HEIGHT_CLASS;
  const showSkeleton = isLoading || shouldHoldSkeleton;
  // The DC web component renders its own bordered card (Source caption,
  // chart, footer with "About this data" + "API code"). Wrapping it in
  // another bordered div produced a double-border look. We keep just a
  // semantic wrapper so the grid layout and print-CSS hooks
  // (.dc-chart-card) still target the card. While the chart loads, a skeleton
  // covers its half-drawn interior and the card holds the space it will fill;
  // once shown, the skeleton fades out over the drawn chart.
  return (
    <div
      className={`dc-chart-card relative${isLoading ? ` ${pendingHeightClass}` : ''}`}
      ref={cardRef}
      style={hidden ? { display: 'none' } : undefined}
    >
      {/* Busy marks only the chart: a live region inside a busy element may
          go unannounced, so the status below stays outside it. Both follow
          the chart's own load, not the held skeleton: the overlay is
          aria-hidden, so a drawn chart is readable beneath it. */}
      <div aria-busy={isLoading}>
        <DataCommonsComponent tag={tag} apiroot={API_ROOT} {...attrs} />
      </div>
      {isLoading && (
        <span role="status" className="sr-only">
          Loading chart
        </span>
      )}
      <div
        aria-hidden="true"
        className={`absolute inset-0 z-10 rounded-chart bg-surface pointer-events-none motion-safe:transition-[opacity,visibility] motion-safe:duration-300 ease-out${
          showSkeleton ? '' : ' opacity-0 invisible'
        }`}
      >
        {/* A light-blue band sweeps top to bottom; under reduced motion it
            stays parked off-canvas. The sweep stops once the skeleton
            releases, so nothing keeps animating behind the faded overlay. */}
        <div className="relative size-full overflow-clip border border-border rounded-chart bg-surface">
          <div
            className={`absolute inset-0 -translate-y-full bg-linear-to-b from-transparent via-surface-blue to-transparent${
              showSkeleton ? ' motion-safe:animate-shimmer' : ''
            }`}
          />
        </div>
      </div>
    </div>
  );
}

/**
 * Maps an agent vizType to a DC web component tag. Anything without an
 * explicit mapping falls back to line, which is the most forgiving
 * renderer (single variable + single place is always valid).
 */
export function getDcComponentTag(
  viz: ChartItem['vizType'],
): DataCommonsComponentTagName {
  switch (viz) {
    case 'bar':
      return 'datacommons-bar';
    case 'map':
      return 'datacommons-map';
    case 'ranking':
      return 'datacommons-ranking';
    case 'highlight':
      return 'datacommons-highlight';
    case 'scatter':
      return 'datacommons-scatter';
    default:
      return 'datacommons-line';
  }
}

/**
 * The chart kinds whose web component reads the per-capita variable list from
 * `perCapita`. Scatter reads it from `usePerCapita`.
 */
const PER_CAPITA_KINDS: ReadonlySet<ChartItem['vizType']> = new Set([
  'bar',
  'line',
  'map',
  'ranking',
  'highlight',
]);

/**
 * Builds the attribute set the DC component expects. Attribute names are
 * case-sensitive for some components (e.g. parentPlace, childPlaceType)
 * and the DC components accept space-separated strings for list-shaped
 * attributes (variables, places, perCapita, facetIds). A boolean attribute is
 * set as a bare attribute when true and left off when false, which is how the
 * components' boolean converter reads it.
 */
export function getDcComponentAttributes(
  chart: ChartItem,
): DataCommonsComponentAttributes {
  const variableDcids = chart.variableDcids;
  const attrs: DataCommonsComponentAttributes = {
    header: chart.title ?? '',
    variables: variableDcids.join(' '),
  };
  if (chart.placeDcids && chart.placeDcids.length > 0) {
    // Some DC components key on `places`, others on the singular `place`
    // (highlight). Emit both so the component reads the one it uses and
    // ignores the other.
    attrs.places = chart.placeDcids.join(' ');
    attrs.place = chart.placeDcids[0];
  }
  if (chart.parentPlace) attrs.parentPlace = chart.parentPlace;
  if (chart.childPlaceType) attrs.childPlaceType = chart.childPlaceType;
  if (chart.date) attrs.date = chart.date;
  if (chart.unit) attrs.unit = chart.unit;
  // Highlight requires singular `variable` rather than `variables`.
  if (variableDcids.length === 1) {
    attrs.variable = variableDcids[0];
  }
  if (chart.perCapita && variableDcids.length > 0) {
    if (chart.vizType === 'scatter') {
      attrs.usePerCapita = variableDcids.join(' ');
    } else if (PER_CAPITA_KINDS.has(chart.vizType)) {
      attrs.perCapita = variableDcids.join(' ');
    }
  }
  if (chart.facetIds && variableDcids.length > 0) {
    const facets = chart.facetIds;
    if (chart.vizType === 'highlight') {
      const facetId = facets[variableDcids[0]];
      if (facetId) {
        attrs.facetId = facetId;
      }
    } else if (variableDcids.every((variable) => Boolean(facets[variable]))) {
      attrs.facetIds = variableDcids
        .map((variable) => facets[variable])
        .join(' ');
    } else if (variableDcids.some((variable) => Boolean(facets[variable]))) {
      attrs.facetMapping = JSON.stringify(facets);
    }
  }
  if (chart.rankingCount !== undefined) {
    attrs.rankingCount = chart.rankingCount;
  }
  if (chart.showHighestLowest) {
    attrs.showHighestLowest = true;
  }
  if (chart.showLowest) {
    attrs.showLowest = true;
  }
  if (chart.sort) {
    attrs.sort = chart.sort;
  }
  // Only `<datacommons-line>` reads the date bounds.
  if (chart.vizType === 'line') {
    if (chart.startDate) {
      attrs.startDate = chart.startDate;
    }
    if (chart.endDate) {
      attrs.endDate = chart.endDate;
    }
  }
  return attrs;
}
