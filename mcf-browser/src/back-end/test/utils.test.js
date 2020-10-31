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

import {Node} from '../graph.js';
import {
  doesExistsInKG,
  getRemotePropertyLabels,
  getRemotePropertyValues,
  getValueFromValueObj,
} from '../utils.js';

test('testing getRemotePropertyLabels', async () => {
  const labels = await getRemotePropertyLabels('bio/CTD_CHEMBL2_DOID_2055');

  const expectOut = [
    'compoundID',
    'diseaseID',
    'fdaClinicalTrialPhase',
    'name',
    'provenance',
    'typeOf',
  ];
  expect(labels.outLabels).toStrictEqual(expectOut);
  expect(labels.inLabels).toStrictEqual([]);
});
test('testing getRemotePropertyValues', async () => {
  const vals = await getRemotePropertyValues('bio/CTD_CHEMBL2_DOID_2055',
                                             'compoundID', false);
  const expectVals = [ {
    dcid : 'bio/CHEMBL2',
    name : 'CHEMBL2',
    provenanceId : 'dc/x8m41b1',
    types : [ 'ChemicalCompound' ],
  } ];
  expect(vals).toStrictEqual(expectVals);

  const vals2 = await getRemotePropertyValues('bio/138C10', 'subClassOf', true);
  const expectVals2 = [ {
    dcid : 'bio/antigen_138C10',
    name : 'antigen_138C10',
    provenanceId : 'dc/qec1g11',
    types : [ 'Antigen' ],
  } ];
  expect(vals2).toStrictEqual(expectVals2);
});

test('testing getValueFromValueObj', async () => {
  const valueObj = {
    dcid : 'bio/CHEMBL2',
    name : 'CHEMBL2',
    provenanceId : 'dc/x8m41b1',
    types : [ 'ChemicalCompound' ],
  };

  const node = getValueFromValueObj(valueObj);
  const expectNode = new Node('bio/CHEMBL2', true);
  expectNode.existsInKG = true;
  expectNode.setDCID('bio/CHEMBL2');
  expect(node).toStrictEqual(expectNode);
});

test('testing doesExistsInKG', async () => {
  const notInKg = await doesExistsInKG('test');
  expect(notInKg).toStrictEqual(false);

  const inKg = await doesExistsInKG('bio/CHEMBL2');
  expect(inKg).toStrictEqual(true);
});
