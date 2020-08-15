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

import React from "react";
import {Tooltip, XAxis, YAxis, AreaChart, Area} from 'recharts';
import sortBy from 'lodash/sortBy'
import {numberWithCommas, Colors} from "./Utils";
import dayjs from "dayjs";

type LineGraphPropsType = {
  data: {[date: string]: number},
  value: number,
  width?: number,
  height?: number,
  color?: string,
  title?: string,
  subtitle?: string,
  showAxis?: boolean,
  className?: string
}

/**
 * @param props.data: the timeSeries to display
 * @param props.value: the value to display on top of the graph.
 * @param props.width: the width of the graph.
 * @param props.height: the height of the graph.
 * @param props.color: the color of the graph and text.
 * @param props.title: the graph's title, on-hover.
 * @param props.subtitle: the graph's subtitle, on-hover.
 * @param props.showAxis: should the X and Y axis be displayed?
 * @param props.className: a className that overrides the graph's.
 */
export default function LineGraph(props: LineGraphPropsType) {
  /**
   * Displays a larger LineGraph when hovering on a small LineGraph.
   */
  const customTooltip = ({active}: {active: boolean}) => {
    // Make sure that the current bar is actively being hovered on.
    if (active) {
      return (
        <div className={"pop-up shadow"}>
          <h6 className={"title"}>
            {props.title}
          </h6>
          <h6 className={"title"}
              style={{color: Colors('grey')}}>
            {props.subtitle}
          </h6>
          <LineGraph data={props.data}
                     className={props.className}
                     width={400}
                     height={200}
                     color={props.color}
                     showAxis={true}
                     value={props.value}/>
        </div>
      )
    }
    return null;
  };

  const inputData = props.data || {}

  // Convert the data to a list of objects that the graph can understand.
  const data = Object.entries(inputData).map(([date, value ]) => {
    // Prettify the date.
    const prettyDate = dayjs(date).format("MMM D")
    return {
      // The label to display on graph.
      xAxisLabel: prettyDate,
      // Real iso formatted date.
      date: date,
      // The number for that given date.
      value: value
    }
  })

  // If every value in timeSeries are 0, don't return anything.
  if (data.every(item => item.value === 0)) {
    return <></>
  }

  // Sort the data by date.
  const sortedData = sortBy(data, ['date'])

  // If value is a decimal, round to 1 significant digit.
  // Otherwise, round to the nearest whole number.
  let graphValue: string;
  if (props.value < 1) {
    graphValue = props.value.toFixed(1)
  } else {
    const roundedValue = Math.round(props.value)
    graphValue = numberWithCommas(roundedValue)
  }


  // Color of the graph.
  const color = Colors(props.color || "--dc-red-strong")
  // Width of the graph.
  const width = props.width || 125
  // Height of the graph.
  const height = props.height || 60
  // Should the Y and X axis be shown?
  const showAxis = props.showAxis
  // Only show axis every n-"interval" dates.
  // Looks cleaner.
  const interval = Math.round(sortedData.length / 5)
  // The style of the X-Axis and Y-Axis.
  const axisStyle = {ill: color, fontSize: 12}

  return (
    <div className={"line-graph"}
         style={{width: width}}>
      {graphValue &&
      <h6 className={"value"}
          style={{color: color}}>
        {graphValue}
      </h6>}
      <AreaChart className={"graph " + props.className}
                 width={width}
                 height={height}
                 data={sortedData}>
        <Area type="monotone"
              dataKey="value"
              stroke={color}
              fillOpacity={0.4}
              animationDuration={500}
              fill={color}/>
        <Tooltip position={{y: -170, x: -170}}
                 wrapperStyle={{zIndex: 1000}}
                 content={customTooltip}/>
        <XAxis tick={axisStyle}
               dataKey={"xAxisLabel"}
               interval={interval}
               hide={!showAxis}/>
        <YAxis type={"number"}
               tick={axisStyle}
               hide={!showAxis}/>
      </AreaChart>
    </div>
  )
}