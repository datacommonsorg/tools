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

type ParseFileResponse = {
  /** A list of errors that occurred while parsing
   * the files
   */
  errMsgs: ParsingError[];

  /** A list of the ids of the subject nodes */
  localNodes: string[];
}
/**
 * Parses App state's files list.
 * @param {Array<Blob>} fileList The list of blobs to be parsed.
 * @return {Object} An object containing the ids of the subject nodes and any
 *     parsing error message objects.
 */
async function readFileList(fileList: Blob[]) {
  // Clear previously stored files
  clearFiles();

  // Find TMCF file, if it exists
  let tmcfFile = null;
  for (const file of fileList) {
    const fileName = (file as File).name;
    const fileExt = fileName.split('.').pop();

    if(fileExt === "tmcf"){
      // TODO: confirmed that expected behavior for several 
      // TMCF files is to use the last one
      tmcfFile = file;
    }
  }

  const finalReturn: ParseFileResponse = {'errMsgs': [], 'localNodes': []};

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
      
      finalReturn['localNodes'] = mcfOut['localNodes'];
    } else if (fileExt === 'csv') {
      if (tmcfFile) {
        const tmcfFileName = (tmcfFile as File).name;
        const tmcfOut =
        await ParseTmcf.generateMcf(tmcfFile, file).then((mcf) => {
          const mcfParser = new ParseMcf(tmcfFileName + '&' + fileName);
          return mcfParser.parseMcfStr(mcf as string);
        });

        if (tmcfOut['errMsgs'].length !== 0) {
          finalReturn['errMsgs'] =
            finalReturn['errMsgs'].concat({
              'file': tmcfFileName,
              'errs': tmcfOut['errMsgs'],
            });
        }
        finalReturn['localNodes'] = tmcfOut['localNodes'];
      }
    }
  }
  return finalReturn;
}

/**
  * Clears the backend data. Called when a user presses the 'Clear Files'
  * button or uploads new files.
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
