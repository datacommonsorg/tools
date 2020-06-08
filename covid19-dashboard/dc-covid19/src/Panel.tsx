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
import EmptyPanel from "./EmptyPanel";
import parseData from "./ParseData";
import PanelInfo from "./PanelInfo.json";
import BarGraph from "./BarGraph";

type Props = {
    typeOfGraph: 'bar' | 'line',
    data: any[],
    label: string,
    region: string,
    ISOSelectedDate: string,
    selectedShowTopN: number,
    panelId: string
}

export default class Panel extends React.Component<Props> {

    render() {
        const inputData = this.props.label === 'cases' ? this.props.data[0] : this.props.data[1]
        const data = parseData(inputData, this.props.ISOSelectedDate, PanelInfo[this.props.panelId].deltaDate)

        /**
         * Decides what type of Panel to show.
         * There are three types of panels, BarGraphPanel, EmptyPanel and LineGraphPanel (coming soon).
         */
        if (!Object.keys(data).length) {
            return (<EmptyPanel reason={Object.keys(this.props.data).length === 0 ? 'loading' : 'nan'}/>)
        } else {
            return (
                <div className={"panel chart shadow"}>
                    <h4 className={"title"}>{PanelInfo[this.props.panelId]?.title.replace("{TYPE}", this.props.label[0].toUpperCase() + this.props.label.slice(1, this.props.label.length))}</h4>
                    <h6 className={"title"}>{PanelInfo[this.props.panelId]?.subtitle.replace("{TYPE}", this.props.label[0].toUpperCase() + this.props.label.slice(1, this.props.label.length))}</h6>
                    <BarGraph label={this.props.label}
                              // Remove the [] after you finish fixing
                              data={[]}
                              region={this.props.region}
                              selectedShowTopN={this.props.selectedShowTopN}
                              color={this.props.label === 'cases' ? '#990001' : 'grey'}/>
                </div>
            )
        }
    }
}