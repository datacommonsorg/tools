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
import LineGraph from './LineGraph'
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
    ISOSelectedDate: string
    selectedShowTopN: number,
    typeOfData: string
}

export default function LineGraphPanel(props: Props) {
    /**
     * Converts the raw json data to an array that can be interpreted by BarGraph.tsx.
     * @param data
     */
    const jsonToArray = (data: dataHolder) => {
        let dataAsList: any = []
        if (!Object.keys(data).length) return dataAsList

        console.log(props.ISOSelectedDate)
        console.log(data)
        console.log(data[props.ISOSelectedDate])
        let sortedGeoIds: { [key: string]: number} [] = []

        for (let geoId in data[props.ISOSelectedDate]){
            let value = data[props.ISOSelectedDate][geoId]
            sortedGeoIds.push({[geoId]: value})
        }

        sortedGeoIds = sortedGeoIds.sort((a, b) => Object.values(b)[0] - Object.values(a)[0])
        console.log(sortedGeoIds)
        // sortedGeoIds = sortedGeoIds.map(x => x[Object.values(x)[0]])

        Object.keys(data).forEach(date => {
            let tempData = {}
            for (let geoId in data[date]){
                let regionName = props.dcidMap[geoId]
                tempData[regionName] = data[date][geoId]
            }
            dataAsList.push({...tempData, label: date})
        })
        return dataAsList

    }

    // Data as it is received.
    const preprocesedData: dataHolder = props.data?.[props.selectedDate]?.[props.region]?.[props.typeOfData]?.[props.label] || {}
    // Data as an array to be interpreted by chart.
    const data: dataHolder[] = jsonToArray(preprocesedData)

    return (
        <div className={"panel chart shadow"}>
            <h4 className={"title"}>{PanelInfo[props.typeOfData]?.title.replace("{TYPE}", "Deaths")}</h4>
            <h6 className={"title"}>{PanelInfo[props.typeOfData]?.subtitle.replace("{TYPE}", "Deaths")}</h6>
            <LineGraph dcidMap={props.dcidMap}
                       label={props.label}
                       data={data}
                       region={props.region}
                       selectedShowTopN={props.selectedShowTopN}
                       color={props.label === 'cases' ? '#990001' : 'grey'}/>
        </div>
    )
}
