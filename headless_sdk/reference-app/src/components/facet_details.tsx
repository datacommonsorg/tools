/*
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import React from 'react';
import { Facet } from '@datacommons/headless-sdk';
import './facet_details.css';

/**
 * Props for the FacetDetails component.
 */
interface FacetDetailsProps {
  facet: Facet;
}

/**
 * Component to display metadata about a selected dataset/facet source.
 */
export function FacetDetails({ facet }: FacetDetailsProps) {
  if (!facet) return null;

  return (
    <div className="facet-details">
      <h3>Selected Source Metadata</h3>
      <div className="facet-grid">
        <strong>Source Organization:</strong> <span>{facet.provenanceName || 'N/A'}</span>
        <strong>Dataset Name:</strong> <span>{facet.importName || 'N/A'}</span>
        <strong>Source URL:</strong> <span>{facet.provenanceUrl ? <a href={facet.provenanceUrl} target="_blank" rel="noopener noreferrer">{facet.provenanceUrl}</a> : 'N/A'}</span>
        <strong>Method Name:</strong> <span>{facet.measurementMethodName || 'N/A'}</span>
        {facet.measurementMethodDesc && (
          <>
            <strong>Method Description:</strong> <span>{facet.measurementMethodDesc}</span>
          </>
        )}
        <strong>Observation Period:</strong> <span>{facet.observationPeriod || 'N/A'}</span>
        <strong>Date Coverage:</strong> <span>{facet.dateRangeStart || facet.dateRangeEnd ? `${facet.dateRangeStart || 'Unknown'} to ${facet.dateRangeEnd || 'Unknown'}` : 'N/A'}</span>
        <strong>Unit of Measure:</strong> <span>{facet.unitName || 'N/A'}</span>
      </div>
    </div>
  );
}
