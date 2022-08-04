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

import {Series} from './back-end/data';
import {TimeGraph} from './TimeGraph';
import {groupLocations} from './utils';
import {LoadingSpinner} from './LoadingSpinner';
import {getName} from './back-end/utils';

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

    /** A list of objects for the select component */
    locationOptions: Object[]

    /** The key for the select component to tell it
     * to re-render when the locations are loaded in
     */
    selectKey: string;
}

/** Component to display the timeline explorer */
class TimelineExplorer extends Component<
  TimelineExplorerPropType,
  TimelineExplorerStateType
> {
  /** Constructor for class, sets initial state
   * @param {Object} props the props passed in by parent component
   */
  constructor(props: TimelineExplorerPropType) {
    super(props);
    this.state = {
      locations: [],
      locationOptions: [],
      selectKey: 'unloaded',
    };
  }

  /** Set the location options
   * @param {TimelineExplorerPropType} prevProps the previous props
  */
  componentDidUpdate(prevProps: TimelineExplorerPropType) {
    if (prevProps.data !== this.props.data) {
      this.getAllLocations().then(
          (locationOptions) => {
            this.setState(() => {
              const locations = locationOptions.slice(0, 5).map(
                  (option) => option.value,
              );
              const selectKey = locations.join(',');
              return {
                locations,
                locationOptions,
                selectKey,
              };
            });
          },
      );
    }
  }

  /** Returns the series objects which match the current locations filter
   * @return {Series[]} series that match the filter
  */
  filterLocations() {
    const locations = new Set(
        this.state.locations.map((location) =>
        (location === 'undefined') ? undefined: location,
        ),
    );

    const filteredData = this.props.data.filter(
        (series) => locations.has(series.observationAbout),
    );

    return filteredData;
  }

  /** Processes the data passed in by props and returns the
   * data grouped by variableMeasured
   * @return {Object} an object mapping from variableMeasured to an array
   * of Series with that variableMeasured value
   */
  groupByVariableMeasured() {
    const output: any = {};
    // Filter by location
    const data = this.filterLocations();

    for (const series of data) {
      const varMeasured = series.variableMeasured ?
        series.variableMeasured :
        '';
      if (!output[varMeasured]) {
        output[varMeasured] = [];
      }
      output[varMeasured] = output[varMeasured].concat([series]);
    }

    return output;
  }

  /** Returns the JSX to render a group of related series
   * @param {Series[]} seriesList a list of series objects with
   *                              the same varMeasured
   * @return {Object} a details element plotting all of the series
  */
  renderSeriesGroup(seriesList: Series[]) {
    const varMeasured = seriesList[0].variableMeasured;
    return (
      <details key={varMeasured}>
        <summary>{varMeasured}</summary>
        {groupLocations(seriesList).map((seriesObj: any) => (
          <TimeGraph
            data={seriesObj.subGroup}
            title={seriesObj.title}
            key={seriesObj.title + '\n' + seriesObj.subGroup.map(
                (series: Series) => series.id,
            ).join(',')}
          />
        ))}
      </details>
    );
  }

  /** Get all locations using the observationAbout property
   * @return {Object[]} a list of unique location objects
   */
  private async getAllLocations() {
    const locationSet = new Set(
        this.props.data.map((series) =>
        series.observationAbout ? series.observationAbout : 'undefined'),
    );

    const locations = [...locationSet];
    const labels = await Promise.all(
        locations.map(async (location) => {
          const label =
        (location.startsWith('dcid:') ?
          await getName(location.slice(5)) :
          location
        );

          return label;
        }),
    );
    console.log(locations);
    return locations.map((location, i) => {
      return {
        value: location,
        label: labels[i],
      };
    });
  }

  /** Renders the TimelineExplorer component.
   * @return {Object} the component using TSX code
   */
  render() {
    if (this.props.data.length === 0) {
      return null;
    }
    console.log(this.props.data);
    console.log(this.state.locationOptions);
    const defaultValue = this.state.locationOptions.filter(
        (option: any) => this.state.locations.includes(option.value),
    );
    return (
      <div className="box">
        {/* display loading animation while waiting*/}
        <LoadingSpinner loading={this.props.loading} msg="...loading mcf..." />

        <h3>Timeline Explorer</h3>

        <div id="locationSelect">
          <p>Select a location:</p>
          <Select
            isMulti
            name="colors"
            options={this.state.locationOptions}
            defaultValue={defaultValue}
            onChange={(values: MultiValue<Object>) =>
              this.setState( (prevState) => {
                return {
                  ...prevState,
                  locations: values.map((value) => (value as any).value),
                };
              },
              )}
            key={this.state.selectKey}
          />
        </div>

        {(Object.values(this.groupByVariableMeasured()) as Series[][]).map(
            this.renderSeriesGroup,
        )}
      </div>
    );
  }
}

export {TimelineExplorer};
