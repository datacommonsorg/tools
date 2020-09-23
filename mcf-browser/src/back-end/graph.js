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
  getExistsInKG,
  getRemotePropertyLabels,
  getRemotePropertyValues,
  getValueFromValueObj,
} from './utils.js';

/** Class representation of a single Node in the KG. */
class Node {
  /**
   * Universal id of the node. Every Node obj has a localId, which is either a
   * local reference used in an uplaoded file, or the dcid if the node is never
   * referred to locally (remote only Node).
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
   * @type {?string}
   */
  dcid;
  /**
   * The head of a linked list of Assertion objects representing the outgoing
   * triples of the Node object.
   * @type {?Assertion}
   */
  assertions;
  /**
   * The head of a linked list of Assertion objects representing the incoming
   * triples of the Node object.
   * @type {?Assertion}
   */
  invAssertions;

  /**
   * Create a Node based on a given id.
   * @param {string} id The id of the node to create.
   */
  constructor(id) {
    this.localId = id;
    this.alreadyFetched = false;
    this.existsInKG = false;
    this.dcid = null;
    this.assertions = null;
    this.invAssertions = null;
  }

  /**
   * Indicates if a given object is an instance of Node class.
   * @param {Object} obj The object to check.
   * @return {boolean} True if the object is an instance of Node.
   */
  static isNode(obj) { return obj instanceof Node; }

  /**
   * Returns a node with the given ID, creates a new node if shouldCreate is
   * true, or null if the node does not exist and a node should not be created.
   *
   * @param {string} id The id of the node to find.
   * @param {boolean} shouldCreate True if a new Node should be created if it
   *     does not already exist.
   * @return {Node|null} The found node if it exists or is created.
   */
  static getNode(id, shouldCreate) {
    const existing = Node.nodeHash[id];
    if (existing) {
      return existing;
    }

    if (shouldCreate) {
      const newNode = new Node(id);
      Node.nodeHash[id] = newNode;
      return newNode;
    }
    return null;
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

    if (!this.dcid || this.dcid !== this.localId) {
      localRef = '[l:' + this.localId + ']';
    }
    return [ dcidRef, localRef ].join(' ').trim();
  }

  /**
   * Sets the dcid of Node object. Checks if a separate node based on the dcid
   * already exists. If remote node exists, then the remote node is absorbed by
   * current node via mergeNode() method.
   *
   * @param {string} dcid The dcid to be added to the Node object.
   */
  setDCID(dcid) {
    const remote = Node.nodeHash[dcid];
    if (remote) {
      this.mergeNode(remote);
    }
    this.dcid = dcid;
    Node.nodeHash[dcid] = this;
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

    absorbedNode.getAssertions().forEach((assert) => {
      assert.src = this;
      assert.nextAssertion = this.assertions;
      this.assertions = assert;
    });

    absorbedNode.getInvAssertions().forEach((invAssert) => {
      invAssert.target = this;
      invAssert.invNextAssertion = this.invAssertions;
      this.invAssertions = invAssert;
    });
  }

  /**
   * Sets the property existsInKG to true if the Node has triples in the DC KG.
   */
  async setExistsInKG() {
    if (!this.dcid || this.existsInKG) {
      return;
    }
    this.existsInKG = await getExistsInKG(this.dcid);
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
    for (const label of propLabels) {
      await getRemotePropertyValues(this.dcid, label, isInverse)
          .then((valueList) => {
            if (!valueList) {
              throw new Error('No property values for dcid: ' + this.dcid +
                              ' label: ' + label);
            }

            valueList.forEach((valueObj) => {
              const val = getValueFromValueObj(valueObj);
              const source = isInverse ? val : this;
              const target = isInverse ? this : val;
              new Assertion(source, label, target, valueObj.provenanceId);
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
   * Returns the linked list of assertions of the calling Node as an Array.
   * @return {Array<Assertion>} The array of assertions.
   */
  getAssertions() {
    const assertList = [];
    let assert = this.assertions;

    while (assert) {
      assertList.push(assert);
      assert = assert.nextAssertion;
    }
    return assertList;
  }

  /**
   * Returns the linked list of inverse assertions of the calling Node as an
   * Array.
   * @return {Array<Assertion>} The array of Inverse assertions.
   */
  getInvAssertions() {
    const invAssertList = [];

    let invAssert = this.invAssertions;
    while (invAssert) {
      invAssertList.push(invAssert);
      invAssert = invAssert.invNextAssertion;
    }
    return invAssertList;
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
   * The next Assertion object in a linked list representing the outgoing
   * triples of the Node object stored in src property.
   * @type {?Assertion}
   */
  nextAssertion;
  /**
   * The next Assertion object in a linked list representing the incoming
   * triples of the Node object stored in src property.
   * @type {?Assertion}
   */
  invNextAssertion;

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
    this.nextAssertion = src.assertions;
    src.assertions = this;

    if (target instanceof Object) {
      this.invNextAssertion = target.invAssertions;
      target.invAssertions = this;
    }
  }
}
export {Node, Assertion};
