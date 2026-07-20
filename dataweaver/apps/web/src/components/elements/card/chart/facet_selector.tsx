'use client';

import { Select } from '~/components/elements/select';
import type { FacetInfo } from '~/server/types';
import s from './facet_selector.module.scss';

interface FacetSelectorProps {
  facets: FacetInfo[];
  selectedFacetId: string;
  onSelect: (facetId: string) => void;
  label?: string;
}

const formatFacetLabel = (facet: FacetInfo): string => {
  const unit =
    facet.unit.toLowerCase() === 'dimensionless' ? 'Dimensionless' : facet.unit;
  return `${facet.source}, ${facet.earliestDate}–${facet.latestDate}, ${unit}`;
};

export const FacetSelector = ({
  facets,
  selectedFacetId,
  onSelect,
  label = 'Facet',
}: FacetSelectorProps) => {
  const currentFacet = facets.find((f) => f.facetId === selectedFacetId);

  if (!currentFacet || facets.length <= 1) {
    return currentFacet ? (
      <div className={s.container}>
        <span className={s.prefix}>{label}</span>
        <span className={s.label}>{formatFacetLabel(currentFacet)}</span>
      </div>
    ) : null;
  }

  return (
    <Select
      className={s.container}
      options={facets}
      value={currentFacet}
      onSelect={(facet) => onSelect(facet.facetId)}
      getKey={(facet) => facet.facetId}
      renderOption={formatFacetLabel}
      label={label}
      aria-label={`Select data facet for ${label}`}
    />
  );
};
