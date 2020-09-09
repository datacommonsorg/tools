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
import {Assertion, Node} from 'graph.js';

const NAMESPACES = ['l', 'schema', 'dcs', 'dcid'];

/**
     * Indicates if a line should be parsed.
     * @param {string} line The line to be checked.
     * @return {boolean} False if the line is a comment or empty, otherwise
     *     true.
     */
function
shouldReadLine(line) {
  if (line.startsWith('//') || line.length === 0 || line.startsWith('#')) {
    return false;
  }
  return true;
}

/**
 * Returns the property label of the line.
 * @param {string} line The line to be read.
 * @return {string|null} The property label if the line has one.
 */
function
getPropLabel(line) {
  if (line.split(':').length >= 2) {
    return line.split(':')[0];
  }

  console.log('ERROR Line does not contain colon: ' + line);
  return null;
}

/**
 * Returns the dcid from a single property value of a line.
 * @param {string} propValue A single property value from a line of mcf.
 * @return {string|null} The dcid if the namespace is valid, otherwise null.
 */
function
getDCIDFromPropValue(propValue) {
  const namespace = propValue.split(':')[0].trim();
  if (NAMESPACES.indexOf(namespace) >= 1) return propValue.split(':')[1].trim();
  return null;
}

/**
 * Returns a node object based on a property value from a line of mcf.
 * @param {string} propValue A single property value from a line of mcf.
 * @param {boolean} namespaceRequired Indicates if a namespace if needed. This
 *     should be true for all lines expect those that start with 'Node:'.
 * @return {Node|null} The node that is either created or retrieved based on the
 *     id given in propValue. Null if node was not successfully retreived.
 */
function
getNodeFromPropValue(propValue, namespaceRequired) {
  if (namespaceRequired && propValue.split(':').length !== 2) {
    console.log('ERROR <getNodeFromPropValue> : ' + propValue);
    return null;
  }
  // get node from a local Id
  if (propValue.startsWith('l:') || !propValue.includes(':')) {
    const localID = propValue.replace('l:', '').trim();
    return Node.getNode(localID, /* shouldCreate */ true, /* isDCID */ false);
  }
  // get node from a dcid
  const dcid = getDCIDFromPropValue(propValue);
  if (dcid) {
    return Node.getNode(dcid, /* shouldCreate */ true,
        /* isDCID */ true);
  }

  console.log('ERROR <getNodeFromPropValue> : ' + propValue);
  return null;
}

/**
 * Parses a string represetnaing a comma separated list of property values from
 * a line of an mcf file. Converts the string into an array where each element
 * is each element is either a Node or string representing the property value.
 *
 * @param {string} propValues A comma separated list of property values.
 * @return {Array<Node|string>} The list of parsed values as an array.
 */
function
parsePropValues(propValues) {
  const values = [];

  for (const propValue of propValues.split(',')) {
    switch (propValue.split(':').length) {
      case 2:
        const targetNode = getNodeFromPropValue(propValue, true);
        if (targetNode) values.push(targetNode);
        break;

      case 1: const value = propValue.trim();
        if (value) values.push(value);
        break;

      default: console.log('ERROR <parsePropValues> too many colons: ' +
                               propValues);
    }
  }
  return values;
}
/** Class responsible for parsing an mcf file. */
class ParseMCF {
  /**
   * Create a ParseMCF object which keeps tracks of the current source node of
   * each triple in the mcf and the provenance, which is the mcf file name.
   */
  constructor() {
    this.curNode = null;
    this.prov = null;
  }

  /**
   * Parses a single line of an mcf file. First determines if the line should be
   * read, then finds the property label, then the property values and creates
   * an Assertion object based on the triplle, given the calling object has a
   * curNode property that acts as the source  and a prov property that gives
   * the provenance for the triple.
   *
   * @param {string} line The line of mcf to be parsed.
   */
  parseLine(line) {
    line = line.trim();

    if (!shouldReadLine(line)) return;

    const propLabel = getPropLabel(line);
    if (!propLabel) return;

    const propValues = line.replace(propLabel + ':', '').trim();
    if (!propValues) return;

    switch (propLabel) {
      case 'Node':
        this.curNode = getNodeFromPropValue(propValues, false);
        Node.nodeLocalHash[this.curNode.localID] = this.curNode;
        break;

      case 'dcid':
        if (this.curNode) {
          this.curNode.setDCID(propValues.replace(/"/g, ''));
        } else {
          console.log('ERROR dcid prop declared before Node:' + line);
        }
        break;

      default:
        const values = parsePropValues(propValues);

        values.forEach((value) => Assertion.addAssertion(
            this.curNode, propLabel, value, this.prov));
    }
  }

  /**
   * Parses each line of the given string of an mcf file after setting the prov
   * property of the calling ParseMCF object.
   * @param {string} mcf The string representation of an mcf file to parse.
   * @param {string} fileName The name of file that mcf string comes from.
   * @return {Object} The mapping from local subject id to node, for home page.
   */
  parseMCFStr(mcf, fileName) {
    this.prov = 'local: ' + fileName;

    const lines = mcf.split('\n');
    for (const line of lines) {
      this.parseLine(line);
    }
    return Node.nodeLocalHash;
  }

  /**
   * Reads an mcf file into a string, then creates ParseMCF object to parse the
   * string.
   * @param {FileObject} file An mcf file from the html file-input element.
   * @return {Promise} Promise resolves to Node.nodeLocalHash after parsing mcf.
   */
  static readFile(file) {
    const fileReader = new FileReader();
    fileReader.readAsText(file);
    return new Promise((res, rej) => {
      fileReader.addEventListener('loadend', (result) => {
        const mcfParser = new ParseMCF();
        res(mcfParser.parseMCFStr(fileReader.result, file.name));
      });

      fileReader.addEventListener('error', rej);
    });
  }
}
export {
  ParseMCF,
  shouldReadLine,
  getPropLabel,
  getNodeFromPropValue,
  parsePropValues,
  getDCIDFromPropValue,
};
