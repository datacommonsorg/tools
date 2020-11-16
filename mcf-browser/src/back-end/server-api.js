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

import {Node} from './graph.js';
import {ParseMcf} from './parse-mcf.js';
import {ParseTmcf} from './parse-tmcf.js';

/**
 * Parses App state's fileList to find either one mcf file or one set of
 * tmcf+csv. Parses the files according to their file type.
 * @param {Array<FileBlob>} fileList The list of files to load into memory.
 * @return {Object} An object containing the ids of the subject nodes and any
 *     parsiing errorr messagges.
 */
async function readFileList(fileList) {
  let tmcfFile;
  let csvFile;
  let mcfFile;

  // parse file list
  for (const file of fileList) {
    if (file.name.endsWith('.tmcf')) {
      tmcfFile = file;
    } else if (file.name.endsWith('.csv')) {
      csvFile = file;
    } else {
      mcfFile = file;
    }
  }

  if (mcfFile) {
    // read mcf file
    return ParseMcf.readFile(mcfFile);
  }

  if (tmcfFile && csvFile) {
    // generate mcf string, then parse it
    return ParseTmcf.generateMcf(tmcfFile, csvFile).then((mcf) => {
      console.log(mcf);
      const mcfParser = new ParseMcf(tmcfFile.name + '&' + csvFile.name);
      return mcfParser.parseMcfStr(mcf);
    });
  }
  return {'errMsgs': [], 'localNodes': []};
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
function retrieveNode(id, shouldCreateRemote) {
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
function isNodeObj(obj) {
  return Node.isNode(obj);
}

/**
  * Returns the color that a node should be displayed as in the UI. This String
  * is used as the jsx element id for the text containing the node id.
  * Blue = dcid exists in the DC KG
  * Purple = no dcid, local id is resolved in the local data
  * Orange = no dcid, local id is unresolved
  * Red = default, including dcid does not exist in KG
  *
  * @param {Node} target The node object whose element color needs to be found.
  * @return {String} The appropriate display color for the node.
  */
async function getElemId(target) {
  if (!target) {
    return null;
  }
  if (target.existsInKG) {
    return 'blue';
  }

  return target.setExistsInKG().then(() => {
    if (target.existsInKG) {
      return 'blue';
    }

    if (!target.dcid && target.localId &&
        target.localId in ParseMcf.localNodeHash) {
      return 'purple';
    }

    if (!target.dcid && !(target.localId in ParseMcf.localNodeHash)) {
      return 'orange';
    }
    return 'red';
  });
}

export {
  readFileList,
  clearFiles,
  retrieveNode,
  isNodeObj,
  getElemId,
};
