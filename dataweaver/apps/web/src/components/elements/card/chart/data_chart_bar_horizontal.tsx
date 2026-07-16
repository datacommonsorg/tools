'use client';

import { COLORS } from '@package/tokens/ts';
import { Bar, BarChart, CartesianGrid, Tooltip, XAxis, YAxis } from 'recharts';

import type { ChartSeries } from './chart';
import { ChartContainer } from './chart_container';
import { ChartLegend } from './chart_legend';
import { getSeriesColor } from './chart_palette';
import { mergeSeriesData } from './merge_series_data';
import { TooltipCustom } from './tooltip_custom';

const GRID_COLOR = `rgb(${COLORS['card-chart-grid']})`;
const AXIS_COLOR = `rgb(${COLORS['card-chart-axis']})`;

interface ChartProps {
  series: ChartSeries[];
}

const compactFormatter = new Intl.NumberFormat(undefined, {
  notation: 'compact',
});

export const DataChartBarHorizontal = ({ series }: ChartProps) => {
  const mergedData = mergeSeriesData(series);

  return (
    <ChartContainer aspect={0.75}>
      {(width, height) => (
        <>
          <BarChart
            data={mergedData}
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
              content={<TooltipCustom series={series} />}
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
          {series.length > 1 && <ChartLegend series={series} />}
        </>
      )}
    </ChartContainer>
  );
};
