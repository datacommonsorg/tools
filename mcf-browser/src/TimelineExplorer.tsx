/**
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import React, {Component} from 'react';
import Select, {MultiValue} from 'react-select';

import {Series} from './back-end/time-series';
import {Grouping, groupSeriesByLocations, renderTimeGraph} from './utils';
import {LoadingSpinner} from './LoadingSpinner';
import {getName} from './back-end/utils';
import {PageBar} from './PageBar';

const STAT_VARS_PER_PAGE = 10;
const INITIAL_NUM_LOCATIONS = 5;

interface LocationMapping {
  [dcid: string]: string;
}

interface SelectOption {
  value: string;
  label: string;
}

interface TimelineExplorerPropType {
  /**
  * Passes the data to be plotted
  */
  data: Series[];

  /**
  * Indicates if uploaded files are currently being parsed.
  */
  loading: boolean;
}

interface TimelineExplorerStateType {
  /** The currently selected locations to filter by */
  locations: string[];

  /** A list of possible locations to select from */
  locationOptions: SelectOption[]

  /** The key for the select component to tell it
  * to re-render when the locations are loaded in
  */
  selectKey: string;

  /** A mapping from a location dcid to its name */
  locationMapping: LocationMapping;

  /** The list of groups to plot, grouped by stat var */
  statVarGroups: Series[][];

  /** Tracks which page the user is currently viewing (0-indexed) */
  page: number;
}

/** Component to display the timeline explorer */
class TimelineExplorer extends Component<
  TimelineExplorerPropType,
  TimelineExplorerStateType
