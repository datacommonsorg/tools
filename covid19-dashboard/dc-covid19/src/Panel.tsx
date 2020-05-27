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
import BarGraph from './BarGraph'
import numberWithCommas from "./NumberWithCommas";
import PanelInfo from "./PanelInfo.json";

type dataHolder = {
    regionName: string,
    value: number,
    absolute: number,
    population: number,
    dcid: string,
    labelListLabel: string
}

type Props = {
    data: {},
    label: string,
    region: string,
    dcidMap: {},
    selectedDate: string,
    selectedShowTopN: number,
    loading: boolean,
    typeOfData: string
}

export default class Panel extends React.Component<Props> {
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

    render() {
        // If cases, the color of the graph is red.
        // If deaths, the color is grey.
        const color: string = this.props.label === 'cases' ? '#990001' : 'grey'
        const preprocesedData: dataHolder = this.props.data?.[this.props.selectedDate]?.[this.props.region]?.[this.props.typeOfData]?.[this.props.label] || {}
        const data: dataHolder[] = this.jsonToArray(preprocesedData)
        // If the data has been loaded, show the carts
        console.log(data)
        if (data.length > 0) {
            return (
                <div className={"panel chart shadow"}>
                    <h4 className={"title"}>{PanelInfo[this.props.typeOfData]?.title.replace("{TYPE}", "Deaths")}</h4>
                    <h6 className={"title"}>{PanelInfo[this.props.typeOfData]?.subtitle.replace("{TYPE}", "Deaths")}</h6>
                    <BarGraph dcidMap={this.props.dcidMap}
                              label={this.props.label}
                              data={data}
                              region={this.props.region}
                              color={color}
                              selectedShowTopN={this.props.selectedShowTopN}/>
                </div>
            )
        // If the data hasn't finished loading, then showing an empty panel.
        } else {
            return (
                <div className={"panel chart shadow empty-panel"}>
                    <h2 className={"empty-panel"}>{this.props.loading ? "Loading..." : "No Data To Display"}</h2>
                </div>
            )
        }
    }
}
