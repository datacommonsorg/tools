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

import {
  ParseMCF,
  getPropLabel,
  getNodeFromPropValue,
  parsePropValues,
  getDCIDFromPropValue,
} from '../parse-mcf.js';
import {Node} from '../graph.js';

test('testing readPropLabel: should output the property label', () => {
  const prop = getPropLabel('prop: dcid:geoId/06');
  expect(prop).toBe('prop');

  const prop2 = getPropLabel('no colon');
  expect(prop2).toBe(null);
});

test('testing parsePropValues: should output property values', () => {
  const undef = parsePropValues('');
  expect(undef).toStrictEqual([]);

  const vals = parsePropValues(' "val1", "val2"');
  expect(vals).toStrictEqual(['"val1"', '"val2"']);

  const val2 = parsePropValues(' dcid:bio/DOID_1, dcid:geoId/06');
  expect(val2[0].dcid).toBe('bio/DOID_1');
  expect(val2[1].dcid).toBe('geoId/06');
});

test('testing getDCID: should output dcid', () => {
  const dcid0 = getDCIDFromPropValue('dcs:geoId/06');
  expect(dcid0).toBe('geoId/06');

  const dcid1 = getDCIDFromPropValue('dcid:geoId/06');
  expect(dcid1).toBe('geoId/06');
});

test('testing getNodeFromPropValue: should output node', () => {
  const lID0 = getNodeFromPropValue('dcs:geoId/06', true);
  expect(lID0.dcid).toBe('geoId/06');
  expect(lID0.localID).toBe('geoId/06');

  const lID1 = getNodeFromPropValue('l:geoId/05', true);
  expect(lID1.dcid).toBe(null);
  expect(lID1.localID).toBe('geoId/05');

  const lID2 = getNodeFromPropValue('geoId/04', false);
  expect(lID2.dcid).toBe(null);
  expect(lID2.localID).toBe('geoId/04');
});

test('testing setting a dcid for curNode', () => {
  const prov = 'local: file_name';
  const mcfParser = new ParseMCF(prov);
  mcfParser.parseLine('Node: LocalIndiaNode');
  expect(mcfParser.curNode.localID).toBe('LocalIndiaNode');
  expect(mcfParser.curNode.dcid).toBe(null);

  mcfParser.parseLine('dcid: "country/IND"');
  expect(mcfParser.curNode.localID).toBe('LocalIndiaNode');
  expect(mcfParser.curNode.dcid).toBe('country/IND');

  mcfParser.parseLine('Node: LocalObsNode');
  expect(mcfParser.curNode.localID).toBe('LocalObsNode');
  expect(mcfParser.curNode.dcid).toBe(null);
});

test('testing parseLine: ', () => {
  const prov = 'local: file_name';
  const mcfParser = new ParseMCF();
  mcfParser.prov = prov;
  mcfParser.parseLine('//testProp: "textVal"');
  expect(mcfParser.curNode).toStrictEqual(null);

  const prevNode0 = Node.getNode('geoId/00', true, true);
  mcfParser.curNode = prevNode0;
  mcfParser.parseLine('//testProp: "textVal"');
  expect(mcfParser.curNode).toStrictEqual(prevNode0);

  mcfParser.parseLine('Node: dcid:geoId/06');
  const newNode = mcfParser.curNode;
  expect(newNode.dcid).toBe('geoId/06');

  mcfParser.parseLine('testProp: "textVal"');
  const curNode = mcfParser.curNode;
  expect(curNode.assertions.property).toBe('testProp');
  expect(curNode.assertions.target).toBe('"textVal"');
  expect(curNode.assertions.provenance).toBe(prov);

  mcfParser.curNode = Node.getNode('geoId/08', true, true);
  mcfParser.parseLine('testNodeProp: dcid:geoId/09');
  const curNode2 = mcfParser.curNode;
  expect(curNode2.assertions.src.dcid).toBe('geoId/08');
  expect(curNode2.assertions.property).toBe('testNodeProp');
  expect(curNode2.assertions.target.dcid).toBe('geoId/09');
  expect(curNode2.assertions.provenance).toBe(prov);

  const objNode = Node.getNode('geoId/09', false, true);
  expect(objNode.invAssertions.src.dcid).toBe('geoId/08');
  expect(objNode.invAssertions.provenance).toBe(prov);
  expect(objNode.invAssertions.property).toBe('testNodeProp');
  expect(objNode.invAssertions.target.dcid).toBe('geoId/09');
});
