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

/**
 * Given two values (or one if absolute or absolutePerCapita), return the result of calculationType.
 * @param values: [number, number] -> values[0] is date - deltaDays, values[1] is the actual date.
 * @param calculationType: the type of calculating we are performing on the values
 */

import ChartsConfiguration from "./ChartsConfiguration.json";
import Configuration from "./Configuration.json";
import DeltaDaysToEnglish from "./DeltaDaysToEnglish.json"
import React from "react";

import Section from "./Section";
import OptionPanel from "./OptionPanel";
import {filterGeoIdThatBelongTo, filterJSONByArrayOfKeys} from "./Utils";

type Props = {
    allData: {}[],
    selectedRegion: string,
    selectedShowTopN: number,
    datesToPick: string[]
    datePicked: string,
    availableRegions: {},
    region: string,
    content: string[],
    handleSelectUpdate: (key: string, value: string | number) => void,
}

export default function Content(props: Props) {
    /**
     * Returns only the data corresponding to a specific region. County, State or within a State.
     * @param allData: all the data in the form of [cases, deaths, population, names]
     * @param region: can be State, County or a State's geoId: geoId/XX
     */
    const getStatsDataOnlyForRegion = (allData: {}[], region: string): {}[] => {
        let output: {}[] = []
        const geoIdsContainedInSelectedRegion = filterGeoIdThatBelongTo(allData[3], region)

        // Iterate through all-cases and all-deaths which are found in index 0 and 1
        for (let dataSet of props.allData.slice(0, 2)){
            let filteredDataSet = {}
            for (let date in dataSet){
                const geoIdsForIterativeDate = dataSet[date]
                filteredDataSet[date] = filterJSONByArrayOfKeys(geoIdsForIterativeDate, geoIdsContainedInSelectedRegion)
            }
            output.push(filteredDataSet)
        }
        output.push(props.allData[2])
        output.push(props.allData[3])
        return output
    }

    const allDataForSelectedRegion = getStatsDataOnlyForRegion(props.allData, props.selectedRegion)
    const groupedByDeltaDay = {}
    for (let panelId of props.content) {
        const deltaDays = ChartsConfiguration[panelId].deltaDays || 0
        if (!(deltaDays in groupedByDeltaDay)) groupedByDeltaDay[deltaDays] = []
        groupedByDeltaDay[deltaDays] = [...groupedByDeltaDay[deltaDays], panelId]
    }

    const rows = Object.keys(groupedByDeltaDay)
        .map((deltaDays, index) =>
                <Section key={index}
                         allData={allDataForSelectedRegion}
                         title={DeltaDaysToEnglish[deltaDays]}
                         panels={groupedByDeltaDay[deltaDays]}
                         datePicked={props.datePicked}
                         region={props.selectedRegion}
                         selectedShowTopN={props.selectedShowTopN}/>
    )

    return (
        <div className={"container"}>
            {/*REMOVED TEMPORARILY --- <SideNav handleScrollOnRef={handleScrollOnRef} panelIds={props.content}/>*/}
            <div className={"main-content"}>
                <OptionPanel handleSelectUpdate={props.handleSelectUpdate}
                             geoIdToName={props.allData[3]}
                             defaultShowTopN={props.selectedShowTopN}
                             datesToPick={props.datesToPick}
                             datePicked={props.datePicked}
                             availableRegions={props.availableRegions}
                             selectedRegion={props.selectedRegion}/>
                    {rows}
            </div>
            <h5 className={"footer"}>{Configuration.FOOTER}</h5>
        </div>
    )
}