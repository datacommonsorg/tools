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

from flask import Flask, send_from_directory
from flask_caching import Cache
from flask_cors import CORS
from flask_compress import Compress

from send_request import send_request
from calculate_data import calculate_data

config = dict(DEBUG=True,
              CACHE_TYPE="filesystem",
              CACHE_DIR='/tmp')

app = Flask(__name__, static_folder='./build')
Compress(app)

CORS(app)
app.config.from_mapping(config)

# Load the configuration file from the instance folder
app.config.from_pyfile('config.py')
cache = Cache(app)

# Retrieve the API KEY from the configuration file
API_KEY = app.config['API_KEY']

# Retrives DataCommons Server from configuration file
DC_SERVER = app.config["DC_SERVER"]

# Retrieves the DataCommons Statvars to be used.
INCREMENTAL_CASES_STATVAR = 'IncrementalCount_MedicalCondition' \
                            'Incident_COVID_19_PatientDeceased'
INCREMENTAL_DEATHS_STATVAR = 'IncrementalCount_MedicalConditionIncident' \
                             '_COVID_19_ConfirmedOrProbableCase'

# The type of sub-regions. Used to remove trailing from name.
# For example, "Miami-Dade County" becomes "Miami-Date".
REGION_TYPES = ["County", "Parish", "Borough"]


