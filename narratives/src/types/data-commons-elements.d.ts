// Type declarations for Data Commons web components loaded via
// https://datacommons.org/datacommons.js.
//
// At runtime these are plain HTMLElements. We augment React's existing JSX
// namespace so TypeScript allows the documented attribute set without
// stripping the standard HTML elements (div/span/p/etc.).
//
// Attribute names mirror what the upstream VM template
// (server/templates/custom_dc/custom/homepage.html, renderDCComponent)
// passes to each element.

import type { DetailedHTMLProps, HTMLAttributes } from "react";

type DCAttrs = DetailedHTMLProps<HTMLAttributes<HTMLElement>, HTMLElement> & {
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
};

declare module "react" {
  namespace JSX {
    interface IntrinsicElements {
      "datacommons-line":      DCAttrs;
      "datacommons-bar":       DCAttrs;
      "datacommons-pie":       DCAttrs;
      "datacommons-map":       DCAttrs;
      "datacommons-highlight": DCAttrs;
      "datacommons-ranking":   DCAttrs;
      "datacommons-gauge":     DCAttrs;
      "datacommons-scatter":   DCAttrs;
      "datacommons-slider":    DCAttrs;
    }
  }
}

export {};
