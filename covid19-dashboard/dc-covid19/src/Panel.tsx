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
import React from "react";
import BarGraphPanel from "./BarGraphPanel";
import EmptyPanel from "./EmptyPanel";
import LineGraphPanel from "./LineGraphPanel";

type Props = {
    typeOfGraph: 'bar' | 'line',
    data: {},
    label: string,
    region: string,
    dcidMap: {},
    selectedDate: string,
    selectedShowTopN: number,
    typeOfData: string
}

export default function Panel(props: Props) {
    /**
     * Decides what type of Panel to show.
     * There are three types of panels, BarGraphPanel, EmptyPanel and LineGraphPanel (coming soon).
     */

    if (!Object.keys(props.data).length) {
        return (<EmptyPanel reason={Object.keys(props.data).length === 0 ? 'loading' : 'nan'}/>)
    } else if (props.typeOfGraph === 'bar') {
        return <BarGraphPanel dcidMap={props.dcidMap}
                              data={props.data}
                              selectedDate={props.selectedDate}
                              label={props.label}
                              region={props.region}
                              selectedShowTopN={props.selectedShowTopN}
                              typeOfData={props.typeOfData}/>
    } else if (props.typeOfGraph === 'line'){
        return <LineGraphPanel dcidMap={props.dcidMap}
                               data={props.data}
                               selectedDate={props.selectedDate}
                               label={props.label}
                               region={props.region}
                               selectedShowTopN={props.selectedShowTopN}
                               typeOfData={props.typeOfData}/>
    } else {
        return <div/>
    }
}