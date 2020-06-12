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
import {calculate} from "./DataCalculator";
import ContentFile from "./ContentFile.json";
import EmptyPanel from "./EmptyPanel";
import {getRangeOfDates} from "./Utils";
import Graph from "./Graph";
import generateGraphMetadata from "./MetaDataGenerator";

type Props = {
    allData: any[],
    label: string,
    region: string,
    datePicked: string,
    selectedShowTopN: number,
    panelId: string
}
type DateToGeoIdToValue = {date: {geoId: number}} | {}

export default function Panel(props: Props) {
    const content = ContentFile[props.panelId]
    const deltaDays: number = content.deltaDays

    // Is it cases or deaths?
    const inputData: DateToGeoIdToValue = props.label === 'cases' ? props.allData[0] : props.allData[1]
    const geoIdToPopulation: {geoId: number} = props.allData[2]
    const geoIdToName: {geoId: string} = props.allData[3]
    const rangeOfDates: [string, string] = getRangeOfDates(props.datePicked, deltaDays)

    // Calculate per-capita.
    const calculatedData: DateToGeoIdToValue = calculate(inputData, rangeOfDates, deltaDays, content.dataType, geoIdToPopulation)

    let absoluteIncrease: DateToGeoIdToValue = {}
    if (content.dataType=== 'increase') {
        // If the graph is a percent-increase graph, we also want to show the absolute increase.
        absoluteIncrease = calculate(inputData, rangeOfDates, deltaDays, 'difference', geoIdToPopulation);
    }


    // Generate the metadata for the graph (on-hover, bar text, region names)
    const metadata = generateGraphMetadata(calculatedData, geoIdToPopulation,
        geoIdToName, absoluteIncrease, props.label, content.dataType)


    // If there is data available
    if (Object.keys(inputData).length) {
        return (
            <div className={"panel chart shadow"}>
                <h4 className={"title"}>{content?.title.replace("{TYPE}",
                    props.label[0].toUpperCase() + props.label.slice(1, props.label.length))}</h4>
                <h6 className={"title"}>{content?.subtitle.replace("{TYPE}",
                    props.label[0].toUpperCase() + props.label.slice(1, props.label.length))}</h6>
                <Graph label={props.label}
                       data={calculatedData}
                       selectedShowTopN={props.selectedShowTopN}
                       type={content['graphType']}
                       color={props.label === 'cases' ? '#990001' : 'grey'}
                       metadata={metadata}/>
            </div>
        )
    } else {
        return (<EmptyPanel reason={Object.keys(inputData).length === 0 ? 'loading' : 'nan'}/>)
    }
}