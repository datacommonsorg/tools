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

import {Series, SeriesIdObject} from './back-end/time-series';
import React from 'react';

import {TimeGraph} from './TimeGraph';
import {LocationMapping} from './TimelineExplorer';

/* Simple component to render the colors legend. */
const COLOR_LEGEND = {
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

interface SubGroup {
  subGroup: Series[];
  title: string;
}
interface LocationGroupings {
  [group: string]: SubGroup[];
}

interface Grouping {
  [group: string]: Series[];
}

/**
  * Sets the window hash value to query a given id.
  *
  * @param {string} homeHash The hash saveed in App's state, preserving file
  *     names within url.
  * @param {string} id The id of the desired node to display. This can be either
  *     a dcid or a local id.
  */
function onNodeClick(homeHash: string, id: string) {
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
    * @return {LocationGroupings} an object where the keys are the group names
    * and the values are arrays where each element is a group of data
    * that contains the actual series list and the title of the graph
    */
function groupSeriesByLocations(seriesList: Series[]): LocationGroupings {
  // Group similar series
  const groups: Grouping = {};
  const exclude = ['observationAbout'];
  for (const series of seriesList) {
    const group = series.getHash(exclude);

    if (!groups[group]) {
      groups[group] = [];
    }

    groups[group].push(series);
  }

  // Separate groups into groups of size groupNumber
  const finalGroups: LocationGroupings = {};

  const groupNames = Object.keys(groups);
  for (const groupName of groupNames) {
    const group = groups[groupName];
    const numberOfSubgroups = Math.ceil(group.length / GROUP_NUMBER);

    finalGroups[groupName] = [];

    for (let i = 0; i < group.length; i += GROUP_NUMBER) {
      const subGroup = group.slice(i, i + GROUP_NUMBER);
      const title = (numberOfSubgroups > 1) ?
         `${groupName} (${i + 1} of ${numberOfSubgroups}) ` :
         `${groupName}`;

      finalGroups[groupName].push({subGroup, title});
    }
  }

  return finalGroups;
}

/**
    * Plot a TimeGraph component given all of the data and metadata
    * @param {SubGroup} seriesObj an object containing all the series to plot
    *                  and metadata for the plot
    * @param {LocationMapping} locationMapping a mapping from location dcid to
    * name
    * @return {JSX.Element} the TimeGraph component in TSX code
    */
function plotSeriesObj(seriesObj: SubGroup, locationMapping: LocationMapping)
: JSX.Element {
  return (<TimeGraph
    data={seriesObj.subGroup}
    title={seriesObj.title}
    locationMapping={locationMapping}
    key={seriesObj.title + '\n' + seriesObj.subGroup.map(
        (series: Series) => series.id,
    ).join(',')}
  />);
}

/**
  * Renders a section containing all of the graphs for a group
  * of related series
  * @param {SubGroup[]} group an array of objects where each object contains the
  *              data for a graph
  * @param {string} groupName the name of the group for the summary
  * @param {boolean} keepOpen whether or not to render the details open
  * @param {LocationMapping} locationMapping a mapping from location dcid to
  * name
  * @return {JSX.Element} the details section in TSX code
  */
function renderTimeGraph(
    group: SubGroup[],
    groupName: string,
    keepOpen: boolean,
    locationMapping: LocationMapping,
): JSX.Element {
  const facets: SeriesIdObject = Series.fromID(groupName);
  const facetKeys = Object.keys(facets) as (keyof typeof facets)[];
  return (
    <details key={groupName} open={keepOpen}>
      <summary>{groupName}</summary>
      {facetKeys.map((facet) => {
        return (
           (facets[facet] && facet !== 'variableMeasured') ?
           <p className='facet' key={facet}>{facet}: {facets[facet]}</p> :
           null
        );
      })}
      {group.map((seriesObj) => plotSeriesObj(seriesObj, locationMapping))}
    </details>
  );
}

export {
  COLOR_LEGEND as colorLegend,
  goTo,
  onNodeClick,
  openFile,
  searchId,
  groupSeriesByLocations,
  renderTimeGraph,
};

export type {Grouping};
