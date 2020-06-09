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

import {numberWithCommas} from "./Utils";
import ToolTipContent from "./ToolTipContent";
import React from "react";

type Props = {
    data: dataHolder,
    type: string,
    label: string
}

type dataHolder = {
    regionName: string,
    value: number,
    absolute: number,
    population: number,
    dcid: string,
    labelListLabel: string
}

/**
 * Component for when the user hovers on a bar graph
 * @param props
 * @constructor
 */
export default function ToolTip(props: Props) {
    let disclaimer: string = ''
    let texts: string[];
    if (props.data.dcid === 'geoId/3651000' || props.data.dcid === 'geoId/2938000')
        disclaimer = `All counties in ${props.data.regionName} are combined and reported as one.`

    if (props.type === 'perCapita'){
        texts = [`${props.data.value} ${props.label} per 10,000 people`,
            `New ${props.label}: ${numberWithCommas(props.data.absolute)}`,
            `Total population: ${numberWithCommas(props.data.population)} people`]
    } else if (props.type === 'percent'){
        texts = [`Percent increase: ${numberWithCommas(props.data.value)}%`,
            `Absolute increase: ${numberWithCommas(props.data.absolute)} ${props.label}`]
    } else {
        texts = [`${numberWithCommas(props.data.value)} ${props.label}`]
    }
    return (<ToolTipContent chartInfo={texts} disclaimer={disclaimer}/>);
}