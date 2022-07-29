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

/* Functions to relay information from the back-end to the front-end. */

import {Node} from './graph';
import {ParseMcf} from './parse-mcf';
import {ParseTmcf} from './parse-tmcf';
import {ParsingError} from './utils';
import { Series } from './data';

type ParseFileResponse = {
  /** A list of errors that occurred while parsing
   * the files
   */
  errMsgs: ParsingError[];

  /** A list of the ids of the subject nodes */
  localNodes: string[];

  /** A list of the generated mcf string for 
   * each CSV row
   */
  datapoints: Object[];
}
/**
 * Parses App state's files list.
 * @param {Array<Blob>} fileList The list of blobs to be parsed.
 * @return {Object} An object containing the ids of the subject nodes and any
 *     parsing error message objects.
 */
async function readFileList(fileList: Blob[]) {
  // Get parsing errors and nodes
  const nodes = await getNodes(fileList);

  // Get timeData
  const timeData: Series[] = getTimeData(nodes.datapoints);

  return {...nodes, timeData};
}

/** Parse files and get the local nodes
 * @param {Array<Blob>} fileList the list of blobs to be parsed
 * @return {Object} an object containing all of the ids of the 
 *    subject nodes and the error messages
 */
async function getNodes(fileList: Blob[]) {
  let curTmcf = null;
  const finalReturn: ParseFileResponse = {'errMsgs': [], 'localNodes': [], 'datapoints': []};

  for (const file of fileList) {
    const fileName = (file as File).name;
    const fileExt = fileName.split('.').pop();

    if (fileExt === 'mcf') {
      const mcfOut = await ParseMcf.readFile(file);

      if (mcfOut['errMsgs'].length !== 0) {
        finalReturn['errMsgs'] = finalReturn['errMsgs'].concat([{
          'file': fileName,
          'errs': mcfOut['errMsgs'],
        }]);
      }
      
      finalReturn['localNodes'] =
        finalReturn['localNodes'].concat(mcfOut['localNodes']);
    } else if (fileExt === 'tmcf') {
      curTmcf = file;
    } else {
      if (curTmcf) {
        const tmcf = curTmcf;
        const tmcfOut =
          await ParseTmcf.generateMcf(curTmcf, file).then((mcf) => {
            const mcfParser = new ParseMcf((tmcf as File).name + '&' + fileName);
            return mcfParser.parseMcfStr(mcf as string);
          });

        const datapoints = await ParseTmcf.generateDataPoints(curTmcf, file);
        finalReturn['datapoints'] = finalReturn['datapoints'].concat([datapoints]);

        if (tmcfOut['errMsgs'].length !== 0) {
          finalReturn['errMsgs'] =
            finalReturn['errMsgs'].concat({
              'file': (tmcf as File).name,
              'errs': tmcfOut['errMsgs'],
            });
        }
        finalReturn['localNodes'] =
          finalReturn['localNodes'].concat(tmcfOut['localNodes']);
      }
      curTmcf = null;
    }
  }
  return finalReturn;
}

/** Group nodes and find all time series 
 * @param {Object[]} datapoints the time series data
 * @return {Series[]} an array of time series in the data  
*/
function getTimeData(datapoints: Object[]) {
  // Turn from array of objects (one per file) to one big object

  const allData: any = {};
  for(const data of datapoints) {
    const allSeries = Object.keys(data);
    for(const series of allSeries) {
      allData[series] = (allData[series]) ? allData[series] : {};
      allData[series] = {...allData[series], ...(data as any)[series]};
    }
  }

  // Turn from object to series
  const output = [];
  const allSeries = Object.keys(allData);
  for(const series of allSeries) {
    output.push(parseSeries(series, allData[series]));
  }

  return output;
}

/**
 * Takes in the facet string generated when parsing the file
 * and return an object of type Series
 * @param {string} facets the facets defining the series 
 * @param {Object} values the values for the series
 * @returns {Series} the datapoint as a Series object
 */
function parseSeries(facets: string, values: Object) {
  const [observationAbout, variableMeasured, provenance, measurementMethod, observationPeriod, unit, scalingFactor] = facets.split(",");
  const x = [];
  const y = [];
  for (const date of Object.keys(values)) {
    x.push(parseFloat(date));
    y.push(parseFloat((values as any)[date]));
  }

  x.sort();
  y.sort();
  
  return {
    id: facets,
    x,
    y,
    observationAbout,
    variableMeasured,
    provenance,
    measurementMethod,
    observationPeriod,
    unit,
    scalingFactor: parseFloat(scalingFactor)
  }
}

/**
  * Clears the backend data. Called when a user presses the 'Clear Files'
  * button.
  */
function clearFiles() {
  Node.nodeHash = {};
  ParseMcf.localNodeHash = {};
}

/**
  * Retreives a node specified by the id. If shouldCreateRemote is true, then
  * the dcid of the retreieved node will attempt to be set. The
  * shouldCreateRemote param is true when the user uses the search bar in the UI
  * so that a node is always found. The node properties will display as blank
  * and the node id will be colored red if the node does not exist in the KG.
  *
  * @param {String} id The id (including namespace) of the node to be retreived.
  * @param {boolean} shouldCreateRemote Indicates is the dcid of the retreieved
  *     node should be set to id.
  * @return {Node} The retreived node with the given id.
  */
function retrieveNode(id: string, shouldCreateRemote: boolean) {
  const retrieved = Node.getNode(id);
  if (shouldCreateRemote) {
    retrieved.setDCID(id.replace('dcid:', ''));
  }
  return retrieved;
}

/**
  * Determines if passed in object is a Node object by calling the static Node
  * class function.
  *
  * @param {Object} obj The object to determine if it is of Node type.
  * @return {boolean} True if obj is of Node type and false otherwise.
  */
function isNodeObj(obj: Object) {
  return Node.isNode(obj);
}

/**
  * Returns the class that a node should be contained in based on how it is
  * resolved locally and remotely.
  *
  * @param {Node} target The node object whose element color needs to be found.
  * @return {String} The appropriate css class for the node.
  */
async function getElemClass(target: Node) {
  if (!target) {
    return null;
  }
  if (target.existsInKG) {
    return 'exist-in-kg';
  }

  return target.setExistsInKG().then(() => {
    if (target.existsInKG) {
      return 'exist-in-kg';
    }

    if (!target.dcid && target.localId &&
        target.localId in ParseMcf.localNodeHash) {
      return 'exist-in-local';
    }

    if (!target.dcid && !((target.localId as string) in ParseMcf.localNodeHash)) {
      return 'not-in-local';
    }
    return 'not-in-kg';
  });
}

export {
  readFileList,
  clearFiles,
  retrieveNode,
  isNodeObj,
  getElemClass,
};
