'use client';

import { COLORS } from '@package/tokens/ts';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  usePlotArea,
  XAxis,
  YAxis,
} from 'recharts';

import type { ChartDatum } from './chart';
import { CustomTooltip } from './custom_tooltip';

const BAR_COLOR = `rgb(${COLORS['card-surface-selected']})`;
const GRID_COLOR = `rgb(${COLORS['card-chart-grid']})`;
const AXIS_COLOR = `rgb(${COLORS['card-content-muted']})`;

interface ChartProps {
  data: ChartDatum[];
}

const compactFormatter = new Intl.NumberFormat('en', { notation: 'compact' });

const CustomCursor = (props: {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
}) => {
  const { x = 0, width = 0, height = 0 } = props;
  return (
    <rect
      x={x}
      y={0}
      width={width}
      height={height}
      fill={GRID_COLOR}
      opacity={0.4}
    />
  );
};

const FullWidthAxisLine = () => {
  const plotArea = usePlotArea();
  if (!plotArea) return null;
  const y = plotArea.y + plotArea.height;
  return (
    <line
      x1={0}
      y1={y}
      x2={plotArea.x + plotArea.width}
      y2={y}
      stroke={AXIS_COLOR}
      strokeWidth={1}
    />
  );
};

export const DataChartBarVertical = ({ data }: ChartProps) => {
  return (
    <ResponsiveContainer
      width="100%"
      aspect={1.78}
      style={{ paddingBottom: '28px' }}
    >
      <BarChart
        data={data}
        margin={{ top: 32, right: 0, bottom: 0, left: 0 }}
        style={{ overflow: 'hidden' }}
      >
        <CartesianGrid
          stroke={GRID_COLOR}
          vertical={false}
          x={0}
          width={9999}
        />
        <XAxis
          dataKey="date"
          tickLine={{ stroke: AXIS_COLOR }}
          axisLine={false}
          tick={{ fontSize: 10, fill: AXIS_COLOR }}
          tickMargin={6}
          padding={{ left: 0, right: 4 }}
        />
        <YAxis
          width="auto"
          tickLine={false}
          axisLine={false}
          tick={{ fontSize: 10, dy: -7, textAnchor: 'end' }}
          tickFormatter={(value) => compactFormatter.format(Number(value))}
        />
        <FullWidthAxisLine />
        <Tooltip cursor={<CustomCursor />} content={<CustomTooltip />} />
        <Bar dataKey="value" fill={BAR_COLOR} radius={[2, 2, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
};
