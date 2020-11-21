# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# A dictionary of stat_vars where place_type->key->stat_var.
# There must be at least one stat_var per place_type.
# The key can be made up, this key will be used to output the data.
# Instead of using the long stat_var name.
# The key will be used to identify the stat_var.

covid19 = {
    "Country": {
        "Cases":
            "CumulativeCount_MedicalConditionIncident_COVID_19_ConfirmedCase",
        "Deaths":
            "CumulativeCount_MedicalConditionIncident_COVID_19_PatientDeceased",
        "Hospitalized":
            "CumulativeCount_MedicalConditionIncident_COVID_19_PatientHospitalized",
        "Recovered":
            "CumulativeCount_MedicalConditionIncident_COVID_19_PatientRecovered",
        "ICU":
            "CumulativeCount_MedicalConditionIncident_COVID_19_PatientInICU"

    },
    "State": {
        "Cases":
            "CumulativeCount_MedicalConditionIncident_COVID_19_ConfirmedOrProbableCase",
        "Deaths":
            "CumulativeCount_MedicalConditionIncident_COVID_19_PatientDeceased",
        "Hospitalized":
            "CumulativeCount_MedicalConditionIncident_COVID_19_PatientHospitalized",
        "Recovered":
            "CumulativeCount_MedicalConditionIncident_COVID_19_PatientRecovered",
        "ICU":
            "CumulativeCount_MedicalConditionIncident_COVID_19_PatientInICU"
    },
    "County": {
        "Cases":
            "CumulativeCount_MedicalConditionIncident_COVID_19_ConfirmedOrProbableCase",
        "Deaths":
            "CumulativeCount_MedicalConditionIncident_COVID_19_PatientDeceased",
        "Hospitalized":
            "CumulativeCount_MedicalConditionIncident_COVID_19_PatientHospitalized",
        "Recovered":
            "CumulativeCount_MedicalConditionIncident_COVID_19_PatientRecovered",
        "ICU":
            "CumulativeCount_MedicalConditionIncident_COVID_19_PatientInICU"
    },
}

socialWellness = {
    "Country": {
        "AbovePovertyInLast12Months":
            "Count_Person_AbovePovertyLevelInThePast12Months",
        "BelowPovertyInLast12Months":
            "Count_Person_BelowPovertyLevelInThePast12Months",
        "Unemployed":
            "Count_UnemploymentInsuranceClaim_StateUnemploymentInsurance",
        "UnemploymentRate":
            "UnemploymentRate_Person",
        "Crime":
            "Count_CriminalActivities_CombinedCrime",
        "GiniIndex":
            "GiniIndex_EcconomicActivity",
        "LifeExpectancy":
            "LifeExpectancy_Person",
        "GDP":
            "Amount_EconomicActivity_GrossDomesticProduction_Nominal"


    },
    "State": {
        "AbovePovertyInLast12Months":
            "Count_Person_AbovePovertyLevelInThePast12Months",
        "BelowPovertyInLast12Months":
            "Count_Person_BelowPovertyLevelInThePast12Months",
        "Unemployed":
            "Count_UnemploymentInsuranceClaim_StateUnemploymentInsurance",
        "UnemploymentRate":
            "UnemploymentRate_Person",
        "Crime":
            "Count_CriminalActivities_CombinedCrime",
        "LifeExpectancy":
            "LifeExpectancy_Person",
        "GDP":
            "Amount_EconomicActivity_GrossDomesticProduction_Nominal"
    },
    "County": {
        "AbovePovertyInLast12Months":
            "Count_Person_AbovePovertyLevelInThePast12Months",
        "BelowPovertyInLast12Months":
            "Count_Person_BelowPovertyLevelInThePast12Months",
        "Unemployed":
            "Count_UnemploymentInsuranceClaim_StateUnemploymentInsurance",
        "UnemploymentRate":
            "UnemploymentRate_Person",
        "Crime":
            "Count_CriminalActivities_CombinedCrime",
        "LifeExpectancy":
            "LifeExpectancy_Person",
        "GDP":
            "Amount_EconomicActivity_GrossDomesticProduction_Nominal"
    }
}