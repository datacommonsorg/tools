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

/**
 * @fileoverview V2 API network communication layer, containing POST requests
 * wrapper and parallel properties resolution.
 */

import { DataCommonsClient } from './types';
import { DataCommonsError } from './errors';
import { V2NodeResponse, V2NodePropertyValue } from './types_api';

/**
 * Helper to fetch data from the Data Commons V2 API.
 */
export async function fetchV2(
  state: DataCommonsClient,
  path: string,
  payload: Record<string, unknown>
): Promise<unknown> {
  const url = new URL(path, state.config.apiBaseUrl);
  if (state.config.apiKey) {
    url.searchParams.append('key', state.config.apiKey);
  }

  const response = await fetch(url.toString(), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new DataCommonsError(
      `API request failed with status ${response.status}`,
      response.status.toString()
    );
  }

  try {
    return await response.json();
  } catch (err) {
    throw new DataCommonsError(
      'Failed to parse API response as JSON',
      'PARSE_ERROR'
    );
  }
}

/**
 * Helper to fetch node properties (like names).
 */
export async function fetchNodeProperties(
  state: DataCommonsClient,
  dcids: string[],
  properties: string[]
): Promise<Record<string, Record<string, V2NodePropertyValue[]>>> {
  if (dcids.length === 0 || properties.length === 0) return {};
  const path = '/v2/node';
  
  const results: Record<string, Record<string, V2NodePropertyValue[]>> = {};
  dcids.forEach(dcid => {
    results[dcid] = {};
  });

  const promises = properties.map(async (prop) => {
    try {
      const payload = {
        nodes: dcids,
        property: `->${prop}`
      };
      const response = (await fetchV2(
        state,
        path,
        payload
      )) as V2NodeResponse;
      const data = response?.data || {};
      
      Object.entries(data).forEach(([dcid, nodeData]) => {
        const nodesList = nodeData?.arcs?.[prop]?.nodes || [];
        if (nodesList.length > 0) {
          results[dcid][prop] = nodesList;
        }
      });
    } catch (e) {
      console.warn('Failed to fetch node property: ' + prop, e);
    }
  });
  
  await Promise.all(promises);
  return results;
}
