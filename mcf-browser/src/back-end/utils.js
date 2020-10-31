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
/**
 * Module contains helper functions for api calls to data commons as well as
 * helper functions for parsing file to create local knowledge graph.
 */

import {Node} from './graph.js';
const API_ROOT = 'https://api.datacommons.org';

const ERROR_MESSAGES =
    {
      'curNode-length': 'error in declaring node',
      'curNode-ns': 'invalid namespace in node declaration',
      'setDCID-noCur': 'current node must be set before setting dcid',
      'setDCID-multiple': 'a node can only have one dcid',
      'setDCID-ref': 'dcid property must be a string, not a node reference',
      'setDCID':
          'cannot set dcid for current node; check if dcid is already set',
      'assert-noCur': 'current node must be set before declaring properties',
      'parse-noColon': 'missing \':\', incorrect mcf triple format',
      'parse-noLabel': 'missing property label',
      'parse-noValues': 'missing property value',
    };

/**
 * Gets all property labels of the given dcid that are in the DC KG.
 *
 * @param {string} dcid The dcid of the node to find property labels for.
 * @return {Object} An object containing both 'in' and 'out' property labels.
 */
async function getRemotePropertyLabels(dcid) {
  const targetUrl = API_ROOT + '/node/property-labels?dcids=' + dcid;
  return fetch(targetUrl)
      .then((res) => res.json())
      .then((data) => JSON.parse(data.payload)[dcid]);
}

/**
 * Gets all property values containing the given dcid, property label, and
 * direction.
 *
 * @param {string} dcid The dcid of the node to find property value for.
 * @param {string} label The property label to query for.
 * @param {boolean} isInverse Direction of property label, false indicates
 *     an outgoing label, true is an incoming label.
 * @return {Object} An object containing all found values matching the query.
 */
async function getRemotePropertyValues(dcid, label, isInverse) {
  const direction = isInverse ? 'in' : 'out';
  const targetUrl =
      (API_ROOT + '/node/property-values?limit=500&dcids=' + dcid +
       '&property=' + label + '&direction=' + direction);

  return fetch(targetUrl)
      .then((res) => res.json())
      .then((data) => JSON.parse(data.payload)[dcid])
      .then((triples) => isInverse ? triples.in : triples.out);
}

/**
 * Parses an Object returned from the DC REST get_values API to create a Node
 * object from the value's dcid or to return the string value that the object
 * holds.
 *
 * @param {Object} valueObj An object returned from DC REST get_values API.
 * @return {Node | string} The created Node if the value object has a dcid,
 *     otherwise the string of the value.
 */
function getValueFromValueObj(valueObj) {
  if (!('dcid' in valueObj || 'value' in valueObj)) {
    throw new Error(
        'ERROR: DC API returned an object with no "dcid" or "value" field: ' +
        valueObj);
  }

  if ('dcid' in valueObj) {
    const value = Node.getNode('dcid:' + valueObj.dcid);
    value.setDCID(valueObj.dcid);
    value.existsInKG = true;
    return value;
  }
  return valueObj.value;
}

/**
 * Queries Data Commons to determine if a given dcid is a part of any
 * triples in the Knowledge graph.
 * @param {string} dcid The dcid to check if exists in Data Commons
 * @return {Promise<boolean>} Returns true if given dcid is in any triples in
 *     Data Commons Knowledge Graph.
 */
async function doesExistsInKG(dcid) {
  const url = API_ROOT + '/node/triples?dcids=' + dcid + '&limit=1';
  return fetch(url)
      .then((res) => res.json())
      .then((data) => JSON.parse(data.payload)[dcid] ? true : false);
}

/**
 * Indicates if a line should be parsed.
 * @param {string} line The line to be checked.
 * @return {boolean} False if the line is a comment or empty, otherwise
 *     true.
 */
function shouldReadLine(line) {
  if (line.startsWith('//') || line.length === 0 || line.startsWith('#')) {
    return false;
  }
  return true;
}

export {
  ERROR_MESSAGES,
  getRemotePropertyLabels,
  getRemotePropertyValues,
  getValueFromValueObj,
  doesExistsInKG,
  shouldReadLine,
};
