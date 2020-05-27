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
import numberWithCommas from "./NumberWithCommas";
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

type dataHolder = {
    value: number,
    absolute: number,
    regionName: string,
    population: number,
    dcid: string,
    labelListLabel: string
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
     * This is necessary as Chart.jsx only know how to interpret a dataHolder list.
     * @param data
     */
    jsonToArray = (data: dataHolder) => {
        let dataAsList: dataHolder[] = []
        if (!Object.keys(data).length) return dataAsList

        Object.keys(data['value']).forEach(dcid => {
            let regionName: string = this.props.dcidMap[dcid]
            let value: number = Math.round(data?.value[dcid] * 100000) / 100000
            let absolute: number = data?.absolute?.[dcid]
            let population: number = data?.population?.[dcid]
            dataAsList.push({
                regionName: regionName,
                value: value,
                absolute: absolute,
                population: population,
                dcid: dcid,
                labelListLabel: this.getLabelListLabel(value, absolute, population)
            })
        })
        return dataAsList.sort((a, b) => b.value - a.value)
            .slice(0, this.props.selectedShowTopN)
    }

    /**
     * The chart takes a labelList. Which is a list of strings that will be shown on top of each bar.
     * This will pre-generate those strings.
     * For example, if the chart is a percent chart, we want to generate +800 (12%).
     * @param value
     * @param absolute
     * @param population
     */
    getLabelListLabel = (value, absolute, population) => {
        if (absolute && population) return numberWithCommas(absolute) + ' / ' + numberWithCommas(population)
        else if (absolute && value) return "+" + numberWithCommas(absolute) + " (" + (value) + "%)"
        else return numberWithCommas(value)
    }

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
        let data = this.props.data[this.props.selectedDate]?.[this.props.region]?.[this.props.typeOfData] || {cases: [], deaths: []}
        let prettifiedDate = this.prettifyDate(this.props.ISOSelectedDate)
        let sectionTitle = PanelInfo[this.props.typeOfData].sectionTitle.replace("{DATE}", prettifiedDate)

        return (
            <div className={"row"}
                 ref={this.props.ref_}>
                {// If there is a section title, then show the text.
                    sectionTitle && <h1 className={"section-title"}>{sectionTitle}</h1>}
                {// If there is a section title, then show a separator line as well.
                    sectionTitle && <hr style={{width: '100%'}}/>}
                <div className={"left"}>
                    <Panel dcidMap={this.props.dcidMap}
                           title={PanelInfo[this.props.typeOfData]?.title.replace("{TYPE}", "Cases")}
                           subtitle={PanelInfo[this.props.typeOfData]?.subtitle.replace("{TYPE}", "Cases")}
                           data={this.jsonToArray(data['cases'])}
                           label={"cases"}
                           region={this.props.region}
                           selectedShowTopN={this.props.selectedShowTopN}
                           loading={this.props.loading}/>
                </div>
                <div className={"right"}>
                    <Panel dcidMap={this.props.dcidMap}
                           title={PanelInfo[this.props.typeOfData]?.title.replace("{TYPE}", "Deaths")}
                           subtitle={PanelInfo[this.props.typeOfData]?.subtitle.replace("{TYPE}", "Deaths")}
                           data={this.jsonToArray(data['deaths'])}
                           label={"deaths"}
                           region={this.props.region}
                           selectedShowTopN={this.props.selectedShowTopN}
                           loading={this.props.loading}/>
                </div>
            </div>
        )
    }
}