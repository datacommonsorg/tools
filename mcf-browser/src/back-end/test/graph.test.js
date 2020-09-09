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
  getRemotePropertyLabels,
  getRemotePropertyValues,
  getValueFromValueObj,
  Node,
} from '../graph.js';

test('testing getRemotePropertyLabels', async () => {
  const labels = await getRemotePropertyLabels('bio/CTD_CHEMBL2_DOID_2055');

  const expectOut = [
    'compoundID', 'diseaseID', 'fdaClinicalTrialPhase', 'name', 'provenance',
    'typeOf',
  ];
  expect(labels.outLabels).toStrictEqual(expectOut);
  expect(labels.inLabels).toStrictEqual([]);
});
test('testing getRemotePropertyValues', async () => {
  const vals = await getRemotePropertyValues('bio/CTD_CHEMBL2_DOID_2055',
      'compoundID', true);
  const expectVals = [{
    dcid: 'bio/CHEMBL2',
    name: 'CHEMBL2',
    provenanceId: 'dc/x8m41b1',
    types: ['ChemicalCompound'],
  }];
  expect(vals).toStrictEqual(expectVals);

  const vals2 =
      await getRemotePropertyValues('bio/138C10', 'subClassOf', false);
  const expectVals2 = [{
    dcid: 'bio/antigen_138C10',
    name: 'antigen_138C10',
    provenanceId: 'dc/qec1g11',
    types: ['Antigen'],
  }];
  expect(vals2).toStrictEqual(expectVals2);
});

test('testing getValueFromValueObj', async () => {
  const valueObj = {
    dcid: 'bio/CHEMBL2',
    name: 'CHEMBL2',
    provenanceId: 'dc/x8m41b1',
    types: ['ChemicalCompound'],
  };

  const node = getValueFromValueObj(valueObj);
  const expectNode = new Node('bio/CHEMBL2', true);
  expectNode.existsInKG = true;
  expect(node).toStrictEqual(expectNode);
});

test('testing fetchRemoteData', async () => {
  const tempNode = Node.getNode('BasePairs171115067', true, true);
  await tempNode.fetchRemoteData();
  // console.log(tempNode);
  expect(tempNode.assertions).toEqual(expect.anything());
  expect(tempNode.assertions.nextAssertion).toEqual(expect.anything());
  expect(tempNode.invAssertions).toEqual(expect.anything());
  expect(tempNode.invAssertions.invNextAssertion).toBe(undefined);
  // TODO can make checks more specific
});

test('testing setExistsInKG', async () => {
  const tempNode = Node.getNode('BasePairs171115067', true, true);
  await tempNode.setExistsInKG();
  expect(tempNode.existsInKG).toBe(true);

  const tempNode2 = Node.getNode('test', true, true);
  await tempNode2.setExistsInKG();
  expect(tempNode2.existsInKG).toBe(false);

  const tempNode3 = Node.getNode('StatVarObservation', true, true);
  await tempNode3.setExistsInKG();
  expect(tempNode3.existsInKG).toBe(true);
});
