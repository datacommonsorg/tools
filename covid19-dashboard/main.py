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

from collections import defaultdict
from flask import Flask, send_from_directory, make_response, jsonify
import os
from flask_caching import Cache
from flask_cors import CORS
from send_request import send_request
import numpy as np

config = dict(DEBUG=True, CACHE_TYPE="filesystem", CACHE_DIR='/tmp', CACHE_DEFAULT_TIMEOUT=5000)

app = Flask(__name__, static_folder='./dc-covid19/build')
CORS(app)

app.config.from_mapping(config)

# Load the configuration file from the instance folder
app.config.from_pyfile('config.py')
cache = Cache(app)

# Retrieve the API KEY from the configuration file
API_KEY = app.config['API_KEY']


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    """Returns front-end static files."""
    if path != "" and os.path.exists(app.static_folder + '/' + path):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')


# @app.route("/api/places")
# @cache.cached(timeout=864000)
# def get_places():
#     """Returns a dictionary of dcid->(name, type)
#     where name is the name of the region and type is the type of region."""
#     response: dict = send_request(req_url='https://api.datacommons.org/node/property-values',
#                                   req_json={"dcids": ['NYT_COVID19_County', 'NYT_COVID19_State'],
#                                             "property": "member"},
#                                   post=True,
#                                   compress=False,
#                                   api_key=API_KEY)
#
#     counties: dict = {county['dcid']: (county['name'], 'County') for county in response['NYT_COVID19_County']['out']}
#     states: dict = {state['dcid']: (state['name'], 'State') for state in response['NYT_COVID19_State']['out']}
#     return {**counties, **states}


@app.route("/api/total-cases")
@cache.cached(timeout=3600)
def get_total_cases():
    """Returns the total Cumulative Cases of each region per day. day->dcid->cases"""
    dcids: list = list(get_places().keys())
    return get_stats_by_date(dcids, 'NYTCovid19CumulativeCases')


@app.route("/api/total-deaths")
@cache.cached(timeout=3600)
def get_total_deaths():
    """Returns the total Cumulative Deaths of each region. day->dcid->deaths"""
    dcids: list = list(get_places().keys())
    return get_stats_by_date(dcids, 'NYTCovid19CumulativeDeaths')


@app.route("/api/population")
@cache.cached(timeout=864000)
def get_population():
    """Returns the total population of each region. dcid->population"""
    state_response = send_request("https://api.datacommons.org/bulk/place-obs",
                                  dict(placeType='State', populationType="Person", observationDate="2018"),
                                  api_key=API_KEY, compress=True)
    county_response = send_request("https://api.datacommons.org/bulk/place-obs",
                                   dict(placeType='County', populationType="Person", observationDate="2018"),
                                   api_key=API_KEY, compress=True)
    response = state_response['places'] + county_response['places']

    output: defaultdict = defaultdict(int)

    for place in response:
        # Some dcids return None if there is no data, so we have to make sure there is data first.
        if 'place' not in place and not place['place']:
            continue
        if "observations" not in place and not place["observations"]:
            continue
        dcid = place['place']
        for observation in place["observations"]:
            if observation["measurementMethod"] == "CensusACS5yrSurvey":
                if 'measuredValue' not in observation:
                    print("ERROR", dcid)
                    continue
                population = observation['measuredValue']
                output[dcid] = population

    output['geoId/3651000'] = 8399000
    output['geoId/2938000'] = 491918

    return output


@app.route("/api/places")
@cache.cached(timeout=864000)
def get_places():
    """Returns a dictionary of dcid->(name, type) where name is
    the name of the region and type is the type of region."""

    # Get state data
    response = send_request("https://api.datacommons.org/node/places-in",
                            {"dcids": ["country/USA"], "placeType": "State"}, api_key=API_KEY)

    state_dcids = [x['place'] for x in response]
    response = send_request("https://api.datacommons.org/node/property-values",
                            {"dcids": state_dcids, "property": "name"}, api_key=API_KEY)
    states: dict = {}
    for geoId in response:
        if 'out' in response[geoId] and response[geoId]['out'] and 'value' in response[geoId]['out'][0]:
            states[geoId] = (response[geoId]['out'][0]['value'], 'country/USA')

    # Get county data
    response = send_request("https://api.datacommons.org/node/places-in",
                            {"dcids": state_dcids, "placeType": "County"}, api_key=API_KEY)

    county_to_state = {}
    for value in response:
        if 'place' in value and 'dcid' in value:
            county_geoId = value['place']
            belongs_to_state_geoId = value['dcid']
            county_to_state[county_geoId] = belongs_to_state_geoId

    response = send_request("https://api.datacommons.org/node/property-values",
                            {"dcids": list(county_to_state.keys()), "property": "name"}, api_key=API_KEY)

    counties: dict = {}
    for geoId in response:
        if 'out' in response[geoId] and response[geoId]['out'] and 'value' in response[geoId]['out'][0]:
            counties[geoId] = (response[geoId]['out'][0]['value'], county_to_state[geoId])

    counties['geoId/3651000'] = ("New York City", "geoId/36")
    counties['geoId/2938000'] = ("Kansas City", "geoId/29")
    return {**states, **counties}


def get_stats_by_date(place: list, stats_var: str) -> dict:
    """
    In charge of querying and returning the covid data in the appropriate format.
    :param place: list of dcids to get data for
    :param stats_var: the Data Commons stats_var to query data for
    :return: dictionary where every day contains several regions, and those regions contain an int of cases/deaths
    """
    response: dict = send_request("https://api.datacommons.org/bulk/stats",
                                  {"place": place,
                                   "stats_var": stats_var},
                                  api_key=API_KEY)
    output: defaultdict = defaultdict(dict)

    # Store the data in output as dates->dcid->value
    for dcid in response:
        if not response[dcid]:
            continue
        if "data" not in response[dcid]:
            continue
        data = response[dcid]["data"]
        for date in data:
            output[date][dcid] = data[date]
    return output


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
