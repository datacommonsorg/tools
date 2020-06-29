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

"""
This file performs the renaming of all statistical variables present in the Data Commons Knowledge Graph. These StatVar names are incredible useful for end-users as they may be pulled from both the python API 
or Google Sheets API by name. 

1) Base Schema: The basic schema for any human readable statistical variable is
mprop_popType_v1_v2_v3...
For example, Count_Person_BornInStateOfResidence

2) Optional inclusion of StatType
StatType is included when the StatType is not measuredValue or Unknown.
For example, instead of Age_Person, we output MedianAge_Person

3) Certain data sets are blacklisted
For example, all bio data sets and a few miscellaneous ones are excluded. This blacklist was created by Tiffany. 

4) Dependent variables are removed. 
Dependent variables are constraints that are inherently included, but not really necessary. For example, a person earning an income of 10k to 15k USD may only be measured by the census if they are older than 15 and have an income. For example, "Count_Person_Years15Onwards_IncomeOfUSDollar10000To14999_WithIncome" becomes "Count_Person_IncomeOfUSDollar10000To14999" after accounting for the unnecessary variables. These dependent variables are defined in the textproto stat vars config file. 

4) Boolean constraints are replaced by their populations
E.g. p1 = isInternetUser and v1=True/False becomes v1=isInternetUser/notInternetUser. 

5) Measurement properties are stripped from constraints.
E.g. p1 = employment and v1 = USC_Unemployed becomes v1=Unemployed

6) NAICS Industry codes are replaced by industry names.
We have a combination of NAICS specific and overview codes. In both cases, we replace the industry code (e.g. NAICS/23) with the industry.
An example statistical variable is WagesAnnual_Establishment_NAICSConstruction

7) Cause of death properties are renamed.
E.g. p1 = causeOfDeath and v1="ICD10/E00-E89" becomes v1="EndocrineNutritionalMetabolicDiseases". These names are generated directly from the ICD10 names stored in BigQuery. For exceptionally long or confusing names, I manually renamed them.

8) DEA drug names are renamed
E.g. p1="drugPrescribed" and v1="drug/dea/9250" becomes v1="Methadone". These are manually renamed. Some drug names are intentionally left as their codes. For example, dea/7444 corresponds to "4-Hydroxy-3-methoxy-methamphetamine", which does not have a common name. Both the codes and drug names will be valid constraints.

9) Certain variables have text pre/postpended to their constraints to improve readability.
For example p1 = childSchoolEnrollment and v1=EnrolledInPublicSchool is changed to v1="ChildEnrolledInPublicSchool". These mappings are applied to ~15 variables. 

e.g. Count_Parent_Years16Onwards_EnrolledInPublicSchool_InLaborForce
becomes Count_Parent_Years16Onwards_ChildEnrolledInPublicSchool_InLaborForce

10) Misc. changes
a) MeasuredProp InsuredUnemploymentRate changed to Rate_InsuredUnemployment to match the existing formula. 
"""

from absl import app
from google.protobuf import text_format
from google.cloud import bigquery
from google.colab import auth
import re
import os
import pandas as pd

from stat_var_renaming_constants import *

### Constants
# Max total number of constraints of a variable to include (Depedent variables excluded)
MAX_CONSTRAINTS = 3

def authenticate_bq_client():
  """ Authenticates and returns a BigQuery client connection. """

  # TODO how should this authentication happen in prod?
  auth.authenticate_user()

  project_id = "google.com:datcom-store-dev"
  client = bigquery.Client(project=project_id)

  return client