> {
  /** Constructor for class, sets initial state
    * @param {TimelineExplorerPropType} props the props passed in by parent
    * component
    */
  constructor(props: TimelineExplorerPropType) {
    super(props);
    this.state = {
      locations: [],
      locationOptions: [],
      selectKey: 'unloaded',
      locationMapping: {},
      statVarGroups: [],
      page: 0,
    };
  }

  /**
   * Update the state variables whenever necessary given
   * the current value of this.props
   */
  updateState() {
    const locationsPromise = this.getAllLocations();
    locationsPromise.catch(
        () => {
          console.log(
              'Error getting locations for data:',
          );
          console.log(this.props.data);
        },
    );
    locationsPromise.then(
        (locationOptions) => {
          const locations = locationOptions.slice(0, INITIAL_NUM_LOCATIONS)
              .map(
                  (option) => option.value,
              );
          const selectKey = locations.join(',');
          const locationMapping: LocationMapping = {};
          locationOptions.map(
              (obj) => locationMapping[obj.value] = obj.label,
          );
          const page = 0;
          const statVarGroups = Object.values(
              this.getVariableToSeries(locations),
          ) as Series[][];
          this.setState(() => {
            return {
              locations,
              locationOptions,
              selectKey,
              locationMapping,
              statVarGroups,
              page,
            };
          });
        },
    );
  }

  /** Tracks when component is mounted */
  componentDidMount() {
    this.updateState();
  }

  /** Set the location options
    * @param {TimelineExplorerPropType} prevProps the previous props
   */
  componentDidUpdate(prevProps: TimelineExplorerPropType) {
    if (prevProps.data !== this.props.data) {
      this.updateState();
    }
  }

  /** Returns the series objects which match the current locations filter
    * @param {string[]} locations a list of locations to filter by
    * @return {Series[]} series that match the filter
   */
  getFilteredData(locations: string[]): Series[] {
    const cleanedLocations = new Set(locations);

    const filteredData = this.props.data.filter(
        (series) => cleanedLocations.has(series.observationAbout),
    );

    return filteredData;
  }

  /** Processes the data passed in by props and returns the
    * data grouped by variableMeasured
    * @param {string[]} locations a list of locations to filter by
    * @return {Grouping} an object mapping from variableMeasured to an array
    * of Series with that variableMeasured value
    */
  getVariableToSeries(locations: string[]): Grouping {
    const output: Grouping = {};
    // Filter by location
    const data = this.getFilteredData(locations);

    for (const series of data) {
      const varMeasured = series.variableMeasured ?
        series.variableMeasured :
        '';
      if (!output[varMeasured]) {
        output[varMeasured] = [];
      }
      output[varMeasured].push(series);
    }

    return output;
  }


  /** Returns the JSX to render a group of related series
    * @param {Series[]} seriesList a list of series objects with
    *                              the same varMeasured
    * @param {LocationMapping} locationMapping a mapping from location dcid to
    * name
    * @return {JSX.Element} a details element plotting all of the series
   */
  renderSeriesGroup(seriesList: Series[], locationMapping: LocationMapping)
    : JSX.Element {
    const varMeasured = seriesList[0].variableMeasured;
    const groups = groupSeriesByLocations(seriesList);
    const groupNames = Object.keys(groups);

    return (
      <details className="stat-var-section" key={varMeasured}>
        <summary>{varMeasured}</summary>
        {
          groupNames.map(
              (groupName) =>
                renderTimeGraph(
                    groups[groupName],
                    groupName,
                    groupNames.length === 1,
                    locationMapping,
                ),
          )
        }
      </details>
    );
  }

  /** Get all locations using the observationAbout property
    * @return {SelectOption[]} a list of unique location objects
    */
  private async getAllLocations(): Promise<SelectOption[]> {
    // Get an array of unique locations
    const seenLocations = new Set<string>();
    const locations: string[] = [];
    for (const series of this.props.data) {
      const location = series.observationAbout;
      if (!seenLocations.has(location)) {
        locations.push(location);
      }
    }

    const labelPromises = locations.map(async (location) => {
      const label =
      (location.startsWith('dcid:') ?
        await getName(location.slice(5)) :
        await getName(location)
      );
      return label;
    });

    return Promise.all(labelPromises).then(
        (labels) => {
          return locations.map((location, i) => {
            return {
              value: location,
              label: labels[i],
            };
          });
        },
    );
  }

  /** Renders the TimelineExplorer component.
    * @return {JSX.Element} the component using TSX code
    */
  render(): JSX.Element | null {
    if (this.props.data.length === 0) {
      return null;
    }
    const defaultValue = this.state.locationOptions.filter(
        (option: SelectOption) => this.state.locations.includes(option.value),
    );
    const maxPage = Math.ceil(
        this.state.statVarGroups.length / STAT_VARS_PER_PAGE,
    );
    const switchPage = (page: number) => this.setState({page});
    return (
      <div className="box">
        {/* display loading animation while waiting*/}
        <LoadingSpinner loading={this.props.loading} msg="...loading mcf..." />
        <h3>Timeline Explorer</h3>
        <div id="location-select-box">
          <div id="location-select-row">
            <span>Select location(s): </span>
            <div id="location-buttons">
              <button
                className="button"
                onClick={() => {
                  this.setState(() => {
                    const locations = this.state.locationOptions.map(
                        (option: SelectOption) => option.value,
                    );
                    const selectKey = locations.join(',');
                    const page = 0;
                    return {
                      locations,
                      selectKey,
                      page,
                    };
                  });
                }}
              >Select All</button>
              <button
                className="button"
                onClick={() => {
                  this.setState({
                    locations: [],
                    selectKey: '',
                    page: 0,
                  });
                }}
              >Clear All</button>
            </div>
          </div>

          <Select
            isMulti
            name="colors"
            options={this.state.locationOptions}
            defaultValue={defaultValue}
            value={defaultValue}
            onChange={(values: MultiValue<SelectOption>) => {
              const locations = values.map((value) => value.value);
              this.setState(
                  {
                    locations,
                    statVarGroups: Object.values(
                        this.getVariableToSeries(locations),
                    ) as Series[][],
                    page: 0,
                  },
              );
            }
            }
            key={this.state.selectKey}
          />
        </div>

        <div id="stat-var-row">
          <span>Variables</span>
          <div id="stat-var-buttons">
            <button
              className="button"
              onClick={
                () => {
                  document.querySelectorAll('details.stat-var-section')
                      .forEach((section) => section.setAttribute('open', ''));
                }
              }
            >Expand All</button>
            <button
              className="button"
              onClick={
                () => {
                  document.querySelectorAll('details.stat-var-section')
                      .forEach((section) => section.removeAttribute('open'));
                }
              }
            >Collapse All</button>
          </div>
        </div>
        {this.state.statVarGroups
            .slice(
                this.state.page * STAT_VARS_PER_PAGE,
                (this.state.page + 1) * STAT_VARS_PER_PAGE,
            ).map(
                (seriesList) =>
                  this.renderSeriesGroup(
                      seriesList, this.state.locationMapping),
            )}
        <PageBar
          page={this.state.page}
          maxPage={maxPage}
          onNextPageClicked={
            (currPage: number, maxPage: number) => {
              switchPage(PageBar.getNextPage(currPage, maxPage));
            }
          }
          onPrevPageClicked={
            (currPage: number) => {
              switchPage(PageBar.getPrevPage(currPage));
            }
          }
          onPageNumClicked={
            (newPage: number) => {
              switchPage(newPage - 1);
            }
          }
        />
      </div>
    );
  }
}

export {TimelineExplorer};

export type {LocationMapping};
