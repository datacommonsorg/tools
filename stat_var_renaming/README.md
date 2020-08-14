# DataCommons Statistical Variable Generation Tool
Scripts to generate human readable statistical variables across the entire
DataCommons domain. These files handle the creation of the statistical variables,
placement into a writable MCF format, and the creation of documentation.

To Refresh Statistical Variables
1. Determine authentication method for BigQuery in stat_var_renaming.py.
2. Run stat_var_renaming.py after installing requirements.
3. Manifest statistical variable MCF to DataCommons KG.
4. Update statistical_variables.md in the datacommonsorg/docsite GitHub repo.

## Proto defintions
pop_obs_spec_common.proto defines the proto definition for indepedent versus
depedent variables. Certain variables are implicit due to other ones that are
present. For example, the property (withIncome: 20000DollarsOrMore) is always
matched with (incomeStatus: withIncome), but this property is implicit via
withIncome so can be removed from the statistical variable name.
pop_obs_spec_nocovid.textproto has the actual list of variable definitions, for
the statistical variable renaming this list has been modified slightly to remove
certain dependences that are only present for display purposes in the Timeline
tool. For example, confirmed COVID cases has a dependent variable
of medicalStatus: confirmedCase as COVID is currently the only tracked disease
outbreak in DataCommons. This case is commented out for the
naming as otherwise covid would be supressed from the variable name and may break
as the knowledge graph expands.

## Markdown formatting
The output markdown file for statistical variables has some verticals are grouped
such that all population types are a sub-level grouping, while others (like disasters), only
group by population types when there are multiple statistical variables for that
population type. This can be configured in the stat_var_renaming_constants.py file.