def download_stat_vars(client):
  """ Queries unique list of statistical variables from BigQuery.

  Creates a join across statistical populations and observations to generate distinct list. 
  Certain datasets like bio are excluded. The original dpvs are copied to a new columns.

  Returns:
      stat_vars: Pandas dataframe containing unique information for all stat vars in the databaes

  Raises:
      ...
  """
  max_constraints_with_dpv = 6

  # Populate constraints
  constraint_string, pop_string = "", ""
  for num in range(1, MAX_CONSTRAINTS + 1):
    constraint_string += f"SP.v{num} as v{num},\n"
    pop_string += f"SP.p{num} as p{num},\n"

  blacklist = ['"%s"' % prov_id for prov_id in frozenset().union(*[_MISC_DATASETS, _BIO_DATASETS])]
  blacklist_str = ', '.join(blacklist) if blacklist else '""'

  query_for_all_stat_vars = QUERY_FOR_ALL_STAT_VARS.replace("{CONSTRAINTS}", constraint_string) \
                                                  .replace("{POPULATIONS}", pop_string) \
                                                  .replace("{comma_sep_prov_blacklist}", blacklist_str) \
                                                  .replace("{MAX_CONTRAINTS}", str(MAX_CONSTRAINTS))

  # Perform BQ query
  stat_vars = client.query(query_for_all_stat_vars).to_dataframe()

  # Original stat vars are preserved for output MCF
  for c in range(1, max_constraints_with_dpv + 1):
    stat_vars[f"orig_p{c}"] = stat_vars[f"p{c}"]
    stat_vars[f"orig_v{c}"] = stat_vars[f"v{c}"]

  return stat_vars

### Variable renaming scripts
def addPropertyRemapping(remapper, prop, function):
  """ Helper function to add new remapping function to a certain property.

  Args:
    remapper: Dictionary with mapping from populations to functions
    prop: Property to perform remapping on
    function: Function that takes two arguments (property, constraint) and returns the new name for the constraint
  """

  if prop not in remapper:
    remapper[prop] = []

  remapper[prop].append(function)

def remap_numerical_quantities(prop_remap):
  """ Adds a remapping function to change numerical quantities to a more readable format dependent on regex rules. 
  
    Example:  'Years15Onwards' -> '15OrMoreYears' or  'Years25To44' -> '25To44Years'
  """
  def rename_constraint(_, constraint):
    if not pd.isna(constraint):
      # REGEX_NUMERICAL_QUANTITY_RENAMINGS has mappings from a regex expression to a remapping function
      for regex, rename_func in REGEX_NUMERICAL_QUANTITY_RENAMINGS:
        match_obj = regex.match(constraint)
        if match_obj != None:
          return rename_func(match_obj)
      return constraint

  # Opt-in list to rename
  for prop in NUMERICAL_QUANTITY_PROPERTIES_TO_REMAP:
    addPropertyRemapping(prop_remap, prop, rename_constraint)

  return prop_remap

def rename_naics_codes(prop_remap):
  """ Adds a remapping function to change NAICS codes to their corresponding industry.
  
    Example: (NAICS, NAICS/23) -> Construction)
  """
  # Add renaming function
  def rename_naics(NAICS_MAP, industry_code):
    full_code = industry_code.lstrip("NAICS/")

    # If its a range then take the lower bound. E.g. 31-33 = Manufacturing
    if "-" in full_code:
      full_code = full_code.split("-")[0]

    two_digit_code = full_code[0:2]

    if full_code in NAICS_MAP:
      return NAICS_MAP[full_code]

    if two_digit_code in NAICS_MAP:
      return NAICS_MAP[two_digit_code]

    print(f"Industry Code {industry_code} not found!")
    assert False

  contextual_rename = lambda _, industry_code: rename_naics(NAICS_MAP, industry_code)
  addPropertyRemapping(prop_remap, "naics", contextual_rename)

  return prop_remap

def rename_boolean_variables(prop_remap, stat_vars):
  """ Remaps all variables with boolean constraint values.

    Example (hasComputer, False) -> noComputer 
  """
  def map_boolean_constraints(population, value):
    assert (value == "True" or value == "False")
    constraint_value = True if value == "True" else False
    pop, prefix = None, None

    if population.startswith("has"):
      pop = population.lstrip("has")
      prefix = "Has" if constraint_value else "N
    elif population.startswith("is"):
      pop = population.lstrip("is")
      prefix = "Is" if constraint_value else "Not"
    else:
      print("Unhandled prefix {population}")
      assert False

    return prefix + pop


  # Get all properties with boolean 
  boolean_populations = set()
  for c in range(1, MAX_CONSTRAINTS+1):
    unique_constraints = stat_vars[stat_vars[f"v{c}"].isin(['True', 'False'])][f"p{c}"].unique()
    boolean_populations.update(unique_constraints)

  for pop in boolean_populations:
    addPropertyRemapping(prop_remap, pop, map_boolean_constraints)
  
  return prop_remap

