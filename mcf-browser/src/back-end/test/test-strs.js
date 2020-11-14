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
/** File contains strings used in parse-tmcf.test.js */
export const testTMCF1 = `
Node: E:SomeDataset->E1
typeOf: ResponseOption
dcid: C:SomeDataset->ResponseOption_Dcid
name: C:SomeDataset->ResponseOption_Name
identifier: C:SomeDataset->ResponseOption_Identifier
text: C:SomeDataset->ResponseOption_Text

Node: E:SomeDataset->E2
hasResponseOption: E:SomeDataset->E1
typeOf: SurveyItem
dcid: C:SomeDataset->SurveyItem_Dcid

Node: E:COVIDTracking_States->E0
typeOf: dcs:StatVarObservation
variableMeasured: dcs:CumulativeCount_MedicalTest_COVID_19
measurementMethod: dcs:CovidTrackingProject
observationAbout: C:COVIDTracking_States->GeoId
observationDate: C:COVIDTracking_States->Date
value: C:COVIDTracking_States->CumulativeCount_MedicalTest_COVID_19
`;
export const testCSV1 = [
  {
    ResponseOption_Dcid : 'row1_resop_dcid',
    ResponseOption_Name : 'row1_resop_name',
    ResponseOption_Identifier : 'row1_resop_id',
    ResponseOption_Text : 'row1_resop_text',
    SurveyItem_Dcid : 'row1_survey_dcid',
    GeoId : 'row1_geoid',
    Date : 'row1_date',
    CumulativeCount_MedicalTest_COVID_19 : 'row1_test_count',
  },
  {
    ResponseOption_Dcid : 'row2_resop_dcid',
    ResponseOption_Name : 'row2_resop_name',
    ResponseOption_Identifier : 'row2_resop_id',
    ResponseOption_Text : 'row2_resop_text',
    SurveyItem_Dcid : 'row2_survey_dcid',
    GeoId : 'row2_geoid',
    Date : 'row2_date',
    CumulativeCount_MedicalTest_COVID_19 : 'row2_test_count',
  },
];
export const expectedMCF1 = `
Node: SomeDataset_E1_R1
typeOf: ResponseOption
dcid: row1_resop_dcid
name: row1_resop_name
identifier: row1_resop_id
text: row1_resop_text

Node: SomeDataset_E2_R1
hasResponseOption: l:SomeDataset_E1_R1
typeOf: SurveyItem
dcid: row1_survey_dcid

Node: COVIDTracking_States_E0_R1
typeOf: dcs:StatVarObservation
variableMeasured: dcs:CumulativeCount_MedicalTest_COVID_19
measurementMethod: dcs:CovidTrackingProject
observationAbout: row1_geoid
observationDate: row1_date
value: row1_test_count


Node: SomeDataset_E1_R2
typeOf: ResponseOption
dcid: row2_resop_dcid
name: row2_resop_name
identifier: row2_resop_id
text: row2_resop_text

Node: SomeDataset_E2_R2
hasResponseOption: l:SomeDataset_E1_R2
typeOf: SurveyItem
dcid: row2_survey_dcid

Node: COVIDTracking_States_E0_R2
typeOf: dcs:StatVarObservation
variableMeasured: dcs:CumulativeCount_MedicalTest_COVID_19
measurementMethod: dcs:CovidTrackingProject
observationAbout: row2_geoid
observationDate: row2_date
value: row2_test_count
`;
export const testTMCF2 = `
Node: E:COVIDTracking_States->E0
typeOf: dcs:StatVarObservation
variableMeasured: dcs:CumulativeCount_MedicalTest_COVID_19
measurementMethod: dcs:CovidTrackingProject
observationAbout: C:COVIDTracking_States->GeoId
observationDate: C:COVIDTracking_States->Date
value: C:COVIDTracking_States->CumulativeCount_MedicalTest_COVID_19

Node: E:COVIDTracking_States->E1
typeOf: dcs:StatVarObservation
variableMeasured: dcs:CumulativeCount_MedicalTest_COVID_19_Positive
measurementMethod: dcs:CovidTrackingProject
observationAbout: C:COVIDTracking_States->GeoId
observationDate: C:COVIDTracking_States->Date
value: C:COVIDTracking_States->CumulativeCount_MedicalTest_COVID_19_Positive

Node: E:COVIDTracking_States->E2
typeOf: dcs:StatVarObservation
variableMeasured: dcs:CumulativeCount_MedicalTest_COVID_19_Negative
measurementMethod: dcs:CovidTrackingProject
observationAbout: C:COVIDTracking_States->GeoId
observationDate: C:COVIDTracking_States->Date
value: C:COVIDTracking_States->CumulativeCount_MedicalTest_COVID_19_Negative
`;
export const testCSV2 = [
  {
    Date : '2020-07-07',
    GeoId : 'dcid:geoId/02',
    CumulativeCount_MedicalTest_COVID_19 : 131420,
    CumulativeCount_MedicalTest_COVID_19_Positive : 1184,
    CumulativeCount_MedicalTest_COVID_19_Negative : 130236,
    Count_MedicalTest_COVID_19_Pending : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientRecovered : 560,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientDeceased : 17,
    Count_MedicalConditionIncident_COVID_19_PatientHospitalized : 25,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientHospitalized : '',
    Count_MedicalConditionIncident_COVID_19_PatientInICU : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientInICU : '',
    Count_MedicalConditionIncident_COVID_19_PatientOnVentilator : 1,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientOnVentilator : '',
  },
  {
    Date : '2020-07-07',
    GeoId : 'dcid:geoId/01',
    CumulativeCount_MedicalTest_COVID_19 : 461364,
    CumulativeCount_MedicalTest_COVID_19_Positive : 45785,
    CumulativeCount_MedicalTest_COVID_19_Negative : 415579,
    Count_MedicalTest_COVID_19_Pending : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientRecovered : 22082,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientDeceased : 1033,
    Count_MedicalConditionIncident_COVID_19_PatientHospitalized : 1073,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientHospitalized :
        2961,
    Count_MedicalConditionIncident_COVID_19_PatientInICU : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientInICU : 858,
    Count_MedicalConditionIncident_COVID_19_PatientOnVentilator : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientOnVentilator : 479,
  },
  {
    Date : '2020-07-07',
    GeoId : 'dcid:geoId/05',
    CumulativeCount_MedicalTest_COVID_19 : 350655,
    CumulativeCount_MedicalTest_COVID_19_Positive : 24512,
    CumulativeCount_MedicalTest_COVID_19_Negative : 326143,
    Count_MedicalTest_COVID_19_Pending : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientRecovered : 17834,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientDeceased : 292,
    Count_MedicalConditionIncident_COVID_19_PatientHospitalized : 369,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientHospitalized :
        1604,
    Count_MedicalConditionIncident_COVID_19_PatientInICU : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientInICU : '',
    Count_MedicalConditionIncident_COVID_19_PatientOnVentilator : 81,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientOnVentilator : 247,
  },
  {
    Date : '2020-07-07',
    GeoId : 'dcid:geoId/60',
    CumulativeCount_MedicalTest_COVID_19 : 696,
    CumulativeCount_MedicalTest_COVID_19_Positive : 0,
    CumulativeCount_MedicalTest_COVID_19_Negative : 696,
    Count_MedicalTest_COVID_19_Pending : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientRecovered : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientDeceased : 0,
    Count_MedicalConditionIncident_COVID_19_PatientHospitalized : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientHospitalized : '',
    Count_MedicalConditionIncident_COVID_19_PatientInICU : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientInICU : '',
    Count_MedicalConditionIncident_COVID_19_PatientOnVentilator : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientOnVentilator : '',
  },
  {
    Date : '2020-07-07',
    GeoId : 'dcid:geoId/04',
    CumulativeCount_MedicalTest_COVID_19 : 628797,
    CumulativeCount_MedicalTest_COVID_19_Positive : 105094,
    CumulativeCount_MedicalTest_COVID_19_Negative : 523703,
    Count_MedicalTest_COVID_19_Pending : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientRecovered : 12260,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientDeceased : 1927,
    Count_MedicalConditionIncident_COVID_19_PatientHospitalized : 3356,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientHospitalized :
        5272,
    Count_MedicalConditionIncident_COVID_19_PatientInICU : 869,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientInICU : '',
    Count_MedicalConditionIncident_COVID_19_PatientOnVentilator : 544,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientOnVentilator : '',
  },
  {
    Date : '2020-07-07',
    GeoId : 'dcid:geoId/06',
    CumulativeCount_MedicalTest_COVID_19 : 4896370,
    CumulativeCount_MedicalTest_COVID_19_Positive : 277774,
    CumulativeCount_MedicalTest_COVID_19_Negative : 4618596,
    Count_MedicalTest_COVID_19_Pending : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientRecovered : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientDeceased : 6448,
    Count_MedicalConditionIncident_COVID_19_PatientHospitalized : 7499,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientHospitalized : '',
    Count_MedicalConditionIncident_COVID_19_PatientInICU : 1984,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientInICU : '',
    Count_MedicalConditionIncident_COVID_19_PatientOnVentilator : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientOnVentilator : '',
  },
  {
    Date : '2020-07-07',
    GeoId : 'dcid:geoId/08',
    CumulativeCount_MedicalTest_COVID_19 : 360640,
    CumulativeCount_MedicalTest_COVID_19_Positive : 34257,
    CumulativeCount_MedicalTest_COVID_19_Negative : 326383,
    Count_MedicalTest_COVID_19_Pending : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientRecovered : 4636,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientDeceased : 1542,
    Count_MedicalConditionIncident_COVID_19_PatientHospitalized : 327,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientHospitalized :
        5591,
    Count_MedicalConditionIncident_COVID_19_PatientInICU : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientInICU : '',
    Count_MedicalConditionIncident_COVID_19_PatientOnVentilator : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientOnVentilator : '',
  },
  {
    Date : '2020-07-07',
    GeoId : 'dcid:geoId/09',
    CumulativeCount_MedicalTest_COVID_19 : 530107,
    CumulativeCount_MedicalTest_COVID_19_Positive : 47033,
    CumulativeCount_MedicalTest_COVID_19_Negative : 483074,
    Count_MedicalTest_COVID_19_Pending : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientRecovered : 8210,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientDeceased : 4338,
    Count_MedicalConditionIncident_COVID_19_PatientHospitalized : 83,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientHospitalized :
        10411,
    Count_MedicalConditionIncident_COVID_19_PatientInICU : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientInICU : '',
    Count_MedicalConditionIncident_COVID_19_PatientOnVentilator : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientOnVentilator : '',
  },
  {
    Date : '2020-07-07',
    GeoId : 'dcid:geoId/11',
    CumulativeCount_MedicalTest_COVID_19 : 110377,
    CumulativeCount_MedicalTest_COVID_19_Positive : 10569,
    CumulativeCount_MedicalTest_COVID_19_Negative : 99808,
    Count_MedicalTest_COVID_19_Pending : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientRecovered : 1574,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientDeceased : 561,
    Count_MedicalConditionIncident_COVID_19_PatientHospitalized : 90,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientHospitalized : '',
    Count_MedicalConditionIncident_COVID_19_PatientInICU : 25,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientInICU : '',
    Count_MedicalConditionIncident_COVID_19_PatientOnVentilator : 20,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientOnVentilator : '',
  },
  {
    Date : '2020-07-07',
    GeoId : 'dcid:geoId/10',
    CumulativeCount_MedicalTest_COVID_19 : 128685,
    CumulativeCount_MedicalTest_COVID_19_Positive : 12414,
    CumulativeCount_MedicalTest_COVID_19_Negative : 116271,
    Count_MedicalTest_COVID_19_Pending : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientRecovered : 6815,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientDeceased : 514,
    Count_MedicalConditionIncident_COVID_19_PatientHospitalized : 56,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientHospitalized : '',
    Count_MedicalConditionIncident_COVID_19_PatientInICU : 15,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientInICU : '',
    Count_MedicalConditionIncident_COVID_19_PatientOnVentilator : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientOnVentilator : '',
  },
  {
    Date : '2020-07-07',
    GeoId : 'dcid:geoId/12',
    CumulativeCount_MedicalTest_COVID_19 : 2269194,
    CumulativeCount_MedicalTest_COVID_19_Positive : 213794,
    CumulativeCount_MedicalTest_COVID_19_Negative : 2055400,
    Count_MedicalTest_COVID_19_Pending : 1604,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientRecovered : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientDeceased : 3943,
    Count_MedicalConditionIncident_COVID_19_PatientHospitalized : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientHospitalized :
        16733,
    Count_MedicalConditionIncident_COVID_19_PatientInICU : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientInICU : '',
    Count_MedicalConditionIncident_COVID_19_PatientOnVentilator : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientOnVentilator : '',
  },
  {
    Date : '2020-07-07',
    GeoId : 'dcid:geoId/13',
    CumulativeCount_MedicalTest_COVID_19 : 979452,
    CumulativeCount_MedicalTest_COVID_19_Positive : 100470,
    CumulativeCount_MedicalTest_COVID_19_Negative : 878982,
    Count_MedicalTest_COVID_19_Pending : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientRecovered : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientDeceased : 2899,
    Count_MedicalConditionIncident_COVID_19_PatientHospitalized : 2096,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientHospitalized :
        12226,
    Count_MedicalConditionIncident_COVID_19_PatientInICU : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientInICU : 2471,
    Count_MedicalConditionIncident_COVID_19_PatientOnVentilator : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientOnVentilator : '',
  },
  {
    Date : '2020-07-07',
    GeoId : 'dcid:geoId/66',
    CumulativeCount_MedicalTest_COVID_19 : 15911,
    CumulativeCount_MedicalTest_COVID_19_Positive : 303,
    CumulativeCount_MedicalTest_COVID_19_Negative : 15608,
    Count_MedicalTest_COVID_19_Pending : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientRecovered : 184,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientDeceased : 5,
    Count_MedicalConditionIncident_COVID_19_PatientHospitalized : 3,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientHospitalized : '',
    Count_MedicalConditionIncident_COVID_19_PatientInICU : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientInICU : '',
    Count_MedicalConditionIncident_COVID_19_PatientOnVentilator : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientOnVentilator : '',
  },
  {
    Date : '2020-07-07',
    GeoId : 'dcid:geoId/15',
    CumulativeCount_MedicalTest_COVID_19 : 85673,
    CumulativeCount_MedicalTest_COVID_19_Positive : 1030,
    CumulativeCount_MedicalTest_COVID_19_Negative : 84643,
    Count_MedicalTest_COVID_19_Pending : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientRecovered : 781,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientDeceased : 19,
    Count_MedicalConditionIncident_COVID_19_PatientHospitalized : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientHospitalized : 119,
    Count_MedicalConditionIncident_COVID_19_PatientInICU : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientInICU : '',
    Count_MedicalConditionIncident_COVID_19_PatientOnVentilator : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientOnVentilator : '',
  },
  {
    Date : '2020-07-07',
    GeoId : 'dcid:geoId/19',
    CumulativeCount_MedicalTest_COVID_19 : 339298,
    CumulativeCount_MedicalTest_COVID_19_Positive : 32029,
    CumulativeCount_MedicalTest_COVID_19_Negative : 307269,
    Count_MedicalTest_COVID_19_Pending : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientRecovered : 25594,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientDeceased : 725,
    Count_MedicalConditionIncident_COVID_19_PatientHospitalized : 165,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientHospitalized : '',
    Count_MedicalConditionIncident_COVID_19_PatientInICU : 44,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientInICU : '',
    Count_MedicalConditionIncident_COVID_19_PatientOnVentilator : 20,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientOnVentilator : '',
  },
  {
    Date : '2020-07-07',
    GeoId : 'dcid:geoId/16',
    CumulativeCount_MedicalTest_COVID_19 : 108541,
    CumulativeCount_MedicalTest_COVID_19_Positive : 8052,
    CumulativeCount_MedicalTest_COVID_19_Negative : 100489,
    Count_MedicalTest_COVID_19_Pending : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientRecovered : 2907,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientDeceased : 94,
    Count_MedicalConditionIncident_COVID_19_PatientHospitalized : 50,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientHospitalized : 387,
    Count_MedicalConditionIncident_COVID_19_PatientInICU : 19,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientInICU : 130,
    Count_MedicalConditionIncident_COVID_19_PatientOnVentilator : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientOnVentilator : '',
  },
  {
    Date : '2020-07-07',
    GeoId : 'dcid:geoId/17',
    CumulativeCount_MedicalTest_COVID_19 : 1810956,
    CumulativeCount_MedicalTest_COVID_19_Positive : 149574,
    CumulativeCount_MedicalTest_COVID_19_Negative : 1661382,
    Count_MedicalTest_COVID_19_Pending : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientRecovered : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientDeceased : 7273,
    Count_MedicalConditionIncident_COVID_19_PatientHospitalized : 1385,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientHospitalized : '',
    Count_MedicalConditionIncident_COVID_19_PatientInICU : 320,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientInICU : '',
    Count_MedicalConditionIncident_COVID_19_PatientOnVentilator : 153,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientOnVentilator : '',
  },
  {
    Date : '2020-07-07',
    GeoId : 'dcid:geoId/18',
    CumulativeCount_MedicalTest_COVID_19 : 530075,
    CumulativeCount_MedicalTest_COVID_19_Positive : 48626,
    CumulativeCount_MedicalTest_COVID_19_Negative : 481449,
    Count_MedicalTest_COVID_19_Pending : '',
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientRecovered : 36999,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientDeceased : 2717,
    Count_MedicalConditionIncident_COVID_19_PatientHospitalized : 655,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientHospitalized :
        7333,
    Count_MedicalConditionIncident_COVID_19_PatientInICU : 213,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientInICU : 1540,
    Count_MedicalConditionIncident_COVID_19_PatientOnVentilator : 76,
    CumulativeCount_MedicalConditionIncident_COVID_19_PatientOnVentilator : '',
  },
];

export const expectedFilledTemp0 = `
Node: COVIDTracking_States_E0_R8
typeOf: dcs:StatVarObservation
variableMeasured: dcs:CumulativeCount_MedicalTest_COVID_19
measurementMethod: dcs:CovidTrackingProject
observationAbout: dcid:geoId/02
observationDate: 2020-07-07
value: 131420

Node: COVIDTracking_States_E1_R8
typeOf: dcs:StatVarObservation
variableMeasured: dcs:CumulativeCount_MedicalTest_COVID_19_Positive
measurementMethod: dcs:CovidTrackingProject
observationAbout: dcid:geoId/02
observationDate: 2020-07-07
value: 1184

Node: COVIDTracking_States_E2_R8
typeOf: dcs:StatVarObservation
variableMeasured: dcs:CumulativeCount_MedicalTest_COVID_19_Negative
measurementMethod: dcs:CovidTrackingProject
observationAbout: dcid:geoId/02
observationDate: 2020-07-07
value: 130236
`;
