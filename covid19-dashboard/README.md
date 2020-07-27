# DC COVID-19 Dashboard
NOTE: ```place_type``` refers to either ```Country, State or County```.

Examples:
get_stats(place_type="Country") -> Returns stats for all Countries.
get_stats(place_type="State") -> Returns stats for all US States.
get_stats(place_type="County") -> Returns stats for all US Counties.


#### Server APIs:
The APIs are based on a ```place_type```.

**api/country-data**: returns the data for all Countries in the world with WHO COVID-19 data.
 - downloads in a few ms.

**api/state-data**: returns the data for all States in the US with NYT COVID-19 data.
 - downloads in a few ms.

**api/county-data**: returns the data for all Counties in the US with NYT COVID-19 data.
 - downloads in 1-2 seconds.




######The return types for all three APIs are identical, they are of the following type:

``{
"name": string,
'population': int,
'containedIn': string,
'7DayAverageCases': {iso-date: int},
'7DayAverageDeaths': {iso-date: int},
'7DayAverageCasesValue': int,
'7DayAverageDeathsValue': int,
'perCapitaCases': {iso-date: int},
'perCapitaDeaths': {iso-date: int},
'perCapitaCasesValue': int,
'perCapitaDeathsValue': int,
'pctChangeCasesValue': int,
'pctChangeDeathsValue': int
}``


#### Example

{
"name": 'Florida', # region's name.
'population': 21_480_000, # total population.
'containedIn': 'country/USA', # geo_id of the place that directly contains this geoId.
'type': 'State', # type of region: "Country", "State" or "County".
'7DayAverageCases': {'2020-01-01': 10, '2020-01-02': 12}, # time-series data as a dictionary.
'7DayAverageCasesValue': 12, # value for the latest date in the "7DayAverageCases" time-series.
'7DayAverageDeaths': {'2020-01-01': 4, '2020-01-02': 5}, # time-series data as a dictionary.
'7DayAverageDeathsValue': 5, # value for the latest date in the "7DayAverageDeaths" time-series.
'perCapitaCases': {'2020-01-01': 0.46, '2020-01-02': 0.55}, # time-series data as a dictionary.
'perCapitaCasesValue': 0.55, # value for the latest date in the "perCapitaCases" time-series.
'perCapitaDeaths': {'2020-01-01': 0.18, '2020-01-02': 0.23}, # time-series data as a dictionary.
'perCapitaDeathsValue': 0.23, # value for the latest date in the "perCapitaDeaths" time-series.
'pctChangeCasesValue': 19.57, # value representing an increase of cases from date X to latest date.
'pctChangeDeathsValue': 27.78 # value representing an increase of deaths from date X to latest date.
}
