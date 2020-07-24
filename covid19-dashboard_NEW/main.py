# Copyright 2020 Google LLC
#
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

import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Dict, Tuple

from flask import Flask, send_from_directory, Response
from flask_caching import Cache
from flask_compress import Compress

from send_request import send_request
from calculate_data import calculate_data

config = dict(DEBUG=True, CACHE_TYPE="filesystem", CACHE_DIR="/tmp")

app = Flask(__name__, static_folder="./build")

Compress(app)

app.config.from_mapping(config)

# Load the configuration file from the instance folder.
app.config.from_pyfile("config.py")
cache = Cache(app)

# Retrieve the API KEY from the configuration file.
API_KEY = app.config["API_KEY"]

# Retrieves DataCommons Server from configuration file.
DC_SERVER = app.config["DC_SERVER"]

# DataCommons Statvars to be used.
INCREMENTAL_CASES_STATVAR = (
    "IncrementalCount_MedicalConditionIncident_COVID_19_ConfirmedOrProbableCase"
)
INCREMENTAL_DEATHS_STATVAR = (
    "IncrementalCount_MedicalConditionIncident_COVID_19_PatientDeceased")

# The type of sub-regions. Used to remove trailing from name.
# For example, "Miami-Dade County" becomes "Miami-Dade".
PLACE_TYPES = ["County", "Parish", "Borough"]

# COMMONLY-USED TYPES.
OutputDataType = Dict[str, Dict[str, int] or Dict[str, str]]
GeoIdToDataType = Dict[str, Dict[str, int]]
RegionToInfoType = Dict[str, Tuple[str, str, str]]


@app.route('/<path:path>', methods=['GET'])
def static_proxy(path):
    """
    Return the /path file in the directory from the static_folder directory.
    For example, /index.css would return the index.css file.
    No-caching HTTP headers are sent.
    :param path: the file path to return.
    :return: the file if it exists.
    """
    response = send_from_directory(app.static_folder, path)
    response.cache_control.max_age = 0
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/', methods=['GET'])
def index():
    """
    Returns the site's HTML file. No-caching HTTP headers are sent.
    NOTE: Caching may be turned on once the frequency of updates is reduced.
    Otherwise, users my experience a white page due to old files.
    :return: returns the index file for the site.
    """
    response = send_from_directory(app.static_folder, 'index.html')
    response.cache_control.max_age = 0
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route("/api/county-data")
@cache.cached(timeout=3600)
def county_data():
    """
    Returns US County data. Slower than /state-data api.
    NOTE: for return type documentation, please see README.md's APIs section.
    :return: geo_id->{**data, name, geo_id, regionType, containedIn}.
    """
    # Request data for only US Counties.
    data = get_data("County")
    # Adds HTTP headers for browser to store cache.
    response = add_browser_cache_headers_to_response(data)
    return response


@app.route("/api/state-data")
@cache.cached(timeout=3600)
def state_data():
    """
    Returns US state data. Faster than /county-data api.
    NOTE: for return type documentation, please see README.md's APIs section.
    :return: geo_id->{**data, name, geo_id, regionType, containedIn}.
    """
    # Request data for only US States.
    data = get_data("State")
    # Adds HTTP headers for browser to store cache.
    response = add_browser_cache_headers_to_response(data)
    return response


