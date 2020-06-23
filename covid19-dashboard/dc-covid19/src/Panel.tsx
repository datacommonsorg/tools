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
import ContentFile from "./ContentFile.json";
import EmptyPanel from "./EmptyPanel";
import {addOrSubtractNDaysToDate, getRangeOfDates} from "./Utils";
import Graph from "./Graph";
import moment from "moment";
import calculate from "./DataCalculator";
import generateMetadata from "./MetadataGenerator";


type Props = {
    allData: any[],
    region: string,
    datePicked: string,
    selectedShowTopN: number,
    panelId: string
}

type Metadata = {
    geoId: string,
    name: string,
    onHoverInfo: string[]
    textOnTopOfBar: string,
    value: number
}

type DateToGeoIdToValue = {[date: string]: {geoId: number}} | {}
type DateToGeoIdToMetadata = {[date: string]: {geoId: number}} | {}

export default function Panel(props: Props) {
    const content = ContentFile[props.panelId]
    const label: string = content.label || "cases"
    const deltaDays: number = content.deltaDays || 0
    const calculationType: string = content.calculationType || "absolute"

    // inputData is different for cases or deaths.
    const inputData: DateToGeoIdToValue = label === 'cases' ? props.allData[0] : props.allData[1]
    const geoIdToPopulation: {[geoId: string]: number} = props.allData[2]
    const geoIdToName: {[geoId: string]: string} = props.allData[3]
    const rangeOfDates = getRangeOfDates(props.datePicked, deltaDays)

    // These variables are updated on iteration, hence why "let" is used
    let [date0, date1] = [moment(rangeOfDates[0]), moment(rangeOfDates[1])]
    let calculatedData: DateToGeoIdToValue = {}
    let dateToGeoIdToAbsolute: DateToGeoIdToValue = {}

    // From date0 to date1, do X calculation (increase, difference, absolute)
    while (date0 <= date1) {
        const date = date0.format("YYYY-MM-DD")
        calculatedData[date] = {}
        dateToGeoIdToAbsolute[date] = {}

        for (let geoId in inputData[date]) {
            const dateMinusDeltaDays = addOrSubtractNDaysToDate(date, -deltaDays)
            const val0 = inputData[dateMinusDeltaDays][geoId]
            const val1 = inputData[date][geoId]
            // Perform the calculationType on the input data.
            const result = calculate([val0, val1], calculationType)
            // The charts also require the difference, so calculate it.
            const difference = calculate([val0, val1], 'difference')
            // The absolute increase (difference) is necessary to show on-hover info.
            // absolutePerCapita takes the raw absolute number instead of the difference.
            const absolute = calculationType === 'absolutePerCapita' ? val1 : difference

            if (result) {
                // Store result and absolute value
                calculatedData[date][geoId] = result
                dateToGeoIdToAbsolute[date][geoId] = absolute
            }
        }
        date0 = date0.add(1, "days")
    }

    // If perCapita then then divide all results by the geoId's population
    if (['perCapita', 'absolutePerCapita'].includes(calculationType)) {
        for (let date in calculatedData) {
            for (let geoId in calculatedData[date]) {
                const result = calculatedData[date][geoId] / geoIdToPopulation[geoId]
                if (result) calculatedData[date][geoId] = result
            }
        }
    }

    // Generate the metadata for the graph (on-hover, bar text, region names, values, name, etc...)
    const metadata: DateToGeoIdToMetadata = generateMetadata(calculatedData, geoIdToPopulation, geoIdToName,
                                                                  dateToGeoIdToAbsolute, label, calculationType)

    // We only care about the data for picked date
    const dataForPickedDate: {string: Metadata} = metadata[props.datePicked]

    // If there is data available show charts
    if (Object.keys(inputData).length) {
        return (
            <div className={"panel shadow"}>
                <h4 className={"title"}>{content.title}</h4>
                <h6 className={"title"}>{content.subtitle}</h6>
                <Graph label={label}
                       data={{[props.datePicked]: dataForPickedDate || {}}}
                       selectedShowTopN={props.selectedShowTopN}
                       type={content.graphType}
                       color={label === 'cases' ? '#990001' : 'grey'}/>
            </div>
        )
    }
    // Otherwise, show empty panel
    return (<EmptyPanel reason={'loading'}/>)
}