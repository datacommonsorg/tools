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
    'Col1': 'dcid:propVal1',
    'Col2': 'dcid:propVal2',
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

test('testing getFacetAndValueFromRow', () => {
  const parser = new ParseTmcf();
  parser.csvIndex = 8;
  const filledTemp = parser.getFacetAndValueFromRow(
      TestStr.testTMCF2,
      TestStr.testCSV2[0],
  );
  expect(filledTemp).toStrictEqual(TestStr.expectedFacetandValue0);

  // testing multiple propValues that are comma separated
  const template =
    'Node: dcid:test1\npropLabel1: C:TestSet->Col1, C:TestSet->Col2';
  const row = {
    Col1: 'dcid:propVal1',
    Col2: 'dcid:propVal2',
  };
  const filledTemp2 = parser.getFacetAndValueFromRow(template, row);
  expect(filledTemp2).toStrictEqual(TestStr.expectedFacetandValue1);
});

test('testing parseCsv', () => {
  const parser = new ParseTmcf();
  const parsedCsv = parser.parseCsvRows(TestStr.testTMCF1, TestStr.testCSV1);
  const expectedParsedCsv = {
    datapoints: TestStr.expectedDatapoints,
    otherMcfs: TestStr.otherEntities,
  };
  expect(parsedCsv).toStrictEqual(expectedParsedCsv);
});

test('testing getEntityTemplates', () => {
  const parsedTemplate = ParseTmcf.getEntityTemplates(TestStr.testTMCF1);
  expect(parsedTemplate).toStrictEqual(TestStr.expectedTemplate1);
});

test('testing convertCsvToJson', () => {
  const lines = [
    'a,b,c,d,e,f,g',
    '1,2,3,4,5,6,7',
    '9,8,7,6,5,4,3',
    '100,5,2,7,aaaaaa,0,-55',
  ];
  const json = ParseTmcf.convertCsvToJson(lines);

  const expectedJson = [
    {a: '1', b: '2', c: '3', d: '4', e: '5', f: '6', g: '7'},
    {a: '9', b: '8', c: '7', d: '6', e: '5', f: '4', g: '3'},
    {a: '100', b: '5', c: '2', d: '7', e: 'aaaaaa', f: '0', g: '-55'},
  ];

  expect(json).toStrictEqual(expectedJson);

  // test with empty values
  const lines2 = [
    'a,b,c,d,e,f,g',
    ',2,3,4,5,6,7',
    '9,8,7,6,5,4,',
    '100,5,2,7,aaaaaa,,-55',
  ];
  const json2 = ParseTmcf.convertCsvToJson(lines2);

  const expectedJson2 = [
    {a: '', b: '2', c: '3', d: '4', e: '5', f: '6', g: '7'},
    {a: '9', b: '8', c: '7', d: '6', e: '5', f: '4', g: ''},
    {a: '100', b: '5', c: '2', d: '7', e: 'aaaaaa', f: '', g: '-55'},
  ];

  expect(json2).toStrictEqual(expectedJson2);
});
