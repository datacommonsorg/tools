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

import { useState, useEffect } from 'react';
import {
  createDataCommonsClient,
  getMetadata,
  getObservations,
  toRecharts,
  toHighcharts,
  RechartsData,
  HighchartsOptions,
  MetadataResponse,
  Facet,
} from '@datacommons/core';
import { Controls } from './components/controls';
import { ViewRecharts } from './components/view_recharts';
import { ViewHighcharts } from './components/view_highcharts';
import { FacetDetails } from './components/facet_details';
import './App.css';

/**
 * Main application component demonstrating the headless SDK integration.
 */
export function App() {
  const [rechartsData, setRechartsData] = useState<RechartsData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // State for picker (Dimension Picker)
  const [selectedEntity, setSelectedEntity] = useState('country/USA');
  const [selectedVariable, setSelectedVariable] = useState('Count_Person');
  const [selectedFacet, setSelectedFacet] = useState('');
  const [availabilityData, setAvailabilityData] = useState<MetadataResponse | null>(null);
  const [highchartsOptions, setHighchartsOptions] = useState<HighchartsOptions | null>(null);
  
  // Metadata display strings
  const [variableName, setVariableName] = useState('');
  const [entityName, setEntityName] = useState('');

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      setError(null);
      setRechartsData(null);
      setHighchartsOptions(null);
      const apiKey = import.meta.env.VITE_DATACOMMONS_API_KEY;
      if (!apiKey) {
        console.warn(
          'VITE_DATACOMMONS_API_KEY is not defined. ' +
          'Requests may be rate-limited or fail.'
        );
      }
      const client = createDataCommonsClient({ apiKey });
      
      try {
        // 1. Call Metadata API
        const availability = await getMetadata(client, {
          statisticalVariable: selectedVariable,
          observationProperties: [{ entity: selectedEntity }]
        });
        setAvailabilityData(availability);

        // 2. Call Observation API
        const response = await getObservations(client, {
          statisticalVariableDcid: selectedVariable,
          observationProperties: [{ entity: selectedEntity }],
          facetDcid: selectedFacet || undefined
        });
        
        setVariableName(response.header.statisticalVariableInfo.name);
        setEntityName(response.entities[selectedEntity]?.name || selectedEntity);
        
        const pivoted = toRecharts(response);
        setRechartsData(pivoted);

        const hcOptions = toHighcharts(response, {
          title: 'Highcharts View'
        });
        setHighchartsOptions(hcOptions);
      } catch (err: unknown) {
        const errorVal = err as Error;
        setError(errorVal.message || 'Failed to fetch data');
      } finally {
        setLoading(false);
      }
    };
    
    fetchData();
  }, [selectedEntity, selectedVariable, selectedFacet]);

  return (
    <div className="app-container">
      <h1>Headless SDK Reference</h1>
      
      <Controls 
        selectedEntity={selectedEntity}
        setSelectedEntity={setSelectedEntity}
        selectedVariable={selectedVariable}
        setSelectedVariable={setSelectedVariable}
        selectedFacet={selectedFacet}
        setSelectedFacet={setSelectedFacet}
        availabilityData={availabilityData}
      />

      {selectedFacet && availabilityData && availabilityData.facets && (
        <FacetDetails facet={availabilityData.facets.find((f: Facet) => f.facetDcid === selectedFacet) as Facet} />
      )}

      {loading && <div>Loading data...</div>}
      {error && <div style={{ color: 'red' }}>Error: {error}</div>}
      
      {rechartsData && (
        <ViewRecharts 
          chartData={rechartsData}
          variableName={variableName}
          entityName={entityName}
          selectedFacet={selectedFacet}
        />
      )}

      {highchartsOptions && (
        <ViewHighcharts 
          highchartsOptions={highchartsOptions}
          variableName={variableName}
          entityName={entityName}
          selectedFacet={selectedFacet}
        />
      )}
    </div>
  );
}
