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

export default function DataCalculator(values: [number, number], calculationType: string[]): number | null {
    // If there are no input values, we can't perform any calculation
    if (values[0] === undefined || values[0] === null) return null
    if (values[1] === undefined || values[1] === null) return null

    if (calculationType.includes('increase')) {
        if (values[0] === 0) return null
        return (values[1] / values[0]) - 1
    } else if (calculationType.includes('difference')) {
        return values[1] - values[0]
    } else {
        return values[1]
    }
}