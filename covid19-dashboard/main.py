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
from typing import List, Dict, Tuple, Union

from flask import Flask, send_from_directory, Response
from flask_caching import Cache
from flask_compress import Compress

from send_request import send_request
from calculate_data import calculate_data

config = dict(DEBUG=True, CACHE_TYPE="filesystem", CACHE_DIR="/tmp")

app = Flask(__name__, static_folder="./build")

# All API responses are g-zipped/compressed.
Compress(app)

app.config.from_mapping(config)

# Load the configuration file from the instance folder.
app.config.from_pyfile("config.py")
cache = Cache(app)

# Retrieve the API KEY from the configuration file.
API_KEY = app.config["API_KEY"]

# Retrieves DataCommons Server from configuration file.
DC_SERVER = app.config["DC_SERVER"]

# Each place_type has its own stat_var.
# Get the dictionary from the configuration file.
STAT_VARS = app.config["STAT_VARS"]


# COMMONLY-USED TYPES.
DataType = Union[Dict[str, int], int, str]
GeoIdToDataType = Dict[str, DataType]
GeoIdToStatsType = Dict[str, Dict[str, int]]
PlaceToInfoType = Dict[str, Tuple[str, str]]


@app.route("/<path:path>", methods=["GET"])
def static_proxy(path):
    """
    Return the /path file in the directory from the ./build directory.
    For example, /index.css would return the index.css file.
    No-caching HTTP headers are sent.
    :param path: the file path to return.
    :return: the file if it exists.
    """
    response = send_from_directory(app.static_folder, path)
    response.cache_control.max_age = 0
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/", methods=["GET"])
def index():
    """
    Returns the site's HTML file. No-caching HTTP headers are sent.
    NOTE: Caching may be turned on once the frequency of updates is reduced.
    Otherwise, users my experience a white page due to old files.
    :return: returns the index file for the site.
    """
    response = send_from_directory(app.static_folder, "index.html")
    response.cache_control.max_age = 0
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/api/county-data")
@cache.cached(timeout=3600)
def county_data():
    """
    Returns US County data. Slower than /state-data api.
    NOTE: for return type documentation, please see README.md's APIs section.
    :return: geo_id->{**data, name, geo_id, placeType, containedIn}.
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
    :return: geo_id->{**data, name, geo_id, placeType, containedIn}.
    """
    # Request data for only US States.
    data = get_data("State")
    # Adds HTTP headers for browser to store cache.
    response = add_browser_cache_headers_to_response(data)
    return response


@app.route("/api/country-data")
@cache.cached(timeout=3600)
def country_data():
    """
    Returns World Country data.
    NOTE: for return type documentation, please see README.md's APIs section.
    :return: geo_id->{**data, name, geo_id, placeType, containedIn}.
    """
    # Request data for only US States.
    data = get_data("Country")
    # Adds HTTP headers for browser to store cache.
    response = add_browser_cache_headers_to_response(data)
    return response


