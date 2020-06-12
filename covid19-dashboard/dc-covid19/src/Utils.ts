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

import moment from "moment";


/**
 * Given a date and an array of deltaDays compute the real ISODates.
 * For example, date = 2020-01-10 and deltaDays = [0, 1, 7] will return an array with the ISODates
 * [2020-01-10, 2020-01-09, 2020-01-03] because 0 represents today, 1 represents 1 day ago, and 7 represents 7 days ago.
 * @param date
 * @param deltaDays
 */
const getRealISODatesFromArrayOfDeltaDays = (date: string, deltaDays: number[]): string[] => {
    if (!date) return []
    const dates = deltaDays.map(deltaDate => addOrSubtractNDaysToDate(date, -deltaDate))
    return dates.sort((a, b) => (a < b) ? -1 : ((a > b) ? 1 : 0));
}

/**
 * Converts a number to a string including commas for readability.
 * For example, int(10000) would get converted to str(10,000)
 * @param num
 */
const numberWithCommas = (num: number): string => {
    if (!num) return "0"
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",")
}

/**
 * Converts an ISO date to English date.
 * For example, 2020-01-01 is converted to January 1st, 2020.
 * @param ISOdate: a string representing an ISO date.
 */
const prettifyDate = (ISOdate: string): string => {
    const prettifiedDate = moment(ISOdate).format('MMMM Do, YYYY')
    // If prettifiedDate is not valid, it means it wasn't a ISOdate input.
    if (!prettifiedDate) return "Some Day"
    return prettifiedDate
}

/**
 * Adds or subtracts any number of days to an ISO date.
 * For example, 2020-01-07 minus 2 days would return 2020-01-05.
 * NOTE: You can pass in negative or positive days accordingly.
 * @param ISOdate: a string representing a date in ISO format
 * @param days: either positive or negative days to add
 */
const addOrSubtractNDaysToDate = (ISOdate: string, days: number): string => {
    let date;
    if (days < 0){
        date = moment(ISOdate).subtract(Math.abs(days), "days")
    } else {
        date = moment(ISOdate).add(Math.abs(days), "days")
    }
    return date.format("YYYY-MM-DD")
}

/**
 * Returns an array containing [initialDate, lastDate]
 * For example, if we cared about the data from 01-01-10 to 1 week ago.
 * initialDate = 2020-01-10, deltaInDays = 7, returns [2020-01-03, 2020-01-10]
 * @param ISOdate: date to look at
 * @param deltaInDays: number of days before our ISOdate to look at
 */
const getRangeOfDates = (ISOdate: string, deltaInDays: number): [string, string] => {
    return [addOrSubtractNDaysToDate(ISOdate, -deltaInDays), ISOdate]
}

const filterGeoIdByRegionType = (geoIdToType: {geoId: string[]} | {}, regionType: string): string[] => {
    let output: string[] = []
    for (let geoId in geoIdToType) {
        const observedGeoIdRegion = geoIdToType[geoId][1]
        if (observedGeoIdRegion === regionType) output.push(geoId)
    }
    return output
}

/**
 * Returns new copy of the inputted JSON with only the keys that are present in the array.
 * This is similar to the reduce() function, but for JSON.
 * @param JSON: any object
 * @param keys: an array of keys
 */
const filterJSONByArrayOfKeys = (JSON: {}, keys: any[], ): {} => {
    let output: {} = {}
    keys.forEach(key => {if (key in JSON) output[key] = JSON[key]})
    return output
}

export {
    getRealISODatesFromArrayOfDeltaDays,
    numberWithCommas,
    prettifyDate,
    addOrSubtractNDaysToDate,
    getRangeOfDates,
    filterGeoIdByRegionType,
    filterJSONByArrayOfKeys
}
