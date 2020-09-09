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
  csvToMCF, fillTemplateFromRow, getLocalIDFromEntityID,
  getEntityID, getArrowId, parsePropertyValues,
} from '../parse-tmcf.js';
import * as TestStr from './test-strs.js';

test('testing getArrowId', () => {
  const colName = getArrowId('dcid: C:SomeDataset->ResponseOption_Dcid');
  expect(colName).toBe('ResponseOption_Dcid');
});

test('testing getEntitylID', () => {
  const colName = getEntityID('Node: E:COVIDTracking_States->E0');
  expect(colName).toBe('E:COVIDTracking_States->E0');
});

test('testing getLocalIDFromEntityID', () => {
  const index = 8;
  const localID = getLocalIDFromEntityID('E:COVIDTracking_States->E0', index);
  expect(localID).toBe('l:COVIDTracking_States_E0_R8');
});

test('testing parsePropertyValues', () => {
  const index = 8;
  const row = {
    Col1: 'dcid:propVal1',
    Col2: 'dcid:propVal2',
  };

  const templatePropVals1 = 'C:TestSet->Col1, C:TestSet->Col2';
  const expected1 = 'dcid:propVal1, dcid:propVal2';
  const filledPropVals = parsePropertyValues(templatePropVals1, row, index);
  expect(filledPropVals).toBe(expected1);

  const templatePropVals2 = 'E:TestSet->E0, E:TestSet->E1';
  const expected2 = 'l:TestSet_E0_R8, l:TestSet_E1_R8';
  const filledPropVals2 = parsePropertyValues(templatePropVals2, row, index);
  expect(filledPropVals2).toBe(expected2);
});

test('testing fillTemplateFromRow', () => {
  const index = 8;
  const filledTemp =
  fillTemplateFromRow(TestStr.testTMCF2, TestStr.testCSV2[0], index);
  expect(filledTemp).toBe(TestStr.expectedFilledTemp0);

  // testing multiple propValues that are comma separated
  const template =
  'Node: dcid:test1\npropLabel1: C:TestSet->Col1, C:TestSet->Col2';
  const row = {
    Col1: 'dcid:propVal1',
    Col2: 'dcid:propVal2',
  };
  const expectedMCF =
  'Node: dcid:test1\npropLabel1: dcid:propVal1, dcid:propVal2';
  const filledTemp2 = fillTemplateFromRow(template, row, 0);
  expect(filledTemp2).toBe(expectedMCF);
});

test('testing csvToMCF', () => {
  const mcf = csvToMCF(TestStr.testTMCF1, TestStr.testCSV1);
  expect(mcf).toBe(TestStr.expectedMCF1);
});
