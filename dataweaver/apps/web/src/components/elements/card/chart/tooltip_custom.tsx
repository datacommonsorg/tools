import type { ChartSeries } from './chart';
import { getSeriesColor } from './chart_palette';
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
}

const tooltipFormatter = new Intl.NumberFormat(undefined, {
  notation: 'standard',
  maximumFractionDigits: 2,
});

export const TooltipCustom = ({
  active,
  payload,
  label,
  series,
}: TooltipCustomProps) => {
  if (!active || !payload || payload.length === 0) return null;

  const isMulti = series && series.length > 1;

  return (
    <div className={styles.tooltip}>
      <p className={styles.label}>{`${label}`}</p>
      {payload.map((entry, index) => {
        const color = isMulti ? getSeriesColor(index) : entry.color;
        const name = isMulti ? series[index]?.label : undefined;
        return (
          <div key={entry.dataKey ?? index} className={styles.entry}>
            {color && (
              <span
                className={styles.swatch}
                style={{ backgroundColor: color }}
              />
            )}
            {name && <span className={styles.name}>{name}</span>}
            <span className={styles.value}>
              {tooltipFormatter.format(Number(entry.value))}
            </span>
          </div>
        );
      })}
    </div>
  );
};
