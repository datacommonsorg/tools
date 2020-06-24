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

/**
 * Given two values (or one if absolute or absolutePerCapita), return the result of calculationType.
 * @param values: [number, number] -> values[0] is date - deltaDays, values[1] is the actual date.
 * @param calculationType: the type of calculating we are performing on the values
 */

import {numberWithCommas} from "./Utils";

type DateToGeoIdToValue = {[geoId: string]: {[date: string]: number}} | {}

/**
 * Given a list of parameters, return human readable strings explaining the data.
 * @param geoId: the geoId of the region
 * @param regionName: the name of the region
 * @param date: the date of the observation
 * @param value: the value at that specific date for that specific geoId
 * @param population: the total population of that region
 * @param absoluteIncreaseValue: the absolute difference between day 2 and day 1
 * @param label: Are we talking about cases? or deaths?
 * @param calculationType: What is the graph showing? perCapita? Increase? Absolute?
 */
const getOnHoverInfoText = (geoId: string, regionName: string, date: string, value: number, population: number,
                            absoluteIncreaseValue: number, label: string, calculationType: string[]) => {
    let disclaimer: string = ""
    let onHoverInfo: string[] = [`${numberWithCommas(value)} ${label}`]

    // If it's New York City or Kansas City. Show disclaimer. These are NYT exceptions.
    if (['geoId/3651000', 'geoId/2938000'].includes(geoId))
        disclaimer = `All counties in ${regionName} are combined and reported as one.`

    if (calculationType.includes('perCapita')) {
        onHoverInfo = [
            `${(value * 10000).toFixed(3)} ${label} per 10,000 people`,
            `New ${label}: ${numberWithCommas(absoluteIncreaseValue)}`,
            `Total population: ${numberWithCommas(population)} people`]
    } else if (calculationType.includes('increase')) {
        onHoverInfo = [
            `Percent increase: ${numberWithCommas(Math.round(value * 100))}%`,
            `Absolute increase: ${numberWithCommas(absoluteIncreaseValue)} ${label}`]
    }

    if (disclaimer) return [disclaimer, ...onHoverInfo]
    else return onHoverInfo
}

/**
 * Given a list of parameters, return human readable value that will be displayed on top of the graph's bar.
 * @param geoId: the geoId of the region
 * @param regionName: the name of the region
 * @param date: the date of the observation
 * @param value: the value at that specific date for that specific geoId
 * @param population: the total population of that region
 * @param absoluteIncreaseValue: the absolute difference between day 2 and day 1
 * @param label: Are we talking about cases? or deaths?
 * @param calculationType: What is the graph showing? Per-Capita? Increase? Absolute?
 */
const getTextOnTopOfBar = (geoId: string, regionName: string, date: string, value: number, population: number,
                           absoluteIncreaseValue: number, label: string, calculationType: string[]) => {
    let textOnTopOfBar: string = `${numberWithCommas(value)}`

    if (calculationType.includes('perCapita'))
        textOnTopOfBar = `${numberWithCommas(absoluteIncreaseValue)} / ${numberWithCommas(population)}`
    else if (calculationType.includes('increase'))
        textOnTopOfBar = `${numberWithCommas(absoluteIncreaseValue)} (${Math.round(value * 100)}%)`

    return textOnTopOfBar
}

/**
 * Generates information for the graph to display. For example, the Bar Graph must know things such as 'name',
 * 'onHoverInfo', and the 'text' to display on top of the bar.
 * @param dateToGeoIdToValue: date->geoId->value
 * @param geoIdToPopulation: geoId->Population
 * @param geoIdToName: geoId->name
 * @param dateToGeoIdToAbsolute: absolute number from date X to date Y (optional)
 * @param label: Are we talking about cases or deaths?
 * @param calculationType: What is the graph showing? Per-Capita? Increase? Absolute?
 */
export default function generateMetadata(dateToGeoIdToValue: DateToGeoIdToValue,
                                         geoIdToPopulation: {[geoId: string]: number},
                                         geoIdToName: {[geoId: string]: string},
                                         dateToGeoIdToAbsolute: DateToGeoIdToValue,
                                         label: string,
                                         calculationType: string[]): DateToGeoIdToValue {
    let output: DateToGeoIdToValue | {} = {}

    // For every date and geoId in the dataset
    for (let date in dateToGeoIdToValue){
        for (let geoId in dateToGeoIdToValue[date]) {
            const iterativePopulation: number = geoIdToPopulation[geoId] || 0
            // Get the name of the state, and get rid of county or Parish
            let iterativeRegionName: string = geoIdToName[geoId]?.[0] || geoId
            iterativeRegionName.replace(" County", "")
                               .replace(" Parish", "")
                               .replace(" Borough", "")
            // iterativeBelongingRegion holds the region that it belongs to, for example geoId/12345 belongs to geoId/12
            const iterativeBelongingRegion: string = geoIdToName[geoId]?.[1]
            const iterativeValue: number = dateToGeoIdToValue[date]?.[geoId] || 0
            const iterativeAbsoluteIncreaseValue: number = dateToGeoIdToAbsolute[date]?.[geoId] || 0

            // If the region not a State, append the State to the name. Example: "Miami, Florida"
            if (iterativeBelongingRegion.includes("geoId"))
                iterativeRegionName += ", " + geoIdToName[iterativeBelongingRegion]?.[0]

            // Generate the text that is displayed when the user hovers on a graph.
            const onHoverInfo = getOnHoverInfoText(geoId, iterativeRegionName, date, iterativeValue,
                iterativePopulation, iterativeAbsoluteIncreaseValue, label, calculationType)

            const textOnTopOfBar = getTextOnTopOfBar(geoId, iterativeRegionName, date, iterativeValue,
                iterativePopulation, iterativeAbsoluteIncreaseValue, label, calculationType)

            // If the date is not in the output, create it.
            if (!(date in output)) output[date] = {}

            output[date][geoId] = {
                geoId: geoId,
                name: iterativeRegionName,
                onHoverInfo: onHoverInfo,
                textOnTopOfBar: textOnTopOfBar,
                value: dateToGeoIdToValue[date][geoId]
            }
        }
    }
    return output
}