def prefix_strip(prop_remap):
  """ Strips measurement method prefixes from constraints.

    Example: BLS_InLaborForce -> InLaborForce
  """

  for population, prefixes in CONSTRAINT_PREFIXES_TO_STRIP.items():
    def strip_prefixes(pop, constraint):
      # Prefixes may be a list or single value
      prefixes_for_pop = prefixes if isinstance(prefixes, list) else [prefixes]

      for prefix in prefixes_for_pop:
        if constraint.startswith(prefix):
          constraint = constraint.replace(prefix, "")
          return constraint.lstrip("_")

      return constraint

    addPropertyRemapping(prop_remap, population, strip_prefixes)

  return prop_remap 

def cause_of_death_remap(prop_remap, client):
  """ Remaps ICD10 death codes into full names.

    Example: (causeOfDeath, ICD10/A00-B99) -> CertainInfectiousParasiticDiseases
  """

  # Query all drug names from cluster
  cause_of_death_query = """
  SELECT id, name
  FROM `google.com:datcom-store-dev.dc_v3_clustered.Instance`
  WHERE type = "ICD10Section" or type = "ICD10Code"
  """
  cause_of_death_instances = client.query(cause_of_death_query).to_dataframe()

  # Simplify Names
  def provide_consistent_naming(row):
    id = row['ICD10Code']

    # Manually remap abnormally long names
    if id in MANUAL_CAUSE_OF_DEATH_RENAMINGS:
      return MANUAL_CAUSE_OF_DEATH_RENAMINGS[id]
    
    # Otherwise just generate from the database name
    icd10_code = id.replace("ICD10/", "")

    name = row['name']
    name = name.replace(icd10_code, "").strip().lstrip("(").rstrip("()")
    name = standard_name_remapper(name)

    row['id'] = id
    row['name'] = name
    return row

  cause_of_death_instances["ICD10Code"] = cause_of_death_instances["id"]
  cause_of_death_instances = cause_of_death_instances.set_index("id")
  cause_of_death_instances = cause_of_death_instances.apply(provide_consistent_naming, axis=1)

  # Add modification function
  def death_id_to_name(_, death_id):
    return cause_of_death_instances.loc[death_id]['name']
  
  addPropertyRemapping(prop_remap, 'medicalCode', death_id_to_name)
  addPropertyRemapping(prop_remap, 'causeOfDeath', death_id_to_name)

def rename_dea_drugs(prop_remap, client):
  """ Renames dea drig codes to common names.
  Note that some codes are intentionally unmapped as they are exceptionally long and do not have common usage.
  The dea drug names were not in a "nice" format so they are manually renamed.

  Example: (drugPrescribed, drug/dea/4000) -> AnabolicSteroids
  """
  # Add modification function
  def drug_id_to_name(_, drug_id):
    if drug_id in DRUG_REMAPPINGS:
      return DRUG_REMAPPINGS[orig_name]
    else:
      return orig_name.replace("drug/", "") 

  addPropertyRemapping(prop_remap, 'drugPrescribed', drug_id_to_name)

def misc_mappings(prop_remap):
  """ Any misc. renamings that need to happen should go here.
  
    1) Remove ACSED from memberStatus
    2) Quantity for dateBuilt refers to time not count
  """
  def remove_acsed(_, constraint):
    return constraint.replace("ACSED", "")

  addPropertyRemapping(prop_remap, 'memberStatus', remove_acsed)

  def replace_date_built(_, constraint):
    constraint = constraint.replace("OrMore", "OrLater")
    constraint = constraint.replace("Upto", "Before")
    return constraint

  addPropertyRemapping(pop_remap, 'dateBuilt', replace_date_built)

