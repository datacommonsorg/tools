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

from flask import Flask, send_from_directory, make_response
import os
from flask_caching import Cache
from flask_cors import CORS
from COVID19 import COVID19

config = dict(DEBUG=True, CACHE_TYPE="filesystem", CACHE_DIR='/tmp', CACHE_DEFAULT_TIMEOUT=5000)

app = Flask(__name__, static_folder='./dc-covid19/build')
CORS(app)

app.config.from_mapping(config)
cache = Cache(app)


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path != "" and os.path.exists(app.static_folder + '/' + path):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')


@app.route("/get-all-data")
@cache.cached(timeout=5000)
def get_all_data():
    covid = COVID19()
    dcidMap = covid.generate_map_of_dcid_to_name()

    latest = {
        "date": covid.get_latest_date_in_dataset(days_ago=0),
        "county": get_data_for(covid, "county", "latest"),
        "state": get_data_for(covid, "state", "latest")
    }

    seven_days = {
        "date": covid.ISO_date(covid.get_latest_date_in_dataset(days_ago=7)),
        "county": get_data_for(covid, "county", "7days"),
        "state": get_data_for(covid, "state", "7days")
    }

    fourteen_days = {
        "date": covid.ISO_date(covid.get_latest_date_in_dataset(days_ago=14)),
        "county": get_data_for(covid, "county", "14days"),
        "state": get_data_for(covid, "state", "14days")
    }

    thirty_days = {
        "date": covid.ISO_date(covid.get_latest_date_in_dataset(days_ago=30)),
        "county": get_data_for(covid, "county", "30days"),
        "state": get_data_for(covid, "state", "30days")
    }

    for dcid in covid.get_all_state_dcids():
        latest[dcid] = get_data_for(covid, dcid, "latest")
        seven_days[dcid] = get_data_for(covid, dcid, "7days")
        fourteen_days[dcid] = get_data_for(covid, dcid, "14days")
        thirty_days[dcid] = get_data_for(covid, dcid, "30days")

    # Get all states and their dcids
    availableRegions = {dcid: dcidMap[dcid] for dcid in covid.get_all_state_dcids()}

    return make_response({"latest": latest,
                          "sevenDays": seven_days,
                          "fourteenDays": fourteen_days,
                          "thirtyDays": thirty_days,
                          "dcidMap": dcidMap,
                          "availableRegions": availableRegions,
                          "availableDates": {
                              "latest": covid.get_latest_date_in_dataset(days_ago=0),
                              "sevenDays": covid.get_latest_date_in_dataset(days_ago=7),
                              "fourteenDays": covid.get_latest_date_in_dataset(days_ago=14),
                              "thirtyDays": covid.get_latest_date_in_dataset(days_ago=30),
                          }}, 200)


def get_data_for(covid, region, date):
    print("Getting perDay Data")
    daily = {
        'cases': covid.get_cases_for_given_range_alone(region=region, most_recent_date=date, time_delta=1).to_dict(),
        'deaths': covid.get_deaths_for_given_range_alone(region=region, most_recent_date=date, time_delta=1).to_dict()
    }

    print("Getting dailyPerCapita Data")
    dailyPerCapita = {
        'cases': (covid.get_cases_difference_per_capita(region=region, most_recent_date=date, time_delta=1)).to_dict(),
        'deaths': (covid.get_deaths_difference_per_capita(region=region, most_recent_date=date, time_delta=1)).to_dict()
    }

    print("Getting dailyIncrease Data")
    dailyIncrease = {
        'cases': (
            covid.get_cases_increase_pct_for_given_dates(region=region, most_recent_date=date, time_delta=1)).to_dict(),
        'deaths': (
            covid.get_deaths_increase_pct_for_given_dates(region=region, most_recent_date=date, time_delta=1)).to_dict()
    }

    print("Getting perWeek Data")
    weekly = {
        'cases': covid.get_cases_for_given_range_alone(region=region, most_recent_date=date, time_delta=7).to_dict(),
        'deaths': covid.get_deaths_for_given_range_alone(region=region, most_recent_date=date, time_delta=7).to_dict()
    }

    weeklyPerCapita = {
        'cases': (covid.get_cases_difference_per_capita(region=region, most_recent_date=date, time_delta=7)).to_dict(),
        'deaths': (covid.get_deaths_difference_per_capita(region=region, most_recent_date=date, time_delta=7)).to_dict()
    }

    print("Getting weekIncrease Data")
    weeklyIncrease = {
        'cases': (
            covid.get_cases_increase_pct_for_given_dates(region=region, most_recent_date=date, time_delta=7)).to_dict(),
        'deaths': (
            covid.get_deaths_increase_pct_for_given_dates(region=region, most_recent_date=date, time_delta=7)).to_dict()
    }

    print("Getting perMonth Data")
    monthly = {
        'cases': covid.get_cases_for_given_range_alone(region=region, most_recent_date=date, time_delta=30).to_dict(),
        'deaths': covid.get_deaths_for_given_range_alone(region=region, most_recent_date=date, time_delta=30).to_dict()
    }

    monthlyPerCapita = {
        'cases': (covid.get_cases_difference_per_capita(region=region, most_recent_date=date, time_delta=30)).to_dict(),
        'deaths': (
            covid.get_deaths_difference_per_capita(region=region, most_recent_date=date, time_delta=30)).to_dict()
    }

    print("Getting weekIncrease Data")
    monthlyIncrease = {
        'cases': (covid.get_cases_increase_pct_for_given_dates(region=region, most_recent_date=date,
                                                               time_delta=30)).to_dict(),
        'deaths': (covid.get_deaths_increase_pct_for_given_dates(region=region, most_recent_date=date,
                                                                 time_delta=30)).to_dict()
    }

    print("Getting absoluteCumulative Data")
    absoluteCumulative = {
        'cases': covid.get_cumulative_cases_for_given_date(region=region, date=date).to_dict(),
        'deaths': covid.get_cumulative_deaths_for_given_date(region=region, date=date).to_dict()
    }

    print("Getting cumulativePerCapita Data")
    cumulativePerCapita = {
        'cases': (covid.get_cumulative_cases_per_capita_for_given_date(region=region, date=date)).to_dict(),
        'deaths': (covid.get_cumulative_deaths_per_capita_for_given_date(region=region, date=date)).to_dict()
    }

    return {
        "daily": daily,
        "dailyPerCapita": dailyPerCapita,
        "dailyIncrease": dailyIncrease,
        "weekly": weekly,
        "weeklyPerCapita": weeklyPerCapita,
        "weeklyIncrease": weeklyIncrease,
        "monthly": monthly,
        "monthlyPerCapita": monthlyPerCapita,
        "monthlyIncrease": monthlyIncrease,
        "absoluteCumulative": absoluteCumulative,
        "cumulativePerCapita": cumulativePerCapita
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
