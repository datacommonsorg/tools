/**
 * @fileoverview Type definitions for config-driven Key Metrics dashboard charting elements.
 */

/**
 * Allowed visualization types for metrics cards.
 */
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
 * Configuration schema for a single metrics visualization card/tile.
 */
export interface MetricsTile {
  /** The type of web component to render (e.g. line, bar, map). */
  type: MetricsTileType;
  /** Title shown as the card header. */
  title: string;
  /** Custom header override. */
  header?: string;
  /** Variable DCID for single-variable charts. */
  variable?: string;
  /** Comma-separated variable DCIDs for multi-variable charts. */
  variables?: string;
  /** Place DCID for single-place charts. */
  place?: string;
  /** Comma-separated place DCIDs. */
  places?: string;
  /** Parent place DCID (useful for map navigation). */
  parentPlace?: string;
  /** Child place type filter. */
  childPlaceType?: string;
  /** Specific date filter. */
  date?: string;
  /** Maximum number of places to show in ranking charts. */
  rankingCount?: number;
  /** Whether to show both highest and lowest in ranking. */
  showHighestLowest?: boolean;
  /** Whether to show only lowest in ranking. */
  showLowest?: boolean;
  /** Whether to show place labels on maps/charts. */
  showPlaceLabels?: boolean;
  /** Sort order for ranking charts. */
  sort?:
    | "ascending"
    | "descending"
    | "ascendingPopulation"
    | "descendingPopulation";
  /** Custom color palette override. */
  colors?: string;
  /** Unit override. */
  unit?: string;
  /** Minimum range value. */
  min?: number;
  /** Maximum range value. */
  max?: number;
  /** Start date filter range. */
  startDate?: string;
  /** End date filter range. */
  endDate?: string;
}

/**
 * Represents a single tab group containing metrics visualizations.
 */
export interface MetricsTab {
  /** Unique ID for the tab. */
  id: string;
  /** Label text displayed on the tab selector. */
  label: string;
  /** Set of metric visualization cards to render within the tab. */
  tiles: MetricsTile[];
}

/**
 * Key Metrics configuration dashboard schema.
 */
export interface MetricsConfig {
  /** List of tabs containing visualizations. */
  tabs: MetricsTab[];
}
