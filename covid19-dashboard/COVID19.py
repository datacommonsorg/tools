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

from helper_functions import clean_and_transpose
import pandas as pd
from send_request import send_request

import datetime


class COVID19:
    def __init__(self):
        self.data = pd.DataFrame({'country': ['country/USA']})

        self.state_cumulative_cases = pd.DataFrame({})
        self.county_cumulative_cases = pd.DataFrame({})

        self.state_cumulative_deaths = pd.DataFrame({})
        self.county_cumulative_deaths = pd.DataFrame({})

        self.state_cumulative_cases_per_capita = pd.DataFrame({})
        self.county_cumulative_cases_per_capita = pd.DataFrame({})

        self.state_cumulative_deaths_per_capita = pd.DataFrame({})
        self.county_cumulative_deaths_per_capita = pd.DataFrame({})

        print("Starting!")
        self.request_state_dcids()
        self.request_state_names()
        self.request_state_population()
        self.request_county_dcids()
        self.request_county_population()

        # Data index is now the county's dcid
        self.data = self.data.set_index('county_dcid')

        self.add_nyt_exceptions()

        # Request information from the NYT COVID database.
        self.state_cumulative_cases = self.get_covid_data(dcids=list(self.data['state_dcid']),
                                                          stats_var='NYTCovid19CumulativeCases')
        self.state_cumulative_deaths = self.get_covid_data(dcids=list(self.data['state_dcid']),
                                                           stats_var='NYTCovid19CumulativeDeaths')
        self.county_cumulative_cases = self.get_covid_data(dcids=list(self.data.index),
                                                           stats_var='NYTCovid19CumulativeCases')
        self.county_cumulative_deaths = self.get_covid_data(dcids=list(self.data.index),
                                                            stats_var='NYTCovid19CumulativeDeaths')

        # Generate a map from geoId -> region name
        self.generate_map_of_dcid_to_name()

    def request_state_dcids(self):
        """Retrieves all the states dcids in the USA"""
        print("Getting State dcids")
        response = send_request("https://api.datacommons.org/node/places-in",
                                {"dcids": ["country/USA"], "placeType": "State"})
        state_dcids = [x['place'] for x in response]

        self.data['state_dcid'] = pd.Series([state_dcids])
        self.data = self.data.explode('state_dcid')

        # Get rid of Puerto Rico, not County Population data
        self.data = self.data[self.data.state_dcid != 'geoId/72']

    def request_state_names(self):
        """Retrieves the states from the list of state_dcid"""
        print("Getting State names")
        response = send_request("https://api.datacommons.org/node/property-values",
                                {"dcids": list(self.data['state_dcid']), "property": "name"})
        state_names = {dcid: response[dcid]['out'][0]['value'] for dcid in response}
        self.data['state_name'] = self.data['state_dcid'].map(state_names)
        self.data = self.data.explode('state_name')

    def request_state_population(self):
        """Retrieves the state population for the given set of state dcids."""
        print("Getting States population")
        response = send_request("https://api.datacommons.org/bulk/stats",
                                {"place": list(self.data['state_dcid']), "stats_var": "TotalPopulation"})
        state_population = {dcid: response[dcid]['data']['2018'] for dcid in response}
        self.data['state_population'] = self.data['state_dcid'].map(state_population)

    def request_county_dcids(self):
        """Retrieves the states from the list of county_dcid"""
        print("Getting County dcids")
        response = send_request("https://api.datacommons.org/node/places-in",
                                {"dcids": list(self.data['state_dcid']), "placeType": "County"})
        county_dcids = {}

        for elem in response:
            dcid = elem['dcid']
            name = elem['place']
            try:
                county_dcids[dcid].append(name)
            except KeyError:
                county_dcids[dcid] = [name]

        self.data['county_dcid'] = self.data['state_dcid'].map(county_dcids)
        self.data = self.data.explode('county_dcid')

    def request_county_population(self):
        """Retrieves the county population for the given set of county dcids."""
        print("Getting County populations")
        response = send_request(req_url="https://api.datacommons.org/bulk/place-obs",
                                req_json={"placeType": "County",
                                          "populationType": "Person",
                                          "observationDate": "2018"},
                                compress=True)
        response = response['places']
        county_names = {}
        county_population = {}

        for county in response:
            dcid = county['place']
            county_names[dcid] = county['name']
            for observation in county['observations']:
                if observation['measurementMethod'] == 'CensusPEPSurvey' and observation['measuredProp'] == 'count':
                    county_population[dcid] = observation['measuredValue']

        self.data['county_name'] = self.data['county_dcid'].map(county_names)
        self.data['county_population'] = self.data['county_dcid'].map(county_population)

    # def request_city_population(self):
    #     """Retrieves the county population for the given set of county dcids."""
    #     print("Getting County populations")
    #     response = send_request(req_url="https://api.datacommons.org/bulk/place-obs",
    #                             req_json={"placeType": "City",
    #                                       "populationType": "Person",
    #                                       "observationDate": "2018"},
    #                             compress=True)
    #     cities = {'geoId/3651000': response['places']['geoId/3651000']}
    #     cities['geoId/2938000'] = response['places']['geoId/2938000']
    # 
    #     self.data['county_population'] = self.data['county_dcid'].map(cities)

    def add_nyt_exceptions(self):
        """The NYT COVID19 has two exceptions.
        NYC counties are combined into one.
        Kansas City counties are too.
        This function is in charge of adding those counties/cities to self.data"""
        self.data.loc['geoId/3651000', 'county_population'] = 8399000
        self.data.loc['geoId/2938000', 'county_population'] = 491918
        # self.request_city_population()

    def get_covid_data(self, dcids: list, stats_var: str) -> pd.DataFrame:
        """Retrieves COVID19 data given a lsit of dcids and statistical variable"""
        data_holder = {}
        response = send_request("https://api.datacommons.org/bulk/stats",
                                {"place": dcids, "stats_var": stats_var})

        for dcid in response:
            try:
                data = response[dcid]['data']
                data_holder[dcid] = data
            except KeyError:
                continue
        df = pd.DataFrame.from_dict(data_holder, orient='index')
        return clean_and_transpose(df)

    def ISO_date(self, date: str, time_delta: int = 0):
        """Converts to ISO date given a string and a time_delta.
        A time delta is the day you want to retrieve.
        Example: If today is day 10 and time_delta=3, return 7"""
        if date == 'latest':
            date = str(self.state_cumulative_cases.index[-1])
        elif date == '7days':
            date = str(self.state_cumulative_cases.index[-8])
        elif date == '14days':
            date = str(self.state_cumulative_cases.index[-15])
        elif date == '30days':
            date = str(self.state_cumulative_cases.index[-31])
        return (datetime.date.fromisoformat(date) - datetime.timedelta(days=time_delta)).isoformat()

    def get_counties_in_state(self, state_dcid):
        return list(self.data[self.data['state_dcid'] == state_dcid].index)

    def get_cumulative_cases_for_given_date(self, date="latest", region="state"):
        date = self.ISO_date(date)
        if region == 'state':
            df = self.state_cumulative_cases.loc[date]
            df.index.name = 'state_dcid'
        else:
            df = self.county_cumulative_cases.loc[date]
            df.index.name = 'county_dcid'

        if region != 'state' and region != 'county':
            counties_in_state = self.get_counties_in_state(region)
            df = df[df.index.isin(counties_in_state)]

        df = df.to_frame()
        df = df.rename({df.columns.values[0]: "value"}, axis="columns")
        df = df[(df['value'] > 0)]
        return df.sort_values(ascending=False, by="value").dropna()

    def get_cumulative_deaths_for_given_date(self, date="latest", region="state"):
        date = self.ISO_date(date)
        if region == 'state':
            df = self.state_cumulative_deaths.loc[date]
            df.index.name = 'state_dcid'
        else:
            df = self.county_cumulative_deaths.loc[date]
            df.index.name = 'county_dcid'

        if region != 'state' and region != 'county':
            counties_in_state = self.get_counties_in_state(region)
            df = df[df.index.isin(counties_in_state)]

        df = df.to_frame()
        df = df.rename({df.columns.values[0]: "value"}, axis="columns")
        df = df[(df['value'] > 0)]
        return df.sort_values(ascending=False, by="value").dropna()

    def get_cumulative_cases_per_capita_for_given_date(self, date="latest", region="state"):
        date = self.ISO_date(date)
        if region == 'state':
            cumulative = self.state_cumulative_cases.loc[date]
            population = self.data.drop_duplicates('state_dcid').set_index('state_dcid')['state_population']
        else:
            cumulative = self.county_cumulative_cases.loc[date]
            population = self.data['county_population']

        if region != 'state' and region != 'county':
            counties_in_state = self.get_counties_in_state(region)
            cumulative = cumulative[cumulative.index.isin(counties_in_state)]
            population = population[population.index.isin(counties_in_state)]

        df = (cumulative * 10000).div(population)
        df = pd.concat([df, population, cumulative], axis=1)
        df.index.name = region + '_dcid'
        df = df.rename({df.columns.values[0]: "value",
                        df.columns.values[1]: "population",
                        df.columns.values[2]: 'absolute'},
                       axis='columns')
        if region == 'state' or region == 'county':
            df = df[df['population'] >= 10000]
        df = df[(df['value'] > 0)]
        return df.sort_values(ascending=False, by="value").dropna()

    def get_cumulative_deaths_per_capita_for_given_date(self, date="latest", region="state"):
        date = self.ISO_date(date)
        if region == 'state':
            cumulative = self.state_cumulative_deaths.loc[date]
            population = self.data.drop_duplicates('state_dcid').set_index('state_dcid')['state_population']
        else:
            cumulative = self.county_cumulative_deaths.loc[date]
            population = self.data['county_population']

        if region != 'state' and region != 'county':
            counties_in_state = self.get_counties_in_state(region)
            cumulative = cumulative[cumulative.index.isin(counties_in_state)]
            population = population[population.index.isin(counties_in_state)]

        df = (cumulative * 10000).div(population)
        df = pd.concat([df, population, cumulative], axis=1)
        df = df.rename({df.columns.values[0]: "value",
                        df.columns.values[1]: "population",
                        df.columns.values[2]: 'absolute'},
                       axis='columns')
        if region == 'state' or region == 'county':
            df = df[df['population'] >= 10000]
        df = df[(df['value'] > 0)]
        return df.sort_values(ascending=False, by="value").dropna()

    def get_cases_increase_pct_for_given_dates(self, most_recent_date="latest", time_delta=7, region="state"):
        most_recent_date = self.ISO_date(most_recent_date)
        oldest_date = self.ISO_date(most_recent_date, time_delta=time_delta)
        if region == 'state':
            df = (((self.state_cumulative_cases.loc[most_recent_date] /
                    self.state_cumulative_cases.loc[oldest_date]) - 1) * 100)
            difference = self.state_cumulative_cases.loc[most_recent_date] - \
                         self.state_cumulative_cases.loc[oldest_date]
        else:
            df = (((self.county_cumulative_cases.loc[most_recent_date] /
                    self.county_cumulative_cases.loc[oldest_date]) - 1) * 100)
            difference = self.county_cumulative_cases.loc[most_recent_date] - \
                         self.county_cumulative_cases.loc[oldest_date]

        if region != 'state' and region != 'county':
            counties_in_state = self.get_counties_in_state(region)
            df = df[df.index.isin(counties_in_state)]
            difference = difference[difference.index.isin(counties_in_state)]

        df = pd.concat([df, difference], axis=1)
        df = df.rename({df.columns.values[0]: "value",
                        df.columns.values[1]: "absolute"},
                       axis='columns')
        df = df[df["absolute"] >= 10]
        df = df[(df['value'] > 0)]
        return df.round(2).sort_values(ascending=False, by="value").dropna()

    def get_deaths_increase_pct_for_given_dates(self, most_recent_date="latest", time_delta=7, region="state"):
        most_recent_date = self.ISO_date(most_recent_date)
        oldest_date = self.ISO_date(most_recent_date, time_delta=time_delta)
        if region == 'state':
            df = (((self.state_cumulative_deaths.loc[most_recent_date] /
                    self.state_cumulative_deaths.loc[oldest_date]) - 1) * 100)
            difference = self.state_cumulative_deaths.loc[most_recent_date] - self.state_cumulative_deaths.loc[
                oldest_date]
        else:
            df = (((self.county_cumulative_deaths.loc[most_recent_date] /
                    self.county_cumulative_deaths.loc[oldest_date]) - 1) * 100)
            difference = self.county_cumulative_deaths.loc[most_recent_date] - self.county_cumulative_deaths.loc[
                oldest_date]

        if region != 'state' and region != 'county':
            counties_in_state = self.get_counties_in_state(region)
            df = df[df.index.isin(counties_in_state)]
            difference = difference[difference.index.isin(counties_in_state)]

        df = pd.concat([df, difference], axis=1)
        df.index.name = region + '_dcid'
        df = df.rename({df.columns.values[0]: "value",
                        df.columns.values[1]: "absolute"}, axis='columns')

        df = df[df["absolute"] >= 10]
        df = df[(df['value'] > 0)]
        return df.round(2).sort_values(ascending=False, by="value").dropna()

    def get_cases_difference_per_capita(self, most_recent_date="latest", time_delta=7, region="state"):
        most_recent_date = self.ISO_date(most_recent_date)
        oldest_date = self.ISO_date(most_recent_date, time_delta=time_delta)

        if region == 'state':
            difference = self.state_cumulative_cases.loc[most_recent_date] - \
                         self.state_cumulative_cases.loc[oldest_date]
            population = self.data.drop_duplicates('state_dcid').set_index('state_dcid')['state_population']
        else:
            difference = self.county_cumulative_cases.loc[most_recent_date] - \
                         self.county_cumulative_cases.loc[oldest_date]
            population = self.data['county_population']

        if region != 'state' and region != 'county':
            counties_in_state = self.get_counties_in_state(region)
            difference = difference[difference.index.isin(counties_in_state)]
            population = population[population.index.isin(counties_in_state)]

        df = (difference * 10000).div(population)
        df = pd.concat([df, difference, population], axis=1)
        df.index.name = region + '_dcid'
        df = df.rename({df.columns.values[0]: "value",
                        df.columns.values[1]: "absolute",
                        df.columns.values[2]: "population"},
                       axis='columns')
        if region == 'state' or region == 'county':
            df = df[df['population'] >= 10000]
        df = df[(df['value'] > 0)]
        return df.sort_values(ascending=False, by="value").dropna()

    def get_deaths_difference_per_capita(self, most_recent_date="latest", time_delta=7, region="state"):
        most_recent_date = self.ISO_date(most_recent_date)
        oldest_date = self.ISO_date(most_recent_date, time_delta=time_delta)

        if region == 'state':
            difference = self.state_cumulative_deaths.loc[most_recent_date] - \
                         self.state_cumulative_deaths.loc[oldest_date]
            population = self.data.drop_duplicates('state_dcid').set_index('state_dcid')['state_population']
        else:
            difference = self.county_cumulative_deaths.loc[most_recent_date] - \
                         self.county_cumulative_deaths.loc[oldest_date]
            population = self.data['county_population']

        if region != 'state' and region != 'county':
            counties_in_state = self.get_counties_in_state(region)
            difference = difference[difference.index.isin(counties_in_state)]
            population = population[population.index.isin(counties_in_state)]

        df = (difference * 10000).div(population)
        df = pd.concat([df, difference, population], axis=1)
        df.index.name = region + '_dcid'
        df = df.rename({df.columns.values[0]: "value",
                        df.columns.values[1]: "absolute",
                        df.columns.values[2]: "population"},
                       axis='columns')

        if region == 'state' or region == 'county':
            df = df[df['population'] >= 10000]
        df = df[(df['value'] > 0)]
        return df.sort_values(ascending=False, by="value").dropna()

    def get_cases_for_given_range_alone(self, most_recent_date="latest", time_delta=1, region="state"):
        most_recent_date = self.ISO_date(most_recent_date)
        oldest_date = self.ISO_date(most_recent_date, time_delta=time_delta)
        if region == 'state':
            df = self.state_cumulative_cases.loc[most_recent_date] - \
                 self.state_cumulative_cases.loc[oldest_date]
        else:
            df = self.county_cumulative_cases.loc[most_recent_date] - \
                 self.county_cumulative_cases.loc[oldest_date]

        if region != 'state' and region != 'county':
            counties_in_state = self.get_counties_in_state(region)
            df = df[df.index.isin(counties_in_state)]

        df = df.to_frame()
        df.index.name = region + '_dcid'
        df = df.rename({df.columns.values[0]: "value"}, axis="columns")
        df = df[(df['value'] > 0)]
        return df.sort_values(ascending=False, by="value").dropna()

    def get_deaths_for_given_range_alone(self, most_recent_date="latest", time_delta=1, region="state"):
        most_recent_date = self.ISO_date(most_recent_date)
        oldest_date = self.ISO_date(most_recent_date, time_delta=time_delta)
        if region == 'state':
            df = self.state_cumulative_deaths.loc[most_recent_date] - \
                 self.state_cumulative_deaths.loc[oldest_date]
        else:
            df = self.county_cumulative_deaths.loc[most_recent_date] - \
                 self.county_cumulative_deaths.loc[oldest_date]

        if region != 'state' and region != 'county':
            counties_in_state = self.get_counties_in_state(region)
            df = df[df.index.isin(counties_in_state)]

        df = df.to_frame()
        df.index.name = region + '_dcid'
        df = df.rename({df.columns.values[0]: "value"}, axis="columns")
        df = df[(df['value'] > 0)]
        return df.sort_values(ascending=False, by="value").dropna()

    def generate_map_of_dcid_to_name(self):
        geoId_map = {}
        for geoId in self.data.index:
            state_dcid = self.data.loc[geoId]['state_dcid']
            county_dcid = geoId
            county_name = self.data.loc[county_dcid]['county_name']
            county_name = county_name.replace(" County", "").replace(" Parish", "").replace(" City", "").replace(" Borough", "")
            geoId_map[county_dcid] = county_name + ', ' + self.data.loc[county_dcid]['state_name']
            geoId_map[state_dcid] = self.data.loc[county_dcid]['state_name']
        return geoId_map

    def get_latest_date_in_dataset(self, days_ago=0):
        return self.county_cumulative_cases.iloc[~days_ago].name

    def get_all_state_dcids(self):
        return set(self.data['state_dcid'])
