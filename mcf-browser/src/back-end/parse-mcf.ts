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
 * Parses an mcf file and creates local knowledge graph of the parsed data
 * using Node and Assertion Class objects.
 */

import {Assertion, Node} from './graph';
import {ERROR_MESSAGES, shouldReadLine} from './utils';

const NAMESPACES = {
  'l': 'l',
  'schema': 'dcid',
  'dcs': 'dcid',
  'dcid': 'dcid',
};

type ParsedValue = {
  ns: 'l' | 'schema' | 'dcs' | 'dcid',
  ref: string
};

type ParseFileResponse = {
  /** A list of errors that occurred while parsing
   * the files
   */
  errMsgs: string[][];

  /** A list of the ids of the subject nodes */
  localNodes: string[];
};

/** Class responsible for parsing an mcf file. */
class ParseMcf {
  /**
   * Provenance to be used for any Assertion objects created during parsing,
   * based off of the mcf file name.
   * @type {string}
   */
  prov: string;
  /**
   * Current subject Node for any Assertion created. Set when a 'Node:' property
   * label is parsed.
   * @type {Node}
   */
  curNode: Node | null;
  /**
   * Current line number of the line being parsed, used for identifying location
   * of syntax error in the mcf file.
   * @type {number}
   */

  lineNum: number;

  /**
   * List of error messages regarding mcf syntax that are to be displayed to
   * the user. A single entry of this array should be in the format of:
   * [line number, line, error message]
   * @type {Array<Array<String>>}
   */
  errors: string[][];

  /** Current line being parsed */
  line: string | null;

  static localNodeHash: any;

  /**
   * Create a ParseMcf object which keeps tracks of the current source node of
   * each triple in the mcf and the provenance, which is the mcf file name.
   * @param {string} fileName Name of the file to be parsed.
   */
  constructor(fileName: string) {
    this.prov = fileName;
    this.curNode = null;
    this.lineNum = -1;
    this.errors = [];
    this.line = null;
  }

