import styles from './custom_tooltip.module.scss';

const tooltipFormatter = new Intl.NumberFormat('en', {
  maximumFractionDigits: 2,
  notation: 'standard',
});

export const CustomTooltip = ({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { value: number }[];
  label?: string;
}) => {
  if (active && payload && payload.length) {
    const value = tooltipFormatter.format(Number(payload?.[0]?.value));
    return (
      <div className={styles.tooltip}>
        <p className={styles.label}>{`${label}`}</p>
        <p className={styles.value}>{`${value}`}</p>
      </div>
    );
  }
  return null;
};
