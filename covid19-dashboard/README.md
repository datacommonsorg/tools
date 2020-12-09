# DC COVID-19/Social Wellness Dashboard

**NOTE:** ```place_type``` refers to either ```Country, State or County```.

## Server APIs

The /data/ APIs are based on a ```place_type```.
**NOTE:** Only COVID-19 dashboard has County-level data.

**api/data/Country/covid19**: returns the data for all Countries in the world with COVID-19 data.

**api/data/Country/socialWellness**: returns the data for all Countries in the world with Social Wellness data.

**api/data/State/covid19**: returns the data for all States in the US with COVID-19 data.

**api/data/State/socialWellness**: returns the data for all States in the US with Social Wellness data.

**api/data/County/covid19**: returns the data for all Counties in the US with COVID-19 data.

### Return types for all APIs are identical

The keys are based on the Configuration.py file.
There can be many infinite keys.

    {
        "name": string,
        "population": int,
        "containedIn": string,
        "cumulative{key1}": {isoDate: float},
        "cumulative{key2}": {isoDate: float},
        "movingAverage{key1}": {isoDate: float},
        "movingAverage{key2}": {isoDate: float},
        "perCapita{key1}": {isoDate: float},
        "perCapita{key2}": {isoDate: float},
    }

### Example

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

## calculate_data.py

### calculate_data() the following parameters

    1. Stats as a dict of type {date: float}.
        1. date is a string in ISO-8601 format.
        2. value is a float.
    2. Population as an int.
        1. The total population of the region being observed.
        2. This is used to perform per-capita calculations.
        3. Cannot be <= 0.
    3. Moving_average_chunk_size as a int:
        1. The N-days to take the moving average of.
        2. **NOTE:** The first N-day indices of the return type will be omitted.
    4. Clean_step_size as int:
        1. If a date's index is not divisible by clean_step_size, drop it.
        2. Only index divisible by clean_step_size will be kept.
        3. If clean_step_size === 1, keep all values.
        3. Example: clean_step_size = 2, ["Jan", "Feb", "Mar", "Apr", "May"] => ["Jan", "Mar", "May"] because indexes 0, 2 and 4 are divisible by 2.

### calculate_data() performs the following calculations

    1. Moving Average (N-days).
        1. For every date in the input, sum up the values of the previous N-days and divide by N-days.
        2. If Moving Average == 0, skip the moving average calculation. Use raw data instead.
    2. Cumulative:
        1. For every date in the input, sum up the values of all the previous days.
    3. Per Capita of the Moving Average or Raw.
        1. For every date in the Moving Average output, divide by the place's total population.
        2. Multiply by 1M to amplify data -- 0.00001 numbers are not too friendly.
    4. Percent Change of the Moving Average or Raw.
        1. For every date in Moving Average, divide by the value from (date - date_from_baseline).
        2. Subtract 1 to the value.
        2. Multiply by 1M to convert to a percent.

## Front-End

Depending on whether the user visits `/dashboard/covid19` or `/dashboard/socialWellness`, a different configuration file will be used to draw the table.
The browser will use `src/covid19.json` for the COVID-19 dashboard.
The browser will use `src/sociallWelness.json` for the Sociall Wellness dashboard.
The configuration files have a `table` property with a list of category objects.

### Example of Category Object

```
    {
        # title of the category.
        "title": "Above Poverty",
        # key of the category to retrieve data from API. Data must exist in API response, or will be skipped.
        "id": "cumulativeAbovePovertyInLast12Months",
        # what type of graph to draw for this category. View ./src/Th.tsx to add or remove any types.
        "typeOf": "lineGraph",
        # The color of the graph. Any CSS color will also work. View CSS file for any predefined colors.
        "color": "--dc-red-strong",
        # when the user hovers on the graph, the subtitle of the graph.
        "graphSubtitle": "Total Population Above Poverty (Last 12 Months)",
        # is the category enabled by default on page load.
        "enabled": false
    }
```

## Local Development

### Set Google Application Credential

**NOTE:** This project is currently deployed under the GCP Project `datcom-wesbite`, but any other project can be used instead.

```bash
export GOOGLE_CLOUD_PROJECT="datcom-website"
gcloud config set project $GCP_PROJECT && \
gcloud auth application-default login
```

#### Install Node.JS 12 and Python 3.7

**NOTE:** Although other versoins of Node might work, only Node 12 has been tested.
**NOTE:** Although other versions of Python might work, only Python 3.7 has been tested.

Before running the server, install [nodejs](https://nodejs.org/en/download/)
Before running the server, install [python](https://www.python.org/downloads/)

#### Run Google Cloud App Engine Locally

App Engine Documentation [here](https://cloud.google.com/appengine/docs/standard/python3/testing-and-deploying-your-app)
Will start a local server on port 8080.
Visit `localhost:8080/dashboard/?dashboardId=covid19` to view the COVID-19 dashboard.
Visit `localhost:8080/dashboard/?dashboardId=socialWellness` to view the Sociall Wellness dashboard.

```bash
sh run_locally.sh
```

#### Deploy to Google Cloud App Engine

You will be asked some questions prior to deployment. This step requires your input.

```bash
sh deploy_gcloud.sh
```
