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

import {addOrSubtractNDaysToDate, getRealISODatesFromArrayOfDeltaDays} from './Utils'
import moment from "moment";

type DataPerGeoIdPerDate = {string: {string: number}} | {}

/**
 * Performs a calculationType iteratively on two dates.
 * @param data: input data in the form of dates->geoIds->value.
 * @param range: the range of dates to calculate the data for in ISO Format. Example: ["2020-01-01", "2020-01-10"]
 * @param deltaDays: Do we wanna compare the data every 2 days? every 7? Any number works.
 * @param calculationType: What type of calculation are we performing?
 * @param geoIdToPopulation?: geoId->Population. After calculating the difference, we want to divide by total population
 */
export default function dataCalculator(data: DataPerGeoIdPerDate,
                                       range: [string, string],
                                       deltaDays: number,
                                       calculationType: string,
                                       geoIdToPopulation?: {[geoId: string]: number }
): DataPerGeoIdPerDate {
    // If there isn't any data, return an empty {}
    if (!Object.keys(data).length) {
        console.log("No input data.")
        return {}
    }

    const date0IsValid = moment(range[0]).isValid();
    const date1IsValid = moment(range[1]).isValid();

    // If the dates are invalid, return an empty {}
    if (!date0IsValid || !date1IsValid) {
        console.log("Invalid ISO dates.")
        return {}
    }
    
    // If the ranges aren't in order, return {
    if (moment(range[0]) > moment(range[1])) {
        return {}
    }

    // If there is data, begin calculation
    let outputData: DataPerGeoIdPerDate = {}
    let iterativeDate = range[0]
    const lastDayInRange = range[1]

    // For all dates from range[0] to range[1].
    // Because we we want to stop at range[1], we have to add one day to range[1]
    while (iterativeDate !== addOrSubtractNDaysToDate(lastDayInRange, 1)){
        // Get the ISODate of iterativeDate - deltaDays, the function returns an array, so get the only element.
        const deltaDaysFromIterativeDate: string = getRealISODatesFromArrayOfDeltaDays(iterativeDate, [deltaDays])[0]
        // For all geoIds in that given date
        for (let geoId in data[iterativeDate]){
            // We are looking at two different dates, so make sure geoId is present in both dates.
            if (!(deltaDaysFromIterativeDate in data) || !(geoId in data[deltaDaysFromIterativeDate])) continue
            // Get the values for both days
            const iterativeDateValue = data[iterativeDate][geoId]
            const deltaDaysFromIterativeDateValue = data[deltaDaysFromIterativeDate][geoId]
            // If one of the values is invalid, or falsy, continue.
            if (iterativeDateValue === undefined || iterativeDateValue === null) continue
            if (deltaDaysFromIterativeDateValue === undefined || deltaDaysFromIterativeDateValue === null) continue
            // Do some calculation on the data using the calculation function.
            let result: number | null = null;

            switch (calculationType){
                case 'absolute':
                    result = iterativeDateValue
                    break;
                case 'difference':
                    result = iterativeDateValue - deltaDaysFromIterativeDateValue
                    break;
                case 'perCapita':
                    // Make sure the population is above 0, otherwise continue
                    if (geoIdToPopulation?.[geoId] && geoIdToPopulation?.[geoId] > 0)
                        result = ((iterativeDateValue - deltaDaysFromIterativeDateValue) / geoIdToPopulation[geoId])
                    break;
                case 'increase':
                    result = (iterativeDateValue / deltaDaysFromIterativeDateValue) - 1
                    break;
                case 'absolutePerCapita':
                    // Make sure the population is above 0, otherwise continue
                    if (geoIdToPopulation?.[geoId] && geoIdToPopulation?.[geoId] > 0)
                        result = (iterativeDateValue / geoIdToPopulation[geoId])
                    break;
            }

            // If the result is valid, store it
            if (result || result === 0) {
                // If this is the first time storing this date in the output, make some room for it.
                if (!(iterativeDate in outputData)) outputData[iterativeDate] = {}
                outputData[iterativeDate][geoId] = result
            }
        }
        // Add one to the iterativeDate. Example: from "2020-01-01" to "2020-01-02"
        iterativeDate = addOrSubtractNDaysToDate(iterativeDate, 1)
    }
    return outputData
}