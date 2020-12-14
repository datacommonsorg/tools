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
from typing import List, Dict, Union

from flask import Flask, Response
from flask_caching import Cache
from flask_compress import Compress
from flask import request

from send_request import send_request
from calculate_data import calculate_data
from Configuration import covid19, socialWellness

config = dict(DEBUG=True, CACHE_TYPE="filesystem", CACHE_DIR="/tmp")

app = Flask(__name__)

# All API responses are g-zipped/compressed.
Compress(app)

app.config.from_mapping(config)

cache = Cache(app)

# DataCommons Host Server.
DC_SERVER = "https://api.datacommons.org/"

# COMMONLY-USED TYPES.
KeyToTimeSeries = Union[Dict[str, int], int, str]
GeoIdToDataType = Dict[str, KeyToTimeSeries]
GeoIdToStatsType = Dict[str, Dict[str, int]]
PlaceToInfoType = Dict[str, Dict[str, str]]



@app.route("/api/data/<string:geo_id>/<string:dashboard_id>")
@cache.cached(timeout=3600)
def data(geo_id: str, dashboard_id: str):
    """
    Returns any placeType's data.
    NOTE: for return type documentation, please see README.md's APIs section.
    :return: geo_id->{**key_to_timeseries}.
    """
    dashboard_id = dashboard_id or "covid19"

    # TODO(edumorales): make these options config-driven.
    # How many dates should we perform the moving average for?
    # 0 == None
    moving_averages_chunks = {"covid19": 7, "socialWellness": 0}
    moving_average_chunk = moving_averages_chunks[dashboard_id]

    # How many dates should we skip to reduce response size?
    # In days, 1 == None.
    clean_step_sizes = {"covid19": 6, "socialWellness": 1}
    clean_step_size = clean_step_sizes[dashboard_id]

    # Get the stat vars for the given dashboardId.
    stat_vars = _get_stat_vars(dashboard_id)

    # Request data for only US Counties.
    data = _get_data(geo_id, stat_vars, moving_average_chunk, clean_step_size)
    # Adds HTTP headers for browser to store cache.
    response = _add_browser_cache_headers_to_response(data)
    return response


@app.route("/api/places")
@cache.cached(timeout=3600)
def places():
    """
    Returns World Country data.
    NOTE: for return type documentation, please see README.md's APIs section.
    :return: geo_id->{name, placeType, containedIn}.
    """
    countries = _get_countries()
    states = _get_us_places('State')
    counties = _get_us_places('County')
    world = {'World': Place("World", "", "").to_json()}

    # Include the World as a geoId.
    data = {**countries, **states, **counties, **world}

    response = _add_browser_cache_headers_to_response(data)
    return response


def _get_data(place_type: str = "State", STAT_VARS={},
              moving_average_chunk=7, clean_step_size=2) -> GeoIdToDataType:
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
        places: PlaceToInfoType = _get_countries()
    else:
        places: PlaceToInfoType = _get_us_places(place_type)

    # Get the total population of all geo_id.
    geo_id_to_population: Dict[str, int] = _get_population(place_type)

    # Convert the places to a list of geo_id.
    # The dictionary is keyed by geo_id.
    # We can just convert the keys to a list.
    geo_ids: List[str] = list(places.keys())

    # place_type must be a key in STAT_VARS.
    # Otherwise, the request is invalid.
    if place_type not in STAT_VARS:
        return {}

    # 'Cases' and 'Deaths' are examples of keys.
    # Get all the data for the requested place_type.
    # Example: All 'Cases' and 'Deaths' for 'Country'
    for key in STAT_VARS[place_type]:
        # Get the real DC stat_var for this place_type and key.
        stat_var = STAT_VARS[place_type][key]
        # Request the real stats from the DC KG.
        # Store the stats for this stat_var in the map of all_stats.
        # The key might be 'Deaths', but the stat_var might be
        # IncrementalCount_MedicalConditionIncident_COVID_19_PatientDeceased
        all_stats[key] = _get_stats_by_date(geo_ids, stat_var)

    # Iterate through all geo_ids.
    # Calculate the data for all_stats.
    for geo_id in geo_ids:
        all_calculated_data = {}
        # Make sure we have the population for this geo_id.
        if geo_id not in geo_id_to_population:
            continue

        # Get the places' population.
        place_population = geo_id_to_population[geo_id]

        # Make sure the population is >= 0
        if place_population <= 0:
            continue

        for stat_var in all_stats:
            # If the geo_id isn't there, it means there is no data.
            if geo_id not in all_stats[stat_var]:
                continue
            # Make sure we have metadata for this geo_id.
            if geo_id not in places:
                continue
            # Get the stats for this stat_var and geo_id.
            place_stats = all_stats[stat_var][geo_id]

            # Do calculations with the data.
            # See README.md for more information about the return types.
            calculated_data = calculate_data(place_stats,
                                             place_population, moving_average_chunk,
                                             clean_step_size)

            # Rename keys to include stat_var.
            # Example: 'movingAverage' becomes 'movingAverageCases'.
            calculated_data = {f"{key}{stat_var}": value
                               for key, value in calculated_data.items()}

            # Combine calculated_data with its other stat_vars.
            all_calculated_data = {**all_calculated_data,
                                   **calculated_data}

        # Combine both calculated cases and deaths under output[geo_id].
        output[geo_id] = all_calculated_data
    # Return a combination of stats + metadata for all geo_ids.
    # The output is keyed by geo_id.
    # geo_id->{**calculated_data, name, geo_id}
    return output


