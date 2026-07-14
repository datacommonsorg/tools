/**
 * @fileoverview Renders the config-driven Key Metrics dashboard: tabs and tiles from branding.metrics.
 */

import { useState } from "react";
import { useBrand } from "../hooks/branding_context";
import type { MetricsTab, MetricsTile } from "../types/metrics";
import {
  API_ROOT,
  DataCommonsComponent,
  type DataCommonsComponentAttributes,
  type DataCommonsComponentTagName,
} from "../utils/datacommons_component";

/**
 * Key Metrics Dashboard.
 *
 * CONFIG-DRIVEN COMPOSITION: the tab+tile layout comes from
 * `branding.metrics.tabs` fetched at mount. When absent, DEFAULT_METRICS_TABS
 * below is used. This preserves the "configuration over images" property — a
 * new state instance changes its dashboards by editing branding.json in its
 * config bucket, no image rebuild needed.
 *
 * DC components are rendered via the shared <DataCommonsComponent> wrapper
 * (see utils/datacommons_component.tsx), which imperatively mounts each
 * <datacommons-*> element and sets attributes rather than JS properties —
 * working around React 19's custom-element property-setter behavior. `apiroot`
 * is the page origin, per upstream homepage.html.
 */
const FONT_DISPLAY = "var(--font-display)";

/**
 * Fallback dashboard composition when branding.metrics is absent.
 *
 * Lifted from custom-dc-setup's static/custom_dc/custom/standard_insights.html
 * (the IITM India POC dashboard) — generic global-comparison widgets that
 * resolve against any Custom DC backend's base graph without instance-specific
 * data imports. Per-instance branding.json overrides this whole structure.
 */
const DEFAULT_METRICS_TABS: MetricsTab[] = [
  {
    id: "population",
    label: "Population",
    tiles: [
      {
        type: "highlight",
        title: "World population",
        header: "World population",
        variable: "Count_Person",
        place: "Earth",
      },
      {
        type: "highlight",
        title: "USA population",
        header: "USA population",
        variable: "Count_Person",
        place: "country/USA",
      },
      {
        type: "highlight",
        title: "India population",
        header: "India population",
        variable: "Count_Person",
        place: "country/IND",
      },
      {
        type: "highlight",
        title: "China population",
        header: "China population",
        variable: "Count_Person",
        place: "country/CHN",
      },
      {
        type: "line",
        title: "Population — major economies",
        header: "Population over time",
        variables: "Count_Person",
        places: "country/USA country/IND country/CHN country/DEU country/JPN",
      },
      {
        type: "map",
        title: "US population by state",
        header: "Population distribution",
        variable: "Count_Person",
        parentPlace: "country/USA",
        childPlaceType: "State",
      },
      {
        type: "ranking",
        title: "Top countries by population",
        header: "Most populous countries",
        variable: "Count_Person",
        parentPlace: "Earth",
        childPlaceType: "Country",
        rankingCount: 10,
      },
    ],
  },
  {
    id: "economy",
    label: "Economy",
    tiles: [
      {
        type: "bar",
        title: "GDP comparison",
        header: "GDP by country (current US$)",
        variables:
          "Amount_EconomicActivity_GrossDomesticProduction_Nominal",
        places:
          "country/USA country/CHN country/JPN country/DEU country/IND country/GBR country/FRA",
        sort: "descending",
      },
      {
        type: "scatter",
        title: "GDP vs Life Expectancy",
        header: "Economic development vs health",
        variables:
          "Amount_EconomicActivity_GrossDomesticProduction_Nominal LifeExpectancy_Person",
        parentPlace: "Earth",
        childPlaceType: "Country",
      },
    ],
  },
  {
    id: "health",
    label: "Health",
    tiles: [
      {
        type: "line",
        title: "Life expectancy trends",
        header: "Life expectancy at birth",
        variables: "LifeExpectancy_Person",
        places:
          "country/USA country/JPN country/DEU country/IND country/BRA",
      },
    ],
  },
  {
    id: "environment",
    label: "Environment",
    tiles: [
      {
        type: "line",
        title: "CO2 emissions",
        header: "Annual CO2 emissions",
        variables: "Annual_Emissions_GreenhouseGas_CO2",
        places:
          "country/USA country/CHN country/IND country/RUS country/DEU",
      },
    ],
  },
];

