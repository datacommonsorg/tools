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
import {Bar, BarChart, LabelList, Tooltip, XAxis, YAxis} from 'recharts'
import ToolTip from "./ToolTip";

type Props = {
    data: {date: {geoId: Metadata}} | {},
    label: string,
    selectedShowTopN: number,
    color: string
}

type Metadata = {
    name?: string,
    onHoverInfo?: string[]
    textOnTopOfBar?: string,
    value: number,
    geoId?: string
}

export default function BarGraph(props: Props) {
    const datesInData: string[] = Object.keys(props.data)
    let dataAsArray: Metadata[] = []

    // If there is data, then convert it to an array, otherwise dataAsArray will be empty [].
    if (datesInData.length) {
        // Get the most recent date of the data, that's the only one we care about (for now).
        const dataForMostRecentDate: {string: number} = props.data[datesInData[0]]
        dataAsArray = Object.keys(dataForMostRecentDate).map(geoId => dataForMostRecentDate[geoId])
    }

    // Sort the data in ascending order by value.
    dataAsArray.sort((a, b) => b.value - a.value)
    // Only store the first N elements.
    dataAsArray = dataAsArray.slice(0, props.selectedShowTopN)
    // Get rid of any values less than or equal to 0.
    dataAsArray = dataAsArray.filter(point => point.value > 0)

    /**
     * In charge of displaying the tooltip on-hover on the chart.
     * @param active
     * @param payload
     */
    const customTooltip = ({active, payload}) => {
        // Make sure that the current bar is actively being hovered on.
        if (active) {
            const onHoverInfo: string[] = payload[0].payload.onHoverInfo
            return (<ToolTip text={onHoverInfo}/>)
        }
        return null;
    };

    /**
     * Function triggered when each bar in the cart is clicked.
     * Opens a new tab and takes the user to GNI.
     * @param dcid: the dcid that represents the bar
     */
    let barOnClick = ({geoId}) => {
        if (!geoId) return
        const URL: string = `https://browser.datacommons.org/gni#&place=${geoId}&ptpv=MedicalConditionIncident,cumulativeCount,medicalStatus,ConfirmedOrProbableCase,incidentType,COVID_19__MedicalConditionIncident,cumulativeCount,medicalStatus,PatientDeceased,incidentType,COVID_19&pc=1`
        window.open(URL, '_blank');
    }

    /**
     * Function in charge of displaying the labeListLabel string stored in each dataHolder point.
     * @param customizedLabelData: contains data about the bar in the chart as well as the value to print out.
     */
    let renderCustomizedLabel = (customizedLabelData) => {
        const {x, y, width, height, value} = customizedLabelData;
        return (
            <g>
                <text fontSize={11}
                      x={x + width / 2}
                      y={y + height / 2}
                      fill="#fff"
                      textAnchor="middle"
                      dominantBaseline="middle">
                    {value}
                </text>
            </g>
        );
    };

    // If there are only 2 or less data points in the chart, each bar will have 70px of space.
    // If there are more than two points, each bar will have 50px of space.
    // NOTE: this is done because whe the bar graph has less than 2 points, the chart doesn't look good.
    // This is a workaround to fix the height of the chart.
    const graphHeight = dataAsArray.length <= 2 ? 70 * dataAsArray.length : 50 * dataAsArray.length // pixels
    const graphWidth = 400 // pixels
    const individualBarWidth = 18 // pixels
    const tick = {fill: '#868E96', fontSize: 11} // style for x-axis and y-axis labels
    return (
        <BarChart width={graphWidth}
                  height={graphHeight}
                  data={dataAsArray}
                  barSize={individualBarWidth}
                  layout="vertical">
                    <XAxis type="number"
                           tick={false}
                           interval={0}
                           domain={[dataMin => (dataMin / 5), dataMax => (dataMax)]}/>
                    <YAxis type="category"
                           dataKey="name"
                           tick={tick}
                           width={100}
                           interval={0}/>
            <Tooltip content={customTooltip}/>
            <Bar dataKey={"value"}
                 fill={props.color}
                 onClick={barOnClick}
                 radius={[4, 4, 4, 4]} isAnimationActive={false}>
                <LabelList dataKey={"textOnTopOfBar"}
                           content={renderCustomizedLabel}/>
            </Bar>
        </BarChart>
    )
}