def pre_postpend_text(prop_remap):
  """ Adds remapping functions which either prepend or postpend text to all constraints for a property.

    Example: (languageSpokenAtHome, AfricanLanguages) -> AfricanLanguagesSpokenAtHome 
  """
  def addTextToConstraint(variable, prepend="", postpend=""):
    text_mod = lambda _, text: prepend + capitalizeFirst(text) + postpend
    addPropertyRemapping(prop_remap, variable, text_mod)

  addTextToConstraint("languageSpokenAtHome", postpend="SpokenAtHome")
  addTextToConstraint("childSchoolEnrollment", prepend="Child")
  addTextToConstraint("residenceType", prepend="ResidesIn")
  addTextToConstraint("healthPrevented", prepend="Received")
  addTextToConstraint("householderAge", prepend="HouseholderAge")
  addTextToConstraint("householderRace", prepend="HouseholderRace")
  addTextToConstraint("dateBuilt", postpend="Built")
  addTextToConstraint("homeValue", prepend="HomeValue")
  addTextToConstraint("numberOfRooms", prepend="WithTotal")
  addTextToConstraint("naics", prepend="NAICS")
  addTextToConstraint("isic", prepend="ISIC")
  addTextToConstraint("establishmentOwnership", postpend="Establishment")
  addTextToConstraint("householdSize", prepend="With")
  addTextToConstraint("numberOfVehicles", prepend="With")
  addTextToConstraint("income", prepend="IncomeOf")
  addTextToConstraint("grossRent", prepend="GrossRent")
  addTextToConstraint("healthOutcome", prepend="With")
  addTextToConstraint("healthPrevention", prepend="Received")
  addTextToConstraint("propertyTax", prepend="YearlyTax")

def rename_isic_codes(prop_remap, client):
  """ Renames all ISIC economic codes to their full names in the database.

    Example: (isic, ISICv3.1/I) -> ISICTransportStorageCommunications
  """

  # Download all isic codes names from cluster
  ISIC_QUERY = """
  SELECT id, name
  FROM `google.com:datcom-store-dev.dc_v3_clustered.Instance` 
  WHERE type = "ISICv3.1Enum"
  """
  isic_instances = client.query(ISIC_QUERY).to_dataframe()  
  isic_instances = isic_instances.set_index("id")
  isic_instances['name'] = isic_instances['name'].apply(standard_name_remapper)

  # Add modification function
  def isic_id_to_name(_, isic):
    return isic_instances.loc[isic]['name']
  
  addPropertyRemapping(prop_remap, 'isic', isic_id_to_name)

def remap_constraint_from_prop(row, prop_remap):
  """ Helper which applies property remappings to all constraints in a dataset

  Args:
    row: Pandas row to apply function to.
    prop_remap: Dictionary mapping property names to functions that take (property, constraint) -> new constraint name
  """
  for constraint in range(1, 1+row['numConstraints']):
    prop = row[f"p{constraint}"]

    if prop in prop_remap:
      # May need to apply multiple functions for a single property
      remapper = prop_remap[prop]
      for function in remapper:
        row[f"v{constraint}"] = function(prop, row[f"v{constraint}"])

  return row

### Renaming Population
def rename_populations(stat_vars):
  """ Applies various rules to remap population names for the stat vars
    
    1) Strips measurement prefixes. E.g. BLS_Worker -> Worker
    2) Renames populations entirely. E.g. MortalityEvent -> Death
  """

  # Strip prefixes
  population_prefixes_to_strip = ['BLS', 'USC', 'ACSED']

  def strip_population_prefixes(population):
    for prefix in population_prefixes_to_strip:
      if population.startswith(prefix):
        return re.sub(f"^{prefix}", "", population)

    return population

  stat_vars['populationType'] = stat_vars['populationType'].apply(strip_population_prefixes)

  # Rename populations
  populations_to_rename = {
    'MortalityEvent': 'Death',
  }

  stat_vars['populationType'] = stat_vars['populationType'].apply(lambda pop: pop if pop not in populations_to_rename else populations_to_rename[pop])

  return stat_vars

### Remove dependent variables
def generate_dependent_variable_list():
  """ Dynamically creates object proto spec from include file then imports this newly created spec
  and uses it to load list of depedent variables.
  
    Returns:
      obs_spec_list: Observation specification list
  """

  # Generate population observation spec
  os.system("protoc -I=. --python_out=. pop_obs_spec_common.proto")

  # Dynamically load newly created package
  import pop_obs_spec_common_pb2
  obs_spec_list = pop_obs_spec_common_pb2.PopObsSpecList()

  # Load in PV list from spec proto
  # Note that covid cases was temporarily added as a DPV for cases, but truly shouldn't be one
  with open("pop_obs_spec_nocovid.textproto") as f:
    counts = f.read()
    text_format.Parse(counts, obs_spec_list)

  return obs_spec_list

