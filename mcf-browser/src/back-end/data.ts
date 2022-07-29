/**
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

type Series = {
    /** A unique identifier made using the facets */
    id: string;

    /** An ordered list of x-values for the data */
    x: number[];

    /** An ordered list of y-values for the data */
    y: number[];

    /** The observationAbout property of a node */
    observationAbout?: string;

    /** The variable being measured */
    variableMeasured?: string;

    /** The provenance of the data */
    provenance?: string;

    /** The measurement method of the data */
    measurementMethod?: string;

    /** The length of time over which the data point was collected */
    observationPeriod?: string;

    /** The unit for the data */
    unit?: string;

    /** The scaling factor for the data */
    scalingFactor?: number;
};

export type {Series};