# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.
"""
  This file contains various constants and helper code to generate constants
  that are used in the Statistical Variable renaming. 
"""

import pandas as pd
import collections
import re


def capitalizeFirst(word):
    """ Capitalizes the first letter of a string. """
    return word[0].upper() + word[1:]


def standard_name_remapper(orig_name):
    """ General renaming function for long strings into Pascal case.

    Text inbetween trailing parentheses is removed. 
    Commas, dashes, and "ands" are removed. Then string is converted into Pascal
    case without and spaces present.
   """
    # Remove any trailing parentheses.
    # TODO(tjann): to check if this is safe.
    paren_start = orig_name.find("(")
    if paren_start != -1:
        orig_name = orig_name[:paren_start]

    # Removes separating words.
    orig_name = orig_name.replace(",", " ")
    orig_name = orig_name.replace("-", " ")
    orig_name = orig_name.replace("and ", "")
    return "".join([word.capitalize() for word in orig_name.split()])


def _create_naics_map():
    """ Downloads all NAICS codes across long and short form codes. """
    # Read in list of industry topics.
    naics_codes = pd.read_excel(
        "https://www.census.gov/eos/www/naics/2017NAICS/2-6%20digit_2017_Codes.xlsx"
    )
    naics_codes = naics_codes.iloc[:, [1, 2]]
    naics_codes.columns = ['NAICSCode', 'Title']

    # Replace all ranges with individual rows. E.g. 31-33 -> 31, 32, 33.
    def range_to_array(read_code):
        if isinstance(read_code, str) and "-" in read_code:
            lower, upper = read_code.split("-")
            return list(range(int(lower), int(upper) + 1))
        return read_code

    naics_codes = naics_codes.dropna()
    naics_codes['NAICSCode'] = naics_codes['NAICSCode'].apply(range_to_array)
    naics_codes = naics_codes.explode('NAICSCode')

    # Add unclassified code which is used in some statistical variables.
    naics_codes = naics_codes.append(
        {
            "NAICSCode": 99,
            "Title": "Nonclassifiable"
        }, ignore_index=True)

    # Query for only two digit codes.
    short_codes = naics_codes[naics_codes['NAICSCode'] < 100]
    short_codes = short_codes.set_index("NAICSCode")
    short_codes = short_codes['Title'].to_dict()

    # Read in overview codes.
    overview_codes = pd.read_csv(
        "https://data.bls.gov/cew/doc/titles/industry/high_level_industries.csv"
    )
    overview_codes.columns = ["NAICSCode", "Title"]
    overview_codes = overview_codes.set_index("NAICSCode")
    overview_codes = overview_codes['Title'].to_dict()

    # Combine the two sources of codes.
    NAICS_MAP = {}
    combined_codes = short_codes
    combined_codes.update(overview_codes)

    # Rename industries into Pascal case.
    for code, orig_name in combined_codes.items():
        NAICS_MAP[str(code)] = standard_name_remapper(orig_name)

    # Other edge cases.
    NAICS_MAP['00'] = 'Unclassified'
    return NAICS_MAP

# TODO(iancostello): Consider adding function memoization.
NAICS_MAP = _create_naics_map()

### True Constants
# Template of Stat Var MCF.
TEMPLATE_STAT_VAR = """
Node: dcid:{human_readable_dcid}
typeOf: dcs:StatisticalVariable
populationType: dcs:{populationType}
statType: dcs:{statType}
measuredProperty: dcs:{measuredProperty}
{CONSTRAINTS}"""

