'use client';

import { useState } from 'react';
import type { CardState } from '~/components/elements/card/base';
import { Skeleton } from '~/components/elements/skeleton';
import { IconLineGraph } from '~/components/primitives/icons/line_graph';
import { IconTable } from '~/components/primitives/icons/table';
import type { FacetInfo } from '~/server/types';
import s from './chart.module.scss';
import { ConditionalTabs } from './conditional_tabs';
import { DataChartLine } from './data_chart_line';
import { DataTable } from './data_table';
import { FacetSelector } from './facet_selector';

export interface ChartDatum {
  date: string;
  value: number;
}

// TODO: Get dynamically instead of hard coding here
const CHART_WIDTH = 356;
const CHART_HEIGHT = 200;

export interface CardChartProps extends Pick<CardState, 'isLoading'> {
  title?: string;
  description?: string;
  data?: ChartDatum[];
  facets?: FacetInfo[];
}

export const CardChart = ({
  isLoading,
  data,
  facets,
  title,
  description,
}: CardChartProps) => {
  const [selectedFacetId, setSelectedFacetId] = useState<string>(
    facets?.[0]?.facetId ?? '',
  );

  // Derive chart data from selected facet if facets are available
  const currentFacet = facets?.find((f) => f.facetId === selectedFacetId);
  const chartData = currentFacet?.observations ?? data;

  return (
    <>
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
                icon: IconLineGraph,
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
    </>
  );
};
