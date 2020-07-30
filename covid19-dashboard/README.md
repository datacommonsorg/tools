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
    
    {
        "name": string,
        "population": int,
        "containedIn": string,
        "movingAverageCases": {iso-date: int},
        "movingAverageDeaths": {iso-date: int},
        "perCapitaCases": {iso-date: int},
        "perCapitaDeaths": {iso-date: int},
    }

## Example

    {
        # region's name.
        "name": "Florida",
        # total population.
        "population": 21_480_000,
        # geo_id of the place that directly contains this geoId.
        "containedIn": "country/USA",
        # type of region: "Country", "State" or "County".
        "type": "State",
        # time-series data as a dictionary.
        "movingAverageCases": {"2020-01-01": 10, "2020-01-02": 12},
        # time-series data as a dictionary.
        "movingAverageDeaths": {"2020-01-01": 10, "2020-01-02": 12},
        # time-series data as a dictionary.
        "perCapitaCases": {"2020-01-01": 0.46, "2020-01-02": 0.55},
        # time-series data as a dictionary.
        "perCapitaDeaths": {"2020-01-01": 0.18, "2020-01-02": 0.23},
    }



## calculate_data.py:
Takes the following parameters:

    1. stats as a dict of type {date: value}.
        1. date is a string in ISO-8601 format.
        2. value is a float.
    2. population as an int.
        1. The total population of the region being observed.
        2. This is used to perform per-capita calculations.
        3. Cannot be <= 0.
    3. moving_average_chunk_size as a int:
        1. The N-days to take the moving average of.
        2. Note: The first N-day indices of the return type will be omitted.
        
Performs the following calculations:

    1. Moving Average (N-days).
        1. For every date in the input, sum up the values of the previous N-days and divide by N-days.
    2. Per Capita of the Moving Average.
        1. For every date in the Moving Average output, divide by the place's total population.
        2. Multiply by 1M to amplify data -- 0.00001 numbers are not too friendly).
    3. Percent Change of the Moving Average.
        1. For every date in Moving Average, divide by the value from (date - date_from_baseline).
        2. Subtract 1 to the value.
        2. Multiply by 1M to convert to a percent.
        

Outputs the following:
    1. A dictionary of type:

    {
        "movingAverage": {date: value},
        "perCapita": {date: value},
        "pctChange": {date: value}
    }
   