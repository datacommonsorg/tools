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

/**
 * Converts a number to a string including commas for readability.
 * For example, int(10000) would get converted to str(10,000)
 * @param num: the number to replace
 */
export const numberWithCommas = (num: number): string => {
  if (!num) return '0';

  return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
};

/**
 * Gets the latest date in the for a a list of Iso-dates.
 * @param: dates: a list of dates in ISO format. Example: "2020-01-02".
 */
export const getLatestDate = (dates: string[]): string => {
  if (!dates.length) return '';

  return dates.reduce((a, b) => {
    return new Date(a) > new Date(b) ? a : b;
  });
};

/**
 * Returns the exact color for a given CSS variable.
 * @param color: the variable name of the color.
 */
export const Colors = (color: string): string => {
  const css = getComputedStyle(document.body);
  return css.getPropertyValue(color) || color;
};

/**
 * Navigate to a different geoId.
 * @param dashboardId: the id of the dashboard to direct to.
 * @param geoId: the place's geoId we want to view.
 * @param placeType: the types of places we want to view.
 * Example: geoId=country/USA and placeType=County
 * would display all counties in the USA.
 */
export const goToPlace = (dashboardId: string, geoId?: string, placeType?: string): void => {
  let newUrl = `/dashboard/?dashboardId=${dashboardId}`;

  // Redirect to a specific geoId.
  if (geoId && geoId !== 'World') {
    newUrl += `&geoId=${geoId}`;
  } else {
    // if !geoId or geoId == 'World', redirect to homepage.
    window.location.href = newUrl;
    return;
  }

  // If placeType has been given, redirect to this placeType.
  if (placeType && geoId) {
    newUrl += `&placeType=${placeType}`;
  } else if (!placeType && geoId) {
    // Otherwise, State is defaulted.
    newUrl += `&placeType=State`;
  }

  // Redirect to new url.
  window.location.href = newUrl;
};

export const getContent = (dashboardId: string) => {
  return require(`./${dashboardId}.json`)?.['content'] || {}
}

export const getConfiguration = (dashboardId: string) => {
  return require(`./${dashboardId}.json`)?.['configuration'] || {}
}