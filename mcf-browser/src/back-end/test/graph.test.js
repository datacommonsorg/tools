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

import {Assertion, Node} from '../graph.js';

test('testing setDCID w/ merge', async () => {
  Node.nodeHash = {};

  const remoteNode = Node.getNode('remoteId', true);
  remoteNode.setDCID('remoteId');

  const targetNode = Node.getNode('targetId', true);
  const srcNode = Node.getNode('srcId', true);

  new Assertion(remoteNode, 'label1', 'val1', 'prov');
  new Assertion(remoteNode, 'label2', targetNode, 'prov');
  new Assertion(srcNode, 'label3', remoteNode, 'prov');

  const localNode = Node.getNode('localId', true);
  new Assertion(localNode, 'label4', 'val2', 'prov');
  localNode.setDCID('remoteId');

  const expectedHash = {
    'remoteId' : localNode,
    'localId' : localNode,
    'targetId' : targetNode,
    'srcId' : srcNode,
  };

  expect(Node.nodeHash).toStrictEqual(expectedHash);

  const asserts = localNode.getAssertions();
  expect(asserts.length).toBe(3);

  const invAsserts = localNode.getInvAssertions();
  expect(invAsserts.length).toBe(1);

  // assertions with remoteNode as target should now point to localNode
  const srcAssert = srcNode.assertions;
  expect(srcAssert.target).toStrictEqual(localNode);
});

test('testing merge duplicate assertions', async () => {
  /* Example:
   * Node: localNode
   * propLabel: l:localId, dcid:remoteId
   *
   * Node: l:localId
   * dcid: "remoteId"
   *
   * expected behavior: show the assertion twice to show the user the duplicate
   */

  Node.nodeHash = {};

  const localNode = Node.getNode('localNode', true);
  const localValNode = Node.getNode('localId', true);
  const remoteNode = Node.getNode('remoteId', true);
  remoteNode.setDCID('remoteId');

  new Assertion(localNode, 'propLabel', localValNode, 'prov');
  new Assertion(localNode, 'propLabel', remoteNode, 'prov');

  localValNode.setDCID('remoteId');
  const expectedHash = {
    'remoteId' : localValNode,
    'localId' : localValNode,
    'localNode' : localNode,
  };
  expect(Node.nodeHash).toStrictEqual(expectedHash);

  const asserts = localValNode.getAssertions();
  expect(asserts.length).toStrictEqual(0);

  const invAsserts = localValNode.getInvAssertions();
  expect(invAsserts.length).toStrictEqual(2);
});

test('testing getRef', () => {
  Node.nodeHash = {};

  const node = Node.getNode('localId', true);
  expect(node.getRef()).toBe('[l:localId]');
  node.setDCID('remoteId');
  expect(node.getRef()).toBe('remoteId [l:localId]');
  node.localId = 'sameId';
  node.dcid = 'sameId';
  expect(node.getRef()).toBe('sameId');
});

test('testing setExistsInKG', async () => {
  Node.nodeHash = {};

  const tempNode = Node.getNode('BasePairs171115067', true);
  tempNode.setDCID('BasePairs171115067');
  await tempNode.setExistsInKG();
  expect(tempNode.existsInKG).toBe(true);

  const tempNode2 = Node.getNode('test', true);
  tempNode2.setDCID('test');
  await tempNode2.setExistsInKG();
  expect(tempNode2.existsInKG).toBe(false);

  const tempNode3 = Node.getNode('StatVarObservation', true);
  tempNode3.setDCID('StatVarObservation');
  await tempNode3.setExistsInKG();
  expect(tempNode3.existsInKG).toBe(true);
});

test('testing fetchRemoteData', async () => {
  Node.nodeHash = {};

  const tempNode = Node.getNode('BasePairs171115067', true);
  tempNode.setDCID('BasePairs171115067');
  await tempNode.fetchRemoteData();

  expect(tempNode.getAssertions().length).toEqual(5);
  expect(tempNode.getInvAssertions().length).toEqual(1);
});
