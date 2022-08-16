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
  const variableMeasured1 = 'dcs:CumulativeCount_MedicalTest_COVID_19';
  const observationAbout1 = 'geoId/12345';
  const provenance1 = 'geoId/12345';
  const measurementMethod1 = 'dcs:CovidTrackingProject';
  const observationPeriod1 = 'P1Y';
  const unit1 = 'Percent';
  const scalingFactor1 = 100;

  const id1 = Series.toID(
      variableMeasured1,
      observationAbout1,
      provenance1,
      measurementMethod1,
      observationPeriod1,
      unit1,
      scalingFactor1,
  );

  expect(id1).toStrictEqual(TestStr.expectedID1);

  const variableMeasured2 = 'dcs:CumulativeCount_MedicalTest_COVID_19';
  const observationAbout2 = 'geoId/12345';
  const provenance2 = undefined;
  const measurementMethod2 = 'dcs:CovidTrackingProject';
  const observationPeriod2 = 'P1Y';
  const unit2 = undefined;
  const scalingFactor2 = 100;

  const id2 = Series.toID(
      variableMeasured2,
      observationAbout2,
      provenance2,
      measurementMethod2,
      observationPeriod2,
      unit2,
      scalingFactor2,
  );

  expect(id2).toStrictEqual(TestStr.expectedID2);
});
