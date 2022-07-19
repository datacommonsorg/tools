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
 * Module contains Node and Assertion classes which together create a local
 * version of the Data Commons Knowledge Graph.
 */

import {
  doesExistsInKG,
  getRemotePropertyLabels,
  getRemotePropertyValues,
  getValueFromValueObj,
} from './utils.js';

/** Class representation of a single Node in the KG. */
class Node {
  /**
   * The local id used in a parsed mcf file.
   * @type {string}
   */
  localId;

  /**
   * Whether triples from the remote Data Commons Knowledge Graph have already
   * been fetched.
   * @type {boolean}
   */

  alreadyFetched;

  /**
   * Whether the node exists in the Data Commons Knowledge Graph.
   * @type {boolean}
   */
  existsInKG;

  /**
   * Dcid of the node. Set only if a remote id is referred to in a local file or
   * pulled from the Data Commons Knowledge Graph.
   * @type {string}
   */

  dcid;
  /**
   * Array of Assertion objects representing the outgoing triples of the Node
   * object.
   * @type {Array<Assertion>}
   */
  assertions;
  /**
   * Array of Assertion objects representing the incoming triples of the Node
   * object.
   * @type {Array<Assertion>}
   */
  invAssertions;

  /**
   * Create a Node based on a given id.
   * @param {string} id The id of the node to create, including the namespace.
   */
  constructor(id) {
    this.localId = id.startsWith('l:') ? id : null;
    this.dcid = null;

    this.alreadyFetched = false;
    this.existsInKG = false;

    this.assertions = [];
    this.invAssertions = [];

    Node.nodeHash[id] = this;
  }

  /**
   * Returns a node with the given ID. All callers of this function expect a
   * Node object to be returned.If the node does not exist already, then it
   * should be created. If the created node with the requested id does not exist
   * in the local file or in the Data Commons Knowledge Graph, then the
   * front-end will demonstrate this to the user. 
   *
   * @param {string} id The id of the node to find, including the namespace.
   * @return {Node} The found node if it exists or is created.
   */
  static getNode(id) {
    const existing = Node.nodeHash[id];
    return existing ? existing : new Node(id);
  }

  /**
   * Indicates if a given object is an instance of Node class.
   * @param {Object} obj The object to check.
   * @return {boolean} True if the object is an instance of Node.
   */
  static isNode(obj) {
    return obj instanceof Node;
  }

  /**
   * Sets the dcid of Node object. Checks if a separate node based on the dcid
   * already exists. If remote node exists, then the remote node is absorbed by
   * current node via mergeNode() method.
   *
   * @param {string} dcid The dcid to be added to the Node object, should not
   *     include the dcid namespace.
   * @return {boolean} False if the node already has a different dcid, true
   *     otherwise.
   */
  setDCID(dcid) {
    if (this.dcid && this.dcid !== dcid) {
      return false;
    }

    const remote = Node.nodeHash['dcid:' + dcid];
    if (remote && remote !== this) {
      this.mergeNode(remote);
    }
    this.dcid = dcid;
    Node.nodeHash['dcid:' + dcid] = this;
    return true;
  }

  /**
   * Moves the assertions and inverse Assertions from the given param node to
   * the calling Node object by changing the src property for assertions and the
   * target property of the invAssertions.
   *
   * @param {Node} absorbedNode The node object whose triples should be copied.
   */
  mergeNode(absorbedNode) {
    if (this.localId === absorbedNode.localId) {
      return;
    }

    absorbedNode.assertions.forEach((assert) => {
      assert.src = this;
      this.assertions.push(assert);
    });

    absorbedNode.invAssertions.forEach((invAssert) => {
      invAssert.target = this;
      this.invAssertions.push(invAssert);
    });
  }

  /**
   * Sets the property existsInKG to true if the Node has triples in the DC KG.
   */
  async setExistsInKG() {
    if (!this.dcid || this.existsInKG) {
      return;
    }
    this.existsInKG = await doesExistsInKG(this.dcid);
  }

  /**
   * Creates Assertion objects from a list of property labels by calling the
   * helper function getRemotePropertyValues from utils.js to find the values
   * in Data Commons given the current node, a property label, and the direction
   * of the label.
   *
   * @param {Array<string>} propLabels List of property labels associated with
   *     the calling Node object in Data Commons.
   * @param {boolean} isInverse True if the list of labels are incoming labels,
   *     meaning the calling Node object is the target of the triple. False if
   *     the calling Node is the source of the triple.
   */
  async createAssertionsFromLabels(propLabels, isInverse) {
    if(!propLabels || propLabels.length === 0){
      return;
    }

    for (const label of propLabels) {
      await getRemotePropertyValues(this.dcid, label, isInverse)
          .then((valueList) => {
            if (!valueList) {
              throw new Error('No property values for dcid: ' + this.dcid +
                              ' label: ' + label);
            }

            valueList.forEach((valueObj) => {
              const val = getValueFromValueObj(valueObj);

              if (isInverse && !Node.isNode(val)) {
                throw new Error(
                    'Error creating assertion with non Node source');
              }

              const source = isInverse ? val : this;
              const target = isInverse ? this : val;

              // if val is a node and has already been fetched, then the
              // assertion would already be stored in both nodes
              if (!Node.isNode(val) || !val.alreadyFetched) {
                new Assertion(source, label, target, valueObj.provenanceId);
              }
            });
          });
    }
  }

  /**
   * Stores remote triples as assertions and inverse Assertions of the calling
   * Node object. Sets the alreadyFetched property to true if data is fetched.
   */
  async fetchRemoteData() {
    if (this.alreadyFetched || !this.dcid) {
      return;
    }

    await getRemotePropertyLabels(this.dcid).then(async (allLabels) => {
      await this.createAssertionsFromLabels(allLabels.outLabels,
          /* isInverse */ false);
      await this.createAssertionsFromLabels(allLabels.inLabels,
          /* isInverse */ true);
    });
    this.alreadyFetched = true;
  }

  /**
   * Returns the reference to the node that is displayed in browser. If the
   * node has a dcid, then the dcid will be displayed. If the node's local id
   * is different, then the local id is also displayed.
   * Ex: <dcid> [l:<localId>]
   * @return {string} The reference to the node to be displayed.
   */
  getRef() {
    const dcidRef = this.dcid ? this.dcid : '';
    let localRef = '';

    if (this.localId && !this.localId.includes('dcid')) {
      localRef = '[' + this.localId + ']';
    }
    return [dcidRef, localRef].join(' ').trim();
  }
}

Node.nodeHash = {}; // stores all created nodes

/** Class representation of a single Assertion or triple in the KG. */
class Assertion {
  /**
   * The source or subject of the triple.
   * @type {Node}
   */
  src;
  /**
   * The property label or predicate of the triple.
   * @type {string}
   */
  property;
  /**
   * The provenance of the triple.
   * @type {string}
   */
  provenance;
  /**
   * The target or object of the triple.
   * @type {string|Node}
   */
  target;

  /**
   * Create a triple, setting the source's assertion prop to be the new object.
   *
   * @param {Node} src The source or subject of the triple.
   * @param {string} property The property label of the triple.
   * @param {Node|string} target The predicate or target of the triple.
   * @param {string} provenance The provenance of the triple.
   */
  constructor(src, property, target, provenance) {
    this.src = src;
    this.property = property;
    this.provenance = provenance;
    this.target = target;

    src.assertions.push(this);

    if (target instanceof Object) {
      target.invAssertions.push(this);
    }
  }
}

export {Node, Assertion};
