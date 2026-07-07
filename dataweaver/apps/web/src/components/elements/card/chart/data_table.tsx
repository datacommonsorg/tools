import type { ChartDatum } from './chart';
import s from './data_table.module.scss';

interface DataTableProps {
  data: ChartDatum[];
}

const compactFormatter = new Intl.NumberFormat(undefined, {
  notation: 'standard',
});

export const DataTable = ({ data }: DataTableProps) => {
  return (
    <table className={s.table}>
      <thead>
        <tr>
          <th>Date</th>
          <th>Value</th>
        </tr>
      </thead>
      <tbody>
        {data.map(({ date, value }) => (
          <tr key={date}>
            <td>{date}</td>
            <td>{compactFormatter.format(value)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
};
