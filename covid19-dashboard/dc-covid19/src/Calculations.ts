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

import {getRealISODatesFromArrayOfDeltaDays, addOrSubtractNDaysToDate, getRangeOfDates} from './Utils'

type dataPerGeoIdPerDate = {string: {string: number}} | {}

/**
 * Calculates the difference between two days, given a deltaDay.
 * Returns data in the range of [ISODate - deltaDay, ISODate]
 * For example, if the ISOdate is 01-05-2020 and we want to calculate the difference between 30 days.
 * This function would return the difference between values in the range [ISODate - 30 days, ISODate].
 * Where every value represents currentvalue - value30DaysAgo
 * @param data: all the data
 * @param ISOdate: the last date to observe
 * @param deltaDays: N days before ISOdate to observe
 */
const difference = (data: dataPerGeoIdPerDate, ISOdate: string, deltaDays: number): dataPerGeoIdPerDate => {
    let outputData: dataPerGeoIdPerDate = {}
    if (!data) return outputData

    const range: [string, string] = getRangeOfDates(ISOdate, deltaDays)
    let currentDate = range[0]
    const lastDayInRange = range[1]

    // For all dates from range[0] to range[1]
    while (currentDate !== addOrSubtractNDaysToDate(lastDayInRange, 1)){
        const date1: string = getRealISODatesFromArrayOfDeltaDays(currentDate, [deltaDays])[0]
        // For all geoIds in the data
        for (let geoId in data[currentDate]){
            // We are looking at two different dates, so make sure geoId is present in both dates
            if (!(date1 in data) || !(geoId in data[date1])) continue
            // Calculate the difference between the two dates for a given geoId
            const valDifference = data[currentDate][geoId] - data[date1][geoId]
            // If the result is valid, store it under outputData
            if (valDifference) outputData[currentDate] = valDifference
        }
        currentDate = addOrSubtractNDaysToDate(currentDate, 1)
    }
    return outputData
}

const perCapita = (data: dataPerGeoIdPerDate, ISOdate: string, deltaDays: number): dataPerGeoIdPerDate => {
    return {}
}

const increase = (data: dataPerGeoIdPerDate, ISOdate: string, deltaDays: number): dataPerGeoIdPerDate => {
    return {}
}



export {difference, perCapita, increase}



