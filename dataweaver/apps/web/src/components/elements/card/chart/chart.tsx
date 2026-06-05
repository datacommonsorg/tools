'use client';

import type { CardState } from '~/components/elements/card/base';
import { Skeleton } from '~/components/elements/skeleton';
import { IconLineGraph } from '~/components/primitives/icons/line_graph';
import { IconTable } from '~/components/primitives/icons/table';
import s from './chart.module.scss';
import { ConditionalTabs } from './conditional_tabs';
import { type ChartDatum, DataChartLine } from './data_chart_line';
import { DataTable } from './data_table';

// TODO: Get dynamically instead of hard coding here
const CHART_WIDTH = 356;
const CHART_HEIGHT = 200;

interface CardChartProps extends Pick<CardState, 'isLoading'> {
  title?: string;
  description?: string;

  // TODO: Atm data rendered within the card is very specific to the emissions
  // dataset. Let's make it more generic once we have real data to work with
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
