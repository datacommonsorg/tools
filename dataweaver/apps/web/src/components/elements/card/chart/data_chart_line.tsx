'use client';

import { COLORS } from '@package/tokens/ts';
import {
  CartesianGrid,
  Line,
  LineChart,
  Tooltip,
  usePlotArea,
  XAxis,
  YAxis,
} from 'recharts';

import type { ChartSeries } from './chart';
import { ChartContainer } from './chart_container';
import { ChartLegend } from './chart_legend';
import { getSeriesColor } from './chart_palette';
import {
  detectAxisAssignment,
  type MergedRow,
  mergeSeriesData,
} from './merge_series_data';
import { TooltipCustom } from './tooltip_custom';

const GRID_COLOR = `rgb(${COLORS['card-chart-grid']})`;
const AXIS_COLOR = `rgb(${COLORS['card-chart-axis']})`;
const AXIS_SECONDARY_COLOR = `rgb(${COLORS['card-chart-axis-secondary']})`;
const DOT_COLOR = `rgb(${COLORS['card-surface']})`;

interface ChartProps {
  series: ChartSeries[];
}

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

const compactFormatter = new Intl.NumberFormat(undefined, {
  notation: 'compact',
});

export const DataChartLine = ({ series }: ChartProps) => {
  const mergedData: MergedRow[] = mergeSeriesData(series);
  const axisAssignment = detectAxisAssignment(series);
  const hasRightAxis = axisAssignment.includes('right');
  const totalPoints = series.reduce((sum, s) => sum + s.data.length, 0);

  return (
    <ChartContainer aspect={1.78}>
      {(width, height) => (
        <>
          <LineChart
            data={mergedData}
            width={width}
            height={height}
            margin={{
              top: 32,
              right: hasRightAxis ? 8 : 0,
              bottom: 0,
              left: 0,
            }}
            }}
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
              yAxisId="left"
              width="auto"
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 10, dy: -7, textAnchor: 'end' }}
              tickFormatter={(value) => compactFormatter.format(Number(value))}
            />
            {hasRightAxis && (
              <YAxis
                yAxisId="right"
                orientation="right"
                width="auto"
                tickLine={false}
                axisLine={false}
                tick={{
                  fontSize: 10,
                  dy: -7,
                  fill: AXIS_SECONDARY_COLOR,
                  textAnchor: 'start',
                }}
                tickFormatter={(value) =>
                  compactFormatter.format(Number(value))
                }
              />
            )}
            <FullWidthAxisLine />
            <Tooltip
              cursor={<CustomCursor />}
              content={<TooltipCustom series={series} />}
            />
            {series.map((s, i) => {
              const color = getSeriesColor(i);
              return (
                <Line
                  key={s.key}
                  type="monotone"
                  dataKey={`value_${i}`}
                  yAxisId={axisAssignment[i]}
                  name={s.label}
                  stroke={color}
                  strokeWidth={1}
                  connectNulls={s.connectNulls ?? false}
                  dot={
                    totalPoints / series.length > 15
                      ? false
                      : { r: 3, fill: DOT_COLOR }
                  }
                  activeDot={{
                    fill: color,
                    stroke: color,
                    strokeWidth: 1,
                  }}
                />
              );
            })}
          </LineChart>
          {series.length > 1 && <ChartLegend series={series} />}
        </>
      )}
    </ChartContainer>
  );
};
