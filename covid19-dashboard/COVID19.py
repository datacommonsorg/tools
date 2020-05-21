# Import libraries
from send_request import send_request

from helper_functions import clean_and_transpose
import pandas as pd

import datetime


class COVID19:
    def __init__(self):
        self.data = pd.DataFrame({})

        self.state_cumulative_cases = pd.DataFrame({})
        self.county_cumulative_cases = pd.DataFrame({})

        self.state_cumulative_deaths = pd.DataFrame({})
        self.county_cumulative_deaths = pd.DataFrame({})

        self.state_cumulative_cases_per_capita = pd.DataFrame({})
        self.county_cumulative_cases_per_capita = pd.DataFrame({})

        self.state_cumulative_deaths_per_capita = pd.DataFrame({})
        self.county_cumulative_deaths_per_capita = pd.DataFrame({})

        self.set_up()

    def set_up(self):
        print("Starting")
        # Create DataFrame that contains USA
        self.data = pd.DataFrame({'country': ['country/USA']})

        print("Getting State dcids")
        # Get all states dcids
        response = send_request("https://api.datacommons.org/node/places-in",
                                {"dcids": ["country/USA"], "placeType": "State"})
        state_dcids = [x['place'] for x in response]

        self.data['state_dcid'] = pd.Series([state_dcids])
        self.data = self.data.explode('state_dcid')

        # Get rid of Puerto Rico, not County Population data
        self.data = self.data[self.data.state_dcid != 'geoId/72']

        print("Getting State names")
        # Get all state names
        response = send_request("https://api.datacommons.org/node/property-values",
                                {"dcids": state_dcids, "property": "name"})
        state_names = {dcid: response[dcid]['out'][0]['value'] for dcid in response}
        self.data['state_name'] = self.data['state_dcid'].map(state_names)
        self.data = self.data.explode('state_name')

        print("Getting State populations")
        # Get all state populations
        response = send_request("https://api.datacommons.org/bulk/stats",
                                {"place": list(self.data['state_dcid']), "stats_var": "TotalPopulation"})
        state_population = {dcid: response[dcid]['data']['2018'] for dcid in response}
        self.data['state_population'] = self.data['state_dcid'].map(state_population)

        print("Getting County dcids")
        # Get all county dcids
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

        print("Getting County populations")
        # Get all county populations

        response = send_request(req_url="https://api.datacommons.org/bulk/place-obs", req_json={"placeType": "County",
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

        self.data = self.data.append({'country': 'country/USA', 'county_dcid': 'geoId/3651000',
                                      'state_dcid': 'geoId/36',
                                      'state_name': 'New York', 'county_name': 'NYC', 'county_population': 8399000},
                                     ignore_index=True)

        self.data = self.data.append({'country': 'country/USA', 'county_dcid': 'geoId/2938000',
                                      'state_dcid': 'geoId/29',
                                      'state_name': 'Missouri', 'county_name': 'Kansas', 'county_population': 491918},
                                     ignore_index=True)

        self.data = self.data.set_index('county_dcid')

        print("Getting State cumulative cases")
        # Get cumulative state cases
        state_cumulative_cases = {}
        response = send_request("https://api.datacommons.org/bulk/stats",
                                {"place": list(self.data['state_dcid']),
                                 "stats_var": "NYTCovid19CumulativeCases"})

        for dcid in response:
            data = response[dcid]['data']
            state_cumulative_cases[dcid] = data

        self.state_cumulative_cases = pd.DataFrame.from_dict(state_cumulative_cases, orient='index')
        self.state_cumulative_cases = clean_and_transpose(self.state_cumulative_cases)

        print("Getting State cumulative deaths")
        # Get cumulative state cases
        state_cumulative_deaths = {}
        response = send_request("https://api.datacommons.org/bulk/stats",
                                {"place": list(self.data['state_dcid']), "stats_var": "NYTCovid19CumulativeDeaths"})

        for dcid in response:
            data = response[dcid]['data']
            state_cumulative_deaths[dcid] = data

        self.state_cumulative_deaths = pd.DataFrame.from_dict(state_cumulative_deaths, orient='index')
        self.state_cumulative_deaths = clean_and_transpose(self.state_cumulative_deaths)

        print("Getting county cumulative cases")
        # Get cumulative county cases
        county_cumulative_cases = {}
        response = send_request("https://api.datacommons.org/bulk/stats",
                                {"place": list(self.data.index), "stats_var": "NYTCovid19CumulativeCases"})
        for dcid in response:
            try:
                data = response[dcid]['data']
                county_cumulative_cases[dcid] = data
            except KeyError:
                continue

        self.county_cumulative_cases = pd.DataFrame.from_dict(county_cumulative_cases, orient='index')
        self.county_cumulative_cases = clean_and_transpose(self.county_cumulative_cases)

        print("Getting county cumulative deaths")
        # Get cumulative county deaths
        county_cumulative_deaths = {}
        response = send_request("https://api.datacommons.org/bulk/stats",
                                {"place": list(self.data.index), "stats_var": "NYTCovid19CumulativeDeaths"})

        for dcid in response:
            try:
                data = response[dcid]['data']
                county_cumulative_deaths[dcid] = data
            except KeyError:
                continue

        self.county_cumulative_deaths = pd.DataFrame.from_dict(county_cumulative_deaths, orient='index')
        self.county_cumulative_deaths = clean_and_transpose(self.county_cumulative_deaths)

        self.get_geoId_to_name()

    def ISO_date(self, date, time_delta=0):
        if date == 'latest':
            date = str(self.state_cumulative_cases.index[-1])
        elif date == '7days':
            date = str(self.state_cumulative_cases.index[-8])
        elif date == '14days':
            date = str(self.state_cumulative_cases.index[-15])
        elif date == '30days':
            date = str(self.state_cumulative_cases.index[-31])
        return (datetime.date.fromisoformat(date) - datetime.timedelta(days=time_delta)).isoformat()

    def get_cumulative_cases_for_given_date(self, date="latest", region="state", show=30):
        date = self.ISO_date(date)
        if region == 'state':
            df = self.state_cumulative_cases.loc[date]
        else:
            df = self.county_cumulative_cases.loc[date]
        df = df.to_frame()
        df.index.name = region + '_dcid'
        df = df.rename({df.columns.values[0]: "value"}, axis="columns")
        return df.sort_values(ascending=False, by="value").dropna()[:show]

    def get_cumulative_deaths_for_given_date(self, date="latest", region="state", show=30):
        date = self.ISO_date(date)
        if region == 'state':
            df = self.state_cumulative_deaths.loc[date]
        else:
            df = self.county_cumulative_deaths.loc[date]
        df = df.to_frame()
        df.index.name = region + '_dcid'
        df = df.rename({df.columns.values[0]: "value"}, axis="columns")
        return df.sort_values(ascending=False, by="value").dropna()[:show]

    def get_cumulative_cases_per_capita_for_given_date(self, date="latest", region="state", show=30):
        date = self.ISO_date(date)
        if region == 'state':
            cumulative = self.state_cumulative_cases.loc[date]
            population = self.data.drop_duplicates('state_dcid').set_index('state_dcid')['state_population']
        else:
            cumulative = self.county_cumulative_cases.loc[date]
            population = self.data['county_population']
        df = (cumulative * 10000).div(population)
        df = pd.concat([df, population, cumulative], axis=1)
        df.index.name = region + '_dcid'
        df = df.rename({df.columns.values[0]: "value",
                        df.columns.values[1]: "population",
                        df.columns.values[2]: 'absolute'},
                       axis='columns')
        df = df[df['population'] >= 10000]
        return df.sort_values(ascending=False, by="value").dropna()[:show]

    def get_cumulative_deaths_per_capita_for_given_date(self, date="latest", region="state", show=30):
        date = self.ISO_date(date)
        if region == 'state':
            cumulative = self.state_cumulative_deaths.loc[date]
            population = self.data.drop_duplicates('state_dcid').set_index('state_dcid')['state_population']
        else:
            cumulative = self.county_cumulative_deaths.loc[date]
            population = self.data['county_population']
        df = (cumulative * 10000).div(population)
        df = pd.concat([df, population, cumulative], axis=1)
        df.index.name = region + '_dcid'
        df = df.rename({df.columns.values[0]: "value",
                        df.columns.values[1]: "population",
                        df.columns.values[2]: 'absolute'},
                       axis='columns')
        df = df[df['population'] >= 10000]
        return df.sort_values(ascending=False, by="value").dropna()[:show]

    def get_cases_increase_pct_for_given_dates(self, most_recent_date="latest", time_delta=7, region="state", show=30):
        most_recent_date = self.ISO_date(most_recent_date)
        oldest_date = self.ISO_date(most_recent_date, time_delta=time_delta)
        if region == 'state':
            df = (((self.state_cumulative_cases.loc[most_recent_date] /
                    self.state_cumulative_cases.loc[oldest_date]) - 1) * 100)
            difference = self.state_cumulative_cases.loc[most_recent_date] - self.state_cumulative_cases.loc[
                oldest_date]
        else:
            df = (((self.county_cumulative_cases.loc[most_recent_date] /
                    self.county_cumulative_cases.loc[oldest_date]) - 1) * 100)
            difference = self.county_cumulative_cases.loc[most_recent_date] - self.county_cumulative_cases.loc[
                oldest_date]
        df = pd.concat([df, difference], axis=1)
        df.index.name = region + '_dcid'
        df = df.rename({df.columns.values[0]: "value",
                        df.columns.values[1]: "absolute"},
                       axis='columns')
        df = df[df["absolute"] >= 200]
        return df.round(2).sort_values(ascending=False, by="value").dropna()[:show]

    def get_deaths_increase_pct_for_given_dates(self, most_recent_date="latest", time_delta=7, region="state", show=30):
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

        df = pd.concat([df, difference], axis=1)
        df.index.name = region + '_dcid'
        df = df.rename({df.columns.values[0]: "value",
                        df.columns.values[1]: "absolute"}, axis='columns')

        df = df[df["absolute"] >= 10]
        return df.round(2).sort_values(ascending=False, by="value").dropna()[:show]

    def get_cases_difference_per_capita(self, most_recent_date="latest", time_delta=7, region="state", show=30):
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
        df = (difference * 10000).div(population)
        df = pd.concat([df, difference, population], axis=1)
        df.index.name = region + '_dcid'
        df = df.rename({df.columns.values[0]: "value",
                        df.columns.values[1]: "absolute",
                        df.columns.values[2]: "population"},
                       axis='columns')
        df = df[df['population'] >= 10000]
        return df.sort_values(ascending=False, by="value").dropna()[:show]

    def get_deaths_difference_per_capita(self, most_recent_date="latest", time_delta=7, region="state", show=30):
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
        df = (difference * 10000).div(population)
        df = pd.concat([df, difference, population], axis=1)
        df.index.name = region + '_dcid'
        df = df.rename({df.columns.values[0]: "value",
                        df.columns.values[1]: "absolute",
                        df.columns.values[2]: "population"},
                       axis='columns')
        df = df[df['population'] >= 10000]
        return df.sort_values(ascending=False, by="value").dropna()[:show]

    def get_cases_for_given_range_alone(self, most_recent_date="latest", time_delta=1, region="state", show=30):
        most_recent_date = self.ISO_date(most_recent_date)
        oldest_date = self.ISO_date(most_recent_date, time_delta=time_delta)
        if region == 'state':
            df = self.state_cumulative_cases.loc[most_recent_date] - \
                 self.state_cumulative_cases.loc[oldest_date]
        else:
            df = self.county_cumulative_cases.loc[most_recent_date] - \
                 self.county_cumulative_cases.loc[oldest_date]

        df = df.to_frame()
        df.index.name = region + '_dcid'
        df = df.rename({df.columns.values[0]: "value"}, axis="columns")
        return df.sort_values(ascending=False, by="value").dropna()[:show]

    def get_deaths_for_given_range_alone(self, most_recent_date="latest", time_delta=1, region="state", show=30):
        most_recent_date = self.ISO_date(most_recent_date)
        oldest_date = self.ISO_date(most_recent_date, time_delta=time_delta)
        if region == 'state':
            df = self.state_cumulative_deaths.loc[most_recent_date] - \
                 self.state_cumulative_deaths.loc[oldest_date]
        else:
            df = self.county_cumulative_deaths.loc[most_recent_date] - \
                 self.county_cumulative_deaths.loc[oldest_date]
        df = df.to_frame()
        df.index.name = region + '_dcid'
        df = df.rename({df.columns.values[0]: "value"}, axis="columns")
        return df.sort_values(ascending=False, by="value").dropna()[:show]

    def get_geoId_to_name(self):
        geoId_map = {}
        for geoId in self.data.index:
            state_dcid = self.data.loc[geoId]['state_dcid']
            county_dcid = geoId
            county_name = self.data.loc[county_dcid]['county_name']
            county_name = county_name.replace(" County", "").replace(" Parish", "").replace(" City", "")
            geoId_map[county_dcid] = county_name + ', ' + self.data.loc[county_dcid]['state_name']
            geoId_map[state_dcid] = self.data.loc[county_dcid]['state_name']
        return geoId_map

    def get_latest_date(self, days_ago=0):
        return self.county_cumulative_cases.iloc[~days_ago].name
