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
import IsoDate from "./IsoDate";

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
   * In charge of displaying the tooltip on-hover on the chart.
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

  const data = Object.entries(inputData).map(obj => {
    const date = new IsoDate(obj[0]).format("MMM D")
    return {
      xAxisLabel: date,
      date: obj[0],
      value: obj[1]
    }
  })

  if (data.every(item => item.value === 0)) {
    return <div>
    </div>
  }

  const sortedData = sortBy(data, ['date'])

  let value: string;
  if (props.value < 1) {
    value = props.value.toFixed(1)
  } else {
    const roundedValue = Math.round(props.value)
    value = numberWithCommas(roundedValue)
  }


  const color = Colors(props.color || "#990001")
  const width = props.width || 125
  const height = props.height || 60
  const showAxis = props.showAxis
  const interval = Math.round(sortedData.length / 5)

  return (
    <div className={"line-graph"} style={{width: width}}>
      {value &&
      <h6 className={"value"}
          style={{color: color}}>
        {value}
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
        <XAxis tick={{ill: color, fontSize: 12}}
               dataKey={"xAxisLabel"}
               interval={interval}
               hide={!showAxis}/>
        <YAxis type={"number"}
               tick={{ill: color, fontSize: 12}}
               hide={!showAxis}/>
      </AreaChart>
    </div>
  )
}