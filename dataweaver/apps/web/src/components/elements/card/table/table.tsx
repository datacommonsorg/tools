import type { CardState } from '~/components/elements/card/base';
import { Skeleton } from '~/components/elements/skeleton';
import type { ChartMetadata, ChartVariable } from '~/server/types';
import s from './table.module.scss';

export interface CardTableProps extends Pick<CardState, 'isLoading'> {
  title?: string;
  variables?: ChartVariable[];
  metadata?: ChartMetadata[];
}

export const CardTable = ({
  isLoading,
  title,
  variables,
  metadata,
}: CardTableProps) => {
  return (
    <>
      {title && <h2 className={s.title}>{title}</h2>}

      {isLoading || !variables ? (
        <Skeleton />
      ) : (
        <table className={s.table}>
          <thead>
            <tr>
              <th>Statistical Variable</th>
              <th>Facets</th>
              <th>Rationale</th>
            </tr>
          </thead>
          <tbody>
            {variables.map((variable) => {
              const meta = metadata?.find(
                (m) => m.variableDcid === variable.dcid,
              );
              const firstFacet = meta?.facets[0];

              return (
                <tr key={variable.dcid}>
                  <td>{variable.name}</td>
                  <td>
                    {firstFacet ? (
                      <>
                        <div className={s['facet-source']}>
                          {firstFacet.source}
                        </div>
                        <div className={s['facet-meta']}>
                          {firstFacet.earliestDate} – {firstFacet.latestDate}
                          {firstFacet.unit ? ` · ${firstFacet.unit}` : ''}
                        </div>
                      </>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td>{variable.rationale || '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </>
  );
};