  /**
   * Parses a string representing a comma separated list of property values
   * from a line of an mcf file. Returns a list having either a string or
   * <namespace, reference> pair.
   *
   * @param {string} propValues A comma separated list of property values.
   * @return {Array<(string|Object)>} Array of
   *     parsed values.
   */
  parsePropValues(propValues: string) {
    const values = [];
    // split propValues on commas which are not enclosed by double quotes
    // split string at each comma followed by even number of double quotes
    // caveat: does not work if quotes are unbalanced
    for (const propValue of propValues.split(/,(?=(?:(?:[^"]*"){2})*[^"]*$)/)) {
      const namespace = propValue.split(':')[0].trim();
      if (namespace in NAMESPACES) {
        values.push({
          ns: namespace,
          ref: propValue.substring(propValue.indexOf(':') + 1).trim(),
        });
      } else if (
        propValue.split(':').length > 1 &&
        !namespace.startsWith('"')
      ) {
        this.errors.push([
          this.lineNum.toString(),
          this.line as string,
          'unrecognized namespace',
        ]);
        return [];
      } else {
        // push property value with surrounding double quotes trimmed
        values.push(propValue.replace(/^[" ]*(.*?)[" ]*$/g, '$1'));
      }
    }
    return values;
  }

  /**
   * Sets curNode variable of the calling ParseMcf object based on the passed in
   * parsed values of a line of mcf, given the property label for the line was
   * 'Node'. The parsed value either is a local reference with or without the
   * 'l' namespace, or it has a remote namespace. If the namespace is remote,
   * then the dcid for curNode is set. Updates localNodeHash mapping to store
   * the subject nodes to be displayed in home screen of browser.
   *
   * @param {Array<string|Object>} parsedValues The array of parsed values from
   *     a line of mcf with property label of 'Node'.
   */
  setCurNode(parsedValues: Object[]) {
    if (parsedValues.length !== 1) {
      this.errors.push([
        this.lineNum.toString(),
        this.line as string,
        ERROR_MESSAGES.CUR_NODE_LENGTH,
      ]);
      return;
    }

    let nodeRef;
    let ns;

    if (parsedValues[0] instanceof Object) {
      // handle case: Node: dcid:remoteRef, which means that
      // parsedValues[0] === {'ns':'dcid', 'ref':'remoteRef' }
      const firstValue = (parsedValues[0]) as ParsedValue;
      ns = firstValue['ns'];
      if (ns === 'dcid') {
        ns = ns + ':';
        nodeRef = firstValue['ref'];
      } else {
        this.errors.push([
          this.lineNum.toString(),
          this.line as string,
          ERROR_MESSAGES.CUR_NODE_NS,
        ]);
        return;
      }
    } else {
      // handle case: Node: localRef, which means parsedValues[0]==='localRef'
      nodeRef = parsedValues[0];
      ns = '';
    }
    // combine the namespace and reference into single id
    const nodeId = 'l:' + ns + nodeRef;
    this.curNode = Node.getNode(nodeId);

    if (ns === 'dcid:') {
      if (this.curNode && !this.curNode.setDCID(nodeRef)) {
        this.errors.push([
          this.lineNum.toString(),
          this.line as string,
          ERROR_MESSAGES.SET_DCID,
        ]);
        return;
      }
      ParseMcf.localNodeHash[ns + nodeRef] = this.curNode;
    } else {
      ParseMcf.localNodeHash[nodeId] = this.curNode;
    }
  }

  /**
   * Sets the dcid of the curNode variable of the calling ParseMcf object given
   * the property label of the line being parsed is 'dcid'.
   * @param {Array<string|Object>} parsedValues The array of parsed values from
   *     a line of mcf with property label of 'dcid'.
   */
  setCurNodeDCID(parsedValues: (string | Object)[]) {
    if (!this.curNode) {
      this.errors.push([
        this.lineNum.toString(),
        this.line as string,
        ERROR_MESSAGES.SET_DCID_NO_CUR,
      ]);
      return;
    }
    if (parsedValues.length !== 1) {
      this.errors.push([
        this.lineNum.toString(),
        this.line as string,
        ERROR_MESSAGES.SET_DCID_MULTIPLE,
      ]);
      return;
    }
    if (typeof parsedValues[0] !== 'string') {
      this.errors.push([
        this.lineNum.toString(),
        this.line as string,
        ERROR_MESSAGES.SET_DCID_REF,
      ]);
      return;
    }

    if (!this.curNode.setDCID(parsedValues[0])) {
      this.errors.push([
        this.lineNum.toString(),
        this.line as string,
        ERROR_MESSAGES.SET_DCID,
      ]);
    }
  }

  /**
   * Create Assertion objects using curNode variable of calling ParseMcf object
   * as the source of the triple and the prov variable of the ParseMcf object
   * as the provenance of the triple.One Assertion object is created for each
   * parsed value given in the array parsedValues.
   *
   * @param {string} propLabel The property label of the triple to be created.
   * @param {Array<string|Object>} parsedValues The parsed values from a line of
   *     mcf, used to create the target for each created triple.
   */
  createAssertionsFromParsedValues(
      propLabel: string,
      parsedValues: (string | Object)[],
  ) {
    if (!this.curNode) {
      this.errors.push([
        this.lineNum.toString(),
        this.line as string,
        ERROR_MESSAGES.ASSERT_NO_CUR,
      ]);
      return;
    }
    for (const val of parsedValues) {
      let target;
      if (val instanceof Object) {
        const parsedVal = val as ParsedValue;
        target = Node.getNode(
            NAMESPACES[parsedVal['ns']] + ':' + parsedVal['ref'],
        );
        if (NAMESPACES[parsedVal['ns']] === 'dcid') {
          if (!target.setDCID(parsedVal['ref'])) {
            this.errors.push([
              this.lineNum.toString(),
              this.line as string,
              ERROR_MESSAGES.SET_DCID,
            ]);
          }
        }
      } else {
        target = val;
      }
      new Assertion(this.curNode, propLabel, target, this.prov);
    }
  }

  /**
   * Parses a single line of an mcf file. First determines if the line should be
   * read, then finds the property label, then the property values and creates
   * an Assertion object based on the triple, given the calling object has a
   * curNode property that acts as the source  and a prov property that gives
   * the provenance for the triple.
   *
   * @param {string} line The line of mcf to be parsed.
   */
  parseLine(line: string) {
    line = line.trim();

    if (!shouldReadLine(line)) {
      return; // not an error
    }

    if (!line.includes(':')) {
      this.errors.push([
        this.lineNum.toString(),
        this.line as string,
        ERROR_MESSAGES.PARSE_NO_COLON,
      ]);
      return;
    }

    const propLabel = line.split(':', 1)[0].trim();
    const propValues = line.substring(line.indexOf(':') + 1).trim();

    if (!propLabel) {
      this.errors.push([
        this.lineNum.toString(),
        this.line as string,
        ERROR_MESSAGES.PARSE_NO_LABEL,
      ]);
      return;
    }
    if (!propValues) {
      // if there is a missing property value, do not return error
      return;
    }

    const parsedValues = this.parsePropValues(propValues);

    switch (propLabel) {
      case 'Node':
        this.setCurNode(parsedValues);
        break;

      case 'dcid':
        this.setCurNodeDCID(parsedValues);
        break;

      default:
        this.createAssertionsFromParsedValues(propLabel, parsedValues);
    }
  }

  /**
   * Parses each line of the given string of an mcf file after setting the prov
   * property of the calling ParseMcf object.
   * @param {string} mcf The string representation of an mcf file to parse.
   * @return {Object} A list of the local node ids and the list of error
   * messages which should be empty if no mcf syntax errors were found.
   */
  parseMcfStr(mcf: string) {
    const lines = mcf.split('\n');
    this.lineNum = 1;

    lines.forEach((line) => {
      this.line = line;
      this.parseLine(line);
      this.lineNum++;
    });

    return {
      localNodes: Object.keys(ParseMcf.localNodeHash),
      errMsgs: this.errors,
    };
  }

  /**
   * Reads an mcf file into a string, then creates ParseMcf object to parse the
   * string.
   * @param {FileObject} file An mcf file from the html file-input element.
   * @return {Promise} Promise returns the result of parseMcfStr.
   */
  static readFile(file: Blob): Promise<ParseFileResponse> {
    const fileReader = new FileReader();
    fileReader.readAsText(file);

    return new Promise((res, rej) => {
      fileReader.addEventListener('loadend', () => {
        const mcfParser = new ParseMcf((file as File).name);
        res(mcfParser.parseMcfStr(fileReader.result as string));
      });
      fileReader.addEventListener('error', rej);
    });
  }
}

ParseMcf.localNodeHash = {}; // stores mapping of mcf subject IDs to the Node

export {ParseMcf};
