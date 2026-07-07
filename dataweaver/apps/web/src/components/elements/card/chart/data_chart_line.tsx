'use client';

import { COLORS } from '@package/tokens/ts';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  usePlotArea,
  XAxis,
  YAxis,
} from 'recharts';

import type { ChartDatum } from './chart';
import { CustomTooltip } from './custom_tooltip';

const LINE_COLOR = `rgb(${COLORS['card-surface-selected']})`;
const GRID_COLOR = `rgb(${COLORS['card-chart-grid']})`;
const AXIS_COLOR = `rgb(${COLORS['card-content-muted']})`;
const DOT_COLOR = `rgb(${COLORS['card-surface']})`;

interface ChartProps {
  data: ChartDatum[];
}

const compactFormatter = new Intl.NumberFormat(undefined, {
  notation: 'compact',
});

const CustomCursor = (props: {
  points?: { x: number; y: number }[];
  top?: number;
  height?: number;
}) => {
  const { points, top = 0 } = props;
  const point = points?.[0];
  if (!point) return null;
  const x = point.x;
  return (
    <line
      x1={x}
      y1={0}
      x2={x}
      y2={top + ((props.height ?? 0) - 1)}
      stroke={GRID_COLOR}
      strokeWidth={1}
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

export const DataChartLine = ({ data }: ChartProps) => {
  return (
    <ResponsiveContainer
      width="100%"
      aspect={1.78}
      style={{ paddingBottom: '28px' }}
    >
      <LineChart
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
          padding={{ left: 0, right: 10 }}
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
        <Line
          type="monotone"
          dataKey="value"
          stroke={LINE_COLOR}
          strokeWidth={1}
          dot={
            data.length > 15
              ? false
              : {
                  r: 3,
                  fill: DOT_COLOR,
                }
          }
          activeDot={{
            fill: LINE_COLOR,
            stroke: LINE_COLOR,
            strokeWidth: 1,
          }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
};
