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

import {Series} from './back-end/data';
import {TimeGraph} from './TimeGraph';

interface TimelineExplorerPropType {
  /**
   * Passes the data to be plotted
   */
  data: Series[];
}

/** Component to display the timeline explorer */
class TimelineExplorer extends Component<
  TimelineExplorerPropType
> {
  /** Constructor for class, sets initial state
   * @param {Object} props the props passed in by parent component
   */
  constructor(props: TimelineExplorerPropType) {
    super(props);
    this.state = {};
  }

  /** Processes the data passed in by props and returns the
   * data grouped by variableMeasured
   * @return {Object} an object mapping from variableMeasured to an array
   * of Series with that variableMeasured value
   */
  groupByVariableMeasured() {
    const output: any = {};
    for (const series of this.props.data) {
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
      <details>
        <summary>{varMeasured}</summary>
        {seriesList.map((series) => (
          <TimeGraph data={[series]} key={varMeasured}/>
        ))}
      </details>
    );
  }

  /** Renders the TimelineExplorer component.
   * @return {Object} the component using TSX code
   */
  render() {
    if (this.props.data.length === 0) {
      return null;
    }
    return (
      <div className="box">
        <h3>Timeline Explorer</h3>
        {(Object.values(this.groupByVariableMeasured()) as Series[][]).map(
            this.renderSeriesGroup,
        )}
      </div>
    );
  }
}

export {TimelineExplorer};
