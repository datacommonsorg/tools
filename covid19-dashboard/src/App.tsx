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
import DataTable from './DataTable';
import MultiButtonGroup from './MultiButtonGroup';
import CumulativePanel from './CumulativePanel';
import NavigationBar from './NavigationBar';
import {getLatestDate, goToPlace} from './Utils';
import Config from './Config.json';
import './index.css';
import '../node_modules/bootstrap/dist/css/bootstrap.min.css';
import {GeoIdToDataType, GeoIdToPlaceInfoType, KeyToTimeSeriesType} from './Types';
import Content from './Content.json';
import debounce from 'lodash/debounce';
import Breadcrumb from 'react-bootstrap/cjs/Breadcrumb';
import Place from './Place';
import dayjs from 'dayjs';

type AppPropsType = {
  location: any;
};

type AppStateType = {
  // When searching, this value gets updated.
  searchQuery: string;
};

class App extends React.Component<AppPropsType, AppStateType> {
  // The geoId we are currently observing. Default is World.
  geoId: string;

  // The place type we are currently observing. Default is Country.
  // Can be "Country", "State" or "County.
  placeTypeToShow: string;

  // Every geoId contains a Place object.
  // The place object has information such as name, containedIn and data.
  places: {[geoId: string]: Place};

  state = {
    searchQuery: '',
  };

  constructor(props: AppPropsType) {
    super(props);
    const urlParams = new URLSearchParams(this.props.location.search);
    this.geoId = urlParams.get('geoId') || 'World';
    this.placeTypeToShow = urlParams.get('placeType') || 'Country';
    this.places = {};
  }

  /**
   * On page load, fetch all places and timeSeries data in parallel.
   */
  componentDidMount = () => {
    this.fetchData();
  };

  /**
   * Fetches placeTypeToShow's data from APIs including /api/places
   * which contains a place's info such as name and containedIn.
   * Stores an object where each geoId maps to
   * a set of keys containing the data.
   */
  fetchData = (): void => {
    // Contains the data for placeTypeToShow
    const currentData = `data/${this.placeTypeToShow}`;
    const apis = [
      // contains data
      currentData,
      // contains place information
      'places',
    ];

    const promises = apis.map(api => fetch(`/api/${api}`));

    Promise.all(promises).then(([dataResponse, placeInfoResponse]) => {
      // Get the stat_var data as a dictionary: geoId->stat_var->date->value.
      dataResponse.json().then((geoIdToData: GeoIdToDataType) => {
        // Get the placeInfo as an object.
        // geoId->{name, containedIn, placeType}.
        placeInfoResponse.json().then((geoIdToInfo: GeoIdToPlaceInfoType) => {
          // Create the Place object and store it under places.
          Object.keys(geoIdToInfo).forEach(geoId => {
            const placeInfo = geoIdToInfo[geoId];
            const timeSeriesData = geoIdToData?.[geoId] || {};
            this.places[geoId] = new Place(geoId, placeInfo, timeSeriesData);
          });

          Object.values(this.places).forEach(place => {
            const containedIn = place.containedIn;
            const parentPlace = this.places[containedIn];
            place.setParentPlace(parentPlace);
          });

          // Download the rest of the data once all placeInfo
          // has been stored.
          this.cacheData();

          // Re-render page to display data.
          this.forceUpdate();
        });
      });
    });
  };

  /**
   * Downloads all timeSeries data for all places
   * except this.placeTypeToView and caches it locally.
   * This is done for speed.
   */
  cacheData = (): void => {
    const cacheApis = Config.placeTypes;
    // Delete this.placeTypeToShow from the array since
    // since it is already being requested by fetch data.
    cacheApis.splice(cacheApis.indexOf(this.placeTypeToShow), 1);

    const cachePromises = cacheApis.map(api => {
      return fetch('/api/data/' + api);
    });

    // We don't really care about this data, we only wanted to cache it.
    // None the less, we still store it because
    // it can help when using the search bar.
    Promise.all(cachePromises).then(responses => {
      responses.forEach(response => {
        response.json().then(json => {
          Object.entries(json).forEach(([geoId, value]) => {
            if (geoId in this.places) {
              // Store the timeSeries data for the geoId.
              this.places[geoId].keyToTimeSeries = value as KeyToTimeSeriesType
            }
          })
        })
      })
    });
  };

