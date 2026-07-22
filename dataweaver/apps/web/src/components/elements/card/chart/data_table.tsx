import { formatChartValue } from '~/functions/format_chart_value';
import { mergeClassNames } from '~/functions/merge_class_names';
import type { ChartSeries } from './chart';
import s from './data_table.module.scss';

interface DataTableProps {
  series: ChartSeries[];
}

export const DataTable = ({ series }: DataTableProps) => {
  const isMulti = series.length > 1;

  return (
    <div className={s.container}>
      {series.map((entry) => (
        <table
          key={entry.key}
          className={mergeClassNames(s.table, isMulti && s['is-multi'])}
        >
          <thead>
            {isMulti && (
              <tr>
                <th colSpan={2} className={s['place-name']}>
                  {entry.label}
                </th>
              </tr>
            )}
            <tr>
              <th>Date</th>
              <th>Value</th>
            </tr>
          </thead>
          <tbody>
            {entry.data.map(({ date, value }) => (
              <tr key={date}>
                <td>{date}</td>
                <td>{formatChartValue(value, entry.unit, 'standard')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ))}
    </div>
  );
};
