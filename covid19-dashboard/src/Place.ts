/**
 * Copyright 2024 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */


import {KeyToTimeSeriesType, PlaceInfoType} from './Types';

/**
 * Class that represents a given place in the World.
 * This place holds metadata and timeSeries data.
 */
export default class Place {
  // The identifier of the Place.
  // Example: geoId/12000
  geoId: string;
  // The name of the Place.
  // Example: "Florida"
  name: string;
  // The geoId of the parent Place.
  // Example: geoId/12000 is containedIn geoId/12
  containedIn: string;
  // A reference to the Place object of 'containedIn'.
  parentPlace: Place | null;
  // The type of Place. Example: "County".
  placeType: string;
  // An object where stat_var->date->value.
  // Can contains multiple stat_vars.
  keyToTimeSeries: KeyToTimeSeriesType;
  constructor(
    geoId: string,
    placeInfo: PlaceInfoType,
    keyToTimeSeries: KeyToTimeSeriesType
  ) {
    this.geoId = geoId;
    this.name = placeInfo.name;
    this.containedIn = placeInfo.containedIn;
    this.parentPlace = null;
    this.placeType = placeInfo.placeType;
    this.keyToTimeSeries = keyToTimeSeries;
  }

  /**
   * Returns a boolean representing whether the place holds any subregions.
   */
  private hasSubregions = (): boolean => {
    return this.placeType === 'State' || this.geoId === 'country/USA';
  };

  /**
   * Returns what placeType this place holds as a subregion.
   * For example: Country has State as a subregion.
   * If this place doesn't have any subregions, return "".
   * Example: if Place is a County, return "".
   */
  getSubregionType = (): string => {
    const hasSubregions = this.hasSubregions();
    const subregions: {[region: string]: string} = {
      World: 'Country',
      Country: 'State',
      State: 'County',
    };

    // If the place has subregions, then return the type of subregion.
    // Example: "Country" has "State" subregion.
    // Example: "State" has "County" subregion.
    if (hasSubregions) {
      return subregions[this.placeType];
    } else {
      return '';
    }
  };

  /**
   * Sets the pointer to the object of the parent place.
   * A parent place is a Place in which this place belongs to.
   * Example: The parent place of San Francisco is California.
   * @param parentPlace
   */
  setParentPlace = (parentPlace: Place): void => {
    this.parentPlace = parentPlace;
  };
}
