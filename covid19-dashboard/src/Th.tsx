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


import {TimeSeriesType} from "./Types";
import LineGraph from "./LineGraph";
import React from "react";
import {Colors} from './Utils'

type ThPropsType = {
  timeSeries: TimeSeriesType,
  typeOf: string,
  className: string,
  graphTitle?: string,
  graphSubtitle?: string
  color?: string
}

/**
 * Displays a value in the Table.
 * @param props.timeSeries: the timeSeries being observed.
 * @param props.typeOf: type of Th to display.
 * @param props.className: className to overwrite style.
 * @param props.graphTitle: if it's a graph, it must contain a title.
 * @param props.graphSubtitle: if it's a graph, it may contain a subtitle.
 * @param props.color: what should the color be? grey by default.
 */
export default (props: ThPropsType) => {
  const timeSeries = props.timeSeries // the timeSeries being observed.
  const dates = Object.keys(timeSeries)
  const latestDate = dates[dates.length - 1]
  const value = timeSeries[latestDate] as number // the value to display
  const color = props.color ? Colors(props.color) : Colors('grey')

  // Depending on the type of Th, display different th.
  // Numbers should be rounded, but not strings.
  if (props.typeOf === 'lineGraph') {
    return (
      <th>
        <LineGraph
          data={timeSeries}
          className={props.className}
          title={props.graphTitle}
          subtitle={props.graphSubtitle}
          color={color}
          value={value}/>
      </th>
    )
  } else if (props.typeOf === 'number' && value) {
    return <th>{value?.toFixed(2)}</th>
  } else if (props.typeOf === 'percent' && value) {
    return <th>{value?.toFixed(2) + "%"}</th>
  } else {
    return <th>{'~'}</th>
  }
}