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

import { ObservationsResponse } from '../src/types';

export const samplePopulationData: ObservationsResponse = {
  header: {
    statisticalVariableInfo: {
      dcid: 'Count_Person',
      name: 'Population',
    },
    observationProperties: [{ entity: 'country/USA' }, { entity: 'country/CHN' }],
    facet: {
      facetDcid: 'facet1',
      importDcid: '',
      provenanceUrl: 'https://example.org',
    },
  },
  observations: [
    {
      date: '2020',
      value: 331000000,
      observationProperties: { entity: 'country/USA' },
    },
    {
      date: '2021',
      value: 332000000,
      observationProperties: { entity: 'country/USA' },
    },
    {
      date: '2020',
      value: 1410000000,
      observationProperties: { entity: 'country/CHN' },
    },
    {
      date: '2021',
      value: 1412000000,
      observationProperties: { entity: 'country/CHN' },
    },
  ],
  entities: {
    'country/USA': { dcid: 'country/USA', name: 'United States', typeDcid: 'Country' },
    'country/CHN': { dcid: 'country/CHN', name: 'China', typeDcid: 'Country' },
  },
};
