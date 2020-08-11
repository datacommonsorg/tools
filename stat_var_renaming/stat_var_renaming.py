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
This file performs the renaming of all statistical variables present in the Data
Commons Knowledge Graph. Human-intelligible StatVar names are useful for end 
users as they may be pulled from both the Python API or Google Sheets API by
name.

1) Base Schema: The basic schema for any human readable statistical variable is
   mprop_popType_v1_v2_v3... For example, Count_Person_BornInStateOfResidence

2) Optional inclusion of StatType: statType is included when the StatType is not
   measuredValue or Unknown. For example, instead of Age_Person, we output
   MedianAge_Person

3) Certain data sets are blacklisted: for example, all bio data sets and a few
   miscellaneous ones are excluded. This blacklist was created by tjann.

4) Dependent variables are removed. dependent variables are constraints that are
   inherently included, but not really necessary. For example, a person earning
   an income of 10k to 15k USD may only be measured by the US Census if they are
   older than 15 and have an income. For example,
   "Count_Person_Years15Onwards_IncomeOfUSDollar10000To14999_WithIncome" becomes
   "Count_Person_IncomeOfUSDollar10000To14999" after accounting for the
   unnecessary variables. These dependent variables are defined in the textproto
   stat vars config file.

4) Boolean constraints are replaced by their populations: for example, p1 =
   isInternetUser and v1=True/False becomes v1=isInternetUser/notInternetUser.

5) Measurement properties are stripped from constraints: for example, 
  p1 = employment and v1 = USC_Unemployed becomes v1=Unemployed

6) NAICS Industry codes are replaced by industry names: we have a combination of
   NAICS specific and overview codes. In both cases, we replace the industry
   code (e.g. NAICS/23) with the industry. An example statistical variable is
   WagesAnnual_Establishment_NAICSConstruction

7) Cause of death properties are renamed: e.g., p1 = causeOfDeath and
   v1="ICD10/E00-E89" becomes v1="EndocrineNutritionalMetabolicDiseases". These
   names are generated directly from the ICD10 names stored in BigQuery. 
   Exceptionally long or confusing names were manually renamed.

8) DEA drug names are renamed: e.g., p1="drugPrescribed" and v1="drug/dea/9250"
   become v1="Methadone". These are manually renamed. Some drug names are
   intentionally left as their codes. For example, dea/7444 corresponds to
   "4-Hydroxy-3-methoxy-methamphetamine", which does not have a common name.
   Both the codes and drug names will be valid constraints.

9) Certain variables have text prepended or appended to their constraints to
   improve readability: for example p1 = childSchoolEnrollment and
   v1=EnrolledInPublicSchool is changed to v1="ChildEnrolledInPublicSchool".
   These mappings are applied to ~15 variables.

10) Miscellaneous changes: a) MeasuredProp InsuredUnemploymentRate changed to
  Rate_InsuredUnemployment to match the existing formula.
