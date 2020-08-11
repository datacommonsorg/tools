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
""" Defines functions used for remapping constraints in the statistical
variable renaming. 

Each function in this file defines a renaming of a particular constraint.
Each encompassing function takes in a prop_remap object, which is a dictionary
of properties to a list renaming functions. 
Each renaming functions should be of the form(property, constraint, popType)
and should return the renamed constraint. In the main code, these functions are
iterated on all matching properties in the order that they are added.


Main Function.
Args:
  prop_remap: Dictionary mapping properties to a list of renaming functions. 
Returns:
  prop_remap: Updated dictionary.

Renaming Function.
Args:
  property: The property of the object to be renamed. E.g. householderAge.
  constraint: The value of the property. E.g. Years15Onwards.
  popType: The population type that this property belongs to. E.g. Person.
"""

import stat_var_renaming as svr
import stat_var_renaming_constants as svrc
import pandas as pd
import re

def remap_numerical_quantities(prop_remap):
    """ Adds a remapping function to change numerical quantities to a more
    readable format dependent on regex rules. 

    Examples: 'Years15Onwards': '15OrMoreYears'
              'Years25To44': '25To44Years'
  """
    def remap_numerical_quantities_helper(_, constraint, _pop):
        if not pd.isna(constraint):
            for regex, renaming_func in svrc.REGEX_NUMERICAL_QUANTITY_RENAMINGS:
                match_obj = regex.match(constraint)
                if match_obj:
                    return renaming_func(match_obj)
            return constraint
        else:
            return None

    # Opt-in list to rename.
    for prop in svrc.NUMERICAL_QUANTITY_PROPERTIES_TO_REMAP:
        svr.addPropertyRemapping(prop_remap, prop,
                             remap_numerical_quantities_helper)
    return prop_remap


def rename_boolean_variables(prop_remap, stat_vars):
    """ Remaps all variables with boolean constraint values.

    Args:
      stat_vars: List of all statistical variables. Used to find which
          properties have entirely boolean values.

    Example: (hasComputer, False) -> noComputer.
  """
    def map_boolean_constraints(property, value, _pop):
        assert (value == "True" or value == "False")
        constraint_value = value == "True"
        pop = None
        prefix = None
        if property.startswith("has"):
            pop = property[3:]
            prefix = "Has" if constraint_value else "No"
        elif property.startswith("is"):
            pop = property[2:]
            prefix = "Is" if constraint_value else "Not"
        else:
            assert False, f"Unhandled prefix {property}"
        return prefix + pop

    # Get all constraints with boolean values and add a remapping.
    boolean_populations = set()
    for c in range(1, svrc.MAX_CONSTRAINTS + 1):
        unique_constraints = stat_vars[stat_vars[f"v{c}"].isin(
            ['True', 'False'])][f"p{c}"].unique()
        boolean_populations.update(unique_constraints)
    for pop in boolean_populations:
        svr.addPropertyRemapping(prop_remap, pop, map_boolean_constraints)
    return prop_remap


def prefix_strip(prop_remap):
    """ Strips measurement method prefixes from constraints.

    Example: BLS_InLaborForce -> InLaborForce.
  """
    def strip_prefixes(prop, constraint, _pop):
        # Prefixes may be a list or single value.
        prefixes = CONSTRAINT_PREFIXES_TO_STRIP[prop]
        prefixes_for_prop = prefixes if isinstance(prefixes,
                                                   list) else [prefixes]

        for prefix in prefixes_for_prop:
            if constraint.startswith(prefix):
                constraint = constraint.replace(prefix, "")
                return constraint.lstrip("_")
        return constraint

    for prop_to_add in svrc.CONSTRAINT_PREFIXES_TO_STRIP:
        svr.addPropertyRemapping(prop_remap, prop_to_add, strip_prefixes)

    return prop_remap


