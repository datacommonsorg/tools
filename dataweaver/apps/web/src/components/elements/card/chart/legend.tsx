import type { ChartSeries } from './chart';
import s from './legend.module.scss';
import { getSeriesColor } from './palette';

interface ChartLegendProps {
  series: ChartSeries[];
}

export const ChartLegend = ({ series }: ChartLegendProps) => {
  return (
    <div className={s.container}>
      {series.map((entry, index) => (
        <div key={entry.key} className={s.item}>
          <span
            className={s.swatch}
            style={{ backgroundColor: getSeriesColor(index) }}
          />
          <span className={s.label}>{entry.label}</span>
        </div>
      ))}
    </div>
  );
};
