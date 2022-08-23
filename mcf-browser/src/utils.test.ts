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

import {Series} from './back-end/time-series';
import {groupSeriesByLocations} from './utils';

test('testing groupSeriesByLocations', () => {
  const x = ['2018', '2019', '2020', '2021'];
  const y = [5, 100, 5.5, 63];
  const data1 = x.map((xValue, index) => {
    return {x: xValue, y: y[index]};
  });
  const data2 = x.map((xValue, index) => {
    return {x: xValue, y: 2 * y[index]};
  });
  const data3 = x.map((xValue, index) => {
    return {x: xValue, y: 2 + y[index]};
  });

  const seriesA1 = new Series(
      data1,
      'dcs:CumulativeCount_MedicalTest_COVID_19',
      'New York',
      undefined,
      'dcs:CovidTrackingProject',
      undefined,
      undefined,
      100,
  );
  const seriesA2 = new Series(
      data3,
      'dcs:CumulativeCount_MedicalTest_COVID_19',
      'Texas',
      undefined,
      'dcs:CovidTrackingProject',
      undefined,
      undefined,
      100,
  );
  const seriesA3 = new Series(
      data2,
      'dcs:CumulativeCount_MedicalTest_COVID_19',
      'Alabama',
      undefined,
      'dcs:CovidTrackingProject',
      undefined,
      undefined,
      100,
  );

  const seriesB1 = new Series(
      data2,
      'dcs:Count_MedicalTest_COVID_19',
      'California',
      undefined,
      'dcs:CovidTrackingProject',
      undefined,
      undefined,
      100,
  );

  const seriesList: Series[] = [
    seriesA1, seriesA2, seriesA3, seriesB1,
  ];

  const groups = groupSeriesByLocations(seriesList);
  const expectedGroups = {
    'CumulativeCount_MedicalTest_COVID_19,,CovidTrackingProject,,,100': [
      {
        subGroup: [seriesA1, seriesA2, seriesA3],
        title:
        'CumulativeCount_MedicalTest_COVID_19,,CovidTrackingProject,,,100',
      },
    ],
    'Count_MedicalTest_COVID_19,,CovidTrackingProject,,,100': [
      {
        subGroup: [seriesB1],
        title:
        'Count_MedicalTest_COVID_19,,CovidTrackingProject,,,100',
      },
    ],
  };
  expect(groups).toStrictEqual(expectedGroups);
});
