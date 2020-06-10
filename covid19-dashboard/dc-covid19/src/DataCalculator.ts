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

type dataPerGeoIdPerDate = {string: {string: number}} | {}
type calculationFunction = (val1: number, val2: number, assistanceObject: string) => number

/**
 * Performs a calculation() iteratively on two dates.
 * @param data: input data in the form of dates->geoIds->value.
 * @param range: the range of dates to calculate the data for in ISO Format. Example: ["2020-01-01", "2020-01-10"]
 * @param deltaDays: Do we wanna compare the data every 2 days? every 7? Any number works.
 * @param calculation: The function in charge of doing some calculation on the data for dates X and Y.
 * @private
 */
const _performIterationCalculation = (data: dataPerGeoIdPerDate, range: [string, string],
                                deltaDays: number, calculation: calculationFunction): dataPerGeoIdPerDate => {
    if (!data) return {}
    let outputData: dataPerGeoIdPerDate = {}

    let iterativeDate = range[0]
    const lastDayInRange = range[1]

    // For all dates from range[0] to range[1].
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
            if (!iterativeDateValue || !deltaDaysFromIterativeDateValue) continue
            // Do some calculation on the data using the calculation function.
            const result = calculation(iterativeDateValue, deltaDaysFromIterativeDateValue, geoId)
            // If the result is valid, store it
            if (result) {
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

/**
 * Calculates the difference between date X and date Y for a given range.
 * X = someDay - deltaDays, Y = someday
 * @param data: input data in the form of dates->geoIds->value.
 * @param range: the range of dates to calculate the data for in ISO Format. Example: ["2020-01-01", "2020-01-10"]
 * @param deltaDays: Do we wanna compare the data every 2 days? every 7? Any number works.
 */
const difference = (data: dataPerGeoIdPerDate, range: [string, string], deltaDays: number): dataPerGeoIdPerDate => {
    if (!data) return {}
    const differenceFunction: calculationFunction= (val1: number, val2: number): number => val1 - val2
    return _performIterationCalculation(data, range, deltaDays, differenceFunction)
}

/**
 * Calculates the difference divided per the population between date X and date Y for a given range.
 * X = someDay - deltaDays, Y = someday
 * @param data: input data in the form of dates->geoIds->value.
 * @param range: the range of dates to calculate the data for in ISO Format. Example: ["2020-01-01", "2020-01-10"]
 * @param deltaDays: Do we wanna compare the data every 2 days? every 7? Any number works.
 * @param geoIdToPopulation: geoId->Population. After calculating the difference, we want to divide by total population
 */
const perCapita = (data: dataPerGeoIdPerDate ,range: [string, string], deltaDays: number, geoIdToPopulation: {string: number}): dataPerGeoIdPerDate => {
    if (!geoIdToPopulation || !data) return {}
    const perCapitaFunction: calculationFunction = (val1: number, val2: number, geoId: string): number => (val1 - val2) / geoIdToPopulation[geoId]
    return _performIterationCalculation(data, range, deltaDays, perCapitaFunction)
}

/**
 * Calculates the percent increase between date X and date Y for a given range.
 * X = someDay - deltaDays, Y = someday
 * @param data: input data in the form of dates->geoIds->value.
 * @param range: the range of dates to calculate the data for in ISO Format. Example: ["2020-01-01", "2020-01-10"]
 * @param deltaDays: Do we wanna compare the data every 2 days? every 7? Any number works.
 */
const increase = (data: dataPerGeoIdPerDate, range: [string, string], deltaDays: number): dataPerGeoIdPerDate => {
    if (data) return {}
    const perCapitaFunction: calculationFunction = (val1: number, val2: number): number => (val1 / val2) - 1
    return _performIterationCalculation(data, range, deltaDays, perCapitaFunction)
}

/**
 * Returns the values for a given range. No other calculation is performed.
 * This method should be used to clean out unnecessary dates from the dataset.
 * @param data: input data in the form of dates->geoIds->value.
 * @param range: the range of dates to return the data for in ISO Format. Example: ["2020-01-01", "2020-01-10"]
 */
const absolute = (data: dataPerGeoIdPerDate, range: [string, string]): dataPerGeoIdPerDate => {
    if (!data) return {}
    const absoluteFunction: calculationFunction = (val1: number, val2: number): number => val2
    return _performIterationCalculation(data, range, 0, absoluteFunction)
}

export {absolute, difference, perCapita, increase}