def _get_population(place_type: str = "Country") -> Dict[str, int]:
    """
    Returns the total population of each place as a dictionary.
    The key is the geo_id and the value is the population number.
    :return: dict of geo_id->population.
    """
    # Depending on the place_type, the population is stored differently
    # In the Data Commons KG.
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
        if "place" not in place:
            continue
        if not place["place"]:
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


def _get_countries() -> PlaceToInfoType:
    """
    Returns a dictionary of all Countries in the world.
    The return type is a dict where the key is the geo_id being observed
    and the value is an object of information about that place.
    :return: a dictionary of geo_id->{name, containedIn, placeType}.
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
        output[geo_id] = Place(name, "World", "Country").to_json()

    return output


def _get_us_places(place_type: str = "State") -> PlaceToInfoType:
    """
    Returns a dictionary of either US States or US Counties.
    The return is a dict where the key is the geo_id being observed
    and the value is an object of information about that place.
    :param place_type: return states OR counties.
    :return: a dictionary of geo_id->{name: str, containedIn: str}.
    """
    # Get US State data.
    response = send_request(
        DC_SERVER + "node/places-in",
        {"dcids": ["country/USA"],
         "placeType": "State"},
    )

    # Get the geo_id for all the States.
    # The geo_id is stored under 'place'.
    state_geo_ids: List[str] = [state["place"] for state in response]

    state_names = _get_place_names(state_geo_ids)

    # Store all the US State metadata as an object of geoId->info.
    # Where the object is of type geo_id -> {name, containedIn, placeType}
    states: PlaceToInfoType = {
        geo_id: Place(name, "country/USA", "State").to_json()
        for geo_id, name in state_names.items()
    }

    # If the user didn't request County data, they requested State data.
    # Return state data.
    if place_type != "County":
        return states

    # Get US County data belonging to the US States.
    response = send_request(
        DC_SERVER + "node/places-in",
        {"dcids": state_geo_ids,
         "placeType": "County"},
    )

    # Keep track of what State each County belongs to.
    # geo_id -> belongs_to_geo_id.
    # Example: {"geoId/12000": "geoId/12"}
    county_to_state: Dict[str, str] = {}
    for value in response:
        if "place" not in value:
            continue
        if "dcid" not in value:
            continue

        county_geo_id: str = value["place"]
        belongs_to_geo_id: str = value["dcid"]
        county_to_state[county_geo_id]: str = belongs_to_geo_id

    county_geo_ids = list(county_to_state.keys())

    county_names = _get_place_names(county_geo_ids)

    # Store all the US County metadata as a dict of tuples.
    # geo_id -> (name: str, containedIn: str, placeType: str).
    counties: PlaceToInfoType = {
        geo_id: Place(name, county_to_state[geo_id], "County").to_json()
        for geo_id, name in county_names.items()
    }

    # NYT combines several counties into one larger county.
    # Only for the following two exceptions.
    # https://github.com/nytimes/covid-19-data#geographic-exceptions
    counties["geoId/3651000"] = Place("New York City",
                                      "geoId/36", "County").to_json()
    counties["geoId/2938000"] = Place("Kansas City",
                                      "geoId/29", "County").to_json()

    return counties


def _get_stats_by_date(geo_ids: List[str],
                       stats_var: str) -> GeoIdToStatsType:
    """
    Queries and returns the data in the as a dict of type geo_id->date->value.
    :param geo_ids: list of geo_ids to query data for.
    :param stats_var: the DC stats_var to query data for.
    :return: a dict of type geo_id->date->value.
    Example: {geoId/12: {'2020-01-01': 10, '2020-01-02: 20'},
              geoId/13: {'2020-01-01': 6, '2020-01-02: 15'}}
    """
    response = send_request(
        DC_SERVER + "bulk/stats",
        {"place": geo_ids,
         "stats_var": stats_var},
    )

    # geo_id->date->value
    # Example: {geoId/12: {'2020-01-01': 10, '2020-01-02: 20'},
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


def _add_browser_cache_headers_to_response(data: Dict,
                                           minutes: int = 100) -> Response:
    """
    Adds the HTTP headers to the response for browser to store cache.
    :param data: JSON data to return, any type.
    :param minutes: the time to cache the data, in minutes.
    :return: a flask.Response instance.
    """
    response: Response = app.response_class(
        response=json.dumps(data),
        mimetype="application/json")
    exp_time: datetime = datetime.now() + timedelta(minutes=minutes)
    response.headers.add("Expires",
                         exp_time.strftime("%a, %d %b %Y %H:%M:%S GMT"))
    response.headers.add("Cache-Control",
                         "public,max-age=%d" % int(60 * minutes))

    return response


def _get_stat_vars(dashboard_id: str):
    if dashboard_id == 'socialWellness':
        return socialWellness
    else:
        return covid19


class Place:
    def __init__(self, name, contained_in, place_type):
        self.name = name
        self.containedIn = contained_in
        self.placeType = place_type

    def to_json(self):
        return self.__dict__


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
