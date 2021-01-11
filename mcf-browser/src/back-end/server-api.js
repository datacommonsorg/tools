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
 * Parses App state's files list.
 * @param {Array<Blob>} fileList The list of blobs to be parsed.
 * @return {Object} An object containing the ids of the subject nodes and any
 *     parsing error message objects.
 */
async function readFileList(fileList) {
  console.log(fileList);
  let curTmcf = null;
  const finalReturn = {'errMsgs': [], 'localNodes': []};

  for (const file of fileList) {
    const fileExt = file.name.split('.').pop();

    if (fileExt === 'mcf') {
      const mcfOut = await ParseMcf.readFile(file);
      console.log(mcfOut);
      finalReturn['errMsgs'] = finalReturn['errMsgs'].concat({
        'file':file.name,
        'errs': mcfOut['errMsgs'],
      });
      finalReturn['localNodes'] =
        finalReturn['localNodes'].concat(mcfOut['localNodes']);
    } else if (fileExt === 'tmcf') {
      curTmcf = file;
    } else {
      if (curTmcf) {
        const tmcf = curTmcf;
        const tmcfOut =
          await ParseTmcf.generateMcf(curTmcf, file).then((mcf) => {
            console.log(mcf);
            const mcfParser = new ParseMcf(tmcf.name + '&' + file.name);
            return mcfParser.parseMcfStr(mcf);
          });
        finalReturn['errMsgs'] =
          finalReturn['errMsgs'].concat({
            'file':tmcf.name,
            'errs': tmcfOut['errMsgs'],
          });
        finalReturn['localNodes'] =
          finalReturn['localNodes'].concat(tmcfOut['localNodes']);
      }
      curTmcf = null;
    }
  }
  return finalReturn;
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
  * Returns the class that a node should be contained in based on how it is
  * resolved locally and remotely.
  *
  * @param {Node} target The node object whose element color needs to be found.
  * @return {String} The appropriate css class for the node.
  */
async function getElemClass(target) {
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

    if (!target.dcid && !(target.localId in ParseMcf.localNodeHash)) {
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
