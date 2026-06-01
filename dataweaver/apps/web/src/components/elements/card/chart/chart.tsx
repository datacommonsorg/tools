'use client';

import { useState } from 'react';
import { IconLineGraph } from '~/components/primitives/icons/line_graph';
import { IconTable } from '~/components/primitives/icons/table';
import s from './chart.module.scss';
import { type ChartDatum, DataLineChart } from './data_line_chart';
import { DataTable } from './data_table';
import { type TabItem, Tabs } from './tabs';

const TABS: TabItem[] = [
  { id: 'chart', label: 'Chart', icon: IconLineGraph },
  { id: 'table', label: 'Table', icon: IconTable },
] as const;

// TODO: Get dynamically instead of hard coding here
const CHART_WIDTH = 356;
const CHART_HEIGHT = 200;

interface CardChartProps {
  title?: string;
  description?: string;
  data?: ChartDatum[];

  /**
   * Renders skeleton lines in place of the body while content loads.
   *
   * @default false
   */
  isLoading?: boolean;
}

export const CardChart = ({
  data,
  title,
  description,

  // TODO: Support loading state here
  // isLoading = false,
}: CardChartProps) => {
  const [activeTab, setActiveTab] = useState('chart');

  return (
    <>
      {(title || description) && (
        <div className={s['header-container']}>
          {title && <h2 className={s.title}>{title}</h2>}
          {description && <p className={s.description}>{description}</p>}
        </div>
      )}

      <Tabs tabs={TABS} activeTab={activeTab} onChange={setActiveTab} />

      {activeTab === 'chart' && data && (
        <DataLineChart data={data} width={CHART_WIDTH} height={CHART_HEIGHT} />
      )}

      {activeTab === 'table' && data && <DataTable data={data} />}
    </>
  );
};
