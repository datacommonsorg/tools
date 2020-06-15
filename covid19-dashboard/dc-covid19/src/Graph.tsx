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
import BarGraph from "./BarGraph";
import LineGraph from "./LineGraph";

type DateToGeoIdToValue = {string: {string: number}} | {}

type Metadata = {
    name: string,
    onHoverInfo: string[]
    textOnTopOfBar: string,
    value?: number,
    geoId?: string
}

type Props = {
    label: string
    data: DateToGeoIdToValue,
    metadata?: {date: {geoId: Metadata}} | {},
    type: 'bar' | 'line',
    selectedShowTopN: number,
    color: string
}

export default function Graph(props: Props) {
    let data: {} = {}

    for (let date in props.data){
        let dataForIterativeDate = {}
        for (let geoId in props.data[date]){
            const value: number = props.data[date][geoId] || 0
            const metadata: Metadata = props.metadata?.[date]?.[geoId] || {}

            dataForIterativeDate[geoId] = {
                geoId: geoId,
                value: value,
                name: metadata?.name || geoId,
                onHoverInfo: metadata?.onHoverInfo || [],
                textOnTopOfBar: metadata?.textOnTopOfBar || String(value)
            }
        }
        data[date] = dataForIterativeDate
    }

    if (props.type === 'line') {
        return (
            <LineGraph
                label={props.label}
                data={data}
                selectedShowTopN={props.selectedShowTopN}
                color={props.color}
                metadata={props.metadata}/>)
    } else {
        return (
            <BarGraph
                label={props.label}
                data={data}
                selectedShowTopN={props.selectedShowTopN}
                color={props.color}
                metadata={props.metadata}/>)
    }
}