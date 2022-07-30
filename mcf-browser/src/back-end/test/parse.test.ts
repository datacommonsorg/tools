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

import {getTimeData, parseSeries} from '../parse';
import {Series} from '../data';
import * as TestStr from './test-strs';

test('testing parseSeries', () => {
  const facets =
  'dcs:CumulativeCount_MedicalTest_COVID_19,,,dcs:CovidTrackingProject,,,100';
  const values = {
    '2018': 5,
    '2019': 100,
    '2020': 5.5,
    '2021': 63,
  };
  const series = parseSeries(facets, values);

  const expectedSeries = new Series(
      ['2018', '2019', '2020', '2021'],
      [5, 100, 5.5, 63],
      'dcs:CumulativeCount_MedicalTest_COVID_19',
      undefined,
      undefined,
      'dcs:CovidTrackingProject',
      undefined,
      undefined,
      100,
  );
  expect(series).toStrictEqual(expectedSeries);
});

test('testing getTimeData', () => {
  const series = getTimeData(TestStr.datapoints);
  expect(series).toStrictEqual(TestStr.expectedSeries);
});