  /**
   * Get the parent places of the current geoId.
   * For example, ['World', 'US', 'Florida', 'Miami-Dade County']
   * would be the parent places for 'Miami-Dade County'.
   *
   * Note: The geoId is also returned in the list at the last index.
   */
  getParentPlaces = (): string[] => {
    // If none of the places have loaded yet, exit out.
    if (!Object.keys(this.places).length) return [];

    // Starting geoId.
    let geoId = this.geoId;

    // List of all parent places.
    const parentPlaces: string[] = [];

    // There can only be "World", "Country", "States", "County".
    // So our iteration shouldn't go above our placesTypes length.
    // If it does, there is an issue and break out of loop.
    for (let i = 0; i <= Config.placeTypes.length; i++) {
      // If we've reached the highest-level place, break out.
      if (!geoId) break;

      const place = this.places[geoId];
      // Add geoId to list.
      parentPlaces.unshift(geoId);
      // Travel up to parent geoId.
      // Repeat step.
      geoId = place?.containedIn;
    }

    return parentPlaces;
  };

  /**
   * When the user searches on the search bar
   * searchQuery is updated in real-time.
   * debounce is used to only trigger a one setState every 250ms.
   * @param value: contains the text the user inputted.
   */
  onSearchInput = debounce((value: string): void => {
    this.setState({searchQuery: value});
  }, 250);