def get_data(place_type: str = "State") -> GeoIdToDataType:
    """
    Requests cases and deaths from the DC, and performs calculations.
    NOTE: for return type documentation, please see README.md's APIs section.
    :param place_type: return states OR counties.
    :return: geo_id->{**calculated_data, name, geo_id, placeType, containedIn}.
    """
    all_stats: Dict[str, GeoIdToStatsType] = {}
    output: GeoIdToDataType = {}

    # Request the geo_ids for the place_type.
    if place_type == "Country":
        places: PlaceToInfoType = get_countries()
    else:
        places: PlaceToInfoType = get_us_places(place_type)

    # Get the total population of all geo_id.
    geo_id_to_population: Dict[str, int] = get_population(place_type)

    # Convert the places to a list of geo_id.
    # The dictionary is keyed by geo_id.
    # We can just convert the keys to a list.
    geo_ids: List[str] = list(places.keys())

    # place_type must be a key in STAT_VARS.
    # Otherwise, the request is invalid.
    if place_type not in STAT_VARS:
        return {}

    # 'Cases' and 'Deaths' are example of keys.
    # Get all the data for the requested place_type.
    # Example: All 'Cases' and 'Deaths' for 'Country'
    for key in STAT_VARS[place_type]:
        # Get the real DC stat_var for this place_type and key.
        stat_var = STAT_VARS[place_type][key]
        # Request the real stats from the DC KG.
        # Store the stats for this stat_var in the map of all_stats.
        # The key might be 'Deaths', but the stat_var might be
        # IncrementalCount_MedicalConditionIncident_COVID_19_PatientDeceased
        all_stats[key] = get_stats_by_date(geo_ids, stat_var)

    # Iterate through all geo_ids.
    # Calculate the data for all_stats.
    for geo_id in geo_ids:
        all_calculated_data = {}
        # Make sure we have the population for this geo_id.
        if geo_id not in geo_id_to_population:
            continue

        # Get the places's population.
        place_population = geo_id_to_population[geo_id]

        for stat_var in all_stats:
            # If the geo_id isn't there, it means there is no data.
            if geo_id not in all_stats[stat_var]:
                continue
            place_stats = all_stats[stat_var][geo_id]
            calculated_data = calculate_data(stat_var, place_stats,
                                             place_population)
            # Combine and store all the calculated_data for this geo_id.
            all_calculated_data = {**all_calculated_data, **calculated_data}

        # Make sure we have metadata for this geo_id.
        if geo_id not in places:
            continue

        # Retrieve metadata from places for this geo_id.
        name: str = places[geo_id][0]
        contained_in_geo_id: str = places[geo_id][1]

        # Combine both calculated cases and deaths under output[geo_id].
        output[geo_id] = {
            **all_calculated_data,
            **{
                "geoId": geo_id,
                "containedIn": contained_in_geo_id,
                "name": name,
                "placeType": place_type,
            },
        }
    # Return a combination of stats + metadata for all geo_ids.
    # The output is keyed by geo_id.
    # geo_id->{**calculated_data, name, geo_id, placeType, containedIn}
    return output


def get_population(place_type: str = "Country") -> Dict[str, int]:
    """
    Returns the total population of each place as a dictionary.
    The key is the geo_id and the value is the population number.
    :return: dict of geo_id->population.
    """
    # Depending on the place_type, the population is stored differently.

    # US States and US Counties use the census.
    measurement_key = "measurementMethod"
    measurement = "CensusACS5yrSurvey"
    # Counties use a generic count variable.
    if place_type == "Country":
        measurement_key = "measuredProp"
        measurement = "count"

    response: Dict[str, List[Dict]] = send_request(
        DC_SERVER + "bulk/place-obs",
        {
            "placeType": place_type,
            "populationType": "Person",
            "observationDate": "2018",
        },
        api_key=API_KEY,
        compress=True,
        )

    # If 'places' isn't a key in the response.
    # The response isn't valid, so return empty data.
    if "places" not in response:
        return {}

    places = response["places"]

    output: Dict[str, int] = {}

    for place in places:
        # Some geo_ids return None if there is no data.
        # Make sure there is data first.
        if "place" not in place and not place["place"]:
            continue
        geo_id: str = place["place"]

        # The population data can be found in place["observations"].
        if "observations" not in place:
            continue
        if not place["observations"]:
            continue

        for observation in place["observations"]:
            # If you find the population data.
            # Different place_types use different measurement methods.
            if observation[measurement_key] == measurement:
                # Make sure measuredValue exists.
                # measuredValue IS the population.
                if "measuredValue" not in observation:
                    continue
                # Store the population.
                output[geo_id] = observation["measuredValue"]

    # NYT combines several counties into one larger county.
    # Only for the following two exceptions.
    # https://github.com/nytimes/covid-19-data
    if place_type == "County":
        # New York City.
        output["geoId/3651000"] = 8_399_000
        # Kansas City.
        output["geoId/2938000"] = 491_918

    return output