def get_data(place_type: str = "State") -> OutputDataType:
    """
    Requests cases and deaths from the DC, and performs calculations.
    NOTE: for return type documentation, please see README.md's APIs section.
    :param place_type: return states OR counties.
    :return: geo_id->{**data, name, geo_id, regionType, containedIn}.
    """
    # Get all the places in the US.
    # States and Counties.
    places: RegionToInfoType = get_us_places(place_type)
    # Get the total population of all geo_id.
    population: Dict[str, int] = get_population()

    # Convert the places to a list of geo_id.
    # The dictionary is keyed by geo_id, so we can just use that.
    geo_ids: List[str] = list(places.keys())

    # Request all cases and deaths.
    all_cases: GeoIdToDataType = get_stats_by_date(geo_ids,
                                                   INCREMENTAL_CASES_STATVAR)
    all_deaths: GeoIdToDataType = get_stats_by_date(geo_ids,
                                                    INCREMENTAL_DEATHS_STATVAR)

    output: OutputDataType = {}

    for geo_id in geo_ids:
        calculated_cases: Dict[str, int] = {}
        calculated_deaths: Dict[str, int] = {}
        # Make sure we have the population for this geo_id.
        if geo_id not in population:
            continue
        # Otherwise, get the population for this geo_id.
        region_pop = population[geo_id]
        # Get the data for this geo_id.
        if geo_id in all_cases:
            cases = all_cases[geo_id]
            # Perform XYZ calculations.
            calculated_cases = calculate_data("Cases", cases, region_pop)
        if geo_id in all_deaths:
            deaths = all_deaths[geo_id]
            # Perform XYZ calculations.
            calculated_deaths = calculate_data("Deaths", deaths, region_pop)

        name: str = ""
        contained_in_geo_id: str = ""
        place_type: str = ""

        if geo_id in places:
            name: str = places[geo_id][0]
            contained_in_geo_id: str = places[geo_id][1]
            place_type: str = places[geo_id][2]

        # Combine both calculated cases and deaths under output[geo_id].
        output[geo_id] = {
            **calculated_cases,
            **calculated_deaths,
            **{
                "geoId": geo_id,
                "containedIn": contained_in_geo_id,
                "name": name,
                "placeType": place_type,
            },
        }
    # Return a combination of cases + deaths + metadata.
    return output


def get_population() -> Dict[str, int]:
    """
    Returns the total population of each region as a dictionary.
    The key is the geo_id and the value is the population number.
    :return: dict of geo_id->population.
    """
    # Request US State population from DataCommons KG.
    state_response: Dict[str, List[Dict]] = send_request(
        DC_SERVER + "bulk/place-obs",
        {
            "placeType": "State",
            "populationType": "Person",
            "observationDate": "2018",
        },
        api_key=API_KEY,
        compress=True,
        )

    # Request US County population from DataCommons KG.
    county_response: Dict[str, List[Dict]] = send_request(
        DC_SERVER + "bulk/place-obs",
        {
            "placeType": "County",
            "populationType": "Person",
            "observationDate": "2018",
        },
        api_key=API_KEY,
        compress=True,
        )

    # Merge US State and US County responses into one response.
    response: List[Dict] = state_response["places"] + county_response["places"]

    output: Dict[str, int] = {}

    for place in response:
        # Some geo_ids return None if there is no data.
        # Make sure there is data first.
        if "place" not in place and not place["place"]:
            continue
        geo_id: str = place["place"]

        # The census data can be found in place["observations"].
        if "observations" not in place and not place["observations"]:
            continue

        # Search for CensusACS5yrSurvey in observations.
        for observation in place["observations"]:
            # If you find the census data
            if observation["measurementMethod"] == "CensusACS5yrSurvey":
                # Make sure measuredValue has a real value.
                # It is the population.
                if "measuredValue" not in observation:
                    continue
                # Store the population.
                output[geo_id] = observation["measuredValue"]

    # NYT combines several counties into one larger county.
    # Only for the following two exceptions.
    # https://github.com/nytimes/covid-19-data
    # New York City.
    output["geoId/3651000"] = 8_399_000
    # Kansas City.
    output["geoId/2938000"] = 491_918
    return output


