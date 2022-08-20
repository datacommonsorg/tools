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
import {Line} from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';

import {Series} from './back-end/time-series';

const COLORS = [
  '#bcf60c',
  '#fabebe',
  '#008080',
  '#e6beff',
  '#9a6324',
  '#fffac8',
  '#800000',
  '#aaffc3',
  '#e6194b',
  '#3cb44b',
  '#ffe119',
  '#4363d8',
  '#f58231',
  '#911eb4',
  '#46f0f0',
  '#f032e6',
  '#808000',
  '#ffd8b1',
  '#000075',
  '#808080',
  '#d37295',
  '#000000',
];

ChartJS.register(
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    Title,
    Tooltip,
    Legend,
);

 interface TimeGraphPropType {
   /**
    * Passes the data to be plotted
    */
   data: Series[];

   /**
    * The title of the graph
    */
   title: string;

   /** A mapping from a location dcid to its name */
   locationMapping: Object;
 }

 interface TimeGraphStateType {
   /** The lineData for the Line graph component */
   lineData: any;

   /** The lineOptions for the Line graph component */
   lineOptions: Object;
 }

/** Component to display a single graph */
class TimeGraph extends Component<TimeGraphPropType, TimeGraphStateType> {
  /** Constructor for class, sets initial state
    * @param {Object} props the props passed in by parent component
    */
  constructor(props: TimeGraphPropType) {
    super(props);
    this.state = {
      lineData: {},
      lineOptions: {},
    };
  }

  /** Sets lineData and lineOptions when rendering */
  componentDidMount() {
    const lineOptions = this.getOptions();
    this.getLineData().then(
        (lineData) => this.setState(
            {
              lineData,
              lineOptions,
            },
        ),
    );
  }

  /** Returns a new set of data where each series
    * has the same x-values (the union of all x-values)
    * @return {Series[]} an array of the data where missing values
    * are filled with undefined
    */
  getUnionData() {
    const data = [];

    // Get union of x-values
    const allXSet: Set<string> = new Set();
    for (const series of this.props.data) {
      for (const datapoint of series.data) {
        allXSet.add(datapoint.x);
      }
    }

    // Get sorted x-values
    const allX = [...allXSet];
    allX.sort();

    // Fill in missing values for each Series
    for (const series of this.props.data) {
      const seriesData: any = {};
      for (const datapoint of series.data) {
        seriesData[datapoint.x] = datapoint.y;
      }

      // Make a copy to use
      const newSeries = series.copy();

      // Update with new x,y values
      const newData = allX.map((x) => {
        return {
          x,
          y: seriesData[x],
        };
      });
      newSeries.data = newData;

      data.push(newSeries);
    }

    return data;
  }

  /**
    * Generates the data object necessary for the Line component
    * @return {Object} the data object to be used a prop for Line
    */
  async getLineData() {
    // Change series to have union of all x-values
    // Also sorts the data in the process
    const data = this.getUnionData();

    // Get object per series
    const labels = data[0].data.map((datapoint) => datapoint.x);
    const datasets = data.map((series, i) => {
      const labelID =
         series.observationAbout ? series.observationAbout : 'undefined';
      const label = (this.props.locationMapping as any)[labelID];
      return {
        label: label,
        fill: false,
        data: series.data.map((datapoint) => datapoint.y),
        borderColor: COLORS[i % COLORS.length],
      };
    });

    return {labels, datasets};
  }

  /**
    * Generate the graph's options
    * @return {Object} the options for the graph
    */
  getOptions() {
    return {
      interaction: {
        intersect: false,
      },
      scales: {
        x: {
          grid: {
            display: false,
          },
        },
      },
      plugins: {
        legend: {
          display: true,
          labels: {
            font: {
              size: 12,
            },
          },
        },
        title: {
          display: true,
          text: this.props.title,
        },
      },
    };
  }

  /** Renders the TimeGraph component.
    * @return {Object} the component using TSX code
    */
  render() {
    if (Object.keys(this.state.lineData).length == 0) {
      return null;
    }
    return (
      <div className='graph'>
        <Line data={this.state.lineData}
          options={this.state.lineOptions} />
      </div>
    );
  }
}

export {TimeGraph};
