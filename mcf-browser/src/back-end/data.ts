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

class Series {
    /** A unique identifier made using the facets */
    id: string;

    /** An ordered list of x-values for the data */
    x: string[];

    /** An ordered list of y-values for the data */
    y: number[];

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

    /** The constructor for the Series class
     */
    constructor(
        x: string[],
        y: number[],
        variableMeasured?: string,
        provenance?: string,
        measurementMethod?: string,
        observationPeriod?: string,
        unit?: string,
        scalingFactor?: number
    ) {
        this.x = x;
        this.y = y;
        this.variableMeasured = variableMeasured;
        this.provenance = provenance;
        this.measurementMethod = measurementMethod;
        this.observationPeriod = observationPeriod;
        this.unit = unit;
        this.scalingFactor = scalingFactor ? scalingFactor : 1;

        this.id = Series.toID(
            variableMeasured,
            provenance,
            measurementMethod,
            observationPeriod,
            unit,
            scalingFactor
        );
    }

    /** Generates an ID given the facet variables
     */
    static toID(
        variableMeasured?: string,
        provenance?: string,
        measurementMethod?: string,
        observationPeriod?: string,
        unit?: string,
        scalingFactor?: number
    ){
        const facetList = [
            variableMeasured ? variableMeasured : "",
            provenance ? provenance : "",
            measurementMethod ? measurementMethod : "",
            observationPeriod ? observationPeriod : "",
            unit ? unit : "",
            scalingFactor ? scalingFactor.toString() : "1"
        ]

        return facetList.join(",");
    }

    /** Takes in an ID string and returns the corresponding
     * values in an object
     */
    static fromID(id: string) {
        const [
            variableMeasured,
            provenance,
            measurementMethod,
            observationPeriod,
            unit,
            scalingFactor
        ] = id.split(",");

        return {
            variableMeasured,
            provenance,
            measurementMethod,
            observationPeriod,
            unit,
            scalingFactor: parseFloat(scalingFactor)
        };
    };
};

export {Series};