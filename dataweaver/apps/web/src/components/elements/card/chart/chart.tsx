'use client';

import { AnimatePresence } from 'motion/react';
import { useMemo, useRef, useState } from 'react';
import { type TLShapeId, useEditor } from 'tldraw';
import { Button } from '~/components/elements/button';
import { Card } from '~/components/elements/card';

import type { CardState } from '~/components/elements/card/base';
import baseStyles from '~/components/elements/card/base.module.scss';
import { useCardAutoHeight } from '~/components/elements/card/use_card_auto_height';
import { Skeleton } from '~/components/elements/skeleton';
import { IconBarChartOutlined } from '~/components/primitives/icons/bar_chart_outlined';
import { IconDelete } from '~/components/primitives/icons/delete';
import { IconExport } from '~/components/primitives/icons/export';
import { IconLineGraphSingle } from '~/components/primitives/icons/line_graph_single';
import { IconPencil } from '~/components/primitives/icons/pencil';
import { IconTable } from '~/components/primitives/icons/table';
import { useExportActions } from '~/components/scopes/atlas/export_provider';
import { useQueryActions } from '~/components/scopes/atlas/query_provider';
import type { FacetInfo } from '~/server/types';
import s from './chart.module.scss';
import { ConditionalTabs } from './conditional_tabs';
import { DataChartBarHorizontal } from './data_chart_bar_horizontal';
import { DataChartBarVertical } from './data_chart_bar_vertical';
import { DataChartLine } from './data_chart_line';
import { DataTable } from './data_table';
import { FacetSelector } from './facet_selector';
import { generateTestSeries } from './generate_test_series';
import { type ChartStyle, MenuChartOptions } from './menu_chart_options';

// Toggle to true to inject dummy multi-series data for dev testing.
const USE_TEST_DATA = false;

export interface ChartDatum {
  date: string;
  value: number;
}

export interface ChartSeries {
  key: string;
  label: string;
  data: ChartDatum[];
  connectNulls?: boolean;
  unit?: string;
}

export interface CardChartProps extends CardState {
  id: TLShapeId;
  title?: string;
  description?: string;

  // Legacy single-series prop (backwards-compatible shorthand).
  data?: ChartDatum[];
  // Multi-series prop — takes priority over `data` when provided.
  series?: ChartSeries[];
  facets?: FacetInfo[];
  /** Per-series facets, keyed by series `key` (e.g. placeDcid). */
  seriesFacets?: Record<string, FacetInfo[]>;
  relatedQueries?: string[];
}

