'use client';

import { AnimatePresence } from 'motion/react';
import { useRef, useState } from 'react';
import { type TLShapeId, useEditor } from 'tldraw';
import { Button } from '~/components/elements/button';
import { Card } from '~/components/elements/card';

import type { CardState } from '~/components/elements/card/base';
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
import { type ChartStyle, MenuChartOptions } from './menu_chart_options';

export interface ChartDatum {
  date: string;
  value: number;
}

export interface CardChartProps extends CardState {
  id: TLShapeId;
  title?: string;
  description?: string;

  // TODO: Atm data rendered within the card is very specific to the emissions
  // dataset. Let's make it more generic once we have real data to work with
  data?: ChartDatum[];
  facets?: FacetInfo[];
  relatedQueries?: string[];
}

export const CardChart = ({
  id,
  isLoading,
  selection,
  title,
  description,
  data,
  facets,
  relatedQueries,
}: CardChartProps) => {
  const editor = useEditor();

  const { open: openExport } = useExportActions();
  const { runPrompt } = useQueryActions();

  const baseChildrenContainerRef = useRef<HTMLDivElement>(null);
  const contentInnerRef = useRef<HTMLDivElement>(null);

  // TODO: Support the different chart styles (for now we always show bar chart)
  const [selectedStyle, setSelectedStyle] =
    useState<ChartStyle>('bar-vertical');
  const [isStyleMenuOpen, setIsStyleMenuOpen] = useState(false);
  const [activeTabIndex, setActiveTabIndex] = useState(0);
  const [selectedFacetId, setSelectedFacetId] = useState<string>(
    facets?.[0]?.facetId ?? '',
  );

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
  return (
    <Card.Base
      id={id}
      childrenContainerRef={baseChildrenContainerRef}
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

          {isLoading || !chartData ? (
            <Skeleton />
          ) : (
            <>
              {facets && facets.length > 0 && (
                <FacetSelector
                  facets={facets}
                  selectedFacetId={selectedFacetId}
                  onSelect={setSelectedFacetId}
                />
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
                        <DataChartBarVertical
                          data={chartData}
                          unit={currentFacet?.unit}
                        />
                      ) : selectedStyle === 'bar-horizontal' ? (
                        <DataChartBarHorizontal
                          data={chartData}
                          unit={currentFacet?.unit}
                        />
                      ) : (
                        <DataChartLine
                          data={chartData}
                          unit={currentFacet?.unit}
                        />
                      ),
                  },
                  {
                    icon: IconTable,
                    label: 'Table',
                    children: <DataTable data={chartData} />,
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
              setSelectedStyle(newStyle);
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
