/**
 * Copyright 2020 Google LLC
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

import {Series} from './back-end/data';

/* Simple component to render the colors legend. */
const colorLegend = {
  'exist-in-kg': 'Node has dcid that exists in DC KG',
  'exist-in-local': 'Node has resolved local reference and no dcid',
  'not-in-local': 'Node has unresolved local reference and no dcid',
  'not-in-kg': 'Node has dcid which does not exist in DC KG',
};

const GROUP_NUMBER = 20; // The maximum number of series per graph

/* Simple type to represent index of colorLegend */
export type ColorIndex =
  | 'exist-in-kg'
  | 'exist-in-local'
  | 'not-in-local'
  | 'not-in-kg';

/**
 * Sets the window hash value to query a given id.
 *
 * @param {string} homeHash The hash saveed in App's state, preserving file
 *     names within url.
 * @param {string} id The id of the desired node to display. This can be either
 *     a dcid or a local id.
 */
function goToId(homeHash: string, id: string) {
  if (id.includes(':')) {
    window.location.hash = homeHash + '&id=' + id;
  } else {
    window.location.hash = homeHash + '&id=dcid:' + id;
  }
}

/**
 * Sets the window hash value to query a given id.
 * @param {string} homeHash The hash saveed in App's state, preserving file
 *     names within url.
 * @param {string} id The id of the desired node to display. This can be either
 *     a dcid or a local id.
 */
function searchId(homeHash: string, id: string) {
  if (id.includes(':')) {
    window.location.hash = homeHash + '&search=' + id;
  } else {
    window.location.hash = homeHash + '&search=dcid:' + id;
  }
}

/**
 * Sets the window hash value to given value.
 * @param {string} hash The value that the window's hash should be set to.
 */
function goTo(hash: string) {
  window.location.hash = hash;
}

/**
 * Opens the given file url.
 * @param {string} fileUrl Url of the fileee to open.
 */
function openFile(fileUrl: string) {
  if (fileUrl.startsWith('https')) {
    window.open(fileUrl);
  }
}

/** Groups data with equal values for everything except for their
   * locations into groups of groupNumber to be plotted together
   * @param {Series[]} seriesList the data to group
   * @return {Object[]} an array where each element is a group of data
   * that contains the actual series list and the title of the graph
   */
function groupLocations(seriesList: Series[]) {
  // Group similar series
  const groups: any = {};
  const exclude = ['observationAbout'];
  for (const series of seriesList) {
    const group = series.getHash(exclude);

    if (!groups[group]) {
      groups[group] = [];
    }

    groups[group] = groups[group].concat([series]);
  }

  // Separate groups into groups of size groupNumber
  const finalGroups = [];

  const groupNames = Object.keys(groups);
  for (const groupName of groupNames) {
    const group = groups[groupName];
    const numberOfSubgroups = Math.ceil(group.length / GROUP_NUMBER);

    for (let i = 0; i < group.length; i += GROUP_NUMBER) {
      const subGroup = group.slice(i, i + GROUP_NUMBER);
      const title = (numberOfSubgroups > 1) ?
        `${groupName} (${i + 1} of ${numberOfSubgroups}) ` :
        `${groupName}`;
      finalGroups.push({subGroup, title});
    }
  }

  return finalGroups;
}


export {colorLegend, goTo, goToId, openFile, searchId, groupLocations};