def cause_of_death_remap(prop_remap, client):
    """ Remaps ICD10 death codes into full names.

    Args:
      client: Authenticated BigQuery client. Used to get names of ICD10 codes.

    Example: (causeOfDeath, ICD10/A00-B99) -> InfectiousParasiticDiseases.
  """
    # Query all drug names from cluster.
    cause_of_death_query = """
  SELECT id, name
  FROM `google.com:datcom-store-dev.dc_v3_clustered.Instance`
  WHERE type = "ICD10Section" or type = "ICD10Code"
  """
    cause_of_death_instances = client.query(
        cause_of_death_query).to_dataframe()

    # Helper function to rename ICD10 codes to easier to read names.
    def provide_consistent_naming(row):
        icd10_code = row['ICD10Code']
        # Manually remap abnormally long names.
        if icd10_code in svrc.MANUAL_CAUSE_OF_DEATH_RENAMINGS:
            return svrc.MANUAL_CAUSE_OF_DEATH_RENAMINGS[id]

        # Otherwise remove codes and camel case the name.
        row['id'] = icd10_code
        row['name'] = svrc.standard_name_remapper(
            (row['name'].replace(icd10_code.replace("ICD10/", ""),
                                 "").strip().lstrip("(").rstrip("()")))
        return row

    cause_of_death_instances["ICD10Code"] = cause_of_death_instances["id"]
    cause_of_death_instances = cause_of_death_instances.set_index("id")
    cause_of_death_instances = cause_of_death_instances.apply(
        provide_consistent_naming, axis=1)

    # Add modification function.
    def death_id_to_name(_, death_id, _pop):
        return cause_of_death_instances.loc[death_id]['name']

    svr.addPropertyRemapping(prop_remap, 'medicalCode', death_id_to_name)
    svr.addPropertyRemapping(prop_remap, 'causeOfDeath', death_id_to_name)


def rename_dea_drugs(prop_remap, client):
    """ Renames DEA drug codes to common names. Note that some codes are
  intentionally unmapped as they are exceptionally long and do not have common
  usage. The DEA drug names were not in a "nice" format so they are manually
  renamed.

  Example: (drugPrescribed, drug/dea/4000) -> AnabolicSteroids
  """

    # Add modification function from manual naming scheme.
    def drug_id_to_name(_, drug_id, _pop):
        if drug_id in svrc.DRUG_REMAPPINGS:
            return svrc.DRUG_REMAPPINGS[drug_id]
        else:
            return drug_id.replace("drug/", "")

    svr.addPropertyRemapping(prop_remap, 'drugPrescribed', drug_id_to_name)


def misc_mappings(prop_remap):
    """ Any miscellaneous renamings that need to happen should go here.

    1) Remove ACSED from memberStatus.
    2) Quantity for dateBuilt refers to time not count so use different
    terminology.
  """
    def remove_acsed(_, constraint, _pop):
        return constraint.replace("ACSED", "")

    svr.addPropertyRemapping(prop_remap, 'memberStatus', remove_acsed)

    def replace_date_built(_, constraint, _pop):
        constraint = constraint.replace("OrMore", "OrLater")
        return constraint.replace("Upto", "Before")

    svr.addPropertyRemapping(prop_remap, 'dateBuilt', replace_date_built)


def prepend_and_append_text(prop_remap):
    """ Adds remapping functions which either prepend or append text to all
    constraints for a property.

    Example: (languageSpokenAtHome, AfricanLanguages) ->
    AfricanLanguagesSpokenAtHome 
  """
    def addTextToConstraint(prop,
                            prepend="",
                            append="",
                            include_pop=[],
                            exclude_pop=[]):
        """ Helper to add a simple prepend/append renaming scheme to a property.

    Args:
      prop: Property to apply the remapping to.
      prepend: Text to prepend to constraint.
      append: Text to append to constraint.
      include_pop: Only apply the remapping to popTypes in this group or
        to all groups if this list is empty.
      exclude_pop: Do not apply the remapping to any popTypes in this group.
    """
        def apply_to_pop(pop):
            if pop in exclude_pop:
                return False
            elif include_pop == []:
                return True
            else:
                return pop in include_pop

        text_mod = (
            lambda _, text, pop: prepend + svrc.capitalizeFirst(text) + append
            if apply_to_pop(pop) else text)
        svr.addPropertyRemapping(prop_remap, prop, text_mod)

    addTextToConstraint("languageSpokenAtHome", append="SpokenAtHome")
    addTextToConstraint("childSchoolEnrollment", prepend="Child")
    addTextToConstraint("residenceType", prepend="ResidesIn")
    addTextToConstraint("healthPrevented", prepend="Received")
    addTextToConstraint("householderAge", prepend="HouseholderAge")
    addTextToConstraint("householderRace", prepend="HouseholderRace")
    addTextToConstraint("dateBuilt", append="Built")
    addTextToConstraint("homeValue", prepend="HomeValue")
    addTextToConstraint("numberOfRooms", prepend="WithTotal")
    addTextToConstraint("naics", prepend="NAICS")
    addTextToConstraint("isic", prepend="ISIC")
    addTextToConstraint("establishmentOwnership", append="Establishment")
    addTextToConstraint("householdSize", prepend="With")
    addTextToConstraint("numberOfVehicles", prepend="With")
    addTextToConstraint("income", prepend="IncomeOf")
    addTextToConstraint("grossRent", prepend="GrossRent")
    addTextToConstraint("healthOutcome", prepend="With")
    addTextToConstraint("healthPrevention", prepend="Received")
    addTextToConstraint("propertyTax", prepend="YearlyTax")
    addTextToConstraint("detailedLevelOfSchool", prepend="Detailed")
    addTextToConstraint("medicalCondition", prepend="Condition")
    addTextToConstraint("educationalAttainment",
                        prepend="EducationalAttainment")


