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

from send_request import send_request
from collections import defaultdict


class Covid19:
    def __init__(self, api_key) -> None:
        self._geo_exceptions = ['geoId/3651000', 'geoId/2938000']
        self.api_key = api_key
        self.counties = {}
        self.states = {}
        self.county_cases = {}
        self.county_deaths = {}
        self.state_cases = {}
        self.state_deaths = {}

    def load(self):
        """Loads the data.
        This method is meant to be called every time the cache expires."""
        self.counties = send_request(req_url='https://api.datacommons.org/node/property-values',
                                     req_json={"dcids": ['NYT_COVID19_County'], "property": "member"},
                                     post=True,
                                     compress=False,
                                     api_key=self.api_key)['NYT_COVID19_County']['out']

        self.states = send_request(req_url='https://api.datacommons.org/node/property-values',
                                   req_json={"dcids": ['NYT_COVID19_State'], "property": "member"},
                                   post=True,
                                   compress=False,
                                   api_key=self.api_key)['NYT_COVID19_State']['out']

        self.county_cases = self.get_covid_data(list(self.dcid_to_county_name().keys()), 'NYTCovid19CumulativeCases')
        self.county_deaths = self.get_covid_data(list(self.dcid_to_county_name().keys()), 'NYTCovid19CumulativeDeaths')
        self.state_cases = self.get_covid_data(list(self.dcid_to_state_name().keys()), 'NYTCovid19CumulativeCases')
        self.state_deaths = self.get_covid_data(list(self.dcid_to_state_name().keys()), 'NYTCovid19CumulativeDeaths')

    def dcid_to_county_name(self) -> dict:
        """
        Gets a dictionary of state names.
        :return: dictionary where dcid->name of the state.
        """
        print(len(self.counties))
        return {county['dcid']: county['name'] for county in self.counties}

    def dcid_to_state_name(self) -> dict:
        """
        Gets a dictionary of state names.
        :return: dictionary where dcid->name of the state
        """
        return {state['dcid']: state['name'] for state in self.states}

    def get_covid_data(self, place: list, stats_var: str) -> dict:
        """
        In charge of querying and returning the covid data in the appropriate format.
        :param place: list of dcids to get data for
        :param stats_var: NYTCovid19CumulativeCases or NYTCovid19CumulativeDeaths
        :return: dictionary where every day contains several regions, and those regions contain an int of cases/deaths
        """
        response = send_request("https://api.datacommons.org/bulk/stats",
                                {"place": place,
                                 "stats_var": stats_var},
                                api_key=self.api_key)
        output = defaultdict(dict)

        # Store the data in output as dates->dcid->value
        for dcid in response:
            if "data" not in response[dcid]:
                continue
            data = response[dcid]["data"]
            for day in data:
                output[day][dcid] = data[day]
        return output

    def get_state_population(self) -> dict:
        """
        Get the total population of all the states.
        :return: all the state populations. geoId->population
        """
        return self.get_population(list(self.dcid_to_state_name().keys()))

    def get_county_population(self) -> dict:
        """
        Get the total population of all the counties.
        :return: all the county populations. geoId->population
        """
        dcids = list(self.dcid_to_county_name().keys())
        dcids.extend(self._geo_exceptions)
        print(dcids)
        return self.get_population(dcids)

    def get_population(self, dcids) -> dict:
        """
        In charge of getting the total population of 2018, and returning a dictionary of geoId->population
        :param dcids: the list of dcids to query the poopulation from
        :return: a dictionary
        """
        response = send_request("https://api.datacommons.org/bulk/stats",
                                {"place": dcids,
                                 "stats_var": "TotalPopulation"},
                                api_key=self.api_key)
        output = defaultdict()
        for dcid in response:
            if not response[dcid]:
                continue
            output[dcid] = response[dcid]['data']['2018']
        return output