@app.route('/<path:path>', methods=['GET'])
def static_proxy(path):
    """
    Return the /path file in the directory from the static_folder directory.
    For example, /index.css would return the index.css file.
    :param path: the file name to return.
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
    Returns the site's HTML file. No caching is turned.
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


@app.route("/api/all-data")
@cache.cached(timeout=3600)
def all_data():
    """
    Returns both US state and US county data. Slower than /state-data api.
    :return: a JSON geoId-> cases/deaths.
    """
    # Request data for only counties.
    data = get_data(counties=True)
    # Adds HTTP headers for browser to store cache.
    response = local_cache(data)
    return response


@app.route("/api/state-data")
@cache.cached(timeout=3600)
def states_data():
    """
    Only returns US state data. Faster then /all-data api.
    :return: a JSON geoId -> cases/deaths.
    """
    # Request data for only states.
    data = get_data(counties=False)
    # Adds HTTP headers for browser to store cache.
    response = local_cache(data)
    return response


def get_data(counties=False):
    """
    Requests cases and deaths from the DC, and performs calculations.
    :param counties: Whether we want both counties and states or just states.
    :return: geoId->calculated data for both cases and deaths.
    """
    # Get all the places in the US.
    # States and Counties.
    places: dict = get_places(counties)
    # Get the total population of all geoIds.
    population: dict = get_population()

    # Convert the places to a list of geoIds.
    # The dictionary is keyed by geoId, so we can just use that.
    dcids: list = list(places.keys())

    # Request all cases and deaths.
    all_cases: dict = get_stats_by_date(dcids,
                                        INCREMENTAL_CASES_STATVAR)
    all_deaths: dict = get_stats_by_date(dcids,
                                         INCREMENTAL_DEATHS_STATVAR)

    output: dict = {}

    for geo_id in dcids:
        calculated_cases = {}
        calculated_deaths = {}
        # Make sure we have the population for this geoId.
        if geo_id not in population:
            continue
        # Otherwise, get the population for this geoId.
        region_pop = population[geo_id]
        # Get the data for this geoId.
        if geo_id in all_cases:
            cases: dict = all_cases[geo_id]
            # Perform XYZ calculations.
            calculated_cases: dict = calculate_data('Cases',
                                                    cases,
                                                    region_pop)
        if geo_id in all_deaths:
            deaths: dict = all_deaths[geo_id]
            # Perform XYZ calculations.
            calculated_deaths: dict = calculate_data('Deaths',
                                                     deaths,
                                                     region_pop)

        # Combine both calculated cases and deaths under output[geoId].
        output[geo_id] = {
            **calculated_cases,
            **calculated_deaths,
            **{"geoId": geo_id,
               "name": places[geo_id][0],
               "containedIn": places[geo_id][1],
               "type": places[geo_id][2]}
        }

    # Return a combination of cases + deaths + metadata.
    return output


def get_population():
    """
    Returns the total population of each region. geoId->population"
    :return: geoId->population
    """

    # Request US State population from DataCommons KG.
    state_response: dict = send_request(DC_SERVER + "bulk/place-obs",
                                        dict(placeType='State',
                                             populationType="Person",
                                             observationDate="2018"),
                                        api_key=API_KEY,
                                        compress=True)

    # Request US County population from DataCommons KG.
    county_response: dict = send_request(DC_SERVER + "bulk/place-obs",
                                         dict(placeType='County',
                                              populationType="Person",
                                              observationDate="2018"),
                                         api_key=API_KEY,
                                         compress=True)

    # Merge US State and US County into one response.
    response: list = state_response['places'] + county_response['places']

    output: dict = {}

    for place in response:
        # Some geoIds return None if there is no data.
        # Make sure there is data first.
        if 'place' not in place and not place['place']:
            continue
        geo_id: str = place['place']

        # The census data can be found in place["observations"].
        if "observations" not in place and not place["observations"]:
            continue

        # Search for CensusACS5yrSurvey in observations.
        for observation in place["observations"]:
            # If you find the census data
            if observation["measurementMethod"] == "CensusACS5yrSurvey":
                # Make sure measuredValue has a real value.
                # It is the population.
                if 'measuredValue' not in observation:
                    continue
                # Store the population.
                output[geo_id] = observation['measuredValue']

    # NYT exceptions.
    # New York City.
    output['geoId/3651000'] = 8_399_000
    # Kansas City.
    output['geoId/2938000'] = 491_918

    return output


def get_places(return_counties=False):
    """
    Returns a list of places in the United States.
    :param return_counties: whether to return information
    for counties+states or just states.
    :return: geoId -> (name, containedIn, typeOfRegion)
    """

    # Get US State data.
    response: dict = send_request(DC_SERVER + "node/places-in", {
        "dcids": ["country/USA"],
        "placeType": "State"
    },
                                  api_key=API_KEY)

    # Get the names for the US State data.
    state_dcids: list = [x['place'] for x in response]
    response: dict = send_request(DC_SERVER + "node/property-values", {
        "dcids": state_dcids,
        "property": "name"
    },
                                  api_key=API_KEY)
    states: dict = {}

    # For every geoId, store (name, containedIn, typeOfRegion).
    for geo_id in response:
        if 'out' in response[geo_id] and response[geo_id]['out']:
            if 'value' in response[geo_id]['out'][0]:
                # Store the data for the geoId.
                name = response[geo_id]['out'][0]['value']
                states[geo_id] = (name, 'country/USA', "State")

    # Get US County data.
    response: dict = send_request(DC_SERVER + "node/places-in", {
        "dcids": state_dcids,
        "placeType": "County"
    },
                                  api_key=API_KEY)

    # Keep track of what county each state belongs to.
    county_to_state: dict = {}
    for value in response:
        if 'place' in value and 'dcid' in value:
            county_geo_id: str = value['place']
            belongs_to_geo_id: str = value['dcid']
            county_to_state[county_geo_id]: str = belongs_to_geo_id

    # Get the name of all counties
    response: dict = send_request(DC_SERVER + "node/property-values", {
        "dcids": list(county_to_state.keys()),
        "property": "name"
    },
                                  api_key=API_KEY)

    # Store all the counties.
    counties: dict = {}

    # If param return_counties == True, get county data.
    if return_counties:
        for geo_id in response:
            if 'out' in response[geo_id] and response[geo_id]['out']:
                if 'value' in response[geo_id]['out'][0]:
                    name: str = response[geo_id]['out'][0]['value']
                    # Get rid of trailing strings in names such as County.
                    for region_type in REGION_TYPES:
                        name: str = name.replace(" " + region_type, "")
                    # The geoId where this region belongs to.
                    belongs_to: str = county_to_state[geo_id]
                    counties[geo_id] = (name, belongs_to, "County")

        # NYT exceptions.
        counties['geoId/3651000'] = ("New York City", "geoId/36", "County")
        counties['geoId/2938000'] = ("Kansas City", "geoId/29", "County")

    return {**states, **counties}


def get_stats_by_date(place: list, stats_var: str) -> dict:
    """
    Queries and returns the data in the appropriate format.
    :param place: list of dcids to get data for
    :param stats_var: the Data Commons stats_var to query data for
    :return: dictionary where every day contains several regions,
    and those regions contain an int of cases/deaths
    """
    response: dict = send_request(DC_SERVER + "bulk/stats", {
        "place": place,
        "stats_var": stats_var
    },
                                  api_key=API_KEY)

    output: defaultdict = defaultdict(dict)

    # Store the data in output as dates->dcid->value
    for dcid in response:
        if not response[dcid]:
            continue
        if "data" not in response[dcid]:
            continue
        data: dict = response[dcid]["data"]
        for date in data:
            output[dcid][date] = data[date]
    return output


def local_cache(data, minutes=100):
    """
    Adds the HTTP headers to the response so that the browser knows to
    cache the data.
    :param data: JSON data to return.
    :param minutes: the time to cache the data for in minutes.
    :return: a flask.response instance.
    """
    response = app.response_class(response=json.dumps(data),
                                  mimetype='application/json')
    exp_time = datetime.now() + timedelta(minutes=minutes)
    response.headers.add('Expires',
                         exp_time.strftime("%a, %d %b %Y %H:%M:%S GMT"))
    response.headers.add('Cache-Control',
                         'public,max-age=%d' % int(60 * minutes))
    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
