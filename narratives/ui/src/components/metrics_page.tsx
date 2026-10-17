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
 * @fileoverview Renders the Key Metrics dashboard from the instance's
 * `metrics.tabs` configuration.
 */

import { type ReactNode, useState } from 'react';
import { getInstanceConfig } from '@/src/config/instance_config';
import type { MetricsTab, MetricsTile } from '@/src/types/metrics';
import {
  API_ROOT,
  DataCommonsComponent,
  type DataCommonsComponentAttributes,
  type DataCommonsComponentTagName,
} from '@/src/utils/datacommons_component';

const FONT_DISPLAY = 'var(--font-display)';

/** Renders the Key Metrics dashboard page: heading, category tabs, and tile grid. */
export function MetricsPage() {
  const config = getInstanceConfig();
  const tabs = config.metrics.tabs;
  const [activeId, setActiveId] = useState<string>(tabs[0]?.id ?? '');
  const active = tabs.find((tab) => tab.id === activeId) ?? tabs[0];

  return (
    <div className="flex-1 overflow-y-auto px-4 lg:px-12 py-8 w-full">
      <div className="max-w-7xl mx-auto">
        <header className="mb-6">
          <h1
            style={{
              fontFamily: FONT_DISPLAY,
              fontSize: 32,
              lineHeight: '36px',
              fontWeight: 500,
              color: 'var(--color-on-surface)',
              margin: 0,
            }}
          >
            Key Metrics
          </h1>
          {tabs.length > 0 && (
            <p className="text-body-large text-subtle mt-2">
              {config.instanceName} dashboards — powered by Data Commons web
              components.
            </p>
          )}
        </header>

        {!active ? (
          <EmptyState />
        ) : (
          <>
            <SubTabs tabs={tabs} activeId={active.id} onChange={setActiveId} />

            <TilesGrid key={active.id} tiles={active.tiles} />
          </>
        )}
      </div>
    </div>
  );
}

interface SubTabsProps {
  tabs: MetricsTab[];
  activeId: string;
  onChange: (id: string) => void;
}

/** Renders the category tab strip below the page heading. */
function SubTabs({ tabs, activeId, onChange }: SubTabsProps) {
  return (
    <div
      role="tablist"
      aria-label="Metrics categories"
      className="flex gap-1 border-b border-outline mb-6"
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
                ? 'border-theme-primary text-theme-primary'
                : 'border-transparent text-on-surface-variant hover:text-on-surface'
            }`}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

interface TilesGridProps {
  tiles: MetricsTile[];
}

/** Renders the active tab's tiles in a responsive two-column grid. */
function TilesGrid({ tiles }: TilesGridProps) {
  if (tiles.length === 0) {
    return null;
  }
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

interface TileProps {
  title: string;
  children: ReactNode;
}

/** Card container around a single dashboard tile. */
function Tile({ title, children }: TileProps) {
  return (
    <section className="bg-surface rounded-card border border-outline overflow-hidden shadow-sm">
      <header className="px-5 py-3 border-b border-outline-variant">
        <h3
          style={{
            fontFamily: FONT_DISPLAY,
            fontSize: 16,
            lineHeight: '24px',
            fontWeight: 500,
            color: 'var(--color-on-surface)',
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

/** Shown when the instance configuration declares no metrics tabs. */
function EmptyState() {
  return (
    <div className="py-16 text-center">
      <h2
        className="text-display-small mb-2"
        style={{ color: 'var(--color-on-surface)' }}
      >
        No metrics configured
      </h2>
      <p className="text-body-large text-subtle">
        No dashboards are configured for this instance.
      </p>
    </div>
  );
}
