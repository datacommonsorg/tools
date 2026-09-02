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
import { MetadataResponse, Facet } from '@datacommons/headless-sdk';
import './controls.css';

/**
 * Props for the Controls component.
 */
interface ControlsProps {
  selectedEntity: string;
  setSelectedEntity: (value: string) => void;
  selectedVariable: string;
  setSelectedVariable: (value: string) => void;
  selectedFacet: string;
  setSelectedFacet: (value: string) => void;
  availabilityData: MetadataResponse | null;
}

/**
 * Component representing the control selector controls.
 */
export function Controls({
  selectedEntity,
  setSelectedEntity,
  selectedVariable,
  setSelectedVariable,
  selectedFacet,
  setSelectedFacet,
  availabilityData
}: ControlsProps) {
  return (
    <div className="controls-container">
      <div className="control-item">
        <label htmlFor="variable-picker">Select Variable: </label>
        <select 
          id="variable-picker" 
          value={selectedVariable} 
          onChange={(e) => {
            setSelectedVariable(e.target.value);
            setSelectedFacet('');
          }}
        >
          <option value="Count_Person">Population</option>
          <option value="Median_Income_Household">Median Income</option>
          <option value="UnemploymentRate_Person">Unemployment Rate</option>
        </select>
      </div>

      <div className="control-item">
        <label htmlFor="entity-picker">Select Entity: </label>
        <select 
          id="entity-picker" 
          value={selectedEntity} 
          onChange={(e) => {
            setSelectedEntity(e.target.value);
            setSelectedFacet('');
          }}
        >
          <option value="country/USA">United States</option>
          <option value="country/CHN">China</option>
          <option value="country/IND">India</option>
          <option value="country/BRA">Brazil</option>
        </select>
      </div>

      {availabilityData && availabilityData.facets && (
        <div className="control-item">
          <label htmlFor="facet-picker">Select Source/Facet: </label>
          <select 
            id="facet-picker" 
            value={selectedFacet} 
            onChange={(e) => setSelectedFacet(e.target.value)}
          >
            <option value="">All Sources</option>
            {availabilityData.facets.map((facet: Facet) => (
              <option key={facet.facetDcid} value={facet.facetDcid}>
                {facet.provenanceName || facet.importName || facet.importDcid || facet.facetDcid} ({facet.dateRangeStart || 'N/A'} - {facet.dateRangeEnd || 'N/A'})
              </option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
}