export const CardChart = ({
  id,
  isLoading,
  selection,
  title,
  description,
  data,
  series: seriesProp,
  facets,
  seriesFacets,
  relatedQueries,
}: CardChartProps) => {
  const editor = useEditor();

  const { open: openExport } = useExportActions();
  const { runPrompt } = useQueryActions();

  const baseChildrenContainerRef = useRef<HTMLDivElement>(null);
  const contentInnerRef = useRef<HTMLDivElement>(null);

  const [selectedStyleOverride, setSelectedStyleOverride] = useState<
    ChartStyle | undefined
  >(undefined);
  const [isStyleMenuOpen, setIsStyleMenuOpen] = useState(false);
  const [activeTabIndex, setActiveTabIndex] = useState(0);
  const [selectedFacetId, setSelectedFacetId] = useState<string>(
    facets?.[0]?.facetId ?? '',
  );

  // Per-series facet selections for multi-dataset charts.
  const [selectedSeriesFacetIds, setSelectedSeriesFacetIds] = useState<
    Record<string, string>
  >(() => {
    if (!seriesFacets) return {};
    const initial: Record<string, string> = {};
    for (const [key, facetList] of Object.entries(seriesFacets)) {
      const firstFacet = facetList[0];
      if (firstFacet) {
        initial[key] = firstFacet.facetId;
      }
    }
    return initial;
  });

  // Only auto-height when the chart tab is active — table tab should scroll
  // within the card at its current (chart-determined) height.
  useCardAutoHeight(
    id,
    baseChildrenContainerRef,
    contentInnerRef,
    Infinity,
    activeTabIndex === 0,
  );

  // Derive chart data from selected facet if facets are available
  const currentFacet = facets?.find((f) => f.facetId === selectedFacetId);
  const chartData = currentFacet?.observations ?? data;

  // Normalize to multi-series: explicit `series` prop takes priority,
  // otherwise wrap legacy single-series `chartData` into a one-element
  // array.
  const baseSeries: ChartSeries[] | undefined = useMemo(() => {
    if (seriesProp && seriesFacets) {
      // Apply per-series facet selections to override series data.
      return seriesProp.map((entry) => {
        const facetList = seriesFacets[entry.key];
        const selectedId = selectedSeriesFacetIds[entry.key];
        if (!facetList || !selectedId) return entry;
        const facet = facetList.find((f) => f.facetId === selectedId);
        if (!facet) return entry;
        return { ...entry, data: facet.observations, unit: facet.unit };
      });
    }
    return (
      seriesProp ??
      (chartData
        ? [
            {
              key: 'default',
              label: title ?? 'Value',
              data: chartData,
              unit: currentFacet?.unit,
            },
          ]
        : undefined)
    );
  }, [
    seriesProp,
    seriesFacets,
    selectedSeriesFacetIds,
    chartData,
    title,
    currentFacet?.unit,
  ]);

  // Dev-only: augment with random dummy series to test multi-series rendering.
  const chartSeries = USE_TEST_DATA
    ? generateTestSeries(baseSeries, { count: 3, mode: 'places' })
    : baseSeries;

  // Default to line chart when data has many points; allow manual override.
  const totalPoints = chartSeries
    ? chartSeries.reduce((sum, s) => sum + s.data.length, 0)
    : 0;
  const defaultStyle: ChartStyle = totalPoints > 15 ? 'line' : 'bar-vertical';
  const selectedStyle = selectedStyleOverride ?? defaultStyle;
  return (
    <Card.Base
      id={id}
      childrenContainerRef={baseChildrenContainerRef}
      childrenClassName={baseStyles['allow-overflow']}
      isLoading={isLoading}
      selection={selection}
      actions={[
        {
          icon: IconBarChartOutlined,
          label: 'Chart options',
          isDisabled: isLoading,
          isActive: isStyleMenuOpen,
          onClick: () => setIsStyleMenuOpen((isOpen) => !isOpen),
        },
        {
          icon: IconExport,
          label: 'Export',
          isDisabled: isLoading,
          onClick: () => {
            editor.select(id);
            openExport();
          },
        },
        {
          icon: IconDelete,
          label: 'Delete',
          onClick: () => editor.deleteShapes([id]),
        },
      ]}
    >
      <div className={s['content-outer']}>
        <div ref={contentInnerRef} className={s['content-inner']}>
          {(title || description) && (
            <div className={s['header-container']}>
              {title && <h2 className={s.title}>{title}</h2>}
              {description && <p className={s.description}>{description}</p>}
            </div>
          )}

          {isLoading || !chartSeries ? (
            <Skeleton />
          ) : (
            <>
              {facets && facets.length > 0 && (
                <div className={s['facet-selectors-container']}>
                  <FacetSelector
                    facets={facets}
                    selectedFacetId={selectedFacetId}
                    onSelect={setSelectedFacetId}
                  />
                </div>
              )}

              {seriesFacets && seriesProp && (
                <div className={s['facet-selectors-container']}>
                  {seriesProp.map((entry) => {
                    const facetList = seriesFacets[entry.key];
                    if (!facetList || facetList.length === 0) {
                      return null;
                    }
                    return (
                      <FacetSelector
                        key={entry.key}
                        facets={facetList}
                        selectedFacetId={
                          selectedSeriesFacetIds[entry.key] ??
                          facetList[0]?.facetId ??
                          ''
                        }
                        onSelect={(facetId) =>
                          setSelectedSeriesFacetIds((prev) => ({
                            ...prev,
                            [entry.key]: facetId,
                          }))
                        }
                        label={entry.label}
                      />
                    );
                  })}
                </div>
              )}

              <ConditionalTabs
                activeIndex={activeTabIndex}
                onActiveIndexChange={setActiveTabIndex}
                tabs={[
                  {
                    icon: IconLineGraphSingle,
                    label: 'Chart',
                    children:
                      selectedStyle === 'bar-vertical' ? (
                        <DataChartBarVertical series={chartSeries} />
                      ) : selectedStyle === 'bar-horizontal' ? (
                        <DataChartBarHorizontal series={chartSeries} />
                      ) : (
                        <DataChartLine series={chartSeries} />
                      ),
                  },
                  {
                    icon: IconTable,
                    label: 'Table',
                    children: <DataTable series={chartSeries} />,
                  },
                ]}
              />
            </>
          )}

          {relatedQueries && relatedQueries.length > 0 && !isLoading && (
            <Card.Footer>
              {relatedQueries.map((query) => (
                <Button
                  key={query}
                  size="small"
                  variant="flat"
                  tone="accent-subtle"
                  icon={IconPencil}
                  onPointerDown={(event) => event.stopPropagation()}
                  onClick={() => runPrompt(query)}
                >
                  {query}
                </Button>
              ))}
            </Card.Footer>
          )}
        </div>
      </div>

      <AnimatePresence>
        {isStyleMenuOpen && (
          <MenuChartOptions
            value={selectedStyle}
            onConfirmSelectionChange={(newStyle) => {
              setSelectedStyleOverride(newStyle);
              setIsStyleMenuOpen(false);
              editor.updateShape({
                id,
                type: 'card',
                props: { isManuallyResized: false },
              });
            }}
            onClose={() => setIsStyleMenuOpen(false)}
          />
        )}
      </AnimatePresence>
    </Card.Base>
  );
};
