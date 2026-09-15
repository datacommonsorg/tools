/**
 * @fileoverview Types describing the config-driven Key Metrics dashboard composition.
 */

/** Chart flavors the metrics dashboard can render, one per <datacommons-*> web component. */
export type MetricsTileType =
  | "line"
  | "bar"
  | "map"
  | "ranking"
  | "highlight"
  | "scatter"
  | "pie"
  | "gauge"
  | "slider";

/**
 * One dashboard tile, mapping 1:1 onto a <datacommons-${type}> web component.
 * The MetricsPage <Tile> wrapper shows `title` as its chrome header; everything
 * else passes through as attributes to the DC component. See
 * website/packages/web-components/docs/components/*.md for the per-type
 * required/optional attribute set.
 *
 * Highlight cards are just `type: "highlight"` tiles — they render with the
 * DC component's native light-blue chip styling (no custom gradient wrapper).
 */
export interface MetricsTile {
  type: MetricsTileType;
  title: string;
  header?: string;
  variable?: string;
  variables?: string;
  place?: string;
  places?: string;
  parentPlace?: string;
  childPlaceType?: string;
  date?: string;
  rankingCount?: number;
  showHighestLowest?: boolean;
  showLowest?: boolean;
  showPlaceLabels?: boolean;
  sort?:
    | "ascending"
    | "descending"
    | "ascendingPopulation"
    | "descendingPopulation";
  colors?: string;
  unit?: string;
  min?: number;
  max?: number;
  startDate?: string;
  endDate?: string;
}

/** One dashboard tab: a labelled group of tiles. */
export interface MetricsTab {
  id: string;
  label: string;
  tiles: MetricsTile[];
}

/** Root of the metrics block in branding.json: the full tab set. */
export interface MetricsConfig {
  tabs: MetricsTab[];
}
