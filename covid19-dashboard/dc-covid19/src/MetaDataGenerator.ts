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
 * Given two values, return the result of calculationType.
 * @param values: values[0] is date - deltaDays, values[1] is the date.
 * @param calculationType: the type of calculating we are performing
 */

import {numberWithCommas} from "./Utils";

type DateToGeoIdToValue = {[geoId: string]: {[date: string]: number}} | {}

/**
 * Returns strings briefly explaining the calculation performed
 * @param geoId: the geoId of the region
 * @param regionName: the name of the region
 * @param date: the date of the observation
 * @param value: the value at that specific date for that specific geoId
 * @param population: the total population of that region
 * @param absolute: the absolute difference between day 2 and day 1
 * @param label: Are we talking about cases? or deaths?
 * @param calculationType: calculations performed on data: eg. ['difference']
 * @return onHoverInfo: human readable text to display on graph's on-hover
 */
const getOnHoverInfoText = (geoId: string,
                            regionName: string,
                            date: string,
                            value: number,
                            population: number,
                            absolute: number,
                            label: string,
                            calculationType: string[]) => {
    let disclaimer = ""
    let onHoverInfo = [`${numberWithCommas(value)} ${label}`]


    // If it's New York City or Kansas City. Show a disclaimer.
    // These are NYT exceptions.
    if (['geoId/3651000', 'geoId/2938000'].includes(geoId)) {
        disclaimer = `All counties in ${regionName}` +
            'are combined and reported as one.'
    }

    const absoluteWithCommas = numberWithCommas(absolute)
    if (calculationType.includes('perCapita')) {
        const populationWithCommas = numberWithCommas(population)
        const per10000People = (value * 10000).toFixed(3)
        onHoverInfo = [
            `${per10000People} ${label} per 10,000 people`,
            `New ${label}: ${absoluteWithCommas}`,
            `Total population: ${populationWithCommas} people`
        ]
    } else if (calculationType.includes('increase')) {
        const percentWithCommas = numberWithCommas(Math.round(value * 100))
        const absoluteWithCommas = numberWithCommas(absolute)
        onHoverInfo = [
            `Percent increase: ${percentWithCommas}%`,
            `Absolute increase: ${absoluteWithCommas} ${label}`
        ]
    }

    if (disclaimer) {
        return [disclaimer, ...onHoverInfo]
    } else {
        return onHoverInfo
    }
}

/**
 * Returns strings display on top of graph's bar.
 * @param geoId: the geoId of the region
 * @param regionName: the name of the region
 * @param date: the date of the observation
 * @param value: the value at that specific date for that specific geoId
 * @param population: the total population of that region
 * @param absoluteIncrease: the absolute difference between day 2 and day 1
 * @param label: Are we talking about cases? or deaths?
 * @param calculationType: calculations performed on data: eg. ['difference']
 * @return onHoverInfo: human readable text on top of
 */
const getTextOnTopOfBar = (geoId: string,
                           regionName: string,
                           date: string,
                           value: number,
                           population: number,
                           absoluteIncrease: number,
                           label: string,
                           calculationType: string[]): string => {

    const absoluteWithCommas = numberWithCommas(absoluteIncrease)

    if (calculationType.includes('perCapita')) {
        const populationWithCommas = numberWithCommas(population)
        return `${absoluteWithCommas} / ${populationWithCommas}`
    } else if (calculationType.includes('increase')) {
        const percentIncrease = Math.round(value * 100)
        return `${absoluteWithCommas} (${percentIncrease}%)`
    } else {
        return `${numberWithCommas(value)}`
    }
}

/**
 * Generates an object for the information to display.
 * For example, the Bar Graph must know things such as 'value', 'name',
 * 'onHoverInfo', and the 'text' to display on top of the bar.
 * @param dateToGeoIdToValue: date->geoId->value
 * @param geoIdToPopulation: geoId->Population
 * @param geoIdToName: geoId->name
 * @param dateToGeoIdToAbsolute: absolute number from date X to date Y
 * @param label: Are we talking about cases or deaths?
 * @param calculationType: calculations performed on data: eg. ['difference']
 */
function generateMetadata(dateToGeoIdToValue: DateToGeoIdToValue,
                          geoIdToPopulation: {[geoId: string]: number},
                          geoIdToName: {[geoId: string]: string},
                          dateToGeoIdToAbsolute: DateToGeoIdToValue,
                          label: string,
                          calculationType: string[]): DateToGeoIdToValue {

    let output: DateToGeoIdToValue | {} = {}

    // For every date and geoId in the dataset
    for (let date in dateToGeoIdToValue){
        for (let geoId in dateToGeoIdToValue[date]) {
            const iterativePopulation = geoIdToPopulation[geoId]
            // Get the name of the state, and get rid of county or Parish
            let regionName: string = geoIdToName[geoId]?.[0] || geoId

            regionName.replace(" County", "")
                      .replace(" Parish", "")
                      .replace(" Borough", "")

            // containedIn holds the region that it belongs to
            // For example geoId/12345 belongs to geoId/12
            const containedIn: string = geoIdToName[geoId]?.[1]
            const value: number = dateToGeoIdToValue[date]?.[geoId]
            const absolute: number = dateToGeoIdToAbsolute[date]?.[geoId]

            // If the region is not a State, append the State to the name.
            // Example: "Miami, Florida"
            if (containedIn.includes("geoId")) {
                regionName += ", " + geoIdToName[containedIn]?.[0]
            }

            // Generate the text displayed when the user hovers on a graph.
            const onHoverInfo = getOnHoverInfoText(geoId,
                                                   regionName,
                                                   date,
                                                   value,
                                                   iterativePopulation,
                                                   absolute,
                                                   label,
                                                   calculationType)

            const textOnTopOfBar = getTextOnTopOfBar(geoId,
                                                     regionName,
                                                     date,
                                                     value,
                                                     iterativePopulation,
                                                     absolute,
                                                     label,
                                                     calculationType)

            // If the date is not in the output, create it.
            if (!(date in output)){
                output[date] = {}
            }

            output[date][geoId] = {
                geoId: geoId,
                name: regionName,
                onHoverInfo: onHoverInfo,
                textOnTopOfBar: textOnTopOfBar,
                value: dateToGeoIdToValue[date][geoId]
            }
        }
    }
    return output
}

export default generateMetadata