# Main query for stat vars. Combines across populations and observations
# to create statistical variables.
QUERY_FOR_ALL_STAT_VARS = """
SELECT DISTINCT
  SP.population_type as populationType,
  {CONSTRAINTS}
  {POPULATIONS}
  O.measurement_qualifier AS measurementQualifier,
  O.measurement_denominator as measurementDenominator,
  O.measured_prop as measuredProp,
  O.unit as unit,
  O.scaling_factor as scalingFactor,
  O.measurement_method as measurementMethod,
  SP.num_constraints as numConstraints,
  CASE
    WHEN O.measured_value IS NOT NULL THEN "measuredValue" 
    WHEN O.sum_value IS NOT NULL THEN "sumValue"
    WHEN O.mean_value IS NOT NULL THEN "meanValue"
    WHEN O.min_value IS NOT NULL THEN "minValue"
    WHEN O.max_value IS NOT NULL THEN "maxValue"
    WHEN O.std_deviation_value IS NOT NULL THEN "stdDeviationValue"
    WHEN O.growth_rate IS NOT NULL THEN "growthRate"
    WHEN O.median_value IS NOT NULL THEN "medianValue"
    ELSE "Unknown"
  END AS statType
FROM
  `google.com:datcom-store-dev.dc_v3_clustered.StatisticalPopulation`
    AS SP JOIN
  `google.com:datcom-store-dev.dc_v3_clustered.Observation`
    AS O 
  ON (SP.id = O.observed_node_key) 
WHERE
  O.type <> "ComparativeObservation"
  AND SP.is_public 
  AND SP.prov_id NOT IN ({comma_sep_prov_blacklist})
"""

# Dataset blacklist.
_BIO_DATASETS = frozenset([
    'dc/p47rsv3',  # UniProt
    'dc/0cwj4g1',  # FDA_Pharmacologic_Class
    'dc/5vxrbh3',  # SIDER
    'dc/ff08ks',  # Gene_NCBI
    'dc/rhjyj31',  # MedicalSubjectHeadings
    'dc/jd648v2',  # GeneticVariantClinVar
    'dc/x8m41b1',  # ChEMBL
    'dc/vbyjkh3',  # SPOKESymptoms
    'dc/gpv9pl2',  # DiseaseOntology
    'dc/8nwtbj2',  # GTExSample0
    'dc/t5lx1e2',  # GTExSample2
    'dc/kz0q1c2',  # GTExSample1
    'dc/8xcvhx',  # GenomeAssemblies
    'dc/hgp9hn1',  # Species
    'dc/9llzsx1',  # GeneticVariantUCSC
    'dc/f1fxve1',  # Gene_RNATranscript_UCSC
    'dc/mjgrfc',  # Chromosome
    'dc/h2lkz1',  # ENCODEProjectSample
])

_MISC_DATASETS = frozenset([
    'dc/93qydx3',  # NYBG
    'dc/g3rq1f1',  # DeepSolar
    'dc/22t2hr3',  # EIA_860
    'dc/zkhvp12',  # OpportunityInsightsOutcomes
    'dc/89fk9x3',  # CollegeScorecard
])

# List of constraint prefixes to remove from certain properties.
CONSTRAINT_PREFIXES_TO_STRIP = {
    'nativity': 'USC',
    'age': 'USC',
    'institutionalization': 'USC',
    'educationStatus': 'USC',
    'povertyStatus': 'USC',
    'workExperience': 'USC',
    'nativity': 'USC',
    'race': ['USC', 'CDC', 'DAD'],
    'employment': ['USC', 'BLS'],
    'employmentStatus': ['USC', 'BLS'],
    'schoolGradeLevel': 'NCES',
    'patientRace': 'DAD'
}

