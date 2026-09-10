import type { ChartSeries } from './chart';
import { getSeriesColor } from './palette';
import { Tooltip, TooltipContent, type TooltipContentItem } from './tooltip';

export interface TooltipRechartsProps {
  active?: boolean;
  payload?: Array<{
    value: number | null;
    dataKey?: string;
    name?: string;
    color?: string;
  }>;
  label?: string;
  series?: ChartSeries[];
  unit?: string;
}

/**
 * Recharts adapter component.
 * Maps Recharts payload to clean TooltipContent items inside the universal Tooltip shell.
 */
export const TooltipRecharts = ({
  active,
  payload,
  label,
  series,
  unit,
}: TooltipRechartsProps) => {
  if (!active || !payload || payload.length === 0) return null;

  const isMulti = series && series.length > 1;
  const items: TooltipContentItem[] = payload.map((entry, index) => {
    const currentSeries =
      (entry.name && series?.find((item) => item.label === entry.name)) ||
      series?.[index];
    const seriesIndex =
      currentSeries && series ? series.indexOf(currentSeries) : index;
    const seriesName = entry.name || currentSeries?.label;
    const color = isMulti ? getSeriesColor(seriesIndex) : entry.color;
    const entryUnit = currentSeries?.unit ?? unit;

    return {
      name: isMulti ? seriesName : undefined,
      value: entry.value,
      color,
      unit: entryUnit,
    };
  });

  return (
    <Tooltip>
      <TooltipContent
        items={items}
        subtitle={label ? `in ${label}` : undefined}
      />
    </Tooltip>
  );
};
