'use client';

import { COLORS } from '@package/tokens/ts';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { YAxisTickContentProps } from 'recharts/types/util/types';

import type { ChartDatum } from './chart';

const BAR_COLOR = `rgb(${COLORS['card-surface-selected']})`;
const GRID_COLOR = `rgb(${COLORS['card-chart-grid']})`;
const AXIS_COLOR = `rgb(${COLORS['card-content-muted']})`;

interface ChartProps {
  data: ChartDatum[];
}

const compactFormatter = new Intl.NumberFormat('en', { notation: 'compact' });
const tooltipFormatter = new Intl.NumberFormat('en', {
  maximumFractionDigits: 2,
  notation: 'standard',
});

const CustomYTick = ({ x, y, payload }: YAxisTickContentProps) => (
  <text
    x={Number(x) + 8}
    y={y}
    dx={0}
    dy={-5}
    textAnchor="start"
    fontSize={10}
    fill={AXIS_COLOR}
  >
    {compactFormatter.format(payload.value)}
  </text>
);

export const DataChartBarVertical = ({ data }: ChartProps) => {
  return (
    <ResponsiveContainer
      width="100%"
      aspect={1.78}
      style={{ paddingBottom: '28px' }}
    >
      <BarChart data={data} margin={{ top: 32, right: 0, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={GRID_COLOR} vertical={false} />
        <XAxis
          dataKey="date"
          tickLine={{ stroke: AXIS_COLOR }}
          axisLine={{ stroke: AXIS_COLOR }}
          tick={{ fontSize: 10, fill: AXIS_COLOR }}
          tickMargin={6}
          padding={{ left: 40, right: 12 }}
        />
        <YAxis width={1} tickLine={false} axisLine={false} tick={CustomYTick} />
        <Tooltip
          cursor={{ fill: GRID_COLOR, opacity: 0.4 }}
          formatter={(value) => tooltipFormatter.format(Number(value))}
        />
        <Bar dataKey="value" fill={BAR_COLOR} radius={[2, 2, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
};
