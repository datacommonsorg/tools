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

import {Series} from '../data';
import * as TestStr from './test-strs';


test('testing Series.toID', () => {
  const variableMeasured = 'dcs:CumulativeCount_MedicalTest_COVID_19';
  const observationAbout = 'geoId/12345';
  const provenance = 'geoId/12345';
  const measurementMethod = 'dcs:CovidTrackingProject';
  const observationPeriod = 'P1Y';
  const unit = 'Percent';
  const scalingFactor = 100;

  const id = Series.toID(
      variableMeasured,
      observationAbout,
      provenance,
      measurementMethod,
      observationPeriod,
      unit,
      scalingFactor,
  );

  expect(id).toStrictEqual(TestStr.expectedID);
});
