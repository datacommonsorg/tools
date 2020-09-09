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
const API_ROOT = 'https://api.datacommons.org';

/**
 * Generates the url to get property labels for a dcid using DC REST API.
 *
 * @param {string} dcid The dcid to find property labels for.
 * @return {string} The generated url.
 */
function getLabelsTargetUrl(dcid) {
  const targetUrl = (API_ROOT + '/node/property-labels?dcids=' + dcid);
  return targetUrl;
}

/**
 * Generates the url to get property values from the DC KG using REST API.
 *
 * @param {string} dcid The dcid of the node to get the property values for.
 * @param {string} label The property label to query for.
 * @param {boolean} out The direction of label, true indicates outgoing label.
 * @return {string} The generated url.
 */
function getValuesTargetUrl(dcid, label, out) {
  let targetUrl = (API_ROOT + '/node/property-values?dcids=' + dcid +
                   '&property=' + label + '&direction=');
  if (out) {
    targetUrl += 'out';
  } else {
    targetUrl += 'in';
  }
  targetUrl += '&limit=500';
  return targetUrl;
}

/**
 * Gets all property labels of the given dcid that are in the DC KG.
 *
 * @param {string} dcid The dcid of the node to find property labels for.
 * @return {Object} An object containing both 'in' and 'out' property labels.
 */
