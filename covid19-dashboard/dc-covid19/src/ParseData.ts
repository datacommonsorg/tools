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

import moment from 'moment'

/**
 *
 * @param data: array of data where: [cases, deaths, population, names]
 * @param ISOdate: what is the day we want to look at? Example: March 3rd
 * @param deltaDate: what is the range of dates we want look at? 1 month ago, 2 weeks ago?
 */
export default function parseData(data: {string: {string: number}},
                                  ISOdate: string, deltaDate: number): {string: [number, number]} | {} {
    // If data is empty, just return {}
    if (!data) return {}

    const rangeOfDates: [string, string] = getRangeOfDates(ISOdate, deltaDate)
    return getValuesInRange(data, rangeOfDates)
}

/**
 * Returns an array containing [initialDate, lastDate]
 * For example, if we cared about the data from 01-01-10 to 1 week ago.
 * initialDate = 2020-01-10, deltaInDays = 7, returns [2020-01-03, 2020-01-10]
 * @param ISOdate: date to look at
 * @param deltaInDays: number of days before our ISOdate to look at
 *
 */
let getRangeOfDates = (ISOdate, deltaInDays): [string, string] => {
    return [moment(ISOdate).subtract(deltaInDays, "days")
        .toISOString().substr(0, 10), ISOdate]
}

/**
 * Given data in the form of {ISODate: {geoId: val}}.
 * Return the unique values between the range of dates
 * @param data: geoIds->[oldestDataObservation, mostRecentDataObservation]
 * @param rangeOfDates: array containing 2 dates [oldestDate, mostRecentdate]
 */
let getValuesInRange = (data: {string: {string: number}}, rangeOfDates: [string, string]): {string: [number, number]} | {} => {
    const oldestDate = rangeOfDates[0]
    const mostRecentDate = rangeOfDates[1]

    if (!(oldestDate in data) || !(mostRecentDate in data)) return {}

    const oldestDateObservation = {...data[oldestDate]}
    const mostRecentDateObservation = {...data[mostRecentDate]}

    let uniqueData: {string: [number, number]} | {} = {}

    // Iterate and find the difference between the most recent date and the oldest date.
    // Example: value for oldestDate = 10, mostRecentDate = 20. Return 20
    for (let dcid in oldestDateObservation){
        // Check to make sure both dcids are present in the data
        if (!(dcid in oldestDateObservation) || !(dcid in mostRecentDateObservation)) continue
        uniqueData[dcid] = [oldestDateObservation[dcid], mostRecentDateObservation[dcid]]
    }
    return uniqueData
}
