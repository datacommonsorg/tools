/**
 * Copyright 2022 Google LLC
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

import {getTimeData, mergeDataPoints, parseSeries} from '../parse';
import {Series, TimeDataObject} from '../time-series';
import * as TestStr from './test-strs';

test('testing parseSeries', () => {
  const facet =
   'dcs:CumulativeCount_MedicalTest_COVID_19' +
   ',Covid,,dcs:CovidTrackingProject,,,100';
  const values = {
    '2018': 5,
    '2019': 100,
    '2020': 5.5,
    '2021': 63,
  };
  const seriesOutput = parseSeries(facet, values);

  const x = ['2018', '2019', '2020', '2021'];
  const y = [5, 100, 5.5, 63];
  const data = x.map((xValue, index) => {
    return {x: xValue, y: y[index]};
  });
  const expectedSeries = new Series(
      data,
      'dcs:CumulativeCount_MedicalTest_COVID_19',
      'Covid',
      undefined,
      'dcs:CovidTrackingProject',
      undefined,
      undefined,
      100,
  );
  const expectedOutput = {
    series: expectedSeries,
    errMsgs: [],
  };
  expect(seriesOutput).toStrictEqual(expectedOutput);

  // Check error messages when facet string is invalid
  const missingVarMeasuredFacet = ',Covid,,dcs:CovidTrackingProject,,,100';
  const missingVarMeasuredOutput = parseSeries(missingVarMeasuredFacet, values);
  const expectedMissingVarMeasured = {
    series: null,
    errMsgs: [{
      file: '',
      errs: [[
        '',
        missingVarMeasuredFacet,
        'data point is missing variableMeasured',
      ]],
    }],
  };
  expect(missingVarMeasuredOutput).toStrictEqual(expectedMissingVarMeasured);

  const missingObsAboutFacet =
  'dcs:CumulativeCount_MedicalTest_COVID_19,,,dcs:CovidTrackingProject,,,100';
  const missingObsAboutOutput = parseSeries(missingObsAboutFacet, values);
  const expectedMissingObsAbout = {
    series: null,
    errMsgs: [{
      file: '',
      errs: [[
        '',
        missingObsAboutFacet,
        'data point is missing observationAbout',
      ]],
    }],
  };
  expect(missingObsAboutOutput).toStrictEqual(expectedMissingObsAbout);

  const missingBothFacet = ',,,dcs:CovidTrackingProject,,,100';
  const missingBothOutput = parseSeries(missingBothFacet, values);
  const expectedMissingBoth = {
    series: null,
    errMsgs: [{
      file: '',
      errs: [[
        '',
        missingBothFacet,
        'data point is missing variableMeasured and observationAbout',
      ]],
    }],
  };
  expect(missingBothOutput).toStrictEqual(expectedMissingBoth);
});

test('testing mergeDataPoints', () => {
  let datapoints: TimeDataObject = TestStr.datapoints[0];
  for (const data of TestStr.datapoints) {
    datapoints = mergeDataPoints(datapoints, data);
  }

  expect(datapoints).toStrictEqual(TestStr.expectedTimeData);
});

test('testing getTimeData', () => {
  let datapoints: TimeDataObject = TestStr.datapoints[0];
  for (const data of TestStr.datapoints) {
    datapoints = mergeDataPoints(datapoints, data);
  }
  const timeData = getTimeData(datapoints);
  expect(timeData.timeData).toStrictEqual(TestStr.expectedSeries);
  expect(timeData.errMsgs).toStrictEqual([]);
});
