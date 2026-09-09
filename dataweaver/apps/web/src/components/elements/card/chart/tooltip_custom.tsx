import { formatChartValue } from '~/functions/format_chart_value';

import type { ChartSeries } from './chart';
import { getSeriesColor } from './palette';
import s from './tooltip_custom.module.scss';

interface TooltipEntry {
  value: number | null;
  dataKey?: string;
  name?: string;
  color?: string;
}

interface TooltipCustomProps {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: string;
  series?: ChartSeries[];
  unit?: string;
}

export const TooltipCustom = ({
  active,
  payload,
  label,
  series,
  unit,
}: TooltipCustomProps) => {
  if (!active || !payload || payload.length === 0) return null;

  const isMulti = series && series.length > 1;

  return (
    <div className={s.tooltip}>
      {payload.map((entry, index) => {
        const currentSeries =
          (entry.name && series?.find((s) => s.label === entry.name)) ||
          series?.[index];
        const seriesIndex =
          currentSeries && series ? series.indexOf(currentSeries) : index;
        const seriesName = entry.name || currentSeries?.label;
        const color = isMulti ? getSeriesColor(seriesIndex) : entry.color;
        const entryUnit = currentSeries?.unit ?? unit;
        const isValueValid =
          entry.value !== null &&
          entry.value !== undefined &&
          !Number.isNaN(Number(entry.value));

        return (
          <div key={entry.dataKey ?? index} className={s.entry}>
            {isMulti && color && (
              <span className={s.swatch} style={{ backgroundColor: color }} />
            )}
            {isMulti && seriesName && (
              <span className={s.name}>{seriesName}</span>
            )}
            <span className={s.value}>
              {isValueValid
                ? formatChartValue(Number(entry.value), entryUnit, 'standard')
                : '—'}
            </span>
          </div>
        );
      })}
      {label && <p className={s.label}>in {`${label}`}</p>}
    </div>
  );
};
