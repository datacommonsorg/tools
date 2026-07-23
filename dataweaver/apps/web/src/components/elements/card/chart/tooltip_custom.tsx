import { formatChartValue } from '~/functions/format_chart_value';

import type { ChartSeries } from './chart';
import { getSeriesColor } from './palette';
import styles from './tooltip_custom.module.scss';

interface TooltipEntry {
  value: number;
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
    <div className={styles.tooltip}>
      {payload.map((entry, index) => {
        const color = isMulti ? getSeriesColor(index) : entry.color;
        const entryUnit = series?.[index]?.unit ?? unit;
        return (
          <div key={entry.dataKey ?? index} className={styles.entry}>
            {isMulti && color && (
              <span
                className={styles.swatch}
                style={{ backgroundColor: color }}
              />
            )}
            <span className={styles.value}>
              {entry.value !== null && entry.value !== undefined
                ? formatChartValue(Number(entry.value), entryUnit, 'standard')
                : '—'}
            </span>
          </div>
        );
      })}
      {label && <p className={styles.label}>in {`${label}`}</p>}
    </div>
  );
};
