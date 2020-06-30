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

import ChartsConfiguration from './ChartsConfiguration.json';
import Configuration from './Configuration.json';
import DeltaDaysToEnglish from './DeltaDaysToEnglish.json';
import React from 'react';

import Section from './Section';
import OptionPanel from './OptionPanel';
import {filterByRegionsContainedIn, filterJSONByArrayOfKeys} from './Utils';

type Props = {
    allData: {}[];
    selectedRegion: string;
    selectedShowTopN: number;
    datesToPick: string[];
    datePicked: string;
    availableRegions: {};
    region: string;
    content: string[];
    handleSelectUpdate: (key: string, value: string | number) => void;
};

export default function Content(props: Props) {
    const dataForRegion: {}[] = [];
    const geoIdsInRegion = filterByRegionsContainedIn(
        props.allData[3],
        props.region
    );

    // Iterate through all-cases and all-deaths.
    // Which are found in index 0 and 1.
    for (const dataSet of props.allData.slice(0, 2)) {
        const filteredDataSet = {};
        for (const date in dataSet) {
            filteredDataSet[date] = filterJSONByArrayOfKeys(
                dataSet[date],
                geoIdsInRegion
            );
        }
        dataForRegion.push(filteredDataSet);
    }
    dataForRegion.push(props.allData[2]);
    dataForRegion.push(props.allData[3]);

    // Iterate through all panels and group panels by deltaDay.
    // Each deltaDay is a section.
    // Example: Today, 1 week ago, 1 month ago.
    const sections: {[deltaDate: string]: string[]} = {};
    for (const panelId of props.content) {
        const deltaDays = ChartsConfiguration[panelId].deltaDays;
        // If deltaDay not in the sections, create space for it.
        if (!(deltaDays in sections)) {
            sections[deltaDays] = [];
        }
        // Append the panelId to the corresponding section
        sections[deltaDays] = [...sections[deltaDays], panelId];
    }

    const rows = Object.keys(sections).map((deltaDays, index) =>
        <Section
            key={index}
            allData={dataForRegion}
            title={DeltaDaysToEnglish[deltaDays]}
            panels={sections[deltaDays]}
            datePicked={props.datePicked}
            region={props.selectedRegion}
            selectedShowTopN={props.selectedShowTopN}
        />
    );

    return (
        <div className={'container'}>
            {/*REMOVED TEMPORARILY ---
              <SideNav handleScrollOnRef={handleScrollOnRef}
              panelIds={props.content}/>*/}
            <div className={'main-content'}>
                <OptionPanel
                    handleSelectUpdate={props.handleSelectUpdate}
                    geoIdToName={props.allData[3]}
                    defaultShowTopN={props.selectedShowTopN}
                    datesToPick={props.datesToPick}
                    datePicked={props.datePicked}
                    availableRegions={props.availableRegions}
                    selectedRegion={props.selectedRegion}
                />
                {rows}
            </div>
            <h5 className={'footer'}>{Configuration.FOOTER}</h5>
        </div>
    );
}
