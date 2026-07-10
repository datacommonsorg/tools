/**
 * @fileoverview Renders a Data Commons web-component chart (line/bar/map/ranking/…) from an agent chart config.
 */

import type { ChartConfig, ChartItem, ProvenanceItem } from "../hooks/use_sse_chat";
import {
  API_ROOT,
  DataCommonsComponent,
  type DataCommonsComponentTagName,
} from "../utils/datacommons_component";

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
  provenance?: ProvenanceItem[];
}

const MAX_CHARTS = 3;

/** Renders the agent's chart directive as a responsive grid of DC charts. */
export function ChartTile({ config }: ChartTileProps) {
  if (!config || !config.shouldRender || config.hideCharts) return null;

  // Legacy single-chart payloads are folded into `charts` upstream by
  // mapRawChartConfig, so an empty list here means nothing to render.
  const charts: ChartItem[] | undefined = config.charts;
  if (!charts || !Array.isArray(charts) || charts.length === 0) {
    return null;
  }

  const toRender = charts
    .slice(0, MAX_CHARTS)
    .filter((chart) => chart.variableDcids && chart.variableDcids.length > 0)
    // Each DC component needs SOME place anchor — either explicit places
    // or a parent + child type. Drop entries the agent under-specified
    // rather than letting the component crash.
    .filter(
      (chart) =>
        (chart.placeDcids && chart.placeDcids.length > 0) ||
        (chart.parentPlace && chart.childPlaceType),
    );
  if (toRender.length === 0) return null;

  const isGrid = toRender.length >= 2;
  return (
    <div
      className="dc-charts-container mt-4"
      style={{
        display: "grid",
        gridTemplateColumns: isGrid
          ? "repeat(auto-fit, minmax(min(100%, 320px), 1fr))"
          : "1fr",
        gap: 24,
      }}
    >
      {toRender.map((chart, index) => (
        <ChartCard key={index} chart={chart} />
      ))}
    </div>
  );
}

/** Renders one chart as a Data Commons web component inside the card wrapper. */
function ChartCard({ chart }: { chart: ChartItem }) {
  const tag = getDcComponentTag(chart.vizType);
  const attrs = getDcComponentAttributes(chart);
  // The DC web component renders its own bordered card (Source caption,
  // chart, footer with "About this data" + "API code"). Wrapping it in
  // another bordered div produced a double-border look. We keep just a
  // semantic wrapper so the grid layout and print-CSS hooks
  // (.dc-chart-card) still target the card.
  return (
    <div className="dc-chart-card">
      <DataCommonsComponent tag={tag} apiroot={API_ROOT} {...attrs} />
    </div>
  );
}

/**
 * Maps an agent vizType to a DC web component tag. Anything without an
 * explicit mapping falls back to line, which is the most forgiving
 * renderer (single variable + single place is always valid).
 */
function getDcComponentTag(
  viz: ChartItem["vizType"],
): DataCommonsComponentTagName {
  switch (viz) {
    case "bar":
      return "datacommons-bar";
    case "map":
      return "datacommons-map";
    case "ranking":
      return "datacommons-ranking";
    case "pie":
      return "datacommons-pie";
    case "gauge":
      return "datacommons-gauge";
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
 * Builds the attribute set the DC component expects. Attribute names are
 * case-sensitive for some components (e.g. parentPlace, childPlaceType)
 * and the DC components accept space-separated strings for list-shaped
 * attributes (variables, places).
 */
function getDcComponentAttributes(
  chart: ChartItem,
): Record<string, string | undefined> {
  const attrs: Record<string, string | undefined> = {
    header: chart.title ?? "",
    variables: chart.variableDcids.join(" "),
  };
  if (chart.placeDcids && chart.placeDcids.length > 0) {
    // Some DC components key on `places`, others on the singular `place`
    // (highlight, gauge). Emit both so the component picks the one it
    // wants and ignores the other.
    attrs.places = chart.placeDcids.join(" ");
    attrs.place = chart.placeDcids[0];
  }
  if (chart.parentPlace) attrs.parentPlace = chart.parentPlace;
  if (chart.childPlaceType) attrs.childPlaceType = chart.childPlaceType;
  if (chart.date) attrs.date = chart.date;
  if (chart.unit) attrs.unit = chart.unit;
  // Highlight/gauge require singular `variable` not `variables`.
  if (chart.variableDcids.length === 1) {
    attrs.variable = chart.variableDcids[0];
  }
  return attrs;
}
