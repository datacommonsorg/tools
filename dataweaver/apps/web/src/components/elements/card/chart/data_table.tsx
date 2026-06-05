import type { ChartDatum } from './chart';
import s from './data_table.module.scss';

interface DataTableProps {
  data: ChartDatum[];
}

// TODO: This is temporary - either style it or render using recharts
export const DataTable = ({ data }: DataTableProps) => {
  return (
    <table className={s.table}>
      <thead>
        <tr>
          <th>Year</th>
          <th>Emissions (Mt CO₂e)</th>
        </tr>
      </thead>
      <tbody>
        {data.map(({ year, emissions }) => (
          <tr key={year}>
            <td>{year}</td>
            <td>{emissions}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
};
