'use client';

import { COLORS } from '@package/tokens/ts';
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from 'recharts';
import type { ChartDatum } from './chart';

const LINE_COLOR = `rgb(${COLORS['card-surface-selected']})`;
const GRID_COLOR = `rgb(${COLORS['card-chart-grid']})`;
const AXIS_COLOR = `rgb(${COLORS['card-content-muted']})`;

interface ChartProps {
  data: ChartDatum[];
  width: number;
  height: number;
}

const compactFormatter = new Intl.NumberFormat('en', { notation: 'compact' });

export const DataChartLine = ({ data, width, height }: ChartProps) => {
  return (
    <LineChart
      width={width}
      height={height}
      data={data}
      margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
    >
      <CartesianGrid stroke={GRID_COLOR} vertical={false} />
      <XAxis
        dataKey="date"
        tickLine={false}
        axisLine={false}
        tick={{ fontSize: 10, fill: AXIS_COLOR }}
      />
      <YAxis
        width={36}
        tickLine={false}
        axisLine={false}
        tick={{ fontSize: 10, fill: AXIS_COLOR }}
        tickFormatter={(v) => compactFormatter.format(v)}
      />
      <Line
        type="monotone"
        dataKey="value"
        stroke={LINE_COLOR}
        strokeWidth={2}
        dot={false}
      />
    </LineChart>
  );
};
