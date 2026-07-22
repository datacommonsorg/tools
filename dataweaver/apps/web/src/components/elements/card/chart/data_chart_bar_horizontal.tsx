'use client';

import { COLORS } from '@package/tokens/ts';
import { useMemo } from 'react';
import { Bar, BarChart, CartesianGrid, Tooltip, XAxis, YAxis } from 'recharts';

import { formatChartValue } from '~/functions/format_chart_value';

import type { ChartSeries } from './chart';
import { ChartContainer } from './chart_container';
import s from './chart_container.module.scss';
import { ChartLegend } from './chart_legend';
import { getSeriesColor } from './chart_palette';
import { type MergedRow, mergeSeriesData } from './merge_series_data';
import { TooltipCustom } from './tooltip_custom';

const GRID_COLOR = `rgb(${COLORS['card-chart-grid']})`;
const AXIS_COLOR = `rgb(${COLORS['card-chart-axis']})`;

const AXIS_FONT = '10px sans-serif';
const AXIS_PADDING = 12;
const MAX_Y_AXIS_RATIO = 0.35;

function measureYAxisWidth(data: MergedRow[], chartWidth: number): number {
  if (data.length === 0) return 60;
  let maxWidth = 0;
  if (typeof document !== 'undefined') {
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    if (ctx) {
      ctx.font = AXIS_FONT;
      for (const row of data) {
        const w = ctx.measureText(String(row.date)).width;
        if (w > maxWidth) maxWidth = w;
      }
    }
  } else {
    for (const row of data) {
      const w = String(row.date).length * 6;
      if (w > maxWidth) maxWidth = w;
    }
  }
  return Math.min(maxWidth + AXIS_PADDING, chartWidth * MAX_Y_AXIS_RATIO);
}

interface ChartProps {
  series: ChartSeries[];
}

export const DataChartBarHorizontal = ({ series }: ChartProps) => {
  const mergedData = mergeSeriesData(series);
  const unit = series[0]?.unit;

  return (
    <ChartContainer aspect={0.75}>
      {(width, height) => (
        <DataChartBarHorizontalInner
          data={mergedData}
          series={series}
          unit={unit}
          width={width}
          height={height}
        />
      )}
    </ChartContainer>
  );
};

interface InnerProps {
  data: MergedRow[];
  series: ChartSeries[];
  unit: string | undefined;
  width: number;
  height: number;
}

const DataChartBarHorizontalInner = ({
  data,
  series,
  unit,
  width,
  height,
}: InnerProps) => {
  const yAxisWidth = useMemo(
    () => measureYAxisWidth(data, width),
    [data, width],
  );

  return (
    <>
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
          tickFormatter={(value) => formatChartValue(Number(value), unit)}
          tickMargin={6}
        />
        <YAxis
          type="category"
          dataKey="date"
          width={yAxisWidth}
          tickLine={false}
          axisLine={{ stroke: AXIS_COLOR }}
          tick={{ fontSize: 10, fill: AXIS_COLOR }}
        />
        <Tooltip
          cursor={{ fill: GRID_COLOR, opacity: 0.4 }}
          content={<TooltipCustom series={series} unit={unit} />}
        />
        {series.map((s, i) => (
          <Bar
            key={s.key}
            dataKey={`value_${i}`}
            name={s.label}
            fill={getSeriesColor(i)}
            radius={[0, 2, 2, 0]}
          />
        ))}
      </BarChart>
      {unit && (
        <div
          className={s['axis-label-bottom']}
          style={{ paddingLeft: yAxisWidth }}
        >
          {unit}
        </div>
      )}
      {series.length > 1 && <ChartLegend series={series} />}
    </>
  );
};
