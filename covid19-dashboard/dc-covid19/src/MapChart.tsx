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
import { ComposableMap, Geographies, Geography } from "react-simple-maps";
import { scaleQuantize } from "d3-scale";
import numberWithCommas from "./NumberWithCommas";
import tooltip from "wsdm-tooltip"

const geoUrl = "https://cdn.jsdelivr.net/npm/us-atlas@3/counties-10m.json";

const colorScale = scaleQuantize()
    .domain([1000, 100000])
    .range([
        "#ffedea",
        "#ffcec5",
        "#ffad9f",
        "#ff8a75",
        "#ff5533",
        "#e2492d",
        "#be3d26",
        "#9a311f",
        "#782618"
    ]);

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
    typeOfData: string
}

export default class MapChart extends React.Component<Props> {
    constructor(props: Props) {
        super(props)
        this.handleMouseMove = this.handleMouseMove.bind(this)
        this.handleMouseLeave = this.handleMouseLeave.bind(this)
    }
    tip = tooltip()
    componentDidMount() {
        this.tip = tooltip()
        this.tip.create()
    }
    handleMouseMove(geography, evt) {
        console.log(geography)
        this.tip.show(`<div class="tooltip-content"><h6>{${geography.id}}</h6></div>`)
        this.tip.position({ pageX: geography.pageX, pageY: geography.pageY })
    }
    handleMouseLeave() {
        this.tip.hide()
    }

    render() {
        /**
         * Converts the raw json data to an array that can be interpreted by BarGraph.tsx.
         * @param data
         */
        const jsonToArray = (data: dataHolder) => {
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
                    labelListLabel: getLabelListLabel(value, absolute, population)
                })
            })

            return dataAsList.sort((a, b) => b.value - a.value)
        }

        /**
         * The chart takes a labelList. Which is a list of strings that will be shown on top of each bar.
         * This will pre-generate those strings.
         * For example, if the chart is a percent chart, we want to generate +800 (12%).
         * @param value
         * @param absolute
         * @param population
         */
        const getLabelListLabel = (value, absolute, population) => {
            if (absolute && population) return numberWithCommas(absolute) + ' / ' + numberWithCommas(population)
            else if (absolute && value) return "+" + numberWithCommas(absolute) + " (" + (value) + "%)"
            else return numberWithCommas(value)
        }

        // Data as it is received.
        const preprocesedData: dataHolder = this.props.data?.[this.props.selectedDate]?.[this.props.region]?.[this.props.typeOfData]?.[this.props.label] || {}
        // Data as an array to be interpreted by chart.
        const data: dataHolder[] = jsonToArray(preprocesedData)
        console.log(data)

        return (
            <React.Fragment>
                <ComposableMap projection="geoAlbersUsa">
                    <Geographies geography={geoUrl}>
                        {({geographies, projection}) =>
                            geographies.map(geo => {
                                const cur = data.find(s => {
                                    console.log(s)
                                    return s.dcid === 'geoId/' + geo.id
                                });
                                return (
                                    <Geography
                                        key={geo.rsmKey}
                                        geography={geo}
                                        fill={colorScale(cur ? cur.value : "#EEE")}
                                        projection={projection}
                                        onMouseMove={this.handleMouseMove}
                                        onMouseLeave={this.handleMouseLeave}
                                        style={{
                                            hover: { fill: "#DDD", outline: "1" }
                                        }}
                                    />
                                );
                            })
                        }
                    </Geographies>
                </ComposableMap>
            </React.Fragment>
        );
    }
};