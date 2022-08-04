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

  /** Tracks when component is mounted */
  componentDidMount() {
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

  /** Set the location options
   * @param {TimelineExplorerPropType} prevProps the previous props
  */
  componentDidUpdate(prevProps: TimelineExplorerPropType) {
    if (prevProps.data !== this.props.data) {
      this.componentDidMount();
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
    const groups = groupLocations(seriesList);
    const groupNames = Object.keys(groups);

    const plotSeriesObj = (seriesObj: any) => {
      return (<TimeGraph
        data={seriesObj.subGroup}
        title={seriesObj.title}
        key={seriesObj.title + '\n' + seriesObj.subGroup.map(
            (series: Series) => series.id,
        ).join(',')}
      />);
    };
    const renderTimeGraph = (groupName: string, keepOpen: boolean) => {
      const facets: any = Series.fromID(groupName);
      return (
        <details key={groupName} open={keepOpen}>
          <summary>{groupName}</summary>
          {Object.keys(facets).map((facet) => {
            return (
              facets[facet] ?
              <p className='facet' key={facet}>{facet}: {facets[facet]}</p> :
              null
            );
          })}
          {groups[groupName].map(plotSeriesObj)}
        </details>
      );
    };
    return (
      <details className="stat-var-section" key={varMeasured}>
        <summary>{varMeasured}</summary>
        {
          groupNames.map(
              (groupName) =>
                renderTimeGraph(groupName, groupNames.length === 1),
          )
        }
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
    const defaultValue = this.state.locationOptions.filter(
        (option: any) => this.state.locations.includes(option.value),
    );
    return (
      <div className="box">
        {/* display loading animation while waiting*/}
        <LoadingSpinner loading={this.props.loading} msg="...loading mcf..." />

        <h3>Timeline Explorer</h3>

        <div id="location-select">
          <div>
            <span>Select location(s): </span>
            {/* <div id="locationButtons">
              <button>Select All</button>
              <button>Clear All</button>
            </div> */}
          </div>

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

        <div>
          <button
            className="stat-var-buttons"
            onClick={
              () => {
                document.querySelectorAll('details.stat-var-section')
                    .forEach((section) => section.setAttribute('open', ''));
              }
            }
          >Expand All</button>
          <button
            className="stat-var-buttons"
            onClick={
              () => {
                document.querySelectorAll('details.stat-var-section')
                    .forEach((section) => section.removeAttribute('open'));
              }
            }
          >Collapse All</button>
        </div>

        {(Object.values(this.groupByVariableMeasured()) as Series[][]).map(
            this.renderSeriesGroup,
        )}
      </div>
    );
  }
}

export {TimelineExplorer};