# List of drug renamings. Note that some drugs are intentionally excluded.
DRUG_REMAPPINGS = {
    'drug/dea/1100': 'Amphetamine',
    'drug/dea/1105B': 'DlMethamphetamine',
    'drug/dea/1105D': 'DMethamphetamine',
    'drug/dea/1205': 'Lisdexamfetamine',
    'drug/dea/1248': 'Mephedrone',
    'drug/dea/1615': 'Phendimetrazine',
    'drug/dea/1724': 'Methylphenidate',
    'drug/dea/2010': 'GammaHydroxybutyricAcid',
    'drug/dea/2012': 'FDAApprovedGammaHydroxybutyricAcidPreparations',
    'drug/dea/2100': 'BarbituricAcidDerivativeOrSalt',
    'drug/dea/2125': 'Amobarbital',
    'drug/dea/2165': 'Butalbital',
    'drug/dea/2270': 'Pentobarbital',  # Intentionally duplicated
    'drug/dea/2285': 'Phenobarbital',  # 
    'drug/dea/2315': 'Secobarbital',
    'drug/dea/2765': 'Diazepam',
    'drug/dea/2783': 'Zolpidem',
    'drug/dea/2885': 'Lorazepam',
    'drug/dea/4000': 'AnabolicSteroids',
    'drug/dea/4187': 'Testosterone',
    'drug/dea/7285': 'Ketamine',
    'drug/dea/7315D': 'Lysergide',
    'drug/dea/7365': 'MarketableOralDronabinol',
    'drug/dea/7369': 'DronabinolGelCapsule',
    'drug/dea/7370': 'Tetrahydrocannabinol',
    'drug/dea/7377': 'Cannabicyclol',
    'drug/dea/7379': 'Nabilone',
    'drug/dea/7381': 'Mescaline',
    'drug/dea/7400': '34Methylenedioxyamphetamine',
    'drug/dea/7431': '5MethoxyNNDimethyltryptamine',
    'drug/dea/7433': 'Bufotenine',
    'drug/dea/7437': 'Psilocybin',
    'drug/dea/7438': 'Psilocin',
    'drug/dea/7455': 'PCE',
    'drug/dea/7471': 'Phencyclidine',
    'drug/dea/7540': 'Methylone',
    'drug/dea/9010': 'Alphaprodine',
    'drug/dea/9020': 'Anileridine',
    'drug/dea/9041L': 'Cocaine',
    'drug/dea/9046': 'Norcocaine',
    'drug/dea/9050': 'Codeine',
    'drug/dea/9056': 'EtorphineExceptHCl',
    'drug/dea/9064': 'Buprenorphine',
    'drug/dea/9120': 'Dihydrocodeine',
    'drug/dea/9143': 'Oxycodone',
    'drug/dea/9150': 'Hydromorphone',
    'drug/dea/9168': 'Difenoxin',
    'drug/dea/9170': 'Diphenoxylate',
    'drug/dea/9180L': 'Ecgonine',
    'drug/dea/9190': 'Ethylmorphine',
    'drug/dea/9193': 'Hydrocodone',
    'drug/dea/9200': 'Heroin',
    'drug/dea/9220L': 'Levorphanol',
    'drug/dea/9230': 'Pethidine',
    'drug/dea/9250B': 'Methadone',
    'drug/dea/9273D': 'BulkDextropropoxyphene',
    'drug/dea/9300': 'Morphine',
    'drug/dea/9313': 'Normorphine',
    'drug/dea/9333': 'Thebaine',
    'drug/dea/9411': 'Naloxone',
    'drug/dea/9600': 'RawOpium',
    'drug/dea/9630': 'TincuredOpium',
    'drug/dea/9639': 'PowderedOpium',
    'drug/dea/9652': 'Oxymorphone',
    'drug/dea/9655': 'Paregoric',
    'drug/dea/9665': '14Hydroxycodeinone',
    'drug/dea/9668': 'Noroxymorphone',
    'drug/dea/9670': 'PoppyStrawConcentrate',
    'drug/dea/9737': 'Alfentanil',
    'drug/dea/9739': 'Remifentanil',
    'drug/dea/9740': 'Sufentanil',
    'drug/dea/9743': 'Carfentanil',
    'drug/dea/9780': 'Tapentadol',
    'drug/dea/9801': 'Fentanyl',
}

# Exceptionally long and confusing cause of death names are manually renamed.
MANUAL_CAUSE_OF_DEATH_RENAMINGS = {
    'ICD10/D50-D89': 'DiseasesOfBloodAndBloodFormingOrgansAndImmuneDisorders',
    'ICD10/R00-R99': 'AbnormalNotClassfied',
    'ICD10/U00-U99': 'SpecialCases',
    'ICD10/V01-Y89': 'ExternalCauses'
}

