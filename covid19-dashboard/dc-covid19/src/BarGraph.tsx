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
type dataPerGeoIdPerDate = {string: {string: number}} | {}

type Props = {
    data: dataPerGeoIdPerDate,
    label: string,
    selectedShowTopN: number,
    color: string
}

export default function BarGraph(props: Props) {
    const datesInData = Object.keys(props.data)
    let dataAsArray: {value: number, dcid: string}[] = []

    // If there is data, then convert it to an array, otherwise dataAsArray will be empty [].
    if (datesInData.length) {
        // Get the most recent date of the data, that's the only one we care about (for now).
        const dataForMostRecentDate: {string: number} = props.data[datesInData[datesInData.length - 1]]
        dataAsArray = Object.keys(dataForMostRecentDate).map(geoId =>
        {return {value: dataForMostRecentDate[geoId], dcid: geoId}}).splice(0, props.selectedShowTopN)
    }

    /**
     * In charge of displaying the tooltip on-hover on the chart.
     * @param active
     * @param payload
     */
    const customTooltip = ({active, payload}) => {
        let tooltipType: string = "normal"
        // Make sure that the current bar is actively being hovered on.
        if (active) {
            const data = payload[0].payload
            if (data.absolute && data.population) {
                tooltipType = "perCapita"
            } else if (data.absolute && !data.population) {
                tooltipType = "percent"
            }
            return <ToolTip data={data} type={tooltipType} label={props.label}/>
        }
        return null;
    };

    /**
     * Function triggered when each bar in the cart is clicked.
     * Opens a new tab and takes the user to GNI.
     * @param {dcid}: the dcid that represents the bar
     */
    let barOnClick = ({dcid}) => {
        const URL: string = `https://browser.datacommons.org/gni#&place=${dcid}&ptpv=MedicalConditionIncident,cumulativeCount,medicalStatus,ConfirmedOrProbableCase,incidentType,COVID_19__MedicalConditionIncident,cumulativeCount,medicalStatus,PatientDeceased,incidentType,COVID_19&pc=1`
        window.open(URL, '_blank');
    }

    /**
     * Function in charge of displaying the labeListLabel string stored in each dataHolder point.
     * @param metadata: contains data about the bar in the chart as well as the value to print out
     */
    let renderCustomizedLabel = (metadata) => {
        const {x, y, width, height, value} = metadata;
        return (
            <g>
                <text fontSize={10}
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
    const graphWidth = 410 // pixels
    const individualBarWidth = 18 // pixels
    return (
        <BarChart width={graphWidth}
                  height={graphHeight}
                  data={dataAsArray}
                  barSize={individualBarWidth}
                  layout="vertical">
                        <XAxis type="number"
                               tick={{fill: '#868E96', fontSize: 10}}
                               interval={0}/>
                        <YAxis type="category"
                               dataKey="regionName"
                               tick={{ill: '#868e96', fontSize: 10}}
                               width={90}
                               interval={0}/>
                        <Tooltip content={customTooltip}/>
                        <Bar dataKey={"value"}
                             fill={props.color}
                             onClick={barOnClick}
                             radius={[4, 4, 4, 4]}>
                            <LabelList dataKey={"labelListLabel"}
                                       content={renderCustomizedLabel}/>
                        </Bar>
        </BarChart>
    );
}