/** Renders the Key Metrics dashboard page: heading, category tabs, and tile grid. */
export function MetricsPage() {
  const brand = useBrand();
  const tabs = brand.metrics?.tabs ?? DEFAULT_METRICS_TABS;
  const [activeId, setActiveId] = useState<string>(tabs[0]?.id ?? "");
  const active = tabs.find((tab) => tab.id === activeId) ?? tabs[0];

  return (
    <div className="flex-1 overflow-y-auto px-4 lg:px-12 py-8 w-full">
      <div className="max-w-7xl mx-auto">
        <header className="mb-6">
          <h1
            style={{
              fontFamily: FONT_DISPLAY,
              fontSize: 32,
              lineHeight: "36px",
              fontWeight: 500,
              color: "var(--color-on-surface)",
              margin: 0,
            }}
          >
            Key Metrics
          </h1>
          <p className="text-body-large text-subtle mt-2">
            {brand.metrics
              ? `${brand.instanceName ?? "Per-instance"} dashboards — `
              : "Default starter palette — "}
            powered by Data Commons web components.
          </p>
        </header>

        {!active ? (
          <EmptyState />
        ) : (
          <>
            <SubTabs
              tabs={tabs}
              activeId={active.id}
              onChange={setActiveId}
            />

            <TilesGrid tiles={active.tiles} />
          </>
        )}
      </div>
    </div>
  );
}

/** Renders the category tab strip below the page heading. */
function SubTabs({
  tabs,
  activeId,
  onChange,
}: {
  tabs: MetricsTab[];
  activeId: string;
  onChange: (id: string) => void;
}) {
  return (
    <div
      role="tablist"
      aria-label="Metrics categories"
      className="flex gap-1 border-b border-gray-200 mb-6"
    >
      {tabs.map((tab) => {
        const active = tab.id === activeId;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(tab.id)}
            className={`px-4 py-2 text-label-large border-b-2 -mb-px transition-colors cursor-pointer ${
              active
                ? "border-brand-primary text-brand-primary"
                : "border-transparent text-on-surface-variant hover:text-on-surface"
            }`}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

/** Renders the active tab's tiles in a responsive two-column grid. */
function TilesGrid({ tiles }: { tiles: MetricsTile[] }) {
  if (tiles.length === 0) return null;
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {tiles.map((tile, index) => {
        const { type, title, ...attrs } = tile;
        return (
          <Tile key={index} title={title}>
            <DataCommonsComponent
              tag={`datacommons-${type}` as DataCommonsComponentTagName}
              apiroot={API_ROOT}
              {...(attrs as DataCommonsComponentAttributes)}
            />
          </Tile>
        );
      })}
    </div>
  );
}

/** Card chrome around one dashboard tile: titled header + padded body. */
function Tile({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="bg-white rounded-[16px] border border-gray-200 overflow-hidden shadow-sm">
      <header className="px-5 py-3 border-b border-gray-100">
        <h3
          style={{
            fontFamily: FONT_DISPLAY,
            fontSize: 16,
            lineHeight: "24px",
            fontWeight: 500,
            color: "var(--color-on-surface)",
            margin: 0,
          }}
        >
          {title}
        </h3>
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

/** Shown when the branding config declares a metrics block with no tabs. */
function EmptyState() {
  return (
    <div className="py-16 text-center">
      <h2
        className="text-display-small mb-2"
        style={{ color: "var(--color-on-surface)" }}
      >
        No metrics configured
      </h2>
      <p className="text-body-large text-subtle">
        This instance's branding.json has no metrics.tabs entries.
      </p>
    </div>
  );
}