"""

from absl import app
from google.protobuf import text_format
from google.cloud import bigquery
from google.colab import auth
import re
import os
import pandas as pd
import numpy as np

import stat_var_renaming_constants as svrc
import stat_var_renaming_functions as svrf

# Constants
# Max total number of constraints of a variable to include (Dependent
# variables excluded).
_MAX_CONSTRAINTS = 3
_MAX_CONSTRAINTS_WITH_DPV = 6
# If true, no new statistical variables will be introduced.
ONLY_REGENERATE_OUTPUT = False


def authenticate_bq_client():
    """ Authenticates and returns a BigQuery client connection. By default this
    code assumes it will be run in Google Colab which handles BigQuery
    authentication. To run this code elsewhere this method needs to be updated
    to properly authenticate a BigQuery client.

    Returns:
    An authenticated SQL client with a function called query that given a SQL 
    query returns a response object that can be converted into a dataframe.
  """
    # Users should update the authentication method if not using Google CoLab.
    auth.authenticate_user()

    # Create and return client.
    project_id = "google.com:datcom-store-dev"
    return bigquery.Client(project=project_id)


def download_stat_vars(client):
    """ Queries unique list of statistical variables from BigQuery.

  Creates a join across statistical populations and observations to generate
  distinct list of statistical variables. Certain datasets like bio are 
  excluded. The original dpvs are preserved in new columns.

  Args:
    client: An authenticate BigQuery SQL client.

  Returns: 
    stat_vars: Pandas dataframe containing unique information for all
    potential stat vars in the database.

  Raises:
    Query failure: If improper authentication is given.
  """
    # Dynamically create query for constraints in SQL query.
    constraint_string = ""
    pop_string = ""
    for num in range(1, _MAX_CONSTRAINTS + 1):
        constraint_string += f"SP.v{num} as v{num},\n"
        pop_string += f"SP.p{num} as p{num},\n"

    # Dynamically create list of blacklisted provences, as a string.
    blacklist = [
        '"%s"' % prov_id
        for prov_id in frozenset().union(*[svrc._MISC_DATASETS, 
                                           svrc._BIO_DATASETS])
    ]
    blacklist_str = ', '.join(blacklist) if blacklist else '""'

    # Input information into SQL template and perform the query.
    query_for_all_stat_vars = (svrc.QUERY_FOR_ALL_STAT_VARS.replace(
        "{CONSTRAINTS}",
        constraint_string).replace("{POPULATIONS}", pop_string).replace(
            "{comma_sep_prov_blacklist}",
            blacklist_str).replace("{MAX_CONTRAINTS}", str(_MAX_CONSTRAINTS)))
    stat_vars = client.query(query_for_all_stat_vars).to_dataframe()

    # Make a pristine copy of constraint names for output MCF.
    for c in range(1, _MAX_CONSTRAINTS_WITH_DPV + 1):
        stat_vars[f"orig_p{c}"] = stat_vars[f"p{c}"]
        stat_vars[f"orig_v{c}"] = stat_vars[f"v{c}"]
    return stat_vars


### Variable renaming scripts
def addPropertyRemapping(remapper, prop, function):
    """ Helper function to add new remapping function to a certain property.

  Args:
    remapper: Dictionary with mapping from properties to renaming functions.
    prop: Property to perform the remapping on.
    function: Renaming function that takes three arguments 
    (prop, constraint, popType) and returns the new name for the constraint.
  """
    if prop not in remapper:
        remapper[prop] = []
    remapper[prop].append(function)


def remap_constraint_from_prop(row, prop_remap):
    """ Helper which applies property remappings to all constraints in a dataset.

  Args: 
    row: Pandas row to apply function to.
    prop_remap: Dictionary of renaming functions for each property.
  """
    for constraint in range(1, 1 + row['numConstraints']):
        prop = row[f"p{constraint}"]
        if prop in prop_remap:
            # May need to apply multiple functions for a single property.
            remapper = prop_remap[prop]
            for function in remapper:
                row[f"v{constraint}"] = function(prop, row[f"v{constraint}"],
                                                 row['populationType'])
    return row


def generate_dependent_constraint_list():
    """ Generates a list of dependent variables.
  Using an OS system call, a protobuf definition is compiled. A definition
  file is then read in and used to generate a pandas dataframe of dependent
  variable definitions. 

  Returns: 
    obs_spec_list: Observation for statistical variables in 
    protobuf object format.
  """
    # Generate population observation spec. Creates a new python file.
    os.system("protoc -I=. --python_out=. pop_obs_spec_common.proto")

    # Load newly created protobuf class definition.
    import pop_obs_spec_common_pb2
    obs_spec_list = pop_obs_spec_common_pb2.PopObsSpecList()

    # Load in PV list from spec proto. Note that covid cases was temporarily
    # added as a DPV for display, but shouldn't truly be one.
    with open("pop_obs_spec_nocovid.textproto") as f:
        counts = f.read()
        text_format.Parse(counts, obs_spec_list)

    # Create a dataframe that matches the greater stat_vars from DB for merging.
    dpvs = pd.DataFrame()
    for spec in obs_spec_list.spec:
        # Get universal props.
        new_row = {}
        new_row['populationType'] = spec.pop_type
        new_row['measuredProp'] = spec.mprop
        new_row['statType'] = spec.stat_type

        # Get independent variables.
        variables = []
        for name in spec.cprop:
            variables.append((name, "", False))
            # Get dependent variables which depend on the value of the
            # constraint.
            for name in spec.dpv:
                variables.append((name.prop, name.val, True))
                # Variables are sorted alphabetically.
                variables = sorted(variables)

                # Add as a row to entire dataframe.
                for index, variable in enumerate(variables):
                    var_name, constraint, is_dpv_var = variable
                    new_row[f"orig_p{index + 1}"] = var_name
                    new_row[f"p{index + 1}_is_dpv"] = is_dpv_var
                    if is_dpv_var:
                        new_row[f"orig_v{index + 1}"] = constraint
                    dpvs = dpvs.append(new_row, ignore_index=True)

    # Only return statistical variables with at least one dependent variable.
    query_string = ""
    for c in range(1, _MAX_CONSTRAINTS + 1):
        query_string += f"p{c}_is_dpv == 1 or "
    return dpvs.query(f"{query_string} False")


def remove_dependent_constraints(stat_vars):
    """ Removes all dependent constraints from list of stat vars.

  Args: stat_vars: Pandas dataframe holding all stat vars

  Returns: stat_vars with all dependent constraints imputed in place for all 
    rows.
  """
    # Generate list of dependent constraints from protobuf config.
    dpvs = generate_dependent_constraint_list()

    # Merge across common columns shared with dependent variable list.
    common_cols = (['measuredProp', 'populationType', 'statType'] +
                   ["orig_p" + x for x in range(_MAX_CONSTRAINTS_WITH_DPV)])
    stat_vars = pd.merge(stat_vars, dpvs, on=common_cols, how='left')

    # Replace any dependent variables and their value with nan.
    for c in range(1, _MAX_CONSTRAINTS + 1):
        dpv_match = stat_vars.query(f"p{c}_is_dpv == 1")
        # Ensure that constraint {c} exists in both tables.
        if f"orig_v{c}_x" in dpv_match and f"orig_v{c}_y" in dpv_match:
            # Only remove dependent constraints where the value matches.
            dpv_match = dpv_match.query(f"orig_v{c}_x == orig_v{c}_y")
            stat_vars.loc[dpv_match.index, f"p{c}"] = np.nan
            stat_vars.loc[dpv_match.index, f"v{c}"] = np.nan
            stat_vars.loc[dpv_match.index, "numConstraints"] = (
                stat_vars.loc[dpv_match.index,
                              "numConstraints"].apply(lambda x: x - 1))
        # Left shift all imputed columns to remove holes.
        stat_vars = stat_vars.apply(left_fill_columns, axis=1)

        # Rename constraints from merge.
        for c in range(1, _MAX_CONSTRAINTS + 1):
            stat_vars = stat_vars.rename({f"orig_v{c}_x": f"orig_v{c}"},
                                         axis=1)
        return stat_vars


def left_fill_columns(row):
    """ Removes holes in constraints after imputing dependent constraints. 
    Args:
    Row of dataframe with or without holes present between constraints.
    
    Returns:
    Row of dataframe without holes present between constraints.
  """
    row_constraints = min(row['numConstraints'], _MAX_CONSTRAINTS_WITH_DPV)
    # Keep track of the search location to look to pull columns from.
    search_location = 2
    for base_col in range(1, row_constraints + 1):
        # If current population is null then search for the next non-null column.
        if pd.isna(row[f"p{base_col}"]):
            search_location = max(search_location, base_col + 1)
            while search_location <= _MAX_CONSTRAINTS:
                # Swap first non-null with the current null location.
                if not pd.isna(row[f"p{search_location}"]):
                    row[f"p{base_col}"] = row[f"p{search_location}"]
                    row[f"v{base_col}"] = row[f"v{search_location}"]
                    row[f"p{search_location}"] = np.nan
                    row[f"v{search_location}"] = np.nan
                    search_location += 1
                    break
                search_location += 1
    return row


def row_to_human_readable(row):
    """ Generates a human readable name for a dataframe row.
  Args:
    Row: A preprocessed dataframe row with dependent variables removed and
    all constraints, values, and populations remove.

  Returns:
    String mapping between the provided row to the corresponding human readable
    dcid format: <?statType>_<mProp>_<popType>_<v1>_<v2>_..._<mQual>_<mDenom>
  """
    # Add measured property and population type. e.g. Count_InsuranceClaim.
    human_string = (f"{svrc.capitalizeFirst(row['measuredProp'])}" +
                    f"_{svrc.capitalizeFirst(row['populationType'])}")

    # StatType (e.g. median) is prepended if the stat type is not measuredValue.
    stat_type = row['statType']
    if stat_type != "measuredValue" and stat_type != "Unknown":
        human_string = (svrc.capitalizeFirst(stat_type.replace("Value", ""))
                        + "_" + human_string)

    # Append renamed constraint fields.
    row_constraints = min(row['numConstraints'], _MAX_CONSTRAINTS_WITH_DPV)
    for num in range(1, row_constraints + 1):
        if not pd.isna(row[f"v{num}"]):
            human_string += "_" + row[f"v{num}"]

    # Append nmeasurement qualifier if it exists.
    measurement_qualifier = row['measurementQualifier']
    if not pd.isna(measurement_qualifier):
        human_string = f"{human_string}_{measurement_qualifier}"

    # Append measurement denominator if it exists.
    measurement_denominator = row['measurementDenominator']
    if not pd.isna(measurement_denominator):
        # Special Case: PerCapita which is directly appended.
        if measurement_denominator == "PerCapita":
            human_string = f"{human_string}_PerCapita"
        # MDoms that are properties (all lower case) are added as Per(Mdom).
        elif measurement_denominator[0].islower():
            human_string = (
                f"{human_string}_Per{svrc.capitalizeFirst(measurement_denominator)}"
            )
        # Everything else is AsAFractionOf.
        else:
            human_string = f"{human_string}_AsAFractionOf{measurement_denominator}"
    return human_string


def ensure_no_overlapping_stat_vars(stat_vars):
    """ Ensures no collisions between statistical variables.
  
  This function ensures that there are not two distinct statistical variables
  (e.g. different constraint, values, etc) that have the same name. There may
  be two rows in the dataframe with the same name that have differences that
  do not result in different statistical variables. E.g. same properties
  except for measurement method.

  Args:
    stat_vars: Dataframe of stat_vars with human readable name generated.

  Returns:
    stat_vars dataframe with no duplicate rows by name.
  
  Raises:
    Assertion error if two distinct statistical variables evaluate to the same
    name.
  """
    # Consider the subset of statistical variables that have at least one overlap.
    overlapping_stat_var_names = (stat_vars[stat_vars.duplicated(
        'HumanReadableName', keep=False)])

    # Check to make sure that none of these are actually different stat vars.
    # TODO(tjann): update this list--measurementDenominator and scalingFactor
    # are no longer SV props.
    properties_of_statistical_variables = [
        'populationType', 'measuredProp', 'measurementQualifier',
        'measurementDenominator', 'statType', 'scalingFactor'
    ]
    for c in range(1, _MAX_CONSTRAINTS + 1):
        properties_of_statistical_variables.append(f"orig_p{c}")
        properties_of_statistical_variables.append(f"orig_v{c}")

    # See if there are any duplicates outside of this set.
    bad_overlaps = overlapping_stat_var_names[
        overlapping_stat_var_names.duplicated(
            properties_of_statistical_variables, keep=False) == False]

    # Print out error if there are real collisions.
    bad_overlaps = bad_overlaps.sort_values(['v1', 'v2', 'v3'])
    bad_overlaps_str = ""
    for index, row in bad_overlaps.iterrows():
        bad_overlaps_str += row_to_stat_var_mcf(row) + ","
    assert bad_overlaps.shape[0] == 0, "Duplicate StatVars!: " + bad_overlaps

    # No issues so remove these duplicate names.
    return stat_vars.drop_duplicates("HumanReadableName")


def build_original_constraints(row):
    """ Builds list of original properties and constraints in MCF Format.
  Helper method for output MCF generation from a statistical variable row. 

  Args:
    row: Row of pandas dataframe with renamed constraint and value fields.

  Returns:
    Multiline string of constraints and values in the format of 
    p1: dcs:v1 
    p2: dcs:v2... 
  """
    constraints_text = ""
    current_constraint = 1
    while (current_constraint <= _MAX_CONSTRAINTS
           and not pd.isna(row[f"orig_p{current_constraint}"])):
        constraints_text += f"{row[f'orig_p{current_constraint}']}:"
        constraints_text += f"dcs:{row[f'orig_v{current_constraint}']}\n"
        current_constraint += 1
    return constraints_text


def row_to_stat_var_mcf(row):
    """ Creates MCF Statistical Variable node from a dataframe row.
    
  To integrate these new statistical variables into the Data Commons graph,
  they need to uploaded as MCF nodes with a new dcid but with the same
  properties.
  This function creates that MCF as a text file from a row of the dataframe.

  Args:
    row: Statistical variable dataframe row with HumanReadableName.
  Returns:
    Multiline string of the new MCF node for that statistical variable.
  """
    new_stat_var = (svrc.TEMPLATE_STAT_VAR
      .replace("{human_readable_dcid}", row['HumanReadableName'])\
      .replace("{populationType}", row['orig_populationType'])\
      .replace("{statType}", row['statType'])\
      .replace("{measuredProperty}", row['measuredProp'])\
      .replace("{CONSTRAINTS}", build_original_constraints(row)))

    # Add optional fields.
    if not pd.isna(row['measurementQualifier']):
        new_stat_var += f"measurementQualifier: dcs:{row['measurementQualifier']}\n"
    if not pd.isna(row['measurementDenominator']):
        new_stat_var += (
            f"measurementDenominator: dcs:{row['measurementDenominator']}\n")

    return new_stat_var


def remove_new_stat_vars(stat_vars, client):
    """ Removes Statistical Variables that do not already exist. 

  Pulls the existing StatVar list from production and makes sure that no new
  statistical variables are added. This function is used in the event that you
  need to refresh a file dependent on this generation, but do not want to
  fully refresh the statistical variable list.

  Args:
    stat_vars: The dataframe of statistical variable with 
    HumanReadableNames generated.
    client: An authenticated BigQuery client.
  """
    stat_vars_query = """
  SELECT distinct id FROM
  `google.com:datcom-store-dev.dc_kg_2020_07_12_01_01_43.Instance`
  WHERE type = "StatisticalVariable"
  """
    existing_stat_vars = client.query(stat_vars_query).to_dataframe()['id']
    return stat_vars[stat_vars['HumanReadableName'].isin(existing_stat_vars)]


def create_human_readable_names(stat_vars, client):
    """ Handles generating human readable statistical variables from BQ
  response.
  This function handles renaming constraints, populations, and values; 
  removing dependent constraints; and adding a column for the HumanReadableName.

  Args:
    stat_vars: Raw dataframe of statistical variables as returned by the
    download_stat_vars function.
    client: Authenticated BigQuery dataframe. x

  Returns:
    stat_vars dataframe with new HumanReadableName column.
  """
    # Build constraint remappings.
    prop_remap = {}
    svrf.rename_naics_codes(prop_remap, client)
    svrf.rename_dea_drugs(prop_remap, client)
    svrf.rename_isic_codes(prop_remap, client)
    svrf.cause_of_death_remap(prop_remap, client)
    svrf.prefix_strip(prop_remap)
    svrf.rename_boolean_variables(prop_remap, stat_vars)
    svrf.remap_numerical_quantities(prop_remap)
    svrf.prepend_and_append_text(prop_remap)
    svrf.misc_mappings(prop_remap)

    # Drop erroneous constraints.
    for c in range(1, _MAX_CONSTRAINTS + 1):
        stat_vars = stat_vars.query(f"v{c} != 'NAICSUnknown'")

    # Apply constraint renamings.
    stat_vars = stat_vars.apply(
        lambda row: remap_constraint_from_prop(row, prop_remap), axis=1)

    # Remove dependent constraints.
    stat_vars = remove_dependent_constraints(stat_vars)
    stat_vars = left_fill_columns(stat_vars)

    # Generate human readable names.
    stat_vars['HumanReadableName'] = stat_vars.apply(row_to_human_readable)

    # Manually rename special case.
    stat_vars.loc[stat_vars['HumanReadableName'] == 'Count_Death_Medicare',
                  'HumanReadableName'] = "Count_Death_MedicareEnrollee"
    return stat_vars


def output_stat_var_documentation(stat_vars):
    """ Outputs markdown file of Statistical Variable list for documentation.

  Outputs Statistical Variable list as a dropdown menu organized by verticals
  and population type. Some verticals have no sub-population type grouping.
  These groupings are defined in STAT_VAR_POPULATION_GROUPINGS. The markdown
  file is output to statistical_variables.md.

  Args:
    stat_vars: The dataframe of statistical variable with 
    HumanReadableNames generated.
  """
    # Dynamically generate list of disasters.
    natural_disasters = []
    for popType in stat_vars['populationType'].unique():
        if "Event" in popType:
            natural_disasters.append(popType)
    # (False, True) -> Only group disaster StatVar by populationType
    # if there are more than 1 statistical variables for that group.
    svrc.STAT_VAR_POPULATION_GROUPINGS.append(
        svrc.SVPopGroup(("Disasters", natural_disasters, False, True)))

    # Assert that all population types belong to a category.
    used = []
    for _, group, _, _ in svrc.STAT_VAR_POPULATION_GROUPINGS:
        used.extend(group)
    for popType in stat_vars['populationType'].unique():
        assert popType in used, (f"{popType} not sorted!")

    # Output markdown file grouped by population type.
    with open('statistical_variables.md', 'w', newline='') as f_out:
        # Output heading.
        f_out.write(svrc.DOCUMENTATION_BASE_MARKDOWN)

        # Output each vertical group. Some verticals are always
        # nested by population.
        # If nested_grouping is True, and, if nested_grouping is false, then
        # stat var groups larger than 1 are grouped
        # if condense_big_groups is true.
        for sv_grouping in svrc.STAT_VAR_POPULATION_GROUPINGS:
            f_out.write(
                svrc.DOCUMENTATION_HEADER_START.replace("{HEADER}",
                                                   sv_grouping.vertical))

            for population_type in sv_grouping.popTypes:
                # GroupBy popType if nested or condensed and more one stat var.
                stat_vars_for_pop_type = stat_vars.query(
                    f"populationType == '{population_type}'"
                )['HumanReadableName']
                group_pop_type = (sv_grouping.subgroupAllPops
                                  or (sv_grouping.subgroupIfMoreThanOne
                                      and len(stat_vars_for_pop_type) > 1))

                if group_pop_type:
                    f_out.write(
                        svrc.DOCUMENTATION_DROPDOWN_START.replace(
                            "{POPULATION_TYPE}", population_type))
                # Output individual statistical variable as a link to DC graph.
                for stat_var in stat_vars_for_pop_type:
                    f_out.write(
                        f"  <li><a href=\"https://browser.datacommons.org/kg?dcid={stat_var}\">{stat_var}</a></li>\n"
                    )
                # End popType group html.
                if group_pop_type:
                    f_out.write("  </ul>\n")
                    f_out.write("</details>\n")
            f_out.write("</details>\n")


def main(argv):
    """ Executes the downloading, preprocessing, renaming, and output of MCF stat
  var renaming.
  
  Outputs:
    renamed_stat_vars.mcf: MCF file to manifest into graph with the newly
      created names for the statistical variables.
    statistical_variables.md: A markdown file for use in documentation that
      is grouped by population type.
    statistical_variables.csv: A CSV, for debugging, that contains information
      about each newly created statistical variable.
  """
    # Authenticate a BigQuery client with production access.
    client = authenticate_bq_client()

    # Query for stat vars by combining population and observation tables.
    stat_vars = download_stat_vars(client)

    # Create human readable names.
    stat_vars = create_human_readable_names(stat_vars, client)

    # Limit to only existing statistical variables if chosen.
    if ONLY_REGENERATE_OUTPUT:
        stat_vars = remove_new_stat_vars(stat_vars, client)
    stat_vars = stat_vars.query("statType != 'Unknown'")

    # Apply filters for special cases as requested by various human reviewers.
    stat_vars = stat_vars.query("numConstraints <= 3")
    stat_vars = stat_vars.query("measuredProp != 'cohortScaleAchievement'")
    stat_vars = stat_vars.query(
        "measuredProp != 'gradeCohortScaleAchievement'")
    stat_vars = stat_vars.query("populationType != 'AcademicAssessmentEvent'")

    # Sort final output for markdown and CSV output.
    stat_vars = stat_vars.sort_values([
        'populationType', 'numConstraints', 'statType', 'measuredProp', 'p1',
        'p2', 'p3', 'p4', 'p5', 'p6', 'v1', 'v2', 'v3', 'v4', 'v5', 'v6',
        'measurementDenominator', 'measurementQualifier'
    ])

    # Check to make sure that there are no statistical variable collisions.
    stat_vars = ensure_no_overlapping_stat_vars(stat_vars)

    # Output statistical variable markdown file.
    output_stat_var_documentation(stat_vars)

    # Output statistical variable MCF.
    with open('renamed_stat_vars.mcf', 'w', newline='') as f_out:
        for _, row in stat_vars.iterrows():
            f_out.write(row_to_stat_var_mcf(row))

    # Output CSV for debugging.
    stat_vars = stat_vars.fillna("None")
    stat_vars[[
        'numConstraints', 'populationType', 'measuredProp', 'p1', 'v1', 'p2',
        'v2', 'p3', 'v3', 'HumanReadableName', 'orig_p1', 'orig_v1', 'orig_p2',
        'orig_v2', 'orig_p3', 'orig_v3', 'orig_p4', 'orig_v4'
    ]].to_csv("statistical_variables.csv", index=False)


if __name__ == '__main__':
    app.run(main)
