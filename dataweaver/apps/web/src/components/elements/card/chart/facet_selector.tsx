'use client';

import clsx from 'clsx';
import { useState } from 'react';
import type { FacetInfo } from '~/server/types';
import s from './facet_selector.module.scss';

interface FacetSelectorProps {
  facets: FacetInfo[];
  selectedFacetId: string;
  onSelect: (facetId: string) => void;
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
}: FacetSelectorProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const currentFacet = facets.find((f) => f.facetId === selectedFacetId);

  if (!currentFacet || facets.length <= 1) {
    return currentFacet ? (
      <div className={clsx(s.label, s.container)}>
        <span className={s.prefix}>Facet</span>
        {formatFacetLabel(currentFacet)}
      </div>
    ) : null;
  }

  return (
    <div className={s.container}>
      <span className={s.prefix}>Facet</span>
      <button
        type="button"
        className={s.trigger}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        onPointerDown={(event) => event.stopPropagation()}
        onClick={() => setIsOpen(!isOpen)}
      >
        <span>{formatFacetLabel(currentFacet)}</span>
        <span className={s.arrow}>▾</span>
      </button>

      {isOpen && (
        <div className={s.dropdown}>
          {facets.map((facet) => (
            <button
              key={facet.facetId}
              type="button"
              className={s.option}
              data-is-selected={facet.facetId === selectedFacetId}
              onPointerDown={(event) => event.stopPropagation()}
              onClick={() => {
                onSelect(facet.facetId);
                setIsOpen(false);
              }}
            >
              {formatFacetLabel(facet)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
