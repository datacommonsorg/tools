'use client';

import { AnimatePresence } from 'motion/react';
import { useMemo, useRef, useState } from 'react';
import { type TLShapeId, useEditor } from 'tldraw';
import { Button } from '~/components/elements/button';
import { CardBase, type CardState } from '~/components/elements/card/base';
import { CardFooter } from '~/components/elements/card/footer';
import { useCardAutoHeight } from '~/components/elements/card/use_card_auto_height';
import { Skeleton } from '~/components/elements/skeleton';
import { IconBarChartOutlined } from '~/components/primitives/icons/bar_chart_outlined';
import { IconDelete } from '~/components/primitives/icons/delete';
import { IconExport } from '~/components/primitives/icons/export';
import { IconLineGraphSingle } from '~/components/primitives/icons/line_graph_single';
import { IconTable } from '~/components/primitives/icons/table';
import { useExportActions } from '~/components/scopes/atlas/export_provider';
import { useQueryActions } from '~/components/scopes/atlas/query_provider';
import type { ChartStyle, FacetInfo } from '~/server/types';
import { useAtlasStore } from '~/store';
import s from './chart.module.scss';
import { extractValidEntityKeys, resolveChartStyle } from './chart_style';
import { ConditionalTabs } from './conditional_tabs';
import { DataChartBarHorizontal } from './data_chart_bar_horizontal';
import { DataChartBarVertical } from './data_chart_bar_vertical';
import { DataChartChoropleth } from './data_chart_choropleth';
import { DataChartLine } from './data_chart_line';
import { DataTable } from './data_table';
import { FacetSelector } from './facet_selector';
import { MenuChartOptions } from './menu_chart_options';
import { useGeoAvailability } from './use_geo_availability';

export interface ChartDatum {
  date: string;
  value: number;
}

export interface ChartSeries {
  key: string;
  label: string;
  data: ChartDatum[];
  facets?: FacetInfo[];
  connectNulls?: boolean;
  unit?: string;
}

export interface CardChartProps extends CardState {
  id: TLShapeId;
  title?: string;
  description?: string;

  series?: ChartSeries[];
  parentPlaceDcid?: string;
  relatedQueries?: string[];
  /** Persisted chart style from the store (survives export/import). */
  chartStyle?: ChartStyle;
}

export const CardChart = ({
  id,
  isLoading,
  selection,
  title,
  description,
  series: seriesProp,
  parentPlaceDcid,
  relatedQueries,
  chartStyle,
}: CardChartProps) => {
  const editor = useEditor();

  const { open: openExport } = useExportActions();
  const { runPrompt } = useQueryActions();
  const cardSetChartStyle = useAtlasStore((s) => s.cardSetChartStyle);
  const cardRegisterChart = useAtlasStore((s) => s.cardRegisterChart);

  const baseChildrenContainerRef = useRef<HTMLDivElement>(null);
  const contentInnerRef = useRef<HTMLDivElement>(null);

  const [selectedStyleOverride, setSelectedStyleOverride] = useState<
    ChartStyle | undefined
  >(undefined);
  const [isStyleMenuOpen, setIsStyleMenuOpen] = useState(false);
  const [activeTabIndex, setActiveTabIndex] = useState(0);
  const [selectedFacetIds, setSelectedFacetIds] = useState<
    Record<string, string>
  >({});

  // Only auto-height when the chart tab is active — table tab should scroll
  // within the card at its current (chart-determined) height.
  useCardAutoHeight(
    id,
    baseChildrenContainerRef,
    contentInnerRef,
    Infinity,
    activeTabIndex === 0,
  );

  const chartSeries: ChartSeries[] | undefined = useMemo(() => {
    if (!seriesProp) return undefined;

    return seriesProp.map((entry) => {
      const activeFacet =
        entry.facets?.find((f) => f.facetId === selectedFacetIds[entry.key]) ??
        entry.facets?.[0];
      if (!activeFacet || !entry.facets) return entry;
      return {
        ...entry,
        data: activeFacet.observations,
        unit: activeFacet.unit ?? entry.unit,
      };
    });
  }, [seriesProp, selectedFacetIds]);

  const validEntityKeys = useMemo(
    () => extractValidEntityKeys(chartSeries),
    [chartSeries],
  );

  const [isGeoAvailable, setIsGeoAvailable] = useGeoAvailability(
    parentPlaceDcid,
    validEntityKeys,
  );

  const totalPoints = useMemo(
    () =>
      chartSeries
        ? chartSeries.reduce((sum, entry) => sum + entry.data.length, 0)
        : 0,
    [chartSeries],
  );

  const selectedStyle = resolveChartStyle({
    chartStyle,
    selectedStyleOverride,
    validEntityCount: validEntityKeys.length,
    isGeoAvailable,
    totalPoints,
  });
  return (
    <CardBase
      id={id}
      childrenContainerRef={baseChildrenContainerRef}
      allowOverflow
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
              {seriesProp &&
                seriesProp.some((s) => s.facets && s.facets.length > 0) && (
                  <div className={s['facet-selectors-container']}>
                    {seriesProp.map((entry) => {
                      if (!entry.facets || entry.facets.length === 0) {
                        return null;
                      }
                      const activeFacet =
                        entry.facets.find(
                          (f) => f.facetId === selectedFacetIds[entry.key],
                        ) ?? entry.facets[0];
                      return (
                        <FacetSelector
                          key={entry.key}
                          facets={entry.facets}
                          selectedFacetId={activeFacet?.facetId ?? ''}
                          onSelect={(facetId) =>
                            setSelectedFacetIds((prev) => ({
                              ...prev,
                              [entry.key]: facetId,
                            }))
                          }
                          label={
                            seriesProp.length > 1 ? entry.label : undefined
                          }
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
                      ) : selectedStyle === 'choropleth' ? (
                        <DataChartChoropleth
                          series={chartSeries}
                          parentPlaceDcid={parentPlaceDcid}
                          onUnavailable={() => setIsGeoAvailable(false)}
                          onEntityClick={(placeDcid) =>
                            cardRegisterChart(id, placeDcid)
                          }
                        />
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
            <CardFooter title="Suggested follow-up questions">
              {relatedQueries.map((query) => (
                <Button
                  key={query}
                  size="small"
                  variant="flat"
                  tone="accent-subtle"
                  onPointerDown={(event) => event.stopPropagation()}
                  onClick={() => runPrompt(query)}
                >
                  {query}
                </Button>
              ))}
            </CardFooter>
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
              cardSetChartStyle(id, newStyle);
              editor.updateShape({
                id,
                type: 'card',
                props: { chartStyle: newStyle, isManuallyResized: false },
              });
            }}
            onClose={() => setIsStyleMenuOpen(false)}
          />
        )}
      </AnimatePresence>
    </CardBase>
  );
};
