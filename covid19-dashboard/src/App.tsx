import React from 'react';
import DataTable from './DataTable';
import MultiButtonGroup from './MultiButtonGroup';
import CumulativePanel from './CumulativePanel';
import NavigationBar from './NavigationBar';
import BreadcrumbNav from './BreadcrumbNav';
import {getLatestDate} from './Utils';
import Config from './Config.json';
import './index.css';
import '../node_modules/bootstrap/dist/css/bootstrap.min.css';
import {DataType, TimeSeriesType, ValueType} from './Types';
import Content from './Content.json';
import debounce from 'lodash/debounce';

type AppPropsType = {
  location: any;
};

type AppStateType = {
  searchQuery: string;
};

class App extends React.Component<AppPropsType, AppStateType> {
  geoId: string;
  placeTypeToShow: string;
  data: DataType;
  places: {[geoId: string]: [string, string, string]};

  state = {
    searchQuery: '', // When searching, this value gets updated.
  };

  constructor(props: AppPropsType) {
    super(props);
    const urlParams = new URLSearchParams(this.props.location.search);

    // The geoId we are currently observing. Default is World.
    this.geoId = urlParams.get(Config.geoIdParam) || 'World';

    // The place type we are currently observing. Default is Country.
    // Can be "Country", "State" or "County.
    this.placeTypeToShow = urlParams.get(Config.placeTypeParam) || 'Country';

    // Every geoId contains a TimeSeries.
    // geoId -> date -> value
    this.data = {};

    // Every geoId contains information in the form of a tuple.
    // geoId -> (name, containedIn, placeType)
    // name: the name of the place. Example: "United States".
    // containedIn: the geoId of its parent place.
    // placeType: the type of place. "Country", "State", "County".
    this.places = {};
  }

  /**
   * On page load, fetch all places and data in parallel.
   */
  componentDidMount = () => {
    this.fetchPlaces();
    this.fetchData();
  };

  /**
   * Fetches all the place information.
   * Stores an object where each key/geoId maps to a tuple of info.
   * geoId -> (name, containedIn, placeType).
   */
  fetchPlaces = () => {
    fetch(Config.host + 'api/places').then(response => {
      response.json().then(json => {
        // Store response.
        this.places = json;
        this.forceUpdate();
      });
    });
  };

  /**
   * Fetches all the data.
   * Stores an object where each geoId maps to
   * a set of keys containing the data.
   */
  fetchData = (): void => {
    const url = Config.host + 'api/data/';

    // Iterate through the array of placeTypes
    // Fetch data for that specific placeType.
    const promises = Config.placeTypes.map(place => {
      return fetch(url + place);
    });

    // Fetch all data in parallel.
    Promise.all(promises).then(responses => {
      responses.forEach(response => {
        response.json().then(json => {
          this.data = {...this.data, ...json};
          // If this is the placeType we want to show
          // Force update the page, to display the new data.
          if (response.url.includes(this.placeTypeToShow)) {
            this.forceUpdate();
          }
        });
      });
    });
  };

  /**
   * Navigate to a different geoId.
   * @param geoId: the place's geoId we want to view.
   * @param placeType: the types of places we want to view.
   * Example: geoId=country/USA and placeType=County
   * would display all counties in the USA.
   */
  goToGeoId = (geoId?: string, placeType?: string): void => {
    let newUrl = '/';

    // Redirect to a specific geoId.
    if (geoId && geoId !== 'World') {
      newUrl += `?${Config.geoIdParam}=${geoId}`;
    } else {
      // if !geoId or geoId == 'World', redirect to homepage.
      window.location.href = '/';
      return;
    }

    // If placeType has been given, redirect to this placeType.
    if (placeType && geoId) {
      newUrl += `&${Config.placeTypeParam}=${placeType}`;
    } else if (!placeType && geoId) {
    // Otherwise, State is defaulted.
      newUrl += `&${Config.placeTypeParam}=State`;
    }

    // Redirect to new url.
    window.location.href = newUrl;
  };

  /**
   * Get the parent places of the current geoId.
   * For example, ['World', 'US', 'Florida', 'Miami-Dade County']
   * would be the parent places for 'Miami-Dade County'.
   *
   * Note: The geoId is also returned in the list at the last index.
   */
  getParentPlaces = (): string[] => {
    // If /places API hasn't finished loading yet, exit out.
    if (!Object.keys(this.places).length) {
      return [];
    }

    // Starting geoId.
    let geoId = this.geoId;

    // List of all parent places.
    const parentPlaces: string[] = [];

    // There can only be "World", "Country", "States", "County".
    // So our iteration shouldn't go above 4.
    // If it does, there is an issue, break out.
    for (let i = 0; i < 4; i++) {
      if (!geoId) break;

      const placeInfo = this.places[geoId];
      parentPlaces.unshift(geoId);
      geoId = placeInfo?.[1]; // place containedIn
    }

    return parentPlaces;
  };

  /**
   * When the user searches on the search bar
   * searchQuery is updated in real-time.
   * @param value: contains the text the user inputted.
   */
  onSearchInput = debounce((value: string): void => {
    this.setState({searchQuery: value});
  }, 500);