def rename_isic_codes(prop_remap, client):
    """ Renames all ISIC economic codes to their full names in the database.
    
    Args:
      client: Authenticated BQ client.

    Example: (isic, ISICv3.1/I) -> ISICTransportStorageCommunications.
  """
    # Download all ISIC codes names from cluster.
    ISIC_QUERY = """
  SELECT id, name
  FROM `google.com:datcom-store-dev.dc_v3_clustered.Instance`
  WHERE type = "ISICv3.1Enum"
  """
    isic_instances = client.query(ISIC_QUERY).to_dataframe()
    isic_instances = isic_instances.set_index("id")
    isic_instances['name'] = isic_instances['name'].apply(
        svrc.standard_name_remapper)

    # Add modification function
    def isic_id_to_name(_, isic, _pop):
        return isic_instances.loc[isic]['name']

    svr.addPropertyRemapping(prop_remap, 'isic', isic_id_to_name)
    return isic_instances


def rename_naics_codes(prop_remap, client):
    """ Adds a remapping function to change NAICS codes to their corresponding
    industry.

    Args:
      client: Authenticated BQ client.

    Example: (NAICS, NAICS/23) -> Construction)
  """
    def filter_to_string(filter):
        new_str = ""
        for char in list(filter):
            new_str += char
        return new_str

    # Download all NAICS codes names from cluster
    NAICS_QUERY = """
  SELECT id, name
  FROM `google.com:datcom-store-dev.dc_v3_clustered.Instance`
  WHERE type = "NAICSEnum"
  """
    naics_instances = client.query(NAICS_QUERY).to_dataframe()
    naics_instances = naics_instances.set_index("id")
    naics_instances['name'] = naics_instances['name'].apply(
        lambda name: filter_to_string(
            filter(lambda c: c.isalpha() or c == " ", name)))
    naics_instances['name'] = naics_instances['name'].apply(
        svrc.standard_name_remapper)

    def naics_id_to_name(_, naics, _pop):
        code = naics.lstrip("NAICSnaics/jolts")
        # Only remap 1-2 digit codes and JOLTS.
        if "JOLTS" not in naics and len(code) > 3:
            return "Unknown"
        if code in svrc.NAICS_MAP:
            return svrc.NAICS_MAP[code]
        if naics in naics_instances:
            return naics_instances.loc[naics]['name']
        return "Unknown"

    svr.addPropertyRemapping(prop_remap, 'naics', naics_id_to_name)
    return prop_remap


def rename_populations(stat_vars):
    """ Applies various rules to remap population names for the stat vars.

    1) Strips measurement prefixes. E.g. BLS_Worker -> Worker.
    2) Renames populations entirely. E.g. MortalityEvent -> Death.

    Args:
      stat_vars: List of all statistical variables before human readable name
        is generated.
    Returns:
      stat_vars with all populations renamed as defined in this function.
  """
    # Prefixes to strip.
    population_prefixes_to_strip = ['BLS', 'USC', 'ACSED']

    def strip_population_prefixes(population):
        for prefix in population_prefixes_to_strip:
            if population.startswith(prefix):
                return re.sub(f"^{prefix}", "", population)
        return population

    stat_vars['populationType'] = stat_vars['populationType'].apply(
        strip_population_prefixes)

    # Rename some populations entirely.
    populations_to_rename = {
        'MortalityEvent': 'Death',
    }
    stat_vars['populationType'] = stat_vars['populationType'].apply(
        lambda pop: populations_to_rename.get(pop, pop))
    return stat_vars
