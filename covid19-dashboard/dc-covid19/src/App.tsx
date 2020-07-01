/**
 Copyright 2020 Google LLC

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

 https://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
 */

import React from 'react';
import Configuration from './Configuration.json';
import {filterGeoIdThatBelongTo} from './Utils';
import Content from './Content';
import IsoDate from "./IsoDate";

type State = {
  allData: {}[]; // [cases, deaths, population, names]
  selectedRegion: string; // current region selected
  selectedShowTopN: number; // default number of top counties/states to show
  datePicked: string; // current date selected, latest is always default
  availableRegions: {}; // regionName -> geoId
  datesToPick: string[]; // available dates to pick from
};

class App extends React.Component<{}, State> {
  state = {
    allData: [{}, {}, {}, {}],
    selectedRegion: 'State',
    selectedShowTopN: 10,
    datePicked: '2020-01-01',
    availableRegions: Configuration.REGIONS,
    datesToPick: ['2020-01-01'],
  };

  componentDidMount() {
    const requests = this.fetchData();

    Promise.all(requests).then(responses => {
      responses.forEach((response, index) => {
        response.json().then(json => {
          // Keep the data stored in the same position.
          // That is: [cases, deaths, population, names]
          const currentData = this.state.allData.map(val => val);
          currentData[index] = json;
          this.setState({allData: currentData});

          // Index 0 contains the 'total-cases' object.
          // total-cases has all the dates as keys.
          if (index === 0) {
            // Get an array of all the dates in the data.
            const allDates = Object.keys(json);

            // Get the latest date.
            const latestDate = allDates.reduce((a, b) => a > b ? a : b);

            // Get the deltaDates from the Configuration file.
            const datesToPick = new IsoDate(latestDate)
              .getDatesFromDeltaDays(Configuration.DATES);

            this.setState({datesToPick: datesToPick});
            this.setState({datePicked: latestDate});

            // Index 3 contains the 'geoId -> belongsToRegion' object.
            // We can get all the available States.
          } else if (index === 3) {
            const regions: {[geoId: string]: string[]} = {};
            const geoIds = filterGeoIdThatBelongTo(json, 'State')
            geoIds.forEach(geoId => {
              regions[geoId] = json[geoId][0]
            })
            this.setState({
              availableRegions: {
                ...this.state.availableRegions,
                ...regions
              },
            });
          }
        });
      });
    });
  }

  /**
   * Set region, date and showTopN states.
   * These are passed down to props
   * @param key: state to set
   * @param value: value to set
   */
  handleSelectUpdate = (key: string, value: any) => {
    switch (key) {
      case 'region':
        this.setState({selectedRegion: value});
        break;
      case 'date':
        this.setState({datePicked: value});
        break;
      case 'showTopN':
        this.setState({selectedShowTopN: value});
        break;
    }
  };

  /**
   * Request the data from the server, and store the Promises in that order.
   * The order is important [cases, deaths, population, places].
   */
  fetchData = () => {
    const url = 'http://localhost/api/';
    const apis = [
      url + 'total-cases',
      url + 'total-deaths',
      url + 'population',
      url + 'places',
    ];
    // Map every url to the promise of the fetch
    return apis.map(api => fetch(api));
  };

  render = () => {
    return (
      <div className={'container'}>
        <h1 className={'main-title'}>
          {Configuration.TITLE + ' '}
          <span style={{color: '#990001'}}>
                        {Configuration.SUBTITLE}
                    </span>
        </h1>
        <Content
          allData={this.state.allData}
          content={Configuration.content}
          selectedRegion={this.state.selectedRegion}
          availableRegions={this.state.availableRegions}
          datePicked={this.state.datePicked}
          datesToPick={this.state.datesToPick}
          region={this.state.selectedRegion}
          handleSelectUpdate={this.handleSelectUpdate}
          selectedShowTopN={this.state.selectedShowTopN}
        />
      </div>
    );
  };
}

export default App;
