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

from flask import Flask, send_from_directory, make_response, jsonify
import os
from flask_caching import Cache
from flask_cors import CORS
from Covid19 import Covid19

config = dict(DEBUG=True, CACHE_TYPE="filesystem", CACHE_DIR='/tmp', CACHE_DEFAULT_TIMEOUT=5000)

app = Flask(__name__, static_folder='./dc-covid19/build')
CORS(app)

app.config.from_mapping(config)

# Load the configuration file from the instance folder
app.config.from_pyfile('config.py')
cache = Cache(app)

# Retrieve the API KEY from the configuration file
API_KEY = app.config['API_KEY']
COVID19 = Covid19(api_key=API_KEY)


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path != "" and os.path.exists(app.static_folder + '/' + path):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')


@cache.cached(timeout=50000)
@app.route("/get-all-region-names")
def get_all_region_names():
    # Re-load all the data when the cache expires.
    COVID19.load()
    # Don't combine the data, we want to know whether it's a county or a state.
    return {**COVID19.dcid_to_county_name(), **COVID19.dcid_to_state_name()}


@cache.cached(timeout=50000)
@app.route("/get-county-data")
def get_county_data():
    # Re-load all the data when the cache expires.
    COVID19.load()
    return {
        "cases": COVID19.county_cases,
        "deaths": COVID19.county_deaths
    }


@cache.cached(timeout=50000)
@app.route("/get-state-data")
def get_state_data():
    # Re-load all the data when the cache expires.
    COVID19.load()
    return {
        "cases": COVID19.state_cases,
        "deaths": COVID19.state_deaths
    }


@cache.cached(timeout=50000)
@app.route("/get-all-population")
def get_all_population():
    # Re-load all the data when the cache expires.
    COVID19.load()
    # Combine the county and state population
    return {**COVID19.get_county_population(), **COVID19.get_state_population()}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
