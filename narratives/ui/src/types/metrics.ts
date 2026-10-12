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
 * @fileoverview Types describing the config-driven Key Metrics dashboard composition.
 */

/** Chart flavors the metrics dashboard can render, one per <datacommons-*> web component. */
export type MetricsTileType =
  | 'line'
  | 'bar'
  | 'map'
  | 'ranking'
  | 'highlight'
  | 'scatter'
  | 'pie'
  | 'gauge'
  | 'slider';

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
    | 'ascending'
    | 'descending'
    | 'ascendingPopulation'
    | 'descendingPopulation';
  colors?: string;
  unit?: string;
  min?: number;
  max?: number;
  startDate?: string;
  endDate?: string;
}

/** One dashboard tab: a labeled group of tiles. */
export interface MetricsTab {
  id: string;
  label: string;
  tiles: MetricsTile[];
}

/** Top-level metrics dashboard configuration from the theme document. */
export interface MetricsConfig {
  tabs: MetricsTab[];
}