  render = () => {
    // The current Place we are viewing.
    const selectedPlace = this.places[this.geoId];

    // Convert the object of geoId->Place to a list of Places.
    const places: Place[] = Object.values(this.places).filter(place => {
      return place.keyToTimeSeries;
    });

    // Filter the data to only contain the places that are contained
    // in this.geoId. That is, if this.geoId === "Florida".
    // Only show those places that are contained in Florida.
    let filteredPlaces = places.filter(place => {
      // If the selected geoId === 'country/USA', then filter by placeType.
      // Otherwise filter by places containedIn this.geoId.
      if (this.geoId === 'country/USA') {
        return place.placeType === this.placeTypeToShow;
      } else {
        return place.containedIn === this.geoId;
      }
    });

    // Generate the cumulativePanel columns from Content.json
    const cumulativePanelColumns = Content.cumulativePanel.map(
      ({
         dataKey,
         title,
         color,
       }: {
        dataKey: string;
        title: string;
        color: string;
      }) => {
        // Sum values for all geoIds for the latest date in the time-series.
        const values = filteredPlaces.map(place => {
          // Get the time-series for the given dataKey.
          // The dataKey comes from the configuration panel.
          // It tells the panel what data to display.
          const cumulativeStats = place.keyToTimeSeries[dataKey] || {};
          // Get a list of all dates.
          const dates = Object.keys(cumulativeStats);
          const latestDate = getLatestDate(dates);
          // Return the value for the latest date in the timeSeries.
          return cumulativeStats[latestDate] || 0;
        });

        // Sum up all the values for that specific dataKey.
        const value = values.reduce((a, b) => a + b, 0);

        // Return an object containing the configuration that column.
        return {
          title: title,
          color: color,
          value: value,
        };
      }
    );

    // If the user entered something on the search bar.
    // Automatically filter by searchQuery.
    // Otherwise, omit this step.
    if (this.state.searchQuery) {
      filteredPlaces = places.filter(place => {
        const placeName = (place.name + place.parentPlace?.name).toLowerCase();
        return placeName.includes(this.state.searchQuery);
      });
    }

    // Get the parent geoIds of this geoId.
    // Example: parent places of Florida: ["World", "US", "Florida"].
    const parentPlaces = this.getParentPlaces();

    // Get the latest date for all places.
    const dates = places
      .map(place => {
        const keyToTimeSeries = place.keyToTimeSeries[Config.tableDefaultSortBy] || {};
        // Config.defaultKey contains our reference key for dates.
        // AKA, what is our most complete dataset? We want to get the date
        // from that dataset.
        const dates = Object.keys(keyToTimeSeries);
        return getLatestDate(dates);
      })
      .filter(date => date);

    // From all the latest dates, calculate the latest date.
    // This will tell us the actual date.
    // Example: If Spain was updated August 17 and the US on August 18,
    // Our latest date will be "August 18" because, that's the most recent date.
    const maxDate = getLatestDate(dates);

    // Format maxDate into a more readable version.
    // Only format the date, if maxDate is valid.
    let formattedDate = '';
    if (maxDate) {
      formattedDate = dayjs(maxDate).format('MMM D, YYYY');
    }

    // Text describing the types of places viewing viewed.
    // "Countries in", "States in", "Counties in".
    const pluralPlaceTypes: {[key: string]: string} = Config.pluralPlaceTypes;
    let subtitle = '';

    // If placeName is "" or undefined, don't display a subtitle.
    // It means hasn't finished loading.
    if (selectedPlace?.name) {
      const pluralPlaceType = pluralPlaceTypes[this.placeTypeToShow];
      // "Counties in Florida", "Countries in World"...
      subtitle = pluralPlaceType + ' in ' + selectedPlace.name;
    }

    // Update the site's HTML title to include the subtitle.
    document.title = `${subtitle} - Data Commons COVID-19`;

    // Iterate through parent places and create an item for each place.
    // Example: World -> United States -> Florida
    const breadcrumbItems = parentPlaces.map(geoId => {
      return {
        // Is the item active?
        active: this.geoId === geoId,
        // What should happen when you click on it?
        onClick: () => goToPlace(geoId),
        // name of the place
        text: this.places[geoId]?.name,
      };
    });

    // Subregion button that is displayed when viewing country/USA.
    // "Compare States" and "Compare Counties".
    const subregionButtons = Config.subregionSelectionButton.map(button => {
      const placeType = button.id;
      // What should happen when a user clicks on the button.
      const onClick = () => goToPlace(this.geoId, placeType);
      return {
        // Is the button currently ON?
        active: this.placeTypeToShow === button.id,
        // What should happen when you click on it?
        onClick: onClick,
        // Text to display on button.
        text: button.text,
      };
    });
    return (
      <div>
        <NavigationBar
          title={'Data Commons'}
          subtitle={Config.subtitle}
          onType={e => {
            // Get the value and convert it to lowercase.
            const target = e.target as HTMLTextAreaElement;
            const value = target.value.toLowerCase();
            this.onSearchInput(value);
          }}
        />
        <div className={'site-container fadeIn'}>
          <div className={'header'}>
            <h6>{formattedDate}</h6>
            {
              // Only display the breadcrumb if not in World view.
              this.geoId !== 'World' && (
                <Breadcrumb className={'breadcrumb-mod'}>
                  {breadcrumbItems.map((item, i) => {
                    return (
                      <Breadcrumb.Item
                        href="#"
                        key={i}
                        active={item.active}
                        onClick={item.onClick}>
                        {item.text}
                      </Breadcrumb.Item>
                    );
                  })}
                </Breadcrumb>
              )
            }
            <h2 className={'title'}>{subtitle || <br />}</h2>
            {
              // Only display multi-button group if on US.
              this.geoId === 'country/USA' && (
                <MultiButtonGroup items={subregionButtons} />
              )
            }
          </div>
          <CumulativePanel textToValue={cumulativePanelColumns} />
          <div className={'content'}>
            <DataTable data={filteredPlaces} />
          </div>
          <footer>{Config.footer}</footer>
        </div>
      </div>
    );
  };
}

export default App;