async function getRemotePropertyLabels(dcid) {
  const targetUrl = getLabelsTargetUrl(dcid);
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
 * @param {boolean} out The direction of label, true indicates outgoing label.
 * @return {Object} An object containing all found values matching the query.
 */
async function getRemotePropertyValues(dcid, label, out) {
  const targetUrl = getValuesTargetUrl(dcid, label, out);
  return fetch(targetUrl)
      .then((res) => res.json())
      .then((data) => JSON.parse(data.payload)[dcid])
      .then((triples) => {
        console.log('url: ' + targetUrl + ', values: ' + triples);
        if (out) {
          return triples.out;
        } else {
          return triples.in;
        }
      });
}

/**
 * Parses an Object returned from the DC REST get_values API to create a Node
 * object from the value's dcid or to return the string value that the object
 * holds.
 *
 * @param {Object} valueObj An object returned from DC REST get_values API.
 * @return {Node | string} The created Node if the value obj has a dcid,
 *     otherwise the string of the value.
 */
function getValueFromValueObj(valueObj) {
  let value;
  if ('dcid' in valueObj) {
    value = Node.getNode(valueObj.dcid, true, true);
    value.existsInKG = true;
  } else if ('value' in valueObj) {
    value = valueObj.value;
  } else {
    console.log('ERROR remote fetch no dcid or value prop: ' + valueObj);
  }
  return value;
}

/** Class representation of a single Node in the KG. */
class Node {
  /**
   * Create a Node based on a given id.
   * @param {string} id The id of the node to find.
   * @param {boolean} isDCID True if the given id is a dcid.
   */
  constructor(id, isDCID) {
    this.localID = id;
    this.alreadyFetched = false;
    this.existsInKG = false;
    if (isDCID) {
      this.dcid = id;
      this.ref = id;
    } else {
      this.dcid = null;
      this.ref = 'l:' + id;
    }
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
   * Returns a node with the given ID, creates a new node if shouldCreate is
   * true, or null if the node does not exist and a node should not be created.
   *
   * @param {string} id The id of the node to find.
   * @param {boolean} shouldCreate True if a new Node should be created if it
   *     does not already exist.
   * @param {boolean} isDCID True if the given id is a dcid.
   * @return {Node|null} The found node if it exists or is created.
   */
  static getNode(id, shouldCreate, isDCID) {
    let existing;

    // check if the DCID can be converted to localID
    if (isDCID) {
      existing = Node.nodeHash[Node.dcidToLocal[id]];
      if (existing) {
        return existing;
      }
    }

    // check if id is in node hash already (cache)
    existing = Node.nodeHash[id];
    if (existing) {
      return existing;
    }

    if (shouldCreate) {
      const newNode = new Node(id, isDCID);
      Node.nodeHash[id] = newNode;
      return newNode;
    }
    return null;
  }

  /**
   * Sets the dcid of Node object and adds the dcid to localId mapping to
   * Node.dcidToLocal
   *
   * @param {string} dcid The dcid to be added to the Node object.
   */
  setDCID(dcid) {
    const remote = Node.nodeHash[dcid];
    if (remote) {
      this.mergeNode(remote);
    }
    this.dcid = dcid;
    Node.dcidToLocal[dcid] = this.localID;
    Node.nodeHash[dcid] = this;
  }

  /**
   * Moves the assertions and invAssertions from the given param node to the
   * calling Node object by changing the src property for assertions and the
   * target property of the invAssertions.
   *
   * @param {Node} absorbedNode The node object whose triples should be copied.
   */
  mergeNode(absorbedNode) {
    const aquiredAsserts = absorbedNode.getAssertions();
    for (const assert of aquiredAsserts) {
      assert.src = this;
      assert.nextAssertion = this.assertions;
      this.assertions = assert;
    }

    const aquiredInvAsserts = absorbedNode.getInvAssertions();
    for (const invAssert of aquiredInvAsserts) {
      invAssert.target = this;
      invAssert.nextInvAssertion = this.invAssertions;
      this.invAssertions = invAssert;
    }
  }

  /**
   * Sets the property existsInKG to true if the Node has triples in the DC KG.
   */
  async setExistsInKG() {
    if (!this.dcid || this.existsInKG) {
      return;
    }

    const url = API_ROOT + '/node/triples?dcids=' + this.dcid + '&limit=1';
    const curNode = this;

    return fetch(url).then((res) => res.json()).then((data) => {
      if (JSON.parse(data.payload)[curNode.dcid]) {
        curNode.existsInKG = true;
      }
    });
  }

  /**
   * Stores remote triples as assertions and invAssertions of the calling Node
   * object. Sets the alreadyFetched property to true if data is fetched.
   */
  async fetchRemoteData() {
    const curNode = this;

    if (curNode.alreadyFetched || !curNode.dcid) {
      return;
    }

    await getRemotePropertyLabels(curNode.dcid).then(async (allLabels) => {
      // create Assertions for each triple current node is source
      for (const label of allLabels.outLabels) {
        await getRemotePropertyValues(curNode.dcid, label, true)
            .then((valueList) => {
              if (!valueList) {
                console.log('ERROR: could not find value for node: ' +
                            curNode.dcid + ', label: ' + label);
                return;
              }
              for (const valueObj of valueList) {
                const target = getValueFromValueObj(valueObj);
                Assertion.addAssertion(curNode, label, target,
                    valueObj.provenanceId);
              }
            });
      }

      // create Inverse Assertion for each triple current node is target
      for (const label of allLabels.inLabels) {
        await getRemotePropertyValues(curNode.dcid, label, false)
            .then((valueList) => {
              for (const valueObj of valueList) {
                const source = getValueFromValueObj(valueObj);
                Assertion.addAssertion(source, label, curNode,
                    valueObj.provenanceId);
              }
            });
      }
    });
    curNode.alreadyFetched = true;
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

Node.nodeLocalHash = {}; // stores mapping of mcf local subject IDs to the Node
Node.dcidToLocal = {}; // stores mapping of dcids to local id equivalents
Node.nodeHash = {}; // stores all created nodes

/** Class representation of a single Assertion (triple) in the KG. */
class Assertion {
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

  /**
   * Creates a new Assertion object given the params.
   * @param {Node} src The source or subject of the triple.
   * @param {string} property The property label of the triple.
   * @param {Node|string} target The predicate or target of the triple.
   * @param {string} provenance The provenance of the triple.
   */
  static addAssertion(src, property, target, provenance) {
    new Assertion(src, property, target, provenance);
  }
}
export {
  Assertion,
  Node,
  getRemotePropertyLabels,
  getRemotePropertyValues,
  getValueFromValueObj,
};
