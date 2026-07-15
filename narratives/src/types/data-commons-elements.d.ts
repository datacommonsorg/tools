/**
 * @fileoverview Declares TypeScript types for the Data Commons custom elements used in JSX.
 *
 * Type declarations for Data Commons web components loaded via
 * https://datacommons.org/datacommons.js.
 *
 * At runtime these are plain HTMLElements. We augment React's existing JSX
 * namespace so TypeScript allows the documented attribute set without
 * stripping the standard HTML elements (div/span/p/etc.).
 *
 * Attribute names mirror what the upstream VM template
 * (server/templates/custom_dc/custom/homepage.html, renderDCComponent)
 * passes to each element.
 */

import type { DetailedHTMLProps, HTMLAttributes } from "react";

/** Attributes accepted by every datacommons-* element, named after React's HTMLAttributes convention. */
interface DataCommonsAttributes
  extends DetailedHTMLProps<HTMLAttributes<HTMLElement>, HTMLElement> {
  // Common
  apiroot?: string;
  header?: string;
  date?: string;
  colors?: string;

  // Plural (line / bar / pie / scatter / etc.)
  variables?: string;
  places?: string;

  // Singular (map / ranking / gauge / highlight / slider)
  variable?: string;
  place?: string;

  // Geographic child enumeration
  parentPlace?: string;
  childPlaceType?: string;

  // Bar
  sort?: "ascending" | "descending";

  // Map / slider
  allowZoom?: boolean | "" | "true" | "false";

  // Pie
  donut?: boolean | "" | "true" | "false";

  // Ranking
  rankingCount?: string | number;
  showHighestLowest?: boolean | "" | "true" | "false";

  // Gauge
  min?: string | number;
  max?: string | number;

  // Scatter
  showPlaceLabels?: boolean | "" | "true" | "false";
}

declare module "react" {
  namespace JSX {
    interface IntrinsicElements {
      "datacommons-line":      DataCommonsAttributes;
      "datacommons-bar":       DataCommonsAttributes;
      "datacommons-pie":       DataCommonsAttributes;
      "datacommons-map":       DataCommonsAttributes;
      "datacommons-highlight": DataCommonsAttributes;
      "datacommons-ranking":   DataCommonsAttributes;
      "datacommons-gauge":     DataCommonsAttributes;
      "datacommons-scatter":   DataCommonsAttributes;
      "datacommons-slider":    DataCommonsAttributes;
    }
  }
}

export {};
