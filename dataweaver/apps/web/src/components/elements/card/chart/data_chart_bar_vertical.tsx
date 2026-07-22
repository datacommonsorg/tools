'use client';

import { COLORS } from '@package/tokens/ts';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Tooltip,
  usePlotArea,
  XAxis,
  YAxis,
} from 'recharts';

import { formatChartValue } from '~/functions/format_chart_value';

import type { ChartSeries } from './chart';
import { ChartContainer } from './chart_container';
import s from './chart_container.module.scss';
import { ChartLegend } from './chart_legend';
import { getSeriesColor } from './chart_palette';
import { mergeSeriesData } from './merge_series_data';
import { TooltipCustom } from './tooltip_custom';

const GRID_COLOR = `rgb(${COLORS['card-chart-grid']})`;
const AXIS_COLOR = `rgb(${COLORS['card-chart-axis']})`;

interface ChartProps {
  series: ChartSeries[];
}

const CustomCursor = (props: {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  top?: number;
}) => {
  const { x = 0, width = 0, height = 0, top = 0 } = props;
  return (
    <rect
      x={x}
      y={0}
      width={width}
      height={height + top}
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

export const DataChartBarVertical = ({ series }: ChartProps) => {
  const mergedData = mergeSeriesData(series);
  const unit = series[0]?.unit;

  return (
    <ChartContainer aspect={1.78}>
      {(width, height) => (
        <>
          <div style={{ position: 'relative' }}>
            <BarChart
              data={mergedData}
              width={width}
              height={height}
              margin={{ top: 32, right: 0, bottom: 0, left: 0 }}
            >
              <CartesianGrid
                stroke={GRID_COLOR}
                vertical={false}
                x={0}
                width={width}
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
                tickFormatter={(value) => formatChartValue(Number(value), unit)}
              />
              <FullWidthAxisLine />
              <Tooltip
                cursor={<CustomCursor />}
                content={<TooltipCustom series={series} unit={unit} />}
              />
              {series.map((s, i) => (
                <Bar
                  key={s.key}
                  dataKey={`value_${i}`}
                  name={s.label}
                  fill={getSeriesColor(i)}
                  radius={[2, 2, 0, 0]}
                />
              ))}
            </BarChart>
            {unit && <span className={s['axis-label-left']}>{unit}</span>}
          </div>
          {series.length > 1 && <ChartLegend series={series} />}
        </>
      )}
    </ChartContainer>
  );
};
