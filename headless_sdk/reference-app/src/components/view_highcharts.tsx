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

import React, { useEffect, useRef } from 'react';
import { HighchartsOptions } from '@datacommons/headless-sdk';
import './chart_view.css';

/**
 * Props for the ViewHighcharts component.
 */
interface ViewHighchartsProps {
  highchartsOptions: HighchartsOptions;
  variableName: string;
  entityName: string;
  selectedFacet: string;
}

/**
 * Component to render a Highcharts time-series chart.
 */
export function ViewHighcharts({
  highchartsOptions,
  variableName,
  entityName,
  selectedFacet,
}: ViewHighchartsProps) {
  const highchartsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (highchartsRef.current && highchartsOptions) {
      (window as any).Highcharts.chart(highchartsRef.current, highchartsOptions);
    }
  }, [highchartsOptions]);

  return (
    <div className="chart-card">
      <h2 className="chart-title">
        {variableName}, {entityName}, {selectedFacet} (Highcharts)
      </h2>
      <div ref={highchartsRef} style={{ width: '100%', height: '400px' }} />
    </div>
  );
}
