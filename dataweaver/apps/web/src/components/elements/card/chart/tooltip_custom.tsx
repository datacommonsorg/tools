import { formatChartValue } from '~/functions/format_chart_value';

import styles from './tooltip_custom.module.scss';

interface TooltipCustomProps {
  active?: boolean;
  payload?: { value: number }[];
  label?: string;
  unit?: string;
}

export const TooltipCustom = ({
  active,
  payload,
  label,
  unit,
}: TooltipCustomProps) => {
  if (active && payload && payload.length) {
    const formatted = formatChartValue(
      Number(payload?.[0]?.value),
      unit,
      'standard',
    );
    return (
      <div className={styles.tooltip}>
        <p className={styles.value}>{formatted}</p>
        <p className={styles.label}>in {`${label}`}</p>
      </div>
    );
  }
  return null;
};
