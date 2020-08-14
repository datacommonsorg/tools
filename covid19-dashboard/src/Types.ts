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


// These are commonly-used types.
export type ValueType = {
  name: string,
  placeType: string,
  containedIn: string,
  keyToTimeSeries: KeyToTimeSeriesType,
  onClick?: () => void
};

export type GeoIdToPlaceInfoType = {
  [geoId: string]: PlaceInfoType
}

export type PlaceInfoType = {
  name: string,
  containedIn: string,
  placeType: string
}

export type TimeSeriesType = {[date: string]: number}

export type KeyToTimeSeriesType = {[dataKey: string]: TimeSeriesType}

export type GeoIdToDataType = {[geoId: string]: KeyToTimeSeriesType}