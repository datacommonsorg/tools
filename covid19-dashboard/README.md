# DC COVID-19 Dashboard

**NOTE:** ```place_type``` refers to either ```Country, State or County```.

Examples:
get_stats(place_type="Country") -> Returns stats for all Countries.
get_stats(place_type="State") -> Returns stats for all US States.
get_stats(place_type="County") -> Returns stats for all US Counties.

## Server APIs

The /data/ APIs are based on a ```place_type```.

**api/data/Country**: returns the data for all Countries
in the world with WHO COVID-19 data.

- Contains approximately 181 Countries in the world.  
- Weighs less than 1MB.

**api/data/State**: returns the data for all States
in the US with NYT COVID-19 data.

- Contains exactly 50 US States and 2 US territories.  
- Weighs less than 1MB.

**api/data/County**: returns the data for all Counties
in the US with NYT COVID-19 data.

- Contains approximately 3,000 US Counties.
- Weighs less than 3MB.

### Returns types for all APIs are identical.

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

## Example

    {
    # region's name.
    "name": 'Florida',
    # total population.
    'population': 21_480_000,
    # geo_id of the place that directly contains this geoId.
    'containedIn': 'country/USA',
    # type of region: "Country", "State" or "County".
    'type': 'State',
    # time-series data as a dictionary.
    '7DayAverageCases': {'2020-01-01': 10, '2020-01-02': 12},
    # value for the latest date in the "7DayAverageCases" time-series.
    '7DayAverageCasesValue': 12,
    # time-series data as a dictionary.
    '7DayAverageDeaths': {'2020-01-01': 4, '2020-01-02': 5},
    # value for the latest date in the "7DayAverageDeaths" time-series.
    '7DayAverageDeathsValue': 5,
    # time-series data as a dictionary.
    'perCapitaCases': {'2020-01-01': 0.46, '2020-01-02': 0.55},
    # value for the latest date in the "perCapitaCases" time-series.
    'perCapitaCasesValue': 0.55,
    # time-series data as a dictionary.
    'perCapitaDeaths': {'2020-01-01': 0.18, '2020-01-02': 0.23},
    # value for the latest date in the "perCapitaDeaths" time-series.
    'perCapitaDeathsValue': 0.23,
    # value representing an increase of cases from date X to latest date.
    'pctChangeCasesValue': 19.57,
    # value representing an increase of deaths from date X to latest date.
    'pctChangeDeathsValue': 27.78
    }
