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

import { useCallback, useEffect, useRef, useState } from "react";

import type { ChartConfig, ChartItem } from "@/src/hooks/use_sse_chat";
import {
  API_ROOT,
  DataCommonsComponent,
  type DataCommonsComponentAttributes,
  type DataCommonsComponentTagName,
  useDcChartEmptyNotice,
} from "@/src/utils/datacommons_component";

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
 * We keep the surrounding card chrome from Figma (rounded border, max
 * charts cap, 2-column grid) but the chart interior is no longer custom.
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
}

const MAX_CHARTS = 3;

/** Renders the agent's chart directive as a responsive grid of DC charts. */
export function ChartTile({ config, onSettled }: ChartTileProps) {
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

  const isGrid = visibleCount >= 2;
  return (
    <div
      /* No top margin: the answer card's own flex gap already spaces this. */
      className="dc-charts-container"
      style={{
        display: "grid",
        gridTemplateColumns: isGrid
          ? "repeat(auto-fit, minmax(min(100%, 320px), 1fr))"
          : "1fr",
        gap: 24,
      }}
    >
      {toRender.map((chart, index) => (
        <ChartCard
          key={index}
          chart={chart}
          hidden={emptyIndices.has(index)}
          onEmpty={() => markEmpty(index)}
          onSettled={() => markSettled(index)}
        />
      ))}
    </div>
  );
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

  return charts
    .slice(0, MAX_CHARTS)
    .filter((chart) => chart.variableDcids && chart.variableDcids.length > 0)
    // Each DC component needs SOME place anchor: either explicit places
    // or a parent + child type. Drop entries the agent under-specified
    // rather than letting the component crash.
    .filter(
      (chart) =>
        (chart.placeDcids && chart.placeDcids.length > 0) ||
        (chart.parentPlace && chart.childPlaceType),
    );
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
  onEmpty,
  onSettled,
}: {
  chart: ChartItem;
  hidden: boolean;
  onEmpty: () => void;
  onSettled: () => void;
}) {
  const cardRef = useRef<HTMLDivElement>(null);
  const tag = getDcComponentTag(chart.vizType);
  const attrs = getDcComponentAttributes(chart);
  useDcChartEmptyNotice(cardRef, tag, onEmpty, onSettled);
  // The DC web component renders its own bordered card (Source caption,
  // chart, footer with "About this data" + "API code"). Wrapping it in
  // another bordered div produced a double-border look. We keep just a
  // semantic wrapper so the grid layout and print-CSS hooks
  // (.dc-chart-card) still target the card.
  return (
    <div
      className="dc-chart-card"
      ref={cardRef}
      style={hidden ? { display: "none" } : undefined}
    >
      <DataCommonsComponent tag={tag} apiroot={API_ROOT} {...attrs} />
    </div>
  );
}

/**
 * Maps an agent vizType to a DC web component tag. Anything without an
 * explicit mapping falls back to line, which is the most forgiving
 * renderer (single variable + single place is always valid).
 */
export function getDcComponentTag(
  viz: ChartItem["vizType"],
): DataCommonsComponentTagName {
  switch (viz) {
    case "bar":
      return "datacommons-bar";
    case "map":
      return "datacommons-map";
    case "ranking":
      return "datacommons-ranking";
    case "highlight":
      return "datacommons-highlight";
    case "scatter":
      return "datacommons-scatter";
    case "line":
    default:
      return "datacommons-line";
  }
}

/**
 * The chart kinds whose web component reads the per-capita variable list from
 * `perCapita`. Scatter reads it from `usePerCapita`.
 */
const PER_CAPITA_KINDS: ReadonlySet<ChartItem["vizType"]> = new Set([
  "bar",
  "line",
  "map",
  "ranking",
  "highlight",
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
    header: chart.title ?? "",
    variables: variableDcids.join(" "),
  };
  if (chart.placeDcids && chart.placeDcids.length > 0) {
    // Some DC components key on `places`, others on the singular `place`
    // (highlight). Emit both so the component reads the one it uses and
    // ignores the other.
    attrs.places = chart.placeDcids.join(" ");
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
    if (chart.vizType === "scatter") {
      attrs.usePerCapita = variableDcids.join(" ");
    } else if (PER_CAPITA_KINDS.has(chart.vizType)) {
      attrs.perCapita = variableDcids.join(" ");
    }
  }
  if (chart.facetIds && variableDcids.length > 0) {
    const facets = chart.facetIds;
    if (chart.vizType === "highlight") {
      const facetId = facets[variableDcids[0]];
      if (facetId) {
        attrs.facetId = facetId;
      }
    } else if (
      variableDcids.every((variable) => Boolean(facets[variable]))
    ) {
      attrs.facetIds = variableDcids
        .map((variable) => facets[variable])
        .join(" ");
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
  return attrs;
}
