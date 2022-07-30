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

import {Node} from './graph';
const API_ROOT = 'https://api.datacommons.org';

const ERROR_MESSAGES = {
  'curNode-length': 'error in declaring node',
  'curNode-ns': 'invalid namespace in node declaration',
  'setDCID-noCur': 'current node must be set before setting dcid',
  'setDCID-multiple': 'a node can only have one dcid',
  'setDCID-ref': 'dcid property must be a string, not a node reference',
  'setDCID': 'cannot set dcid for current node; check if dcid is already set',
  'assert-noCur': 'current node must be set before declaring properties',
  'parse-noColon': 'missing \':\', incorrect mcf triple format',
  'parse-noLabel': 'missing property label',
};

/** A type to represent the format of the errors in the errList prop */
export interface ParsingError {
  /** A list of errors generated when parsing a file */
  errs: string[][];

  /** The file that created the errors */
  file: string;
}

/**
 * Gets all property labels of the given dcid that are in the DC KG.
 *
 * @param {string} dcid The dcid of the node to find property labels for.
 * @return {Object} An object containing both 'in' and 'out' property labels.
 */
async function getRemotePropertyLabels(dcid: string) {
  // Get inward and outward property labels
  const outTargetUrl = `${API_ROOT}/v1/properties/out/${dcid}`;
  const inTargetUrl = `${API_ROOT}/v1/properties/in/${dcid}`;

  const [inPropertyLabels, outPropertyLabels] = await Promise.all([
    fetch(inTargetUrl).then((response) =>
      response.json().then((data) => data.properties),
    ),
    fetch(outTargetUrl).then((response) =>
      response.json().then((data) => data.properties),
    ),
  ]);

  return {outLabels: outPropertyLabels, inLabels: inPropertyLabels};
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
async function getRemotePropertyValues(
    dcid: string,
    label: string,
    isInverse: boolean,
) {
  const direction = isInverse ? 'in' : 'out';
  const targetUrl =
    `${API_ROOT}/v1/property/values/${direction}/${dcid}/${label}`;

  return fetch(targetUrl)
      .then((res) => res.json())
      .then((data) => data.values);
}

export type DCPropertyValueResponse = {
  /** the dcid being queried */
  dcid?: string;

  /** the value of the property being queried */
  value?: string;

  provenanceId: string;
};

/**
 * Parses an Object returned from the DC REST get_values API to create a Node
 * object from the value's dcid or to return the string value that the object
 * holds.
 *
 * @param {Object} valueObj An object returned from DC REST get_values API.
 * @return {Node | string} The created Node if the value object has a dcid,
 *     otherwise the string of the value.
 */
function getValueFromValueObj(valueObj: DCPropertyValueResponse) {
  if (!('dcid' in valueObj || 'value' in valueObj)) {
    throw new Error(
        'ERROR: DC API returned an object with no "dcid" or "value" field: ' +
        valueObj,
    );
  }

  if (valueObj.dcid) {
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
async function doesExistsInKG(dcid: string) {
  const url = `${API_ROOT}/v1/property/values/out/${dcid}/typeOf`;

  // expected response if dcid exists is {"values":"[...]}
  // expected response if dcid does not exist is {}
  return fetch(url)
      .then((res) => res.json())
      .then((data) => (data.values ? true : false));
}

/**
 * Indicates if a line should be parsed.
 * @param {string} line The line to be checked.
 * @return {boolean} False if the line is a comment or empty, otherwise
 *     true.
 */
function shouldReadLine(line: string) {
  if (line.startsWith('//') || line.length === 0 || line.startsWith('#')) {
    return false;
  }
  return true;
}


export {
  doesExistsInKG,
  ERROR_MESSAGES,
  getRemotePropertyLabels,
  getRemotePropertyValues,
  getValueFromValueObj,
  shouldReadLine,
};
