/**
 Copyright 2020 Google LLC

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

 https://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
 */

import HRNumbers from 'human-readable-numbers';
import _ from 'lodash';

/**
 * Converts a number to a string including commas for readability.
 * For example, int(10000) would get converted to str(10,000)
 * @param num: the number to replace
 */
const numberWithCommas = (num: number): string => {
  const outputNum = HRNumbers.toHumanString(num);
  if (!outputNum) {
    return '0';
  }

  return outputNum;
};

/**
 * Given a map of geoId->[name, belongToRegion]
 * return a list of the geoId's that belong to the belongToRegion
 * @param geoIdToType: geoId->[name, belongToRegion]
 * @param belongToRegion: can be any geoId, "County" or "State"
 */
const filterGeoIdThatBelongTo = (
  geoIdToType: {[geoId: string]: string[]} | {},
  belongToRegion: string
): string[] => {
  const countries = new Set(['country/USA']);
  const states: Set<string> = new Set();
  const counties: Set<string> = new Set();

  // Get all geoIds that are states.
  _.forEach(geoIdToType, ([name, belongsTo], geoId) => {
    // If region belongs to any of the countries, it must be a state.
    if (countries.has(belongsTo)) {
      states.add(geoId);
    }
  });

  // If belongToRegion === 'State', no need to continue.
  // Return the list of state geoIds right away.
  if (belongToRegion === 'State') {
    return [...states];
  }

  // Get all the geoIds that are counties.
  _.forEach(geoIdToType, ([name, belongsTo], geoId) => {
    // If region belongs to any of the states, it must be a county.
    if (states.has(belongsTo)) {
      counties.add(geoId);
    }
  });

  // If belongToRegion === 'County', no need to continue.
  // Return the list of county geoIds right away.
  if (belongToRegion === 'County') {
    return [...counties];
  }

  // Get all the geoIds that are counties belonging to belongsToRegion.
  const countiesBelongingToState: Set<string> = new Set();
  _.forEach(geoIdToType, ([name, belongsTo], geoId) => {
    // If region belongs to any of the states, it must be a county.
    if (belongsTo === belongToRegion) {
      countiesBelongingToState.add(geoId);
    }
  });

  return [...countiesBelongingToState];
};

/**
 * Returns copy of the inputted JSON with only the keys that are in the array.
 * This is similar to the reduce() function, but for JSON.
 * @param JSON: any object
 * @param keys: an array of keys
 */
const filterJSONByArrayOfKeys = (JSON: {}, keys: any[]): {} => {
  const output: {} = {};
  keys.forEach(key => {
    if (key in JSON) {
      output[key] = JSON[key];
    }
  });

  return output;
};

export {numberWithCommas, filterGeoIdThatBelongTo, filterJSONByArrayOfKeys};