def get_us_places(place_type: str = "State") -> RegionToInfoType:
    """
    Returns a dictionary of either US States or US Counties.
    The return is a dict where the key is the geo_id being observed
    and the value is a tuple of metadata about that place.
    :param place_type: return states OR counties.
    :return: dict of geo_id->(name: str, containedIn: str, typeOfRegion: str).
    """

    # Get US State data.
    response = send_request(
        DC_SERVER + "node/places-in",
        {"dcids": ["country/USA"],
         "placeType": "State"},
        api_key=API_KEY,
        )

    # Get the names for the US State data.
    state_geo_ids: List[str] = [x["place"] for x in response]
    response = send_request(
        DC_SERVER + "node/property-values",
        {"dcids": state_geo_ids,
         "property": "name"},
        api_key=API_KEY,
        )

    # geo_id -> (name, containedIn, typeOfRegion).
    states: RegionToInfoType = {}

    # Store the US States.
    for geo_id in response:
        if "out" in response[geo_id] and response[geo_id]["out"]:
            if "value" in response[geo_id]["out"][0]:
                # Store the data for the geo_id.
                name = response[geo_id]["out"][0]["value"]
                states[geo_id] = (name, "country/USA", "State")

    # Get US County data belonging to the US States.
    response = send_request(
        DC_SERVER + "node/places-in",
        {"dcids": state_geo_ids,
         "placeType": "County"},
        api_key=API_KEY,
        )

    # Keep track of what State each County belongs to.
    # geo_id -> belongs_to_geo_id.
    # EXAMPLE: {"geoId/12000": "geoId/12"}
    county_to_state: Dict[str, str] = {}
    for value in response:
        if "place" in value and "dcid" in value:
            county_geo_id: str = value["place"]
            belongs_to_geo_id: str = value["dcid"]
            county_to_state[county_geo_id]: str = belongs_to_geo_id

    # Get the name of all Counties.
    response = send_request(
        DC_SERVER + "node/property-values",
        {"dcids": list(county_to_state.keys()),
         "property": "name"},
        api_key=API_KEY,
        )

    # Store all the US County metadata as a dict of tuples.
    # geo_id -> (name: str, containedIn: str, typeOfRegion: str).
    counties: RegionToInfoType = {}

    # If param return_counties == County, only return County data.
    if place_type == "County":
        for geo_id in response:
            if "out" in response[geo_id] and response[geo_id]["out"]:
                if "value" in response[geo_id]["out"][0]:
                    name: str = response[geo_id]["out"][0]["value"]
                    # Get rid of trailing strings in names such as "County".
                    for reg_type in PLACE_TYPES:
                        name: str = name.rstrip("^" + reg_type)
                    # The geo_id where this region belongs to.
                    belongs_to: str = county_to_state[geo_id]
                    counties[geo_id] = (name, belongs_to, "County")

        # NYT combines several counties into one larger county.
        # Only for the following two exceptions.
        # https://github.com/nytimes/covid-19-data#geographic-exceptions
        counties["geoId/3651000"] = ("New York City", "geoId/36", "County")
        counties["geoId/2938000"] = ("Kansas City", "geoId/29", "County")

        return counties
    # Else only return US State data.
    return states


def get_stats_by_date(geo_ids: List[str], stats_var: str) -> GeoIdToDataType:
    """
    Queries and returns the data in the as a dict of type geo_id->date->value.
    :param geo_ids: list of geo_ids to query data for.
    :param stats_var: the DC stats_var to query data for.
    :return: a dict of type geo_id->date->value.
    EXAMPLE: {geoId/12: {'2020-01-01': 10, '2020-01-02: 20'},
              geoId/13: {'2020-01-01': 6, '2020-01-02: 15'}}
    """
    response = send_request(
        DC_SERVER + "bulk/stats",
        {"place": geo_ids,
         "stats_var": stats_var},
        api_key=API_KEY,
        )

    # geo_id->date->value
    # EXAMPLE: {geoId/12: {'2020-01-01': 10, '2020-01-02: 20'},
    #          geoId/13: {'2020-01-01': 6, '2020-01-02: 15'}}
    output: GeoIdToDataType = defaultdict(dict)

    for geo_id in response:
        if not response[geo_id]:
            continue
        if "data" not in response[geo_id]:
            continue
        data: Dict[str, int] = response[geo_id]["data"]
        for date in data:
            output[geo_id][date] = data[date]
    return output


def add_browser_cache_headers_to_response(data: Dict,
                                          minutes: int = 100) -> Response:
    """
    Adds the HTTP headers to the response for browser to store cache.
    :param data: JSON data to return, any type.
    :param minutes: the time to cache the data, in minutes.
    :return: a flask.Response instance.
    """
    response: Response = app.response_class(
        response=json.dumps(data), mimetype="application/json")
    exp_time: datetime = datetime.now() + timedelta(minutes=minutes)
    response.headers.add("Expires",
                         exp_time.strftime("%a, %d %b %Y %H:%M:%S GMT"))
    response.headers.add("Cache-Control",
                         "public,max-age=%d" % int(60 * minutes))
    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)