# List of properties to perform a numerical quantity remap on.
NUMERICAL_QUANTITY_PROPERTIES_TO_REMAP = [
    'income', 'age', 'householderAge', 'homeValue', 'dateBuilt', 'grossRent',
    'numberOfRooms', 'numberOfRooms', 'householdSize', 'numberOfVehicles',
    'propertyTax'
]

# Regex rules to apply to numerical quantity remap.
REGEX_NUMERICAL_QUANTITY_RENAMINGS = [
    # [A-Za-z]+[0-9]+Onwards -> [0-9]+OrMore[A-Za-z]+
    (re.compile(r"^([A-Za-z]+)([0-9]+)Onwards$"),
     lambda match: match.group(2) + "OrMore" + match.group(1)),

    # [A-Za-z]+Upto[0-9]+ -> Upto[0-9]+[A-Za-z]+
    (re.compile(r"^([A-Za-z]+)Upto([0-9]+)$"),
     lambda match: "Upto" + match.group(2) + match.group(1)),

    # [A-Za-z]+[0-9]+To[0-9]+-> [0-9]+To[0-9]+[A-Za-z]+
    (re.compile(r"^([A-Za-z]+)([0-9]+)To([0-9]+)$"),
     lambda match: match.group(2) + "To" + match.group(3) + match.group(1)),

    # [A-Za-z]+[0-9]+ -> [0-9]+[A-Za-z]+
    (re.compile(r"^([A-Za-z]+)([0-9]+)$"),
     lambda match: match.group(2) + match.group(1))
]

# Constants that power Statistical Variable documentation.
# Tuple is defined as follows:
# (Name of Vertical), (Population Type include),
# (whether to subgroup by all population types in demographic),
# (if subgroup all, whether you should group population types with more than 1
# statistical variable).
SVPopGroup = (collections.namedtuple(
    'STAT_VAR_DOCUMENTION_GROUPING',
    'vertical popTypes subgroupAllPops subgroupIfMoreThanOne'))
STAT_VAR_POPULATION_GROUPINGS = [
  SVPopGroup("Demographics",
    ['Person', 'Parent', 'Child', 'Student', 'Teacher'],
    True, False),
  SVPopGroup("Crime",
    ['CriminalActivities'],
    False, False),
  SVPopGroup("Health",
    ['Death', 'DrugDistribution', 'MedicalConditionIncident',
     'MedicalTest', 'MedicareEnrollee'],
    True, False),
  SVPopGroup("Employment",
    ['Worker', 'Establishment', 'JobPosting',
     'UnemploymentInsuranceClaim'],
    True, False),
  SVPopGroup("Economic",
    ['EconomicActivity', 'Consumption', 'Debt', 'TreasuryBill',
     'TreasuryBond', 'TreasuryNote'],
    True, False),
  SVPopGroup("Environment",
  ['Emissions'],
    False, False),
  SVPopGroup("Household",
  ['Household'],
    False, False),
  SVPopGroup("HousingUnit",
  ['HousingUnit'],
    False, False)
]

# HTML for statistical variable markdown.
DOCUMENTATION_BASE_MARKDOWN = \
"""---
layout: default
title: Statistical Variables
nav_order: 2
---

# Statistical Variables

Many of the Data Commons APIs deal with Data Commons nodes of the type
[StatisticalVariable](https://browser.datacommons.org/kg?dcid=StatisticalVariable).
The following list contains all Statistical Variables with human-readable identifiers,
grouped by domain and population type. Some verticals are grouped such that all
population types are a sub-level grouping, while others (like disasters), only
group by population types when there are multiple statistical variables for that
population type.

<style>
details details {
  margin-left: 24px;
}

details details summary {
  font-size: 16px;
}

li {
  white-space: nowrap;
}
</style>
"""

DOCUMENTATION_HEADER_START = \
"""
<details>
  <summary>{HEADER}</summary>
"""

DOCUMENTATION_DROPDOWN_START = \
"""
<details>
  <summary>{POPULATION_TYPE}</summary>
  <ul>
"""
