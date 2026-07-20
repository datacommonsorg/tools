import styles from './tooltip_custom.module.scss';

const tooltipFormatter = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 2,
  notation: 'standard',
});

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
    const unitLower = unit?.toLowerCase() ?? '';
    const isPercent = unitLower.includes('percent');
    const isUSD = unitLower === 'usd' || unitLower.includes('dollar');
    const value = tooltipFormatter.format(Number(payload?.[0]?.value));
    const formatted = isUSD ? `$${value}` : isPercent ? `${value}%` : value;
    return (
      <div className={styles.tooltip}>
        <p className={styles.value}>{formatted}</p>
        <p className={styles.label}>in {`${label}`}</p>
      </div>
    );
  }
  return null;
};
