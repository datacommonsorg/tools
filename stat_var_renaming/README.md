# DataCommons Statistical Variable Generation Tool
Scripts to generate human readable statistical variables across the entire
DataCommons domain. These files handle the creation of the statistical variables,
placement into a writable MCF format, and the creation of documentation.

To Refresh Statistical Variables
1. Determine authentication method for BigQuery in stat_var_renaming.py.
2. Run stat_var_renaming.py after installing requirements.
3. Manifest statistical variable MCF to DataCommons KG.
4. Update statistical_variables.md in the datacommonsorg/docsite GitHub repo.