def get_countries() -> PlaceToInfoType:
    """
    Returns a dictionary of all Countries in the world.
    The return type is a dict where the key is the geo_id being observed
    and the value is a tuple of metadata about that place.
    :return: a dictionary of geo_id->(name: str, containedIn: str).
    """
    # Get the name and geo_ids of all Counties.
    # When requesting the population of Countries.
    # Both geo_id and name are returned. Population is discarded for now.
    response: Dict[str, List[Dict]] = send_request(
        DC_SERVER + "bulk/place-obs",
        {
            "placeType": "Country",
            "populationType": "Person",
            "observationDate": "2018",
        },
        api_key=API_KEY,
        compress=True,
        )

    output: PlaceToInfoType = {}

    # If 'places' isn't a key in the response.
    # The response isn't valid, so return empty data.
    if "places" not in response:
        return {}

    places = response["places"]

    for place in places:
        if "name" not in place:
            continue
        if "place" not in place:
            continue
        name: str = place["name"]
        geo_id: str = place["place"]
        # All countries belong to the world.
        output[geo_id] = (name, "World")

    return output


def _get_place_names(geo_ids: List[str]) -> Dict[str, str]:
    """
    Returns the names of the places given a list of geo_ids.
    :param geo_ids: the list of geo_ids you want the names returned for.
    :return: geo_id->name. A dictionary where the geo_id maps to the name.
    """
    output: Dict[str, str] = {}

    # Request the names from the DC KG.
    response = send_request(
        DC_SERVER + "node/property-values",
        {"dcids": geo_ids,
         "property": "name"},
        api_key=API_KEY,
        )

    # For every geo_id in the response, store the name.
    for geo_id in response:
        if "out" not in response[geo_id]:
            continue
        if not response[geo_id]["out"]:
            continue
        if "value" not in response[geo_id]["out"][0]:
            continue
        name: str = response[geo_id]["out"][0]["value"]
        output[geo_id] = name

    return output


def get_us_places(place_type: str = "State") -> PlaceToInfoType:
    """
    Returns a dictionary of either US States or US Counties.
    The return is a dict where the key is the geo_id being observed
    and the value is a tuple of metadata about that place.
    :param place_type: return states OR counties.
    :return: a dictionary of geo_id->(name: str, containedIn: str).
    """

    # Get US State data.
    response = send_request(
        DC_SERVER + "node/places-in",
        {"dcids": ["country/USA"],
         "placeType": "State"},
        api_key=API_KEY,
        )

    # Get the geo_id for all the States.
    # The geo_id is stored under 'place'.
    state_geo_ids: List[str] = [state["place"] for state in response]

    state_names = _get_place_names(state_geo_ids)

    # Store all the US State metadata as a dict of tuples.
    # geo_id -> (name, containedIn).
    states: PlaceToInfoType = {
        geo_id: (name, "country/USA")
        for geo_id, name in state_names.items()
    }

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
        if "place" not in value:
            continue
        if "dcid" not in value:
            continue

        county_geo_id: str = value["place"]
        belongs_to_geo_id: str = value["dcid"]
        county_to_state[county_geo_id]: str = belongs_to_geo_id

    # If the user didn't request County data, they requested State data.
    # Return state data.
    if place_type != "County":
        return states

    county_geo_ids = list(county_to_state.keys())

    county_names = _get_place_names(county_geo_ids)

    # Store all the US County metadata as a dict of tuples.
    # geo_id -> (name: str, containedIn: str).
    counties: PlaceToInfoType = {
        geo_id: (name, county_to_state[geo_id])
        for geo_id, name in county_names.items()
    }

    # NYT combines several counties into one larger county.
    # Only for the following two exceptions.
    # https://github.com/nytimes/covid-19-data#geographic-exceptions
    counties["geoId/3651000"] = ("New York City", "geoId/36")
    counties["geoId/2938000"] = ("Kansas City", "geoId/29")

    return counties


def get_stats_by_date(geo_ids: List[str], stats_var: str) -> GeoIdToStatsType:
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
    output: GeoIdToStatsType = defaultdict(dict)

    for geo_id in response:
        if not response[geo_id]:
            continue
        if "data" not in response[geo_id]:
            continue
        # Get the data.
        data: Dict[str, int] = response[geo_id]["data"]
        # Store the data by geo_id->date.
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
