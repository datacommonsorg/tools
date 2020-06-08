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
 * Given a date and an array of deltaDates compute the real ISODates.
 * For example, latestDate = 2020-01-10 and deltaDates = [0, 1, 7] will return an array with the ISODates
 * [2020-01-10, 2020-01-09, 2020-01-03] because 0 represents today, 1 represents 1 day ago, and 7 represents 7 days ago.
 * @param latestDate
 * @param deltaDates
 */
export default function getAllAvailableDates(latestDate: string, deltaDates: number[]): string[] {
    if (!latestDate) return []

    const dates = deltaDates.map(deltaDate =>
        moment(latestDate).subtract(deltaDate, "days")
        .toISOString().substr(0,10))

    return dates.sort((a, b) => {
        return (a < b) ? -1 : ((a > b) ? 1 : 0);
    });
}