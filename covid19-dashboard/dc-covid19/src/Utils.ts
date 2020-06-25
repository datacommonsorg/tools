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

import moment from 'moment';

/**
 * Given a date and an array of deltaDays compute the real ISODates.
 * For example, date = 2020-01-10 and deltaDays = [0, 1, 7]
 * will return the following: [2020-01-10, 2020-01-09, 2020-01-03]
 * 0 represents today, N represents N days ago.
 * @param date: the date we are observing
 * @param deltaDays: the date
 */
const getRealISODatesFromArrayOfDeltaDays = (
    date: string,
    deltaDays: number[]
): string[] => {
    if (date === undefined || date === null) return [];
    const dates = deltaDays.map(deltaDate => addNDaysToDate(date, -deltaDate));
    return dates.sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
};

/**
 * Converts a number to a string including commas for readability.
 * For example, int(10000) would get converted to str(10,000)
 * @param num: the number to replace
 */
const numberWithCommas = (num: number): string => {
    if (!num) return '0';
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
};

/**
 * Adds or subtracts any number of days to an ISO date.
 * For example, 2020-01-07 minus 2 days would return 2020-01-05.
 * NOTE: You can pass in negative or positive days accordingly.
 * @param ISOdate: a string representing a date in ISO format
 * @param days: either positive or negative days to add
 */
const addNDaysToDate = (ISOdate: string, days: number): string => {
    let date;
    // Subtracting to date
    if (days < 0) {
        date = moment(ISOdate).subtract(Math.abs(days), 'days');
        // Adding to date
    } else {
        date = moment(ISOdate).add(Math.abs(days), 'days');
    }
    return date.format('YYYY-MM-DD');
};

/**
 * Returns an array containing [initialDate, lastDate]
 * For example, if we cared about the data from 01-01-10 to 1 week ago.
 * initialDate = 2020-01-10, deltaDays = 7, returns [2020-01-03, 2020-01-10]
 * @param ISOdate: date to look at
 * @param deltaDays: number of days before our ISOdate to look at
 */
const getRangeOfDates = (
    ISOdate: string,
    deltaDays: number
): [string, string] => {
    // Will return [ISOdate - deltaDays, ISOdate]
    return [addNDaysToDate(ISOdate, -deltaDays), ISOdate];
};

/**
 * Given a map of geoId->[name, belongsToRegion]
 * Returns a list of the geoId's that belong to a region
 * @param geoIdToInfo: geoId->[name, belongsToRegion]
 * @param belongsToRegion: can be any geoId
 */
const filterGeoIdThatBelongTo = (
    geoIdToInfo: {geoId: string[]} | {},
    belongsToRegion: string
): string[] => {
    if (belongsToRegion === 'County') {
        return Object.keys(geoIdToInfo).filter(
            geoId => geoIdToInfo[geoId][1] !== 'country/USA'
        );
    } else if (belongsToRegion === 'State') {
        return Object.keys(geoIdToInfo).filter(
            geoId => geoIdToInfo[geoId][1] === 'country/USA'
        );
    } else {
        return Object.keys(geoIdToInfo).filter(
            geoId => geoIdToInfo[geoId][1] === belongsToRegion
        );
    }
};

/**
 * Returns new copy of the inputted JSON only containing keys present.
 * This is similar to the reduce() function, but for JSON.
 * @param JSON: any object
 * @param keys: an array of keys
 */
const filterJSONByArrayOfKeys = (JSON: {}, keys: string[]): {} => {
    const output = {};
    keys.forEach(key => {
        if (key in JSON) {
            output[key] = JSON[key];
        }
    });
    return output;
};

export {
    getRealISODatesFromArrayOfDeltaDays,
    numberWithCommas,
    addNDaysToDate,
    getRangeOfDates,
    filterGeoIdThatBelongTo,
    filterJSONByArrayOfKeys,
};
