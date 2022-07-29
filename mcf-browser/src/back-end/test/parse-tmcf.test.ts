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
import {ParseTmcf} from '../parse-tmcf';
import * as TestStr from './test-strs';

test('testing getLocalIDFromEntityID', () => {
  const parser = new ParseTmcf();
  parser.csvIndex = 8;
  const localId = parser.getLocalIdFromEntityId('E:COVIDTracking_States->E0');
  expect(localId).toBe('COVIDTracking_States_E0_R8');
});

test('testing fillPropertyValues', () => {
  const parser = new ParseTmcf();
  parser.csvIndex = 8;
  const row = {
    Col1: 'dcid:propVal1',
    Col2: 'dcid:propVal2',
  };

  const templatePropVals1 = 'C:TestSet->Col1, C:TestSet->Col2';
  const expected1 = 'dcid:propVal1, dcid:propVal2';
  const filledPropVals = parser.fillPropertyValues(templatePropVals1, row);
  expect(filledPropVals).toBe(expected1);

  const templatePropVals2 = 'E:TestSet->E0, E:TestSet->E1';
  const expected2 = 'l:TestSet_E0_R8, l:TestSet_E1_R8';
  const filledPropVals2 = parser.fillPropertyValues(templatePropVals2, row);
  expect(filledPropVals2).toBe(expected2);
});

test('testing fillTemplateFromRow', () => {
  const parser = new ParseTmcf();
  parser.csvIndex = 8;
  const filledTemp = parser.fillTemplateFromRow(
      TestStr.testTMCF2,
      TestStr.testCSV2[0],
  );
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
  const filledTemp2 = parser.fillTemplateFromRow(template, row);
  expect(filledTemp2).toBe(expectedMCF);
});

test('testing csvToMCF', () => {
  const parser = new ParseTmcf();
  const mcf = parser.csvToMcf(TestStr.testTMCF1, TestStr.testCSV1);
  expect(mcf).toBe(TestStr.expectedMCF1);
});
