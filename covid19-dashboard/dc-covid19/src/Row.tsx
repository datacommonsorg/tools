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
import Panel from "./Panel";
import React from "react";
import PanelInfo from './PanelInfo.json'
import moment from "moment";

type Props = {
    data: {},
    ref_: any,
    loading: boolean,
    typeOfData: string,
    selectedDate: string,
    region: string,
    ISOSelectedDate: string,
    selectedShowTopN: number,
    dcidMap: {},
    animationClassName: string
}

/**
 * Each row has two panels, where each panel contains a chart.
 * Each panel is either cases or deaths.
 * @param props
 * @constructor
 */
export default class Row extends React.Component<Props> {
    /**
     * Given a hashmap of data, convert it to a list dataHolder objects.
     * Also sorts the list so that the chart shows the regions from highest to lowest.
     * This is necessary as BarGraph.jsx only know how to interpret a dataHolder list.
     * @param data
     */

    /**
     * Converts an ISO date to English date.
     * For example, 2020-01-01 is converted to January 1st, 2020.
     * @param date
     */
    prettifyDate = (date: string) => {
        if (date.toLowerCase() === "latest") return "Daily"
        else return moment(date).format('MMMM Do, YYYY');
    }

    render() {
        const prettifiedDate = this.prettifyDate(this.props.ISOSelectedDate)
        const sectionTitle = PanelInfo[this.props.typeOfData].sectionTitle.replace("{DATE}", prettifiedDate)
        return (
            <div className={"row"}
                 ref={this.props.ref_}>
                {// If there is a section title, then show the text.
                    sectionTitle && <h1 className={"section-title"}>{sectionTitle}</h1>}
                {// If there is a section title, then show a separator line as well.
                    sectionTitle && <hr style={{width: '100%'}}/>}
                <div className={"left"}>
                    <Panel dcidMap={this.props.dcidMap}
                           data={this.props.data}
                           selectedDate={this.props.selectedDate}
                           label={"cases"}
                           region={this.props.region}
                           selectedShowTopN={this.props.selectedShowTopN}
                           loading={this.props.loading}
                           typeOfData={this.props.typeOfData}/>
                </div>
                <div className={"right"}>
                    <Panel dcidMap={this.props.dcidMap}
                           data={this.props.data}
                           selectedDate={this.props.selectedDate}
                           label={"deaths"}
                           region={this.props.region}
                           selectedShowTopN={this.props.selectedShowTopN}
                           loading={this.props.loading}
                           typeOfData={this.props.typeOfData}/>
                </div>
            </div>
        )
    }
}