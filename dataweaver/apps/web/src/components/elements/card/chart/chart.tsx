'use client';

import { AnimatePresence } from 'motion/react';
import { useState } from 'react';
import { type TLShapeId, useEditor } from 'tldraw';
import { Button } from '~/components/elements/button';
import { Card } from '~/components/elements/card';

import type { CardState } from '~/components/elements/card/base';
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
import { DataChartLine } from './data_chart_line';
import { DataTable } from './data_table';
import { FacetSelector } from './facet_selector';
import { type ChartStyle, MenuChartOptions } from './menu_chart_options';

export interface ChartDatum {
  date: string;
  value: number;
}

// TODO: Get dynamically instead of hard coding here
const CHART_WIDTH = 356;
const CHART_HEIGHT = 200;

export interface CardChartProps extends CardState {
  id: TLShapeId;
  title?: string;
  description?: string;

  // TODO: Atm data rendered within the card is very specific to the emissions
  // dataset. Let's make it more generic once we have real data to work with
  data?: ChartDatum[];
  facets?: FacetInfo[];
  relatedQuery?: string;
}

export const CardChart = ({
  id,
  isLoading,
  selection,
  title,
  description,
  data,
  facets,
  relatedQuery,
}: CardChartProps) => {
  const editor = useEditor();

  const { open: openExport } = useExportActions();
  const { runPrompt } = useQueryActions();

  // TODO: Support the different chart styles (for now we always show bar chart)
  const [selectedStyle, setSelectedStyle] =
    useState<ChartStyle>('bar-vertical');
  const [isStyleMenuOpen, setIsStyleMenuOpen] = useState(false);
  const [selectedFacetId, setSelectedFacetId] = useState<string>(
    facets?.[0]?.facetId ?? '',
  );

  // Derive chart data from selected facet if facets are available
  const currentFacet = facets?.find((f) => f.facetId === selectedFacetId);
  const chartData = currentFacet?.observations ?? data;

  return (
    <Card.Base
      id={id}
      variant="chart"
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
      <div className={s.container}>
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
              tabs={[
                {
                  icon: IconLineGraphSingle,
                  label: 'Chart',
                  children: (
                    <DataChartLine
                      data={chartData}
                      width={CHART_WIDTH}
                      height={CHART_HEIGHT}
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
      </div>

      {relatedQuery && !isLoading && (
        <Card.Footer>
          <Button
            size="small"
            variant="flat"
            tone="accent-subtle"
            icon={IconPencil}
            onPointerDown={(event) => event.stopPropagation()}
            onClick={() => runPrompt(relatedQuery)}
          >
            {relatedQuery}
          </Button>
        </Card.Footer>
      )}

      <AnimatePresence>
        {isStyleMenuOpen && (
          <MenuChartOptions
            value={selectedStyle}
            onConfirmSelectionChange={(newStyle) => {
              setSelectedStyle(newStyle);
              setIsStyleMenuOpen(false);
            }}
            onClose={() => setIsStyleMenuOpen(false)}
          />
        )}
      </AnimatePresence>
    </Card.Base>
  );
};
