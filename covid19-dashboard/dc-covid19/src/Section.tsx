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
import Panel from './Panel'

type Props = {
    allData: {}[],
    title: string
    region: string,
    datePicked: string,
    selectedShowTopN: number,
    panels: string[]
}

/**
 * Each row has two panels, where each panel contains a chart.
 * Each panel is either cases or deaths.
 * @param props
 */
export default function Section(props: Props) {
    const panels = props.panels
        .map((panelId, index) =>
            <div key={index} className={index % 2 === 0 ? "left" : "right"}>
                <Panel allData={props.allData}
                   datePicked={props.datePicked}
                   region={props.region}
                   selectedShowTopN={props.selectedShowTopN}
                   panelId={panelId}/>
            </div>
    )
    return (
        // TODO: Fix so that the every 2 panels, there is a new row.
        <div className={"row"}>
            <h1 className={"section-title"}>{props.title}</h1>
            <hr style={{width: '100%'}}/>
            {panels}
        </div>
    )
}