'use client';

import { COLORS } from '@package/tokens/ts';
import { useMemo } from 'react';
import { Bar, BarChart, CartesianGrid, Tooltip, XAxis, YAxis } from 'recharts';

import { formatChartValue } from '~/functions/format_chart_value';

import type { ChartSeries } from './chart';
import { ChartContainer } from './chart_container';
import s from './chart_container.module.scss';
import { ChartLegend } from './legend';
import { measureAxisWidth } from './measure_axis_width';
import { type MergedRow, mergeSeriesData } from './merge_series_data';
import { getSeriesColor } from './palette';
import { TooltipCustom } from './tooltip_custom';

const GRID_COLOR = `rgb(${COLORS['card-chart-grid']})`;
const AXIS_COLOR = `rgb(${COLORS['card-chart-axis']})`;

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
    () => measureAxisWidth(data.map((row) => String(row.date))),
    [data],
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
        {series.map((entry, i) => (
          <Bar
            key={entry.key}
            dataKey={`value_${i}`}
            name={entry.label}
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
