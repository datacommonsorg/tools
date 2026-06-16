'use client';

import type { CardState } from '~/components/elements/card/base';
import { Skeleton } from '~/components/elements/skeleton';
import { IconLineGraph } from '~/components/primitives/icons/line_graph';
import { IconTable } from '~/components/primitives/icons/table';
import s from './chart.module.scss';
import { ConditionalTabs } from './conditional_tabs';
import { DataChartLine } from './data_chart_line';
import { DataTable } from './data_table';

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
}

export const CardChart = ({
  isLoading,
  data,
  title,
  description,
}: CardChartProps) => {
  return (
    <>
      {(title || description) && (
        <div className={s['header-container']}>
          {title && <h2 className={s.title}>{title}</h2>}
          {description && <p className={s.description}>{description}</p>}
        </div>
      )}

      {isLoading || !data ? (
        <Skeleton />
      ) : (
        <ConditionalTabs
          tabs={[
            {
              icon: IconLineGraph,
              label: 'Chart',
              children: (
                <DataChartLine
                  data={data}
                  width={CHART_WIDTH}
                  height={CHART_HEIGHT}
                />
              ),
            },
            {
              icon: IconTable,
              label: 'Table',
              children: <DataTable data={data} />,
            },
          ]}
        />
      )}
    </>
  );
};
