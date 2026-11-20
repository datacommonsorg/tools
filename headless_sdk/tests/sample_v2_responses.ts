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
 * Mock response matching the Data Commons V2 /observation API structure.
 * This is used to test the SDK's parsing and normalization logic.
 */
export const sampleV2ObservationResponse = {
  "byVariable": {
    "Count_Person": {
      "byEntity": {
        "country/USA": {
          "orderedFacets": [
            {
              "facetId": "20254455",
              "observations": [
                { "date": "2020", "value": 331000000 },
                { "date": "2021", "value": 332000000 }
              ]
            }
          ]
        },
        "country/CHN": {
          "orderedFacets": [
            {
              "facetId": "30456677",
              "observations": [
                { "date": "2020", "value": 1410000000 },
                { "date": "2021", "value": 1412000000 }
              ]
            }
          ]
        }
      }
    }
  },
  "facets": {
    "20254455": {
      "provenanceUrl": "https://census.gov",
      "measurementMethod": "CensusDC",
      "unit": "Person"
    },
    "30456677": {
      "provenanceUrl": "https://stats.gov.cn",
      "measurementMethod": "NationalNBS",
      "unit": "Person"
    }
  }
};
