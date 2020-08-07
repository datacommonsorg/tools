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
import orderBy from 'lodash/orderBy';
import chunk from 'lodash/chunk';
import Content from './Content.json';
import {TimeSeriesType, ValueType} from './Types';
import Configuration from './Config.json';
import Table from 'react-bootstrap/Table';
import Th from './Th';
import TableIndexPagination from './TableIndexPagination';

type OrientationType = 'desc' | 'asc';

type TableStateType = {
  sortBy: string;
  order: OrientationType;
  chunkIndex: number;
};

type TablePropsType = {
  data: ValueType[];
};

/**
 * The data table with all the essential information.
 * @var state.sortBy: the default sortBy category.
 * @var state.order: display data ascending or descending order
 * @var state.chunkIndex: what chunk of data to display.
 * @param props.data: an object where each key is a geoId
 * and each value contains different timeSeries .
 * The table is divided into pages.
 */
export default class DataTable extends React.Component<
  TablePropsType,
  TableStateType
  > {
  state = {
    sortBy: Configuration.tableDefaultSortBy,
    order: 'desc' as OrientationType,
    chunkIndex: 0,
  };

  chunkSize = 30;
  chunkedData: ValueType[][] = [];

  /**
   * Determines what type of arrow display
   * next to the table's header/category. Or whether none at all.
   * @param sortBy: the observed header/category.
   */
  sortArrow(sortBy: string) {
    // If the input sortBy is the same as the state's sortBy,
    // it means we are actively sorting by that header.
    const active = sortBy === this.state.sortBy;

    if (!active) {
      return '';
    } else if (this.state.order === 'desc') {
      return '▼ ';
    } else if (this.state.order === 'asc') {
      return '▲ ';
    }
  }

  /**
   * When triggered, the current sorting orientation will be changed
   * to the opposite orientation.
   */
  changeOrientation = () => {
    // From ascending to descending.
    // From descending to ascending.
    const opposites = {asc: 'desc', desc: 'asc'};

    // Change the current orientation the opposite orientation.
    const newOrientation = opposites[this.state.order] as OrientationType;
    this.setState({
      order: newOrientation,
    });
  };

  /**
   * When tapping on the header, if the sortBy is already active,
   * then change the orientation, otherwise, change the sortBy
   * to the newly selected header.
   * @param sortBy: the header/category to sort the table by.
   */
  sortBy(sortBy: string) {
    const active = this.state.sortBy === sortBy;

    if (active) {
      this.changeOrientation();
    } else {
      this.setState({sortBy: sortBy});
    }

    // Go back to the first page in the table.
    this.setState({chunkIndex: 0});
  }

  /**
   * Go to a specific page index in the table.
   * @param chunkIndex: the index to navigate to.
   * Corresponds to the table's page - 1.
   */
  setChunkIndex = (chunkIndex: number) => {
    // Make sure our table doesn't go out of boundaries.
    if (chunkIndex >= 0 && chunkIndex < this.chunkedData.length) {
      this.setState({chunkIndex: chunkIndex});
    }
  };

  render() {
    // Every time the order or sortBy is changed,
    // we have to recalculate the new value.
    // Sort the time-series by the latest date.
    // Our value is what we use to sort by.
    const dataByKey: ValueType[] = this.props.data.map(obj => {
      const timeSeries: TimeSeriesType = obj[this.state.sortBy] || {};
      // Get the latest date in the timeSeries.
      const dates = Object.keys(timeSeries);
      const latestDate = dates[dates.length - 1];
      // Store the value for the latest date.
      const value = timeSeries[latestDate];

      return {
        ...obj,
        timeSeries: timeSeries,
        value: value,
      };
    });

    // Filter out any undefined values or timeSeries.
    const filteredData = dataByKey.filter(obj => {
      return obj.value && obj.timeSeries;
    });

    // Sort the data by the value property.
    // Value represents the number of selected sortBy on the given date.
    const sortedData = orderBy(filteredData, ['value'], [this.state.order]);

    // Chunk the dataset by groups of this.chunkSize.
    // Each element in the chunk represents a row.
    // Each chunk contains this.chunkSize rows.
    this.chunkedData = chunk(sortedData, this.chunkSize);

    // Depending on what page of the table the user is on, display that chunk.
    // Example: If the user is on page 1, display this.chunkedData[0].
    const chunkDataShown = this.chunkedData?.[this.state.chunkIndex] || [];

    // Get the header names from Content.json
    // When the header is clicked, change the sorting.
    const tableHeaders = Content.table.map((obj, index) => {
      // Should the title have an arrow?
      const title = this.sortArrow(obj.id) + obj.title;
      return (
        <th onClick={() => this.sortBy(obj.id)} key={index}>
          {title}
        </th>
      );
    });

    // Create the data for each row.
    const rows = chunkDataShown.map((rowData, index) => {
      const tableRanking = this.state.chunkIndex * this.chunkSize + index + 1;
      const clickableClass = rowData.onClick ? 'clickable' : '';

      // For every row, generate a Th for each column.
      const thValues = Content.table.map((category, index) => {
        // Get the timeSeries for our current column's id.
        const timeSeries: TimeSeriesType = rowData[category.id] || {};
        return (
          <Th
            timeSeries={timeSeries}
            typeOf={category.typeOf}
            key={index}
            className={clickableClass}
            graphTitle={rowData.name}
            graphSubtitle={category.graphSubtitle}
            color={category.color}
          />
        );
      });

      return (
        <tbody key={index}>
        <tr key={index} className={clickableClass} onClick={rowData.onClick}>
          <th>{tableRanking}</th>
          <th>{rowData.name}</th>
          {thValues}
        </tr>
        </tbody>
      );
    });

    return (
      <>
        <Table responsive="l">
          <thead>
          <tr>
            <th>#</th>
            <th>Name</th>
            {tableHeaders}
          </tr>
          </thead>
          {rows}
        </Table>
        <TableIndexPagination
          index={this.state.chunkIndex}
          totalIndexCount={this.chunkedData.length}
          onIndexChange={this.setChunkIndex}
        />
      </>
    );
  }
}
