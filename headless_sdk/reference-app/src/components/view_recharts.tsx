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
import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, Legend, ResponsiveContainer } from 'recharts';
import { RechartsData, RechartsSeries } from '@datacommons/headless-sdk';
import './chart_view.css';

/**
 * Props for the ViewRecharts component.
 */
interface ViewRechartsProps {
  chartData: RechartsData;
  variableName: string;
  entityName: string;
  selectedFacet: string;
}

/**
 * Component to render a Recharts time-series chart.
 */
export function ViewRecharts({
  chartData,
  variableName,
  entityName,
  selectedFacet,
}: ViewRechartsProps) {
  return (
    <div className="chart-card">
      <h2 className="chart-title">
        {variableName}, {entityName}, {selectedFacet} (Recharts)
      </h2>
      <ResponsiveContainer width="100%" height={400}>
        <LineChart data={chartData.data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" interval="preserveStartEnd" />
          <YAxis width={120} />
          <Tooltip />
          <Legend />
          {chartData.series.map((s: RechartsSeries, index: number) => (
            <Line 
              type="monotone" 
              dataKey={s.id} 
              name={s.name} 
              key={s.id} 
              stroke={index === 0 ? '#8884d8' : '#82ca9d'} 
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