  render = () => {
    // Create objects for all places in our dataset.
    const data: ValueType[] = Object.values(this.data).map(obj => {
      const geoId: string = obj.geoId; // geoId of the place
      const placeInfo = this.places[geoId] || []; // (name, containedIn, placeType)
      const [placeName, containedIn, placeType] = placeInfo; // place info
      const parentPlaceName = this.places[containedIn]?.[0]; // name of parent

      // fullName is the placeName + parentPlaceName.
      let fullName = placeName;

      // If not a country, append parent place to name.
      // Miami-Dade becomes "Miami-Dade, Florida".
      if (placeType !== 'Country') {
        fullName += ', ' + parentPlaceName;
      }

      // Decide what should happen when a user clicks on the place.
      // Default is undefined, unless the place is a State or the US.
      let onClick = undefined;
      if (placeType === 'State' || obj.geoId === 'country/USA') {
        // If the user wants to dive into a place,
        // what placeTypes will they be shown?
        // County, Country or State?
        // Example: If user clicks on State, they should be shown counties.
        const subregions: {[key: string]: string} = Config.subregions;
        const placeTypeToShow = subregions[placeType];
        onClick = () => this.goToGeoId(geoId, placeTypeToShow);
      }

      return {
        ...obj, // destructure all timeSeries. They are stored by key.
        name: fullName, // name of the place
        containedIn: containedIn, // geoId of the parent place
        placeType: placeType, // "Country", "State" or "County"
        onClick: onClick, // What should happen when this geoId is clicked.
      };
    });

    // Filter the data to only contain the places that are contained
    // in this.geoId. That is, if this.geoId === "Florida".
    // Only show those places that are contained in Florida.
    let filteredData = data.filter(obj => {
      // If the selected geoId === 'country/USA', then filter by placeType.
      // Otherwise filter by places containedIn this.geoId.
      if (this.geoId === 'country/USA') {
        return obj.placeType === this.placeTypeToShow;
      } else {
        return obj.containedIn === this.geoId;
      }
    });

    // Generate the cumulativePanel columns given a configuration in Content.json
    const cumulativePanelColumns = Content.cumulativePanel.map(config => {
      // dataKey is the key we want to sum up the values for.
      // This key must be present in the dataset.
      // Example: cumulativeCases.
      const dataKey = config.dataKey;
      // Sum up all values for all geoIds for the latest date in the time-series.
      const values = filteredData.map(data => {
        // Get the time-series for the given dataKey.
        const cumulativeCases: TimeSeriesType = data[dataKey] || {};
        // Get a list of all dates.
        const dates = Object.keys(cumulativeCases);
        const latestDate = getLatestDate(dates);
        // Return the value for the latest date in the timeSeries.
        return cumulativeCases[latestDate] || 0;
      });

      // Sum up all the values for that specific dataKey.
      const value = values.reduce((a, b) => a + b, 0);
      // Return an object containing the configuration that column.
      return {
        title: config.title,
        color: config.color,
        value: value,
      };
    });

    // If the user entered something on the search bar.
    // They are automatically filtering by searchQuery.
    // Otherwise, omit this step.
    if (this.state.searchQuery) {
      filteredData = data.filter(obj => {
        const placeName = obj.name.toLowerCase();
        return placeName.includes(this.state.searchQuery);
      });
    }

    // Get the parent geoIds of this geoId.
    // Example: parent places of Florida: ["World", "US", "Florida"].
    const parentPlaces = this.getParentPlaces();

    // Text describing the types of places viewing viewed.
    // "Countries in", "States in", "Counties in"
    const pluralPlaceTypes: {[key: string]: string} = Config.pluralPlaceTypes;
    let subtitle = '';

    // Get the name for the current geoId.
    const placeName = this.places[this.geoId]?.[0] || '';
    // If placeName is "" or undefined, don't display a subtitle.
    // Data hasn't finished loading.
    if (placeName) {
      // "Counties in Florida", "Countries in World"...
      subtitle = pluralPlaceTypes[this.placeTypeToShow] + ' in ' + placeName;
    }

    // Update the site's HTML title to include the subtitle.
    document.title = `${subtitle} - Data Commons COVID-19`;

    // Iterate through parent places and create an item for each place.
    // Example: World -> United States -> Florida
    const breadcrumbItems = parentPlaces.map(geoId => {
      return {
        active: this.geoId === geoId,
        onClick: () => this.goToGeoId(geoId),
        text: this.places[geoId]?.[0],
      };
    });

    // Subregion button that is displayed when viewing country/USA.
    // "Compare States" and "Compare Counties".
    const subregionButtons = Config.subregionSelectionButton.map(button => {
      const onClick = () => this.goToGeoId(this.geoId, this.placeTypeToShow);
      return {
        active: this.placeTypeToShow === button.id,
        onClick: onClick,
        text: button.text,
      };
    });

    return (
      <div>
        <NavigationBar
          title={'Data Commons'}
          subtitle={Config.SUBTITLE}
          onType={e => {
            // Get the value and convert it to lowercase.
            const target = e.target as HTMLTextAreaElement;
            const value = target.value.toLowerCase();
            this.onSearchInput(value);
          }}
        />
        <div className={'site-container'}>
          <div className={'header'}>
            <BreadcrumbNav items={breadcrumbItems} />
            <h2 className={'title'}>{subtitle}</h2>
            {this.geoId === 'country/USA' && (
              <MultiButtonGroup items={subregionButtons} />
            )}
          </div>
          <CumulativePanel textToValue={cumulativePanelColumns} />
          <div className={'content'}>
            <DataTable data={filteredData} />
          </div>
          <footer>{Config.FOOTER}</footer>
        </div>
      </div>
    );
  };
}

export default App;
