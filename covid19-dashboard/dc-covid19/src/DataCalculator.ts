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

import {getRealISODatesFromArrayOfDeltaDays} from './Utils'
import moment from "moment";

type DataPerGeoIdPerDate = {string: {string: number}} | {}

/**
 * Performs a calculationType iteratively on two dates.
 * @param data: input data in the form of dates->geoIds->value.
 * @param range: the range of dates to calculate the data for in ISO Format. Example: ["2020-01-01", "2020-01-10"]
 * @param calculationType: What type of calculation are we performing?
 * @param deltaDays?: Do we wanna compare the data every 2 days? every 7? Any number works.
 * @param geoIdToPopulation?: geoId->Population. After calculating the difference, we want to divide by total population
 */
export default function dataCalculator(data: DataPerGeoIdPerDate,
                                       range: [string, string],
                                       calculationType: string,
                                       deltaDays?: number,
                                       geoIdToPopulation?: { [p: string]: number }
): DataPerGeoIdPerDate {
    // If there isn't any data, return an empty {}
    if (!Object.keys(data).length) {
        console.log("No input data.")
        return {}
    }

    let date0 = moment(range[0]);
    const date1 = moment(range[1]);

    // If the dates are invalid, return an empty {}
    if (!date0.isValid() || !date1.isValid()) {
        console.log("Invalid ISO dates.")
        return {}
    }

    // If the ranges aren't in order, return empty {}
    if (date0 > date1) {
        console.log("Invalid range.")
        return {}
    }

    // If there is data, begin the calculation
    let outputData: DataPerGeoIdPerDate = {} // store results here

    // For all dates from range[0] to range[1].
    while (date0 <= date1){
        // Convert to ISO format, since our data is stored in ISO format.
        const date = date0.format("YYYY-MM-DD")
        // Get the ISODate of iterativeDate - deltaDays, the function returns an array, so get the only element.
        // since deltaDAys is optional, add 0 if it wasn't included
        const deltaDaysFromIterativeDate: string = getRealISODatesFromArrayOfDeltaDays(date, [deltaDays || 0])[0]
        // For all geoIds in that given date
        for (let geoId in data[date]){
            // We are looking at two different dates, so make sure geoId is present in both dates.
            if (!(deltaDaysFromIterativeDate in data) || !(geoId in data[deltaDaysFromIterativeDate])) continue

            // Get the values for both days
            const iterativeDateValue = data[date][geoId]
            const deltaDaysFromIterativeDateValue = data[deltaDaysFromIterativeDate][geoId]

            // Do some calculation on the data using the getResult function.
            const result: number | null = getResult(
                [deltaDaysFromIterativeDateValue, iterativeDateValue],
                geoIdToPopulation?.[geoId],
                calculationType)

            // If the result is valid, store it otherwise, skip this specific value.
            if (result !== undefined && result !== null) {
                // If this is the first time storing this date in the output, make some room for it.
                if (!(date in outputData)) outputData[date] = {}
                outputData[date][geoId] = result
            }
        }
        // Add one day to the iterativeDate. Example: from "2020-01-01" to "2020-01-02".
        date0 = date0.add(1, "days")
    }
    return outputData
}

/**
 * Given two values (or one if absolute or absolutePerCapita), return the result of calculationType.
 * @param values: [number, number] -> values[0] is date - deltaDays, values[1] is the actual date.
 * @param population: some calculations require the population.
 * @param calculationType: the type of calculating we are performing on the values
 */
const getResult = (values: [number, number],
                   population: number | undefined,
                   calculationType: string): number | null => {
    // If there are no input values, we can't perform any calculation
    if (values[0] === undefined || values[0] === null) return null
    if (values[1] === undefined || values[1] === null) return null

    let result: number | null = null;
    switch (calculationType) {
        case 'difference':
            result = values[1] - values[0]
            break;
        case 'increase':
            if (values[0] !== 0) result = (values[1] / values[0]) - 1
            break;
        case 'perCapita':
            // Make sure the population is above 0, otherwise continue
            if (population && population > 0) result = (values[1] - values[0]) / population
            break;
        case 'absolute':
            result = values[1]
            break;
        case 'absolutePerCapita':
            // Make sure the population is above 0, otherwise continue
            if (population && population > 0) result = values[1] / population
            break;
    }
    return result
}