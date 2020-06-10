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
import PanelInfo from './ContentFile.json'
import Panel from './Panel'
import {prettifyDate} from './Utils'

type Props = {
    data: any[],
    ref_: any,
    panelId: string,
    region: string,
    datePicked: string,
    selectedShowTopN: number
}

/**
 * Each row has two panels, where each panel contains a chart.
 * Each panel is either cases or deaths.
 * @param props
 * @constructor
 */
export default function Row(props: Props) {
    const prettifiedDate = prettifyDate(props.datePicked)
    // Replace the {DATE} string with the actual date in the sectionTitle
    const sectionTitle = PanelInfo[props.panelId].sectionTitle.replace("{DATE}", prettifiedDate)
    return (
        <div className={"row"}
             ref={props.ref_}>
            {// If there is a section title, then show the text.
                sectionTitle && <h1 className={"section-title"}>{sectionTitle}</h1>}
            {// If there is a section title, then show a separator line as well.
                sectionTitle && <hr style={{width: '100%'}}/>}
            <div className={"left"}>
                <Panel data={props.data}
                       datePicked={props.datePicked}
                       label={"cases"}
                       region={props.region}
                       selectedShowTopN={props.selectedShowTopN}
                       panelId={props.panelId}/>
            </div>
            <div className={"right"}>
                <Panel data={props.data}
                       datePicked={props.datePicked}
                       label={"deaths"}
                       region={props.region}
                       selectedShowTopN={props.selectedShowTopN}
                       panelId={props.panelId}/>
            </div>
        </div>
    )
}