def remove_depedent_variables(stat_vars):
  """ Removes all dependent variables from list of stat vars.

    Args:
      stat_vars: Pandas dataframe holding all stat vars
    
    Returns:
      stat_vars with all dependent variables imputed in place and not shifted.

    Notes: 
      Constraints in database are alphabetically sorted. This method should be updated to take advantage of this guarantee
      instead of having to search through all columns.
  """

  # Generate list of depedent vars
  obs_spec_list = generate_dependent_variable_list()

  # Create single list of constraints for stat vars
  def cpropsToList(row):
    cprop_list = []

    for c in range(1, MAX_CONSTRAINTS + 1): 
      next_pop = row[f"p{c}"]
      if not pd.isna(next_pop != None:
        cprop_list.append(next_pop)

    return cprop_list

  stat_vars['CPropList'] = stat_vars.apply(cpropsToList, axis=1)

  # For each depedent variable, get the rows with the matching constraints then remove any DPVs
  for spec in obs_spec_list.spec:
    pop_type = spec.pop_type
    measured_property = spec.mprop
    stat_type = spec.stat_type

    # Get subset of rows with a match
    rows_with_indepedent_matches = stat_vars.query(f"populationType == '{pop_type}' and measuredProp == '{measured_property}' and statType == '{stat_type}'")

    # Find any rows with the matching constraining properties
    for cprop in spec.cprop:
      rows_with_indepedent_matches['CPropContained'] = rows_with_indepedent_matches['CPropList'].apply(lambda c_prop_list: cprop in c_prop_list)
      rows_with_indepedent_matches = rows_with_indepedent_matches.query("CPropContained == True")

    # Erase all depedent variables for each constraint
    for c in range(1, MAX_CONSTRAINTS + 1):
      for dpv in spec.dpv:
        rows_to_erase = matching_common_rows.query(f"p{c} == '{dpv.prop}' and v{c} == '{dpv.val}'")
        stat_vars.loc[rows_to_erase.index, f"p{c}"] = np.nan
        stat_vars.loc[rows_to_erase.index, f"v{c}"] = np.nan

        stat_vars.loc[rows_to_erase.index, f"numConstraints"] = stat_vars.loc[rows_to_erase.index, f"numConstraints"].apply(lambda num: num - 1)

  return stat_vars

# Shift over any removed stat var columns
def left_fill_columns(row):
  ROW_CONSTRAINTS = row['numConstraints']

  location_of_last_found = 2
  for curr_col in range(1, ROW_CONSTRAINTS + 1):
    if pd.isna(row[f"p{curr_col}"]):
      while location_of_last_found <= MAX_CONSTRAINTS:
        if not pd.isna(row[f"p{location_of_last_found}"]):
          row[f"p{curr_col}"] = row[f"p{search}"]
          row[f"v{curr_col}"] = row[f"v{search}"]
          row[f"p{search}"] = np.nan
          row[f"v{search}"] = np.nan
        location_of_last_found += 1

  return row
  
def row_to_human_readable(row):
  """ Applies a mapping between a row in the stat vars dataframe to the corresponding human readable dcid. """

  # Base is measuredProp_PopType => e.g. Count_InsuranceClaims
  human_string = f"{capitalizeFirst(row['measuredProp'])}_{capitalizeFirst(row['populationType'])}"

  # Prepend StatType
  stat_type = row['statType']
  if stat_type != "measuredValue" and stat_type != "Unknown":
    human_string = capitalizeFirst(stat_type.replace("Value", "")) + "_" + human_string

  # Add Constraints
  num_constrains = int(row['numConstraints'])
  for num in range(1, num_constrains + 1): 
    constraint = row[f"v{num}"]

    if not pd.isna(constraint):
      human_string += f"_{constraint}"

  # Postpend measurement denominator
  measurement_denominator = row['measurementDenominator']
  if not pd.isna(measurement_denominator):
    if measurement_denominator == "PerCapita":
      human_string = f"{human_string}_PerCapita"
    else:
      human_string = f"{human_string}_AsAFractionOf{measurement_denominator}"

  # Prepend nmeasurement qualifier
  measurement_qualifier = row['measurementQualifier']
  if not pd.isna(measurement_qualifier):
    human_string = f"{measurement_qualifier}_{human_string}" 

  return human_string

def build_original_constraints(row):
  """ Helper to build list of original properties and constraints. Used to generate output MCF. """

  constraints_text = ""
  next_constraint = 1

  while next_constraint <= MAX_CONSTRAINTS and not pd.isna(row[f"orig_p{next_constraint}"]):
    variable = row[f'orig_p{next_constraint}']
    constraint = row[f'orig_v{next_constraint}']
    constraints_text += f"{variable}: dcs:{constraint}\n"
    next_constraint += 1

  return constraints_text
  
def row_to_stat_var(row):
  """ Creates MCF output for the human readable stat var from the row of a pandas dataframe """

  new_stat_var = TEMPLATE_STAT_VAR

  new_stat_var = new_stat_var.replace("{human_readable_dcid}", row['HumanReadableName'])\
    .replace("{populationType}", row['populationType'])\
    .replace("{statType}", row['statType'])\
    .replace("{measuredProperty}", row['measuredProp'])\
    .replace("{CONSTRAINTS}", row_to_constraints(row))

  if not pd.isna(row['scalingFactor']):
    new_stat_var = new_stat_var + f"scalingFactor: dcs:{row['scalingFactor']}\n"

  if not pd.isna(row['measurementDenominator']):
    new_stat_var = new_stat_var + f"measurementDenominator: dcs:{row['measurementDenominator']}\n"

  if not pd.isna(row['measurementQualifier']):
    new_stat_var = new_stat_var + f"measurementQualifier: dcs:{row['measurementQualifier']}\n"  

  return new_stat_var

def main(argv):
  """ Executes the downloading, preprocessing, renaming, and output of MCF stat var renaming """
  client = authenticate_bq_client()

  # Query for stat vars
  stat_vars = download_stat_vars(client)

  # Build constraint remappings
  prop_remap = {}
  rename_naics_codes(prop_remap)
  rename_dea_drugs(prop_remap, client)
  rename_isic_codes(prop_remap, client)
  cause_of_death_remap(prop_remap, client)
  prefix_strip(prop_remap)
  rename_boolean_variables(prop_remap, stat_vars)
  remap_numerical_quantities(prop_remap)
  pre_postpend_text(prop_remap)
  misc_mappings(prop_remap)

  # Apply constraint renamings
  stat_vars = stat_vars.apply(lambda row: remap_constraint_from_prop(row, prop_remap), axis=1)

  # Remove dependent variables
  stat_vars = remove_depedent_variables(stat_vars)
  stat_vars = left_fill_columns(stat_vars)

  # Generate human readable names
  stat_vars['HumanReadableName'] = stat_vars.apply(row_to_human_readable)

  # Manually rename special case
  stat_vars.loc[stat_vars['HumanReadableName'] == 'Count_Death_Medicare', 'HumanReadableName'] = "Count_Death_MedicareEnrollee" 

  # Filter's for final stat vars
  stat_vars = stat_vars.query("numConstraints <= 3")
  stat_vars = stat_vars.query("statType != 'Unknown'")

  # Temporary filters
  stat_vars = stat_vars.query("measuredProp != 'cohortScaleAchievement'")
  stat_vars = stat_vars.query("measuredProp != 'gradeCohortScaleAchievement'")
  stat_vars = stat_vars.query("populationType != 'AcademicAssessmentEvent'")
  all_but_disaster_populations = []
  for popType in populationTypes:
    if "Event" not in popType or popType in ['MortalityEvent', 'AcademicAssessmentEvent']:
      disaster_populations.append(popType)

  stat_vars = stat_vars[stat_vars['populationType'].isin(all_but_disaster_populations)]
  stat_vars = stat_vars.sort_values(['numConstraints', 'measuredProp', 'populationType', 'p1', 'p2', 'p3', 'v1', 'v2', 'v3'])

  # Output MCF
  with open('renamed_stat_vars.mcf', 'w', newline='') as f_out:
    for index, row in stat_vars.iterrows():
      new_stat_var = row_to_stat_var(row)
      f_out.write(new_stat_var)

  # Output CSV
  stat_vars = stat_vars.fillna("None")
  stat_vars[['numConstraints', 'populationType', 'measuredProp', 'p1', 'v1', 'p2', 'v2', 'p3', 'v3', 'HumanReadableName', 'orig_p1', 'orig_v1', 'orig_p2', 'orig_v2', 'orig_p3', 'orig_v3', 'orig_p4', 'orig_v4']].to_csv("output.csv", index=False)

if __name__ == '__main__':
  app.run(main)



