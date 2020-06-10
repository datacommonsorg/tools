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
import {absolute, difference, perCapita, increase} from "./DataCalculator";
import ContentFile from "./ContentFile.json";
import EmptyPanel from "./EmptyPanel";
import BarGraph from "./BarGraph";
import {getRangeOfDates} from "./Utils";

type Props = {
    data: any[],
    label: string,
    region: string,
    datePicked: string,
    selectedShowTopN: number,
    panelId: string
}
type DataPerGeoIdPerDate = {string: {string: number}} | {}

export default function Panel(props: Props) {
    let data: DataPerGeoIdPerDate = {}
    const content = ContentFile[props.panelId]
    const deltaDays: number = content.deltaDays

    // Is it cases or deaths?
    const inputData: DataPerGeoIdPerDate = props.label === 'cases' ? props.data[0] : props.data[1]
    const geoIdToPopulation: {string: number} = props.data[2]
    const rangeOfDates: [string, string] = getRangeOfDates(props.datePicked, deltaDays)

    // What type of data do we want to calculate? Check the type on the content file
    switch (content.type){
        case 'absolute':
            data = absolute(inputData, rangeOfDates)
            break;
        case 'difference':
            data = difference(inputData, rangeOfDates, deltaDays)
            break;
        case 'perCapita':
            data = perCapita(inputData, rangeOfDates, deltaDays, geoIdToPopulation)
            break;
        case 'increase':
            data = increase(inputData, rangeOfDates, deltaDays)
            break;
    }

    // If there is data available
    if (Object.keys(inputData).length) {
        return (
            <div className={"panel chart shadow"}>
                <h4 className={"title"}>{content?.title.replace("{TYPE}",
                    props.label[0].toUpperCase() + props.label.slice(1, props.label.length))}</h4>
                <h6 className={"title"}>{content?.subtitle.replace("{TYPE}",
                    props.label[0].toUpperCase() + props.label.slice(1, props.label.length))}</h6>
                <BarGraph label={props.label}
                          data={data}
                          region={props.region}
                          selectedShowTopN={props.selectedShowTopN}
                          color={props.label === 'cases' ? '#990001' : 'grey'}/>
            </div>
        )
    } else {
        return (<EmptyPanel reason={Object.keys(inputData).length === 0 ? 'loading' : 'nan'}/>)
    }
}