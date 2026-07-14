'use client';

import { COLORS } from '@package/tokens/ts';
import { Bar, BarChart, CartesianGrid, Tooltip, XAxis, YAxis } from 'recharts';

import type { ChartDatum } from './chart';
import { ChartContainer } from './chart_container';
import { TooltipCustom } from './tooltip_custom';

const BAR_COLOR = `rgb(${COLORS['card-surface-selected']})`;
const GRID_COLOR = `rgb(${COLORS['card-chart-grid']})`;
const AXIS_COLOR = `rgb(${COLORS['card-content-muted']})`;

interface ChartProps {
  data: ChartDatum[];
}

const compactFormatter = new Intl.NumberFormat(undefined, {
  notation: 'compact',
});

export const DataChartBarHorizontal = ({ data }: ChartProps) => {
  return (
    <ChartContainer aspect={0.75}>
      {(width, height) => (
        <BarChart
          data={data}
          width={width}
          height={height}
          layout="vertical"
          margin={{ top: 32, right: 12, bottom: 0, left: 0 }}
        >
          <CartesianGrid stroke={GRID_COLOR} horizontal={false} />
          <XAxis
            type="number"
            tickLine={{ stroke: AXIS_COLOR }}
            axisLine={{ stroke: AXIS_COLOR }}
            tick={{ fontSize: 10, fill: AXIS_COLOR }}
            tickFormatter={(value) => compactFormatter.format(value)}
            tickMargin={6}
          />
          <YAxis
            type="category"
            dataKey="date"
            width={'auto'}
            tickLine={false}
            axisLine={{ stroke: AXIS_COLOR }}
            tick={{ fontSize: 10, fill: AXIS_COLOR }}
          />
          <Tooltip
            cursor={{ fill: GRID_COLOR, opacity: 0.4 }}
            content={<TooltipCustom />}
          />
          <Bar dataKey="value" fill={BAR_COLOR} radius={[0, 2, 2, 0]} />
        </BarChart>
      )}
    </ChartContainer>
  );
};
