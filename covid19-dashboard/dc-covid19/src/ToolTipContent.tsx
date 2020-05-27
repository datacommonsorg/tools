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

export default function ToolTipContent(props: {chartInfo: string[], disclaimer: string}) {
    // Create a new line of h6 for every string in the array.
    let h6LabelInfo = props.chartInfo.map(text => <h6 className={"tooltip-content"}>{text}</h6>)

    return (
        <div style={{backgroundColor: 'white', padding: 10, borderRadius: 5}} className={"shadow"}>
            {h6LabelInfo}
            <div style={{margin: 10}}/>
            {props.disclaimer && <h6 className={"tooltip-content"}>{props.disclaimer}</h6>}
        </div>
    